"""DECIDE-01/02 async EV-based cancel rule.

p95 < 100 ms budget. Composes predict() + expected_loss() + r_capped_curve()
+ gas_history.cancel_cost_pendle(). Errors propagate — NEVER swallow.

EV equation (DECIDE-01):
    EV_hold = R_share × P(no_fill_and_unpurged) − E[loss|fill] × P(fill)
              − cancel_cost × P(purge)               [benign branch]
    EV_hold -= sunk_rewards                          [punitive branch only]

Decision: CANCEL iff EV_hold < 0; HOLD otherwise.

DECIDE-02: branch controlled by config.strategy.voluntary_cancel_forfeits_accumulated.
  False (default, BENIGN): EV is purely forward-looking. Per P0-01 resolution
    2026-04-23 — Boros official team statement confirms accumulated rewards are
    NOT forfeited on voluntary cancel. This branch is the production default.
  True (PUNITIVE): EV subtracts already-accumulated rewards as a sunk cost.
    Retained as dead-code fallback for Phase 5 sensitivity backtesting only.

PITFALLS:
  #7 — Engine NEVER catches FillModel*Error or LossModelNoFreshGridError.
        The coordinator (Plan 04-06) is the single try/except at the loop boundary.
  #5 — cancel_cost always comes from GasHistoryCache; NEVER hardcoded.

[[ev-cancel-rule-implementation-v05]]
[[gas-history-ewma-cancel-cost]]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import structlog

from ..config.schema import BotConfig
from ..fill_model.predict import predict
from ..fill_model.schemas import (
    FillModelNoFreshFitError,  # noqa: F401 — re-exported for coordinator
    FillModelStaleFeatureError,  # noqa: F401 — re-exported for coordinator
    PredictInput,
)
from ..loss_model.expected_loss import expected_loss
from ..loss_model.schemas import ExpectedLossInput, LossModelNoFreshGridError  # noqa: F401
from ..reward_model.r_capped import r_capped_curve
from ..reward_model.schemas import RewardCurveInput
from .gas_history import GasHistoryCache
from .schemas import EvaluateInput, EvaluateOutput

log = structlog.get_logger(__name__)

__all__ = ["evaluate"]


async def evaluate(
    req: EvaluateInput,
    *,
    sqlite_path: Path,
    config: BotConfig,
    gas_cache: GasHistoryCache,
    w3: Any,
) -> EvaluateOutput:
    """Async EV-based cancel rule. Cancel iff EV_hold < 0. NEVER swallows model errors.

    Parameters
    ----------
    req:
        EvaluateInput — 16 fields covering order identity, market features,
        positioning, and the accumulated reward sunk cost (for punitive branch).
    sqlite_path:
        Path to the SQLite state DB — passed directly to predict() and expected_loss().
    config:
        Live BotConfig. Reads strategy, sizer, pricing, reward_share_model,
        decision, execution sub-models.
    gas_cache:
        GasHistoryCache singleton — provides TTL-cached cancel_cost_pendle().
    w3:
        AsyncWeb3 instance for gas_cache fee_history RPC. May be None in tests
        where gas_cache.last_value_pendle provides a pre-seeded value.

    Returns
    -------
    EvaluateOutput
        decision_kind: "CANCEL" | "HOLD"
        ev_hold_pendle: signed EV value (negative → CANCEL)
        Full audit trail for the decision log writer (Plan 04-06).

    Raises
    ------
    FillModelStaleFeatureError
        If predict() detects a NaN/missing covariate. Propagates to coordinator.
    FillModelNoFreshFitError
        If no fresh fill model fit exists. Propagates to coordinator.
    LossModelNoFreshGridError
        If no fresh loss grid exists. Propagates to coordinator.
    """
    # ── Step 1: P(fill) — sync, propagates FillModel*Error ──────────────────
    p_out = predict(
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
    p_fill = p_out.p_fill_this_epoch

    # ── Step 2: E[loss|fill] — sync, propagates LossModelNoFreshGridError ───
    e_out = expected_loss(
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
    e_loss = e_out.expected_loss_pendle

    # ── Step 3: R_share — pure closed-form, no I/O ──────────────────────────
    rc_out = r_capped_curve(
        RewardCurveInput(
            market_id=req.market_id,
            side=req.side,
            q_me_pendle=req.q_me_pendle,
            sigma_others_pendle=req.sigma_others_pendle,
            e_liq_per_epoch_pendle=req.e_liq_per_epoch_pendle,
            side_split=req.side_split,
            t_frac=req.t_frac,
            collateral_usd=config.sizer.collateral_usd,
            pendle_price_usd=config.pricing.pendle_price_usd,
            epoch_days=config.reward_share_model.epoch_days,
        )
    )
    r_share = rc_out.r_capped_pendle

    # ── Step 4: cancel_cost — async, TTL-cached ──────────────────────────────
    cancel_cost = await gas_cache.cancel_cost_pendle(w3=w3, config=config)
    p_purge = req.p_purge

    # ── Step 5: EV_hold — branch on voluntary_cancel_forfeits_accumulated ────
    p_no_fill_unpurged = (1.0 - p_fill) * (1.0 - p_purge)

    branch: Literal["benign", "punitive"]
    if config.strategy.voluntary_cancel_forfeits_accumulated:
        # PUNITIVE branch: EV subtracts already-accumulated epoch rewards as sunk cost.
        # Retained for Phase 5 backtest sensitivity sweep only; NOT the production default.
        sunk = req.r_me_per_epoch_pendle_accumulated_so_far
        ev_hold = r_share * p_no_fill_unpurged - e_loss * p_fill - cancel_cost * p_purge - sunk
        branch = "punitive"
    else:
        # BENIGN branch (default, D-01 / P0-01 resolved): purely forward-looking.
        # voluntary_cancel_forfeits_accumulated = False confirmed 2026-04-23.
        ev_hold = r_share * p_no_fill_unpurged - e_loss * p_fill - cancel_cost * p_purge
        branch = "benign"

    # ── Step 6: Decision ─────────────────────────────────────────────────────
    decision: Literal["CANCEL", "HOLD"] = "CANCEL" if ev_hold < 0.0 else "HOLD"

    log.debug(
        "engine.evaluate",
        order_id=req.order_id,
        market_id=req.market_id,
        side=req.side,
        decision=decision,
        ev_hold_pendle=ev_hold,
        r_share=r_share,
        p_fill=p_fill,
        e_loss=e_loss,
        cancel_cost=cancel_cost,
        p_purge=p_purge,
        branch=branch,
    )

    return EvaluateOutput(
        decision_kind=decision,
        ev_hold_pendle=ev_hold,
        r_share_per_epoch_pendle=r_share,
        p_no_fill_and_unpurged=p_no_fill_unpurged,
        e_loss_pendle=e_loss,
        p_fill=p_fill,
        cancel_cost_pendle=cancel_cost,
        p_purge=p_purge,
        fit_status_fill=p_out.fit_status,
        fit_status_loss=e_out.fit_status,
        voluntary_cancel_branch=branch,
        reasoning={
            "order_id": req.order_id,
            "market_id": req.market_id,
            "side": req.side,
            "p_no_fill_and_unpurged": p_no_fill_unpurged,
            "p_purge": p_purge,
            "sunk_if_punitive": req.r_me_per_epoch_pendle_accumulated_so_far,
            "voluntary_cancel_branch": branch,
        },
    )
