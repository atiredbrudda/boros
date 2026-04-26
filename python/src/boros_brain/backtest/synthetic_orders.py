"""BACK-01: in-memory synthetic-order ledger.

Mirrors state.open_orders shape but lives in-memory only — backtest is hermetic
and never writes to SQLite (single-writer-per-table discipline; backtest is a
read-only-on-state phase per RESEARCH.md L514-524).

Defensive: cancel/fill/purge raise KeyError on unknown order_id (orchestration
bugs surface loudly, not silently).

[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterator, Literal


@dataclass(frozen=True)
class SyntheticOrder:
    """An in-flight synthetic limit order for the backtest ledger.

    Immutable — state transitions (cancel/fill/purge) produce new instances via
    dataclasses.replace().
    """

    order_id: str
    market_id: str
    side: Literal["long", "short"]
    tick: int
    q_me_pendle: float
    placed_at_ts: int
    depth_from_mark_ticks: int
    queue_ahead_wei: int = 0
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

    def update_queue_ahead(self, order_id: str, queue_ahead_wei: int) -> None:
        """Update queue-ahead estimate for an active order. Raises KeyError if unknown."""
        self._orders[order_id] = replace(
            self._orders[order_id], queue_ahead_wei=queue_ahead_wei
        )

    def in_flight(self) -> Iterator[SyntheticOrder]:
        """Iterate over all orders whose status == 'active'."""
        return (o for o in self._orders.values() if o.status == "active")

    def get(self, order_id: str) -> SyntheticOrder | None:
        """Return the order if present, else None."""
        return self._orders.get(order_id)

    def __len__(self) -> int:
        return len(self._orders)


__all__ = ["SyntheticOrder", "SyntheticOrderLedger"]
