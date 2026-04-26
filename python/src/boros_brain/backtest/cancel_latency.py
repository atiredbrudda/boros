"""BACK-02: two-axis cancel-latency simulator.

Latency has two compounding axes:
  Axis 1 (order-of-event): the bot's decision lands at the next 1 Hz tick AFTER a fill.
  Axis 2 (time-since-event): close-at-market is scheduled L seconds after fill detection.

Both apply to the same fill — they compound, they do not multiplex. PITFALLS §C2.

Realized close P&L uses underlying APR at `close_at_ts` — NOT at `fill_ts`.
The L-second window IS the inventory-at-risk period the latency simulation is meant
to capture; using fill_ts basis erases axis-2 of the latency model.

NEVER calls `time.time()` — replay engine passes blockTimestamp (chain time).
scripts/no_time_time_lint.py enforces this.

[[backtest-cancel-latency-two-axis]]
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledClose:
    """A scheduled close-at-market event awaiting its `close_at_ts` to fire.

    Created by LatencyScheduler.schedule(...) when a synthetic order is hit by a trade.
    Consumed by ReplayEngine._fire_scheduled_closes(current_ts) when current_ts >= close_at_ts.
    """

    order_id: str
    fill_ts: float
    fill_event_index: int
    decision_ts: float
    close_at_ts: float
    fill_rate: float


class LatencyScheduler:
    """Two-axis latency simulator. NEVER calls time.time() — replay engine passes blockTimestamp.

    Axis 1 (order-of-event): the bot's 1 Hz decision loop only notices the fill at the
    NEXT tick boundary after the fill. `decision_ts = ceil(fill_ts / dt) * dt`.
    If fill_ts is exactly on a tick, the bot already processed that tick BEFORE the fill
    arrived (block ordering: decision precedes trade events in the same block), so the
    next decision is at the NEXT tick: decision_ts = fill_ts + dt.

    Axis 2 (time-since-event): cancellation takes L_seconds of software + RPC + sequencer
    latency from the decision point. `close_at_ts = decision_ts + L_seconds`.

    Both axes apply to the same fill — they COMPOUND, they do NOT multiplex.
    Total inventory-at-risk window = (decision_ts - fill_ts) + L_seconds.
    """

    def __init__(self, L_seconds: float, decision_period_s: float = 1.0) -> None:
        if L_seconds < 0:
            raise ValueError(f"L_seconds must be >= 0; got {L_seconds}")
        if decision_period_s <= 0:
            raise ValueError(f"decision_period_s must be > 0; got {decision_period_s}")
        self.L = float(L_seconds)
        self.dt = float(decision_period_s)

    def schedule(
        self,
        fill_ts: float,
        fill_rate: float,
        order_id: str,
        *,
        fill_event_index: int = 0,
    ) -> ScheduledClose:
        """Return a ScheduledClose with two-axis latency applied.

        decision_ts = next 1 Hz tick AFTER fill_ts (axis 1).
        close_at_ts = decision_ts + L_seconds (axis 2).

        Parameters
        ----------
        fill_ts:
            blockTimestamp (chain time) of the fill event. NEVER pass time.time() here.
        fill_rate:
            Implied APR at fill (used downstream for P&L computation).
        order_id:
            Synthetic order ID for ledger bookkeeping.
        fill_event_index:
            eventIndex of the fill event (for ordering tie-break diagnostics).
        """
        # Axis 1: order-of-event. Advance to the next dt boundary.
        decision_ts = math.ceil(fill_ts / self.dt) * self.dt
        # If fill_ts is exactly on a tick (e.g., fill_ts=12.0, dt=1.0 → ceil gives 12.0),
        # the bot already processed tick 12.0 BEFORE this fill arrived in the same block
        # (block-ordering semantics: the decision precedes any post-tick trade events).
        # So the next available decision is the NEXT tick.
        if decision_ts == fill_ts:
            decision_ts = fill_ts + self.dt
        # Axis 2: time-since-event. L seconds of software+RPC+sequencer latency.
        close_at_ts = decision_ts + self.L
        return ScheduledClose(
            order_id=order_id,
            fill_ts=fill_ts,
            fill_event_index=fill_event_index,
            decision_ts=decision_ts,
            close_at_ts=close_at_ts,
            fill_rate=fill_rate,
        )


__all__ = ["ScheduledClose", "LatencyScheduler"]
