"""FILL-01: NHPP log-linear fit via statsmodels.GLM(Poisson, log, exposure).

Per RESEARCH §Code Examples #2 (canonical recipe). The critical-path learner
for v0.5. `tick` is kept in the stack for simulation + v1.0 Hawkes staging ONLY
— see [[fill-model-library-decision-tick-vs-statsmodels]].

Note: the wall-clock call is banned in fill_model/ by no_time_time_lint.py (INFRA-14).
The `created_at` field is set to sentinel 0 here; artifact.write_fit_artifact
stamps the real timestamp via datetime.now(UTC).timestamp() before the SQLite write.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
import structlog

from ..config.schema import BotConfig
from .artifact import write_fit_artifact
from .schemas import FitArtifact

log = structlog.get_logger(__name__)

__all__ = ["fit_market_side"]


def _passes_health_gate(
    results: sm.GLMResultsWrapper,
    config: BotConfig,
) -> tuple[bool, str]:
    """Return (passes, reason). reason='ok' iff passes; else one of
    'not_converged' | 'too_few_events' | 'stderr_inflated'."""
    if not bool(results.converged):
        return False, "not_converged"
    n_params = len(results.params)
    if n_params == 0 or results.nobs / n_params < config.fill_model.min_events_per_param_ratio:
        return False, "too_few_events"
    # stderr-inflation: any |bse / params| > 10.0, guarded against params == 0
    params = np.array(results.params)
    bse = np.array(results.bse)
    safe_params = np.where(np.abs(params) < 1e-12, 1e-12, np.abs(params))
    if np.any(np.abs(bse) / safe_params > 10.0):
        return False, "stderr_inflated"
    return True, "ok"


def fit_market_side(
    features_df: pl.DataFrame,
    market_id: str,
    side: Literal["long", "short"],
    config: BotConfig,
    run_id: str,
    sqlite_path: Path,
    event_index_coverage: Literal["full", "degraded"] = "full",
    *,
    persist: bool = True,
    window_end_ts: int | None = None,
) -> FitArtifact:
    """Fit log λ = β₀ + β·x via statsmodels.GLM(Poisson, log, exposure).

    Persists via write_fit_artifact when persist=True (default). Callers that
    need throw-away fits (e.g. bootstrap_gof_threshold in calibration.py)
    must pass persist=False — otherwise 100 bootstrap resamples per invocation
    would pollute state.fill_model_fits and silently degrade get_latest_fit()
    lookups. Returns the FitArtifact (never raises on sparse data — tags
    fit_status='degraded' instead).

    Args:
        window_end_ts: Optional epoch-seconds upper bound for the fit window.
            When provided, this value is stored as fit_window_end_ts on ALL
            artifact paths (empty-data degraded, fit-exception degraded, and
            successful fit). This is critical for the refit-during-replay path:
            the backtest advances current_chain_ts each cadence tick; without
            window_end_ts the successful-fit path uses pdf["bin_start"].max()
            which is anchored to the last real trade bin in the historical
            parquet and does not advance between refits. All refits would then
            upsert onto the same fit_window_end_ts key, leaving a single stale
            row that is always 3600+ s old by the time predict() fires, causing
            FillModelNoFreshFitError. Callers in refit_loop MUST pass this;
            CLI / calibration callers without a bounded window can omit it
            (sentinel behavior preserved for the degraded paths).

    Note: created_at=0 is a sentinel. artifact.write_fit_artifact stamps the
    real datetime.now(UTC) timestamp before the SQLite/parquet write.
    """
    whitelist = list(config.fill_model.covariate_whitelist)

    df = features_df.filter((pl.col("market_id") == market_id) & (pl.col("side") == side)).drop_nulls(
        subset=whitelist + ["trade_count", "bin_duration_s"]
    )

    # Convert to pandas for statsmodels interop via numpy (pyarrow not in project deps)
    needed_cols = whitelist + ["trade_count", "bin_duration_s"] + (["bin_start"] if "bin_start" in df.columns else [])
    pdf = pd.DataFrame({col: df[col].to_numpy() for col in needed_cols if col in df.columns})
    if pdf.empty:
        # Emit a degraded artifact rather than raising — matches RESEARCH §Common Pitfalls #3.
        # Phase 05.5 fix: use window_end_ts (not 0 sentinel) when caller provides it, so that
        # predict() staleness check (fit_age_s = current_chain_ts - fit_window_end_ts) does not
        # treat the degraded artifact as infinitely stale and raise FillModelNoFreshFitError.
        degraded_window_end = window_end_ts if window_end_ts is not None else 0
        artifact = FitArtifact(
            run_id=run_id,
            fit_window_start_ts=0,
            fit_window_end_ts=degraded_window_end,
            market_id=market_id,
            side=side,
            covariate_whitelist=whitelist,
            beta=[0.0] * (1 + len(whitelist)),
            beta_stderr=[float("inf")] * (1 + len(whitelist)),
            log_likelihood=float("nan"),
            deviance=float("nan"),
            aic=float("nan"),
            n_observations=0,
            converged=False,
            fit_status="degraded",
            event_index_coverage=event_index_coverage,
            created_at=0,  # sentinel — stamped by artifact.write_fit_artifact
        )
        log.warning(
            "fill_model.fit_degraded",
            market_id=market_id,
            side=side,
            reason="no_data",
        )
        if persist:
            write_fit_artifact(artifact, sqlite_path=sqlite_path)
        return artifact

    exog_raw = pdf[whitelist].values
    exog = sm.add_constant(exog_raw, has_constant="add")  # always prepend β₀
    endog = pdf["trade_count"].values
    exposure = pdf["bin_duration_s"].values

    model = sm.GLM(
        endog=endog,
        exog=exog,
        family=sm.families.Poisson(link=sm.families.links.Log()),
        exposure=exposure,
    )
    try:
        results = model.fit(method="IRLS", maxiter=100)
    except Exception as exc:  # noqa: BLE001 — statsmodels convergence failures
        log.warning(
            "fill_model.fit_degraded",
            market_id=market_id,
            side=side,
            reason="fit_exception",
            err=str(exc),
        )
        # Phase 05.5 fix: use window_end_ts when provided so this artifact's
        # fit_window_end_ts advances with each refit cadence tick (same as the
        # empty-data path). Without this, the upsert key is stuck at a historical
        # bin_start.max() and the single DB row is always stale.
        exc_window_end = (
            window_end_ts
            if window_end_ts is not None
            else (int(pdf["bin_start"].max()) if "bin_start" in pdf.columns else 0)
        )
        artifact = FitArtifact(
            run_id=run_id,
            fit_window_start_ts=int(pdf["bin_start"].min()) if "bin_start" in pdf.columns else 0,
            fit_window_end_ts=exc_window_end,
            market_id=market_id,
            side=side,
            covariate_whitelist=whitelist,
            beta=[0.0] * (1 + len(whitelist)),
            beta_stderr=[float("inf")] * (1 + len(whitelist)),
            log_likelihood=float("nan"),
            deviance=float("nan"),
            aic=float("nan"),
            n_observations=int(len(endog)),
            converged=False,
            fit_status="degraded",
            event_index_coverage=event_index_coverage,
            created_at=0,  # sentinel
        )
        if persist:
            write_fit_artifact(artifact, sqlite_path=sqlite_path)
        return artifact

    passes, reason = _passes_health_gate(results, config)
    fit_status: Literal["ok", "degraded"] = "ok" if passes else "degraded"

    fit_window_start_ts = int(pdf["bin_start"].min()) if "bin_start" in pdf.columns else 0
    # Phase 05.5 fix: use window_end_ts when provided instead of pdf["bin_start"].max().
    # During backtest replay, bin_start.max() is the last real trade bin in the
    # historical parquet — it does NOT advance between refit cadence ticks because
    # no new trades are appended to parquet during replay. Every refit therefore
    # upserts onto the same fit_window_end_ts key (ON CONFLICT ... DO UPDATE), leaving
    # a single DB row whose fit_window_end_ts equals the initial T0 value. At T+3610
    # predict() computes fit_age_s = 3610 >> fit_max_staleness_s=3600 and raises
    # FillModelNoFreshFitError. Using window_end_ts (= current_chain_ts at each cadence
    # tick) creates a fresh row per refit and keeps fit_age_s bounded to refit_cadence_s.
    fit_window_end_ts = (
        window_end_ts
        if window_end_ts is not None
        else (int(pdf["bin_start"].max()) if "bin_start" in pdf.columns else 0)
    )
    artifact = FitArtifact(
        run_id=run_id,
        fit_window_start_ts=fit_window_start_ts,
        fit_window_end_ts=fit_window_end_ts,
        market_id=market_id,
        side=side,
        covariate_whitelist=whitelist,
        beta=list(map(float, results.params)),
        beta_stderr=list(map(float, results.bse)),
        log_likelihood=float(results.llf),
        deviance=float(results.deviance),
        aic=float(results.aic),
        n_observations=int(results.nobs),
        converged=bool(results.converged),
        fit_status=fit_status,
        event_index_coverage=event_index_coverage,
        created_at=0,  # sentinel — stamped by artifact.write_fit_artifact
    )

    log.info(
        "fill_model.fit_completed",
        market_id=market_id,
        side=side,
        fit_window_end_ts=fit_window_end_ts,
        n_observations=int(results.nobs),
        converged=bool(results.converged),
        fit_status=fit_status,
        log_likelihood=float(results.llf),
        aic=float(results.aic),
    )
    if fit_status == "degraded":
        log.warning(
            "fill_model.fit_degraded",
            market_id=market_id,
            side=side,
            reason=reason,
            n_observations=int(results.nobs),
            n_params=int(len(results.params)),
        )

    if persist:
        write_fit_artifact(artifact, sqlite_path=sqlite_path)
    return artifact
