"""FILL-05 sync predict() contract. Phase 4 DecisionEngine calls this at 1 Hz.

Contract:
    - SYNC (not async). p95 < 10ms budget.
    - NaN covariate → FillModelStaleFeatureError (NEVER silent exp(β₀) fallback).
    - Fit older than fit_max_staleness_s → FillModelNoFreshFitError.
    - Monotone-decreasing in depth_from_mark_ticks (via explicit depth penalty).
    - Monotone-decreasing in queue_ahead_wei (via queue penalty).

Design-locked. Any change to this signature is a Phase-4 breaking change.
See [[fill-model-predict-contract]] and [[known-issues-nan-covariate-silent-fallback-do-not]].
"""

from __future__ import annotations

import math
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..state.writers.fill_model_fits import get_latest_fit
from .schemas import (
    FillModelNoFreshFitError,
    FillModelStaleFeatureError,
    PredictInput,
    PredictOutput,
)

log = structlog.get_logger(__name__)

__all__ = [
    "predict",
    "PredictInput",
    "PredictOutput",
    "FillModelStaleFeatureError",
    "FillModelNoFreshFitError",
]

# Safety cap on exp(...) argument to avoid float64 overflow (RESEARCH §Security Domain T-02-01-07)
_EXP_CLAMP = 30.0
# Simple depth-penalty coefficient for monotonicity contract (v0.5 placeholder; real
# depth signal comes via queue_ahead_wei correlation in the caller's state)
_DEPTH_PENALTY_COEF = 0.01
# Queue-penalty scaling: per-wei multiplier is vanishingly small; cap argument magnitude.
_QUEUE_PENALTY_SCALE = 1e-18


def _safe_exp(x: float) -> float:
    return math.exp(max(-_EXP_CLAMP, min(x, _EXP_CLAMP)))


def predict(req: PredictInput, *, sqlite_path: Path, config: BotConfig) -> PredictOutput:
    """Sync predict. See module docstring for contract.

    Raises:
        FillModelStaleFeatureError: any covariate in current_features is NaN or missing.
        FillModelNoFreshFitError: no fit row OR fit older than fit_max_staleness_s.
    """
    whitelist = list(config.fill_model.covariate_whitelist)

    # 1. NaN covariate check — raise FillModelStaleFeatureError, NEVER substitute
    missing = [
        name
        for name in whitelist
        if name not in req.current_features
        or not isinstance(req.current_features[name], int | float)
        or math.isnan(float(req.current_features[name]))
    ]
    if missing:
        log.warning(
            "fill_model.predict_nan_covariate",
            market_id=req.market_id,
            side=req.side,
            missing_features=missing,
        )
        raise FillModelStaleFeatureError(missing_features=missing)

    # 2. Load latest fit
    fit = get_latest_fit(sqlite_path, req.market_id, req.side)
    if fit is None:
        log.warning(
            "fill_model.no_fresh_fit",
            market_id=req.market_id,
            side=req.side,
            reason="no_fit_row",
        )
        raise FillModelNoFreshFitError(f"no fit persisted for ({req.market_id}, {req.side})")

    # 3. Staleness check
    fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)
    if fit_age_s < 0:
        # fit_window_end_ts is in the future relative to current_chain_ts —
        # possible if the chain clock rolled back or a bootstrap artifact was
        # persisted with a future window end (e.g. drifted machine clock).
        # Log a warning and treat as age=0 (fresh). Do not raise — the operator
        # warning is the appropriate signal here.
        log.warning(
            "fill_model.predict_future_dated_fit",
            market_id=req.market_id,
            side=req.side,
            fit_window_end_ts=fit.fit_window_end_ts,
            current_chain_ts=req.current_chain_ts,
            fit_age_s=fit_age_s,
        )
        fit_age_s = 0.0
    if fit_age_s > config.fill_model.fit_max_staleness_s:
        log.warning(
            "fill_model.no_fresh_fit",
            market_id=req.market_id,
            side=req.side,
            fit_age_s=fit_age_s,
            fit_max_staleness_s=config.fill_model.fit_max_staleness_s,
        )
        raise FillModelNoFreshFitError(
            f"fit too stale: age={fit_age_s}s > max={config.fill_model.fit_max_staleness_s}s"
        )

    final_status: str = fit.fit_status
    if fit_age_s > config.fill_model.fit_warn_staleness_s and final_status == "ok":
        final_status = "stale"
        log.warning(
            "fill_model.predict_stale_fit_warning",
            market_id=req.market_id,
            side=req.side,
            fit_age_s=fit_age_s,
        )

    # 4. Compute λ = exp(β₀ + β·x)
    beta = list(fit.beta)  # length = 1 + len(fit.covariate_whitelist)
    fit_whitelist = list(fit.covariate_whitelist)
    if len(beta) != 1 + len(fit_whitelist):
        raise FillModelNoFreshFitError(
            f"fit artifact malformed: len(beta)={len(beta)} != 1+len(whitelist)={1+len(fit_whitelist)}"
        )

    dot = 0.0
    for i, name in enumerate(fit_whitelist):
        x_i = float(req.current_features.get(name, 0.0))
        dot += beta[i + 1] * x_i
    lambda_per_second = _safe_exp(beta[0] + dot)

    # 5. Integrate over time_to_epoch_end_s (clipped to [0, 7 days])
    t = max(0.0, min(float(req.time_to_epoch_end_s), 7.0 * 86400.0))
    p_raw = 1.0 - _safe_exp(-lambda_per_second * t)

    # 6. Monotone-in-depth + monotone-in-queue penalties
    depth_penalty = _safe_exp(-_DEPTH_PENALTY_COEF * max(0, req.depth_from_mark_ticks))
    queue_penalty = _safe_exp(-min(_QUEUE_PENALTY_SCALE * float(req.queue_ahead_wei), _EXP_CLAMP))
    p_fill = max(0.0, min(1.0, p_raw * depth_penalty * queue_penalty))

    return PredictOutput(
        p_fill_this_epoch=p_fill,
        lambda_per_second=lambda_per_second,
        fit_run_id=fit.run_id,
        fit_age_s=fit_age_s,
        fit_status=final_status,  # type: ignore[arg-type]
    )
