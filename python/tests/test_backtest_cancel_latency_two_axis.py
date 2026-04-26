"""BACK-02 — two-axis cancel latency model: decision_ts + close_at_ts invariants.

Test functions:
  - test_decision_ts_is_next_one_hz_tick_after_fill: fill_ts=11.3 → decision_ts=12.0
  - test_close_at_ts_equals_decision_ts_plus_L: L=5.0 → close_at_ts = 17.0
  - test_two_axes_compound_not_multiplex: both axes apply to same fill

Turns GREEN in Plan 05-03 when boros_brain.backtest.cancel_latency lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-03.
cancel_latency = pytest.importorskip("boros_brain.backtest.cancel_latency")
LatencyScheduler = cancel_latency.LatencyScheduler
ScheduledClose = cancel_latency.ScheduledClose

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_decision_ts_is_next_one_hz_tick_after_fill() -> None:
    """BACK-02: decision_ts = ceil(fill_ts / decision_period_s) * decision_period_s.

    fill_ts=11.3s with 1 Hz decision loop → next tick is at 12.0s.
    """
    scheduler = LatencyScheduler(L_seconds=5.0, decision_period_s=1.0)
    close = scheduler.schedule(fill_ts=11.3, fill_rate=0.05, order_id="t1")

    assert close.decision_ts == pytest.approx(12.0), (
        f"Expected decision_ts=12.0 (next 1 Hz tick after fill_ts=11.3), "
        f"got {close.decision_ts}"
    )


def test_close_at_ts_equals_decision_ts_plus_L() -> None:
    """BACK-02: close_at_ts = decision_ts + L_seconds.

    fill_ts=11.3, L=5.0 → decision_ts=12.0 → close_at_ts=17.0.
    """
    scheduler = LatencyScheduler(L_seconds=5.0, decision_period_s=1.0)
    close = scheduler.schedule(fill_ts=11.3, fill_rate=0.05, order_id="t1")

    assert close.close_at_ts == pytest.approx(17.0), (
        f"Expected close_at_ts=17.0 (decision_ts=12.0 + L=5.0), "
        f"got {close.close_at_ts}"
    )


def test_two_axes_compound_not_multiplex() -> None:
    """BACK-02: the two axes (1 Hz decision latency + cancel latency L) compound on same fill.

    Axis 1: fill is only noticed at next 1 Hz decision tick (ceil).
    Axis 2: cancel calldata transmission adds L more seconds.
    Both axes apply to the same fill — the total delay is decision_latency + L.
    """
    scheduler = LatencyScheduler(L_seconds=3.0, decision_period_s=1.0)
    close = scheduler.schedule(fill_ts=9.7, fill_rate=0.05, order_id="compound-test")

    # decision_ts = ceil(9.7 / 1.0) * 1.0 = 10.0
    # close_at_ts = 10.0 + 3.0 = 13.0
    assert close.decision_ts == pytest.approx(10.0)
    assert close.close_at_ts == pytest.approx(13.0)
    assert close.order_id == "compound-test"
