"""Pydantic + dataclass shapes for the loss model (LOSS-01/02/03).

Phase-4 LOCKED contract — DecisionEngine + Plan 03-03 Sizer consume:
    - LossGridArtifact       (dual-write parquet + state.loss_grid_artifacts)
    - ExpectedLossInput/Output  (sync expected_loss() signature)
    - LossModelNoFreshGridError (raised by expected_loss when grid too stale)

Single home for all loss_model shape declarations so architecture.yml has a single
`brain.loss_model.schemas` node.

[[empirical-loss-grid-v05]]: bucket-edge convention + per-cell stats.
[[ou-on-basis-loss-scaffold]]: v1.0 drop-in interface that mirrors expected_loss.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PerFillPnL:
    """One row of empirical post-fill P&L under immediate-close policy.

    Emitted by replay_historical_fills, consumed by fit_loss_grid bucket aggregator.
    """

    market_id: str
    side: Literal["long", "short"]
    fill_event_index: int | None
    fill_block_ts: int
    fill_rate: float
    fill_size_float: float
    depth_from_mark_ticks: int
    tau_days: float
    close_rate: float
    close_block_ts: int
    close_latency_s: float
    pnl_pendle: float  # P&L after fees, in PENDLE-units
    fee_taker_pendle: float
    fee_settlement_pendle: float
    fee_entrance_amortized_pendle: float
    fee_gas_pendle: float


# --- Pydantic shapes (re-import to keep dataclass section pure) ---------------

from pydantic import BaseModel, ConfigDict  # noqa: E402


class StrictBase(BaseModel):
    """Local strict base for loss_model Pydantic models (avoids circular import
    with config.schema). Matches fill_model/schemas.py pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LossGridCell(StrictBase):
    """Per-(depth_bucket, tau_bucket) aggregated P&L stats for one (market, side)."""

    depth_bucket_idx: int
    tau_bucket_idx: int
    n_samples: int
    mean_pendle: float
    std_pendle: float
    p5_pendle: float
    p50_pendle: float
    p95_pendle: float


class LossGridArtifact(StrictBase):
    """Immutable record of one (market_id, side, window_end_ts) loss-grid fit.

    Persisted to state.loss_grid_artifacts + parquet sidecar. Primary-keyed by
    (market_id, side, window_end_ts).
    """

    run_id: str
    market_id: str
    side: Literal["long", "short"]
    window_start_ts: int
    window_end_ts: int
    fit_status: Literal["ok", "degraded", "stale"]
    depth_bucket_edges: list[float]
    tau_bucket_edges_days: list[float]
    cells: list[LossGridCell]
    event_index_coverage: Literal["full", "degraded"] = "full"
    created_at: int = 0  # sentinel — artifact.write_loss_grid_artifact stamps the real ts


class ExpectedLossInput(StrictBase):
    """Sync expected_loss() request shape — Phase 4 DecisionEngine + Plan 03-03 Sizer."""

    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    time_to_maturity_s: int
    current_chain_ts: int  # Phase 4 supplies from chain_time.now_cached()


class ExpectedLossOutput(StrictBase):
    """Sync expected_loss() response shape — fully-traceable per call.

    fallback_mode = "exact" / "nearest_neighbor" / "coarse_bound" — NEVER silently 0.
    """

    expected_loss_pendle: float
    cell_n_samples: int
    cell_p50_pendle: float
    cell_p95_pendle: float
    fallback_mode: Literal["exact", "nearest_neighbor", "coarse_bound"]
    grid_artifact_run_id: str
    grid_age_s: float
    fit_status: Literal["ok", "degraded", "stale"]


class LossModelNoFreshGridError(RuntimeError):
    """Raised by expected_loss() when no loss-grid artifact fresh enough for (market_id, side).

    Decision engine (Phase 4) catches and routes to PLACE-suppression (P3-9) — but
    existing orders continue to use the stale grid for cancel logic with a warning;
    this is NOT a kill. Mirrors FillModelNoFreshFitError contract.
    """
