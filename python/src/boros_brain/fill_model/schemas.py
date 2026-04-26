"""Pydantic + dataclass shapes for the fill model.

Partial per Plan 02-02: only QueueTracker/AMMConsumption types here.
Plan 02-03 appends FitArtifact, PredictInput, PredictOutput, FillModelStaleFeatureError,
FillModelNoFreshFitError. Keep this file the single home for all fill_model shape
declarations so architecture.yml has a single `brain.fill_model.schemas` node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ReplayResult:
    """Result from QueueTracker.replay_window — tri-track queue estimates + diagnostics."""

    market_id: str
    side: Literal["long", "short"]
    window_start_ts: int
    window_end_ts: int
    # anchor_ts -> tick_int -> queue_wei
    pessimistic_queue_at_anchor: dict[int, dict[int, float]] = field(default_factory=dict)
    realized_queue_at_anchor: dict[int, dict[int, float]] = field(default_factory=dict)
    optimistic_queue_at_anchor: dict[int, dict[int, float]] = field(default_factory=dict)
    drift_diagnostics_per_hour: list[dict[str, float]] = field(default_factory=list)
    event_index_coverage: Literal["full", "degraded"] = "full"


@dataclass(frozen=True)
class EpochFlowSnapshot:
    """Snapshot of flow quantities for a single epoch window.

    Used as the audit trail for assert_epoch_conservation calls.
    """

    epoch_start_ts: int
    epoch_end_ts: int
    book_ahead_start_wei: float
    book_ahead_end_wei: float
    taker_consumption_ahead_wei: float
    amm_consumption_wei: float
    net_placements_ahead_wei: float


class AMMConsumptionIdentityError(RuntimeError):
    """Runtime per-epoch flow-identity violation in brain.fill_model.amm_consumption.

    Distinct from `brain.data.ingester.exceptions.AMMConservationError` which is
    raised at INGEST time when combined < raw on a single snapshot. This error is
    raised at RUNTIME when the per-epoch flow identity is violated:

        book_ahead_end != book_ahead_start - taker_consumption_ahead
                           - amm_consumption + net_placements_ahead

    Or when compute_amm_share_timeseries detects combined < raw beyond tolerance.

    PITFALLS §B3 (AMM double-count) + §Common Pitfalls #2 in 02-RESEARCH.md.
    """


# --- Plan 02-03 additions: Fit + Predict contracts ----------------------------

from pydantic import BaseModel, ConfigDict  # noqa: E402


class StrictBase(BaseModel):
    """Local strict base for fill_model Pydantic models (avoids circular import
    with config.schema). Matches manifest/schema.py pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FitArtifact(StrictBase):
    """Immutable record of one (market_id, side, fit_window) fit.

    Persisted to state.fill_model_fits + parquet sidecar. Primary-key'd by
    (market_id, side, fit_window_end_ts). `beta` has length `1 + len(covariate_whitelist)`
    (the leading entry is the intercept β₀)."""

    run_id: str
    fit_window_start_ts: int
    fit_window_end_ts: int
    market_id: str
    side: Literal["long", "short"]
    covariate_whitelist: list[str]
    beta: list[float]  # length = 1 + len(covariate_whitelist)
    beta_stderr: list[float]
    log_likelihood: float
    deviance: float
    aic: float
    n_observations: int
    converged: bool
    fit_status: Literal["ok", "degraded", "stale"]
    gof_ks_pval: float | None = None
    gof_lr_vs_null: float | None = None
    event_index_coverage: Literal["full", "degraded"] = "full"
    created_at: int


class PredictInput(StrictBase):
    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    queue_ahead_wei: int
    current_features: dict[str, float]  # keyed by covariate_whitelist names
    time_to_epoch_end_s: float
    current_chain_ts: int  # Phase 4 supplies from chain_time.now_cached()


class PredictOutput(StrictBase):
    p_fill_this_epoch: float
    lambda_per_second: float
    fit_run_id: str
    fit_age_s: float
    fit_status: Literal["ok", "degraded", "stale"]


class FillModelStaleFeatureError(RuntimeError):
    """Raised by predict() when any current_features value is NaN or missing.

    Decision engine (Phase 4) catches and routes to cancel-all-and-pause breaker.
    Never silently substitute exp(β₀) — PITFALLS §NaN-covariate silent-fallback
    is the canonical fuck-up here."""

    def __init__(self, missing_features: list[str]):
        self.missing_features = missing_features
        super().__init__(f"stale/missing features: {missing_features}")


class FillModelNoFreshFitError(RuntimeError):
    """Raised by predict() when no fit exists OR all fits older than fit_max_staleness_s.

    Decision engine (Phase 4) catches and blocks PLACE commands (but existing orders
    continue to use the stale fit for cancel logic with a warning) — this is NOT a kill."""
