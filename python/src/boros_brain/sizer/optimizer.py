"""REWARD-03 sync sizing optimizer. Phase 4 DecisionEngine calls this at 1 Hz.

Contract:
    - SYNC (not async). Composes fill_model.predict + loss_model.expected_loss +
      reward_model.r_capped_curve + reward_model.compute_q_cap.
    - p95 < 10ms budget (sub-call p95's ≤ 3ms each; optimizer overhead ≤ 5ms
      for the 50-pt grid + scipy polish).
    - Propagates upstream exceptions WITHOUT swallowing — T-03-09 mitigation:
      FillModelStaleFeatureError, FillModelNoFreshFitError,
      LossModelNoFreshGridError surface to the caller. The DecisionEngine
      (Phase 4) catches and routes to PLACE-suppression with last-known fallbacks.
    - At $100 collateral with notional_per_yu_usd=90000 (ETHUSDT-29MAY2026
      placeholder), Q_max ≈ Q_min and the optimizer returns Q_min trivially
      via the degenerate-interval shortcut (sub_cap regime).

Design-locked. Phase 4 DecisionEngine depends on this signature.
[[sizing-optimizer-sub-cap-regime-v05]]
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import scipy.optimize
import structlog

from ..fill_model.predict import predict
from ..fill_model.schemas import PredictInput
from ..loss_model.expected_loss import expected_loss
from ..loss_model.schemas import ExpectedLossInput
from ..reward_model.q_cap import compute_q_cap
from ..reward_model.r_capped import r_capped_curve
from ..reward_model.schemas import RewardCurveInput, RewardCurveOutput
from .schemas import InsufficientCollateralError, SizerInput, SizerOutput

if TYPE_CHECKING:
    from ..config.schema import BotConfig

log = structlog.get_logger(__name__)

__all__ = ["q_me_target"]


def _build_reward_input(
    req: SizerInput, q_me_pendle: float, config: "BotConfig"
) -> RewardCurveInput:
    """Helper to assemble RewardCurveInput from SizerInput + per-call q_me."""
    return RewardCurveInput(
        market_id=req.market_id,
        side=req.side,
        q_me_pendle=q_me_pendle,
        sigma_others_pendle=req.sigma_others_pendle,
        e_liq_per_epoch_pendle=req.e_liq_per_epoch_pendle,
        side_split=req.side_split,
        t_frac=req.t_frac,
        collateral_usd=config.sizer.collateral_usd,
        pendle_price_usd=config.pricing.pendle_price_usd,
        epoch_days=config.reward_share_model.epoch_days,
    )


def q_me_target(
    req: SizerInput,
    *,
    sqlite_path: Path,
    config: "BotConfig",
) -> SizerOutput:
    """Sync sizing optimizer. See module docstring for contract.

    Algorithm:
      1. Q_min  = config.sizer.q_min_pendle (PENDLE).
      2. Q_max  = collateral_usd × q_max_safety_margin / notional_per_yu_usd
                  (PENDLE — operator-calibrated conversion).
      3. If Q_min > Q_max → raise InsufficientCollateralError.
      4. Q_cap  = compute_q_cap(...)     (REWARD-04 algebra).
      5. If Q_cap < Q_min → market_saturated shortcut, return Q_me=Q_min.
      6. upper  = min(Q_max, Q_cap).
      7. If upper ≤ Q_min × 1.0001 → degenerate-interval shortcut, return
         Q_me=Q_min (this is the $100 sub-cap fixed point).
      8. Pre-compute p_fill + e_loss ONCE outside the grid loop (neither
         depends on Q_me).
      9. Grid search 50 log-spaced points; optional scipy polish in a bracket
         around the grid argmax.

    Raises:
      InsufficientCollateralError: Q_min > Q_max.
      FillModelStaleFeatureError / FillModelNoFreshFitError: propagated.
      LossModelNoFreshGridError: propagated.
    """
    # --- Step 1-3: Q_min / Q_max + collateral guard ---
    q_min = config.sizer.q_min_pendle
    q_max = (
        config.sizer.collateral_usd
        * config.sizer.q_max_safety_margin
        / config.sizer.notional_per_yu_usd
    )
    if q_min > q_max:
        raise InsufficientCollateralError(q_min, q_max)

    # --- Step 4: Q_cap (REWARD-04) ---
    q_cap = compute_q_cap(
        sigma_others_pendle=req.sigma_others_pendle,
        e_liq_per_epoch_pendle=req.e_liq_per_epoch_pendle,
        side_split=req.side_split,
        t_frac=req.t_frac,
        collateral_usd=config.sizer.collateral_usd,
        pendle_price_usd=config.pricing.pendle_price_usd,
        epoch_days=config.reward_share_model.epoch_days,
    )

    # --- Step 8 (early): pre-compute p_fill + e_loss (neither depends on Q_me).
    #     Done BEFORE the regime shortcuts so error propagation is uniform —
    #     a missing fit / stale grid surfaces regardless of sub-cap regime, and
    #     the SizerOutput in the shortcuts can carry the actual p_fill / e_loss
    #     values rather than placeholders. (T-03-09 mitigation: errors propagate
    #     to caller; never silently swallowed.)
    p_fill_output = predict(
        PredictInput(
            market_id=req.market_id,
            side=req.side,
            depth_from_mark_ticks=req.depth_from_mark_ticks,
            queue_ahead_wei=req.queue_ahead_wei,
            current_features=req.current_features,
            time_to_epoch_end_s=req.time_to_epoch_end_s,
            current_chain_ts=req.current_chain_ts,
        ),
        sqlite_path=sqlite_path,
        config=config,
    )
    e_loss_output = expected_loss(
        ExpectedLossInput(
            market_id=req.market_id,
            side=req.side,
            depth_from_mark_ticks=req.depth_from_mark_ticks,
            time_to_maturity_s=req.time_to_maturity_s,
            current_chain_ts=req.current_chain_ts,
        ),
        sqlite_path=sqlite_path,
        config=config,
    )
    p_fill: float = p_fill_output.p_fill_this_epoch
    e_loss: float = e_loss_output.expected_loss_pendle

    # --- Step 5: market_saturated shortcut (Q_cap unreachable below Q_min) ---
    if q_cap < q_min:
        r_out: RewardCurveOutput = r_capped_curve(
            _build_reward_input(req, q_min, config)
        )
        ev = r_out.r_capped_pendle - e_loss * p_fill * q_min
        log.info(
            "sizer.market_saturated_shortcut",
            market_id=req.market_id,
            side=req.side,
            q_cap=q_cap,
            q_min=q_min,
        )
        return SizerOutput(
            q_me_target_pendle=q_min,
            regime="market_saturated",
            r_capped_at_target=r_out.r_capped_pendle,
            expected_loss_at_target=e_loss,
            p_fill_at_target=p_fill,
            ev_at_target=ev,
            q_min_pendle=q_min,
            q_max_pendle=q_max,
            q_cap_pendle=q_cap,
        )

    # --- Step 6: upper = min(Q_max, Q_cap) ---
    upper = min(q_max, q_cap) if not math.isinf(q_cap) else q_max

    # --- Step 7: degenerate-interval shortcut ($100 sub-cap fixed point) ---
    if upper <= q_min * 1.0001:
        r_out = r_capped_curve(_build_reward_input(req, q_min, config))
        ev = r_out.r_capped_pendle - e_loss * p_fill * q_min
        log.info(
            "sizer.q_min_fixed_point",
            market_id=req.market_id,
            side=req.side,
            q_min=q_min,
            upper=upper,
        )
        return SizerOutput(
            q_me_target_pendle=q_min,
            regime=r_out.regime,
            r_capped_at_target=r_out.r_capped_pendle,
            expected_loss_at_target=e_loss,
            p_fill_at_target=p_fill,
            ev_at_target=ev,
            q_min_pendle=q_min,
            q_max_pendle=q_max,
            q_cap_pendle=q_cap,
        )

    # --- Step 9: Grid search + optional scipy polish ---
    def _objective(q: float) -> float:
        r_out_q: RewardCurveOutput = r_capped_curve(
            _build_reward_input(req, q, config)
        )
        return float(r_out_q.r_capped_pendle - e_loss * p_fill * q)

    q_grid = np.logspace(
        np.log10(q_min), np.log10(upper), config.sizer.optimizer_grid_points
    )
    objectives = np.array([_objective(float(q)) for q in q_grid])

    # T-03-10: NaN guard — fall back to grid-only argmax with a warning.
    if np.any(np.isnan(objectives)):
        log.warning(
            "sizer.degraded_scipy_input",
            market_id=req.market_id,
            side=req.side,
        )
        finite_mask = ~np.isnan(objectives)
        if not finite_mask.any():
            # Pathological — every objective is NaN. Return Q_min as the safe
            # default (matches the degenerate-interval semantics).
            q_opt = float(q_min)
        else:
            q_opt = float(q_grid[int(np.nanargmax(objectives))])
    elif config.sizer.optimizer_method == "grid_only":
        q_opt = float(q_grid[int(np.argmax(objectives))])
    elif config.sizer.optimizer_method == "scipy_only":
        res = scipy.optimize.minimize_scalar(
            lambda q: -_objective(float(q)),
            bounds=(q_min, upper),
            method="bounded",
        )
        q_opt = float(res.x)
    else:  # grid_plus_scipy (default)
        q_grid_best_idx = int(np.argmax(objectives))
        q_grid_best = float(q_grid[q_grid_best_idx])
        # Polish in a narrow bracket around the grid argmax.
        bracket_lo = max(q_min, q_grid_best * 0.5)
        bracket_hi = min(upper, q_grid_best * 2.0)
        # If the bracket collapsed (e.g. q_grid_best at a corner of the
        # interval), fall back to grid argmax.
        if bracket_hi <= bracket_lo:
            q_opt = q_grid_best
        else:
            try:
                res = scipy.optimize.minimize_scalar(
                    lambda q: -_objective(float(q)),
                    bounds=(bracket_lo, bracket_hi),
                    method="bounded",
                )
                q_polished = float(res.x)
                # Guard: if scipy diverged below grid sanity, revert.
                if (
                    _objective(q_polished)
                    < _objective(q_grid_best) - 1e-12
                ):
                    q_opt = q_grid_best
                else:
                    q_opt = q_polished
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "sizer.scipy_polish_failed",
                    error=str(exc),
                    fallback="grid",
                )
                q_opt = q_grid_best

    # --- Build SizerOutput at q_opt ---
    r_out_final: RewardCurveOutput = r_capped_curve(
        _build_reward_input(req, q_opt, config)
    )
    ev_final = _objective(q_opt)

    log.info(
        "sizer.q_me_target_computed",
        market_id=req.market_id,
        side=req.side,
        q_me_target=q_opt,
        regime=r_out_final.regime,
        ev=ev_final,
        q_min=q_min,
        q_max=q_max,
        q_cap=q_cap,
    )
    return SizerOutput(
        q_me_target_pendle=q_opt,
        regime=r_out_final.regime,
        r_capped_at_target=r_out_final.r_capped_pendle,
        expected_loss_at_target=e_loss,
        p_fill_at_target=p_fill,
        ev_at_target=ev_final,
        q_min_pendle=q_min,
        q_max_pendle=q_max,
        q_cap_pendle=q_cap,
    )
