"""BACK-01: in-memory synthetic-order ledger.

Mirrors state.open_orders shape but lives in-memory only — backtest is hermetic
and never writes to SQLite (single-writer-per-table discipline; backtest is a
read-only-on-state phase per RESEARCH.md L514-524).

Defensive: cancel/fill/purge raise KeyError on unknown order_id (orchestration
bugs surface loudly, not silently).

[[backtest-replay-engine-v05]]
[[fill-path-repair-2026-04-30]]

Phase 05.3 Plan 01 D1 — YU unit convention (rename queue_ahead_wei →
queue_ahead_yu): the binding-market parquet writes ``size_wei = NULL`` for
every row (ingester correctly emits null when the source is the float column);
the only populated size column is ``size_float`` (YU-denominated). The
backtest's fill detection therefore operates in YU throughout. The live
``fill_model.queue_tracker`` already operates in YU internally (per-tick
dict[int, float] keyed on tick → YU size), so no live-path rename is needed.
The IPC seam (PredictInput / EvaluateInput / SizerInput) keeps wei semantics;
``replay._build_evaluate_input`` converts YU → wei at the seam.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Literal


@dataclass(frozen=True)
class SyntheticOrder:
    """An in-flight synthetic limit order for the backtest ledger.

    Immutable — state transitions (cancel/fill/purge) produce new instances via
    dataclasses.replace().

    ``queue_ahead_yu`` (Phase 05.3 D1, replaces ``queue_ahead_wei``):
        Estimated queue size in YU sitting in front of this order on the
        order book. Compared to trade ``size_float`` (also YU) in the
        backtest fill-detection path; when ``size_float >= queue_ahead_yu``
        the order is considered filled. Default ``0.0`` so an unset queue
        means "next in line" (any nonzero trade event consumes it).
    """

    order_id: str
    market_id: str
    side: Literal["long", "short"]
    tick: int
    q_me_pendle: float
    placed_at_ts: int
    depth_from_mark_ticks: int
    queue_ahead_yu: float = 0.0
    r_accum: float = 0.0
    status: Literal["active", "filled", "cancelled", "purged"] = "active"
    t_frac: float = 1.0


class SyntheticOrderLedger:
    """In-memory order book mirror. NEVER persisted; backtest is hermetic.

    Defensive protocol: cancel/fill/purge raise KeyError when order_id is
    unknown — these indicate an orchestration bug, not a benign runtime branch.
    """

    def __init__(self) -> None:
        self._orders: dict[str, SyntheticOrder] = {}

    def place(self, order: SyntheticOrder) -> None:
        """Register a new active order in the ledger."""
        self._orders[order.order_id] = order

    def cancel(self, order_id: str) -> None:
        """Transition order to 'cancelled'. Raises KeyError if unknown."""
        self._orders[order_id] = replace(self._orders[order_id], status="cancelled")

    def mark_filled(self, order_id: str) -> None:
        """Transition order to 'filled'. Raises KeyError if unknown."""
        self._orders[order_id] = replace(self._orders[order_id], status="filled")

    def mark_purged(self, order_id: str) -> None:
        """Transition order to 'purged'. Raises KeyError if unknown."""
        self._orders[order_id] = replace(self._orders[order_id], status="purged")

    def update_queue_ahead(self, order_id: str, queue_ahead_yu: float) -> None:
        """Update queue-ahead estimate (YU) for an active order. Raises KeyError if unknown.

        Renamed from ``queue_ahead_wei`` in Phase 05.3 D1; semantics unchanged
        beyond the unit convention (now YU).
        """
        self._orders[order_id] = replace(self._orders[order_id], queue_ahead_yu=float(queue_ahead_yu))

    def in_flight(self) -> Iterator[SyntheticOrder]:
        """Iterate over all orders whose status == 'active'."""
        return (o for o in self._orders.values() if o.status == "active")

    def get(self, order_id: str) -> SyntheticOrder | None:
        """Return the order if present, else None."""
        return self._orders.get(order_id)

    def __len__(self) -> int:
        return len(self._orders)


__all__ = ["SyntheticOrder", "SyntheticOrderLedger"]
