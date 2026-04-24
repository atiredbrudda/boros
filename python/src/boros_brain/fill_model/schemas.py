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
