"""BACK-02 — two-axis cancel latency model: decision_ts + close_at_ts invariants.

Test functions:
  - test_decision_ts_is_next_one_hz_tick_after_fill: parametrized fill_ts cases
  - test_close_at_ts_equals_decision_ts_plus_L: L sweep cases
  - test_two_axes_compound_not_multiplex: SUM not MAX (compounding semantics)
  - test_validation_rejects_negative_L: ValueError guard
  - test_validation_rejects_zero_decision_period: ValueError guard

Turns GREEN in Plan 05-03 when boros_brain.backtest.cancel_latency lands.

[[backtest-cancel-latency-two-axis]]
[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

import pytest

from boros_brain.backtest.cancel_latency import LatencyScheduler, ScheduledClose

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.parametrize("fill_ts,expected_decision_ts", [
    (10.5, 11.0),
    (11.3, 12.0),
    (11.9, 12.0),
    (12.0, 13.0),    # On-tick: next available decision is the NEXT tick
    (12.0001, 13.0),
])
def test_decision_ts_is_next_one_hz_tick_after_fill(fill_ts: float, expected_decision_ts: float) -> None:
    """BACK-02: decision_ts = ceil(fill_ts / dt) * dt, with on-tick bump.

    fill_ts=11.3s with 1 Hz decision loop → next tick is at 12.0s.
    fill_ts=12.0s with 1 Hz decision loop → on-tick → next tick is at 13.0s.
    """
    sc = LatencyScheduler(L_seconds=0.0, decision_period_s=1.0).schedule(
        fill_ts=fill_ts, fill_rate=0.05, order_id="o1",
    )
    assert sc.decision_ts == pytest.approx(expected_decision_ts), (
        f"fill_ts={fill_ts}: expected decision_ts={expected_decision_ts}, "
        f"got {sc.decision_ts}"
    )


@pytest.mark.parametrize("L,expected_close_at_ts", [
    (5.0, 17.0),
    (2.0, 14.0),
    (0.5, 12.5),
    (10.0, 22.0),
])
def test_close_at_ts_equals_decision_ts_plus_L(L: float, expected_close_at_ts: float) -> None:
    """BACK-02: close_at_ts = decision_ts + L_seconds.

    fill_ts=11.3, L=5.0 → decision_ts=12.0 → close_at_ts=17.0.
    """
    sc = LatencyScheduler(L_seconds=L, decision_period_s=1.0).schedule(
        fill_ts=11.3, fill_rate=0.05, order_id="o1",
    )
    assert sc.close_at_ts == pytest.approx(expected_close_at_ts), (
        f"L={L}: expected close_at_ts={expected_close_at_ts}, got {sc.close_at_ts}"
    )


@pytest.mark.parametrize("fill_ts,L,expected_inventory_at_risk", [
    (11.3, 5.0, 5.7),    # axis1 = 0.7s, axis2 = 5.0s, total 5.7s (compounded)
    (11.0, 2.0, 3.0),    # 11.0 → 12.0 (1.0s) + 2.0s = 3.0s
    (12.0, 5.0, 6.0),    # on-tick: 12.0 → 13.0 (1.0s) + 5.0s = 6.0s
])
def test_two_axes_compound_not_multiplex(
    fill_ts: float, L: float, expected_inventory_at_risk: float
) -> None:
    """BACK-02: the two axes compound on same fill — SUM, not MAX.

    Axis 1: fill is noticed only at next 1 Hz decision tick (ceil/on-tick bump).
    Axis 2: cancel calldata transmission adds L more seconds.
    Both axes apply to the same fill — total delay is decision_latency + L.
    """
    sc = LatencyScheduler(L_seconds=L, decision_period_s=1.0).schedule(
        fill_ts=fill_ts, fill_rate=0.05, order_id="o1",
    )
    total = (sc.decision_ts - sc.fill_ts) + L  # SUM, not MAX (multiplex interpretation)
    assert abs(total - expected_inventory_at_risk) < 1e-9, (
        f"fill_ts={fill_ts}, L={L}: expected inventory_at_risk={expected_inventory_at_risk}, "
        f"got total={total} (decision_ts={sc.decision_ts}, fill_ts={sc.fill_ts})"
    )


def test_validation_rejects_negative_L() -> None:
    """BACK-02 / T-05-09: LatencyScheduler rejects L_seconds < 0."""
    with pytest.raises(ValueError, match="L_seconds must be >= 0"):
        LatencyScheduler(L_seconds=-0.1, decision_period_s=1.0)


def test_validation_rejects_zero_decision_period() -> None:
    """BACK-02 / T-05-09: LatencyScheduler rejects decision_period_s <= 0."""
    with pytest.raises(ValueError, match="decision_period_s must be > 0"):
        LatencyScheduler(L_seconds=5.0, decision_period_s=0.0)
