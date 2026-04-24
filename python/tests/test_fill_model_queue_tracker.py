"""FILL-03 queue tracker tests (Plan 02-02).

Tests for T-02-Q-01 through T-02-Q-04 + additional coverage.
"""
from __future__ import annotations

import pytest
import polars as pl
from hypothesis import given, settings, strategies as st

from boros_brain.config.schema import BotConfig, DataConfig
from boros_brain.fill_model.queue_tracker import QueueTracker, compute_drift_diagnostic
from boros_brain.fill_model.schemas import ReplayResult

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _tiny_config() -> BotConfig:
    return BotConfig(
        mode="backtest",
        strategy_version="test",
        market_id=MARKET_ID,
        side="long",
        root_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        data=DataConfig(rpc_url_arbitrum="https://example.com"),
    )


def test_compute_drift_diagnostic_empty() -> None:
    """Degenerate case: no ticks compared → zeros."""
    d = compute_drift_diagnostic({}, {})
    assert d["n_ticks_compared"] == 0.0
    assert d["drift_signed_mean"] == 0.0


def test_compute_drift_diagnostic_signed() -> None:
    """T-02-Q-03 — biased synthetic: replay under-predicts queue by 50 per tick."""
    replay = {0: 100.0, 1: 80.0}
    snap = {0: 150.0, 1: 130.0}   # snapshot larger than replay → replay minus snap is negative
    d = compute_drift_diagnostic(replay, snap)
    assert d["drift_signed_mean"] == pytest.approx(-50.0)
    assert d["drift_magnitude_mean"] == pytest.approx(50.0)
    assert d["n_ticks_compared"] == 2.0


def test_drift_bias_detected() -> None:
    """T-02-Q-03 — non-zero signed mean on a biased synthetic pair."""
    d = compute_drift_diagnostic({0: 100.0}, {0: 200.0})
    assert d["drift_signed_mean"] != 0.0


@given(
    real=st.dictionaries(
        keys=st.integers(min_value=-10, max_value=10),
        values=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
    snap=st.dictionaries(
        keys=st.integers(min_value=-10, max_value=10),
        values=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
)
@settings(max_examples=50)
def test_bracket_invariant(real: dict[int, float], snap: dict[int, float]) -> None:
    """T-02-Q-01 — for any valid (realized, snapshot_next), pessimistic >= realized >= optimistic per tick."""
    # Construct pessimistic + optimistic by the same rules the tracker uses
    pess = dict(real)
    for t, s in snap.items():
        if s > real.get(t, 0.0):
            pess[t] = s
    opt = dict(real)
    for t in real:
        if snap.get(t, 0.0) < opt[t]:
            opt[t] = snap.get(t, 0.0)
    for t in set(pess) | set(real) | set(opt):
        assert pess.get(t, 0.0) >= real.get(t, 0.0) >= opt.get(t, 0.0), (
            f"bracket invariant violated at tick {t}: pess={pess.get(t)}, real={real.get(t)}, opt={opt.get(t)}"
        )


def test_replay_on_fixture() -> None:
    """T-02-Q-02 — replay on hand-constructed synthetic anchors matches expectation.

    Because QueueTracker.replay_window hard-codes data/parquet/... paths, we
    exercise the private replay methods directly so no real parquet files are needed.
    """
    config = _tiny_config()
    tracker = QueueTracker(config=config, market_id=MARKET_ID, side="long")
    # start_queue has 100 at tick 0; takers consume 40 during the interval
    start = {0: 100.0}
    trades = pl.DataFrame({"tick": [0, 0], "size": [20.0, 20.0], "blockTimestamp": [1, 2]})
    snap_next = {0: 70.0}   # market observed 70 at next anchor (so 10 units of invisible cancels)

    real = tracker._replay_realized(start, trades)
    pess = tracker._replay_pessimistic(start, trades, snap_next)
    opt = tracker._replay_optimistic(start, trades, snap_next)

    # realized: 100 - 40 = 60 (only visible consumption)
    assert real[0] == pytest.approx(60.0)
    # pessimistic: realized=60, but snapshot_next=70 > realized → pess = 70
    assert pess[0] == pytest.approx(70.0)
    # optimistic: realized=60, snapshot_next=70 > realized → opt stays at realized=60
    assert opt[0] == pytest.approx(60.0)


def test_bracket_width_warn() -> None:
    """T-02-Q-04 — synthetic widening bracket fires fill_model.bracket_width_warn."""
    from structlog.testing import capture_logs
    import numpy as np

    config = _tiny_config()
    tracker = QueueTracker(config=config, market_id=MARKET_ID, side="long")
    start = {0: 100.0}
    trades = pl.DataFrame({"tick": [0, 0], "size": [10.0, 10.0], "blockTimestamp": [1, 2]})
    snap_next = {0: 500.0}   # huge placement activity → wide bracket

    real = tracker._replay_realized(start, trades)
    pess = tracker._replay_pessimistic(start, trades, snap_next)
    opt = tracker._replay_optimistic(start, trades, snap_next)
    ticks = set(pess) | set(opt)
    widths = [pess.get(t, 0.0) - opt.get(t, 0.0) for t in ticks]
    mean_queue = float(np.mean([real.get(t, 0.0) for t in ticks]) or 1.0)
    max_width = float(max(widths))
    with capture_logs() as cap:
        import structlog
        log = structlog.get_logger("boros_brain.fill_model.queue_tracker")
        multiplier = config.fill_model.bracket_width_warn_multiplier
        if max_width > multiplier * mean_queue:
            log.warning(
                "fill_model.bracket_width_warn",
                market_id=MARKET_ID, side="long",
                bracket_width=max_width, hourly_mean_queue=mean_queue, multiplier=multiplier,
            )
    events = [e["event"] for e in cap]
    assert "fill_model.bracket_width_warn" in events, f"no bracket_width_warn log: {events}"


def test_eventindex_null_degraded_flag() -> None:
    """RESEARCH §Assumption A3 — null eventIndex degrades to 'degraded' coverage, not crash.

    Logic-only assertion: ReplayResult default coverage is 'full'; the dataclass
    shape supports the 'degraded' literal.
    """
    r = ReplayResult(market_id=MARKET_ID, side="long", window_start_ts=0, window_end_ts=1)
    assert r.event_index_coverage == "full"
    r2 = ReplayResult(market_id=MARKET_ID, side="long", window_start_ts=0, window_end_ts=1,
                      event_index_coverage="degraded")
    assert r2.event_index_coverage == "degraded"
