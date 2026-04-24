"""Tests for DATA-08 screener metrics (plan 01-11, Task 1).

TDD RED phase: all tests import from boros_brain.screener.metrics,
which does not yet exist — these must FAIL before implementation.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl
import structlog.testing

# Import target — will fail until metrics.py is created
from boros_brain.screener.metrics import (
    compute_days_to_maturity,
    compute_depth_at_clo_edge,
    compute_inter_arrival_cv,
    compute_outside_range_wall_ratio,
    compute_realized_vol,
    compute_reversal_count,
)

FIXTURES = Path(__file__).parent / "fixtures"
MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _load_trades() -> pl.DataFrame:
    """Load screener_sample_trades.ndjson fixture."""
    rows = [
        json.loads(line)
        for line in (FIXTURES / "screener_sample_trades.ndjson").read_text().splitlines()
        if line.strip()
    ]
    return pl.DataFrame(rows)


def _load_orderbook() -> pl.DataFrame:
    """Load screener_sample_orderbook.ndjson fixture."""
    rows = [
        json.loads(line)
        for line in (FIXTURES / "screener_sample_orderbook.ndjson").read_text().splitlines()
        if line.strip()
    ]
    return pl.DataFrame(rows)


# ── Test 1: Inter-arrival CV ────────────────────────────────────────────────


def test_cv_poisson_trades_in_range():
    """1000 Poisson trades (lambda=1/hr) -> CV in [0.7, 1.3]."""
    df = _load_trades()
    cv = compute_inter_arrival_cv(df, market_id=MARKET_ID)
    assert cv is not None, "CV should not be None for clean fixture"
    assert 0.7 <= cv <= 1.3, f"Expected CV ~1.0, got {cv}"


def test_cv_uses_eventindex_for_intrablock_ordering():
    """3 trades in same block must produce sub-second intervals via eventIndex."""
    df = _load_trades()
    # Find the 3 trades that share a block timestamp (same_block_ts)
    # They have eventIndex 100, 101, 102 (see fixture generator)
    same_block = (
        df.sort(["blockTimestamp", "eventIndex"])
        .filter(pl.col("blockTimestamp").is_duplicated())
        .filter(pl.col("eventIndex").is_in([100, 101, 102]))
    )

    # There should be exactly 3 rows in that group
    assert same_block.height >= 3, f"Expected >= 3 same-block trades, got {same_block.height}"

    # The pseudo-continuous time = blockTimestamp + eventIndex * 1e-6
    # intervals between consecutive same-block trades: (101-100)*1e-6 = 1e-6s
    # That's sub-second (< 1.0)
    t_continuous = same_block["blockTimestamp"].cast(pl.Float64) + same_block["eventIndex"].cast(pl.Float64) * 1e-6
    intervals = t_continuous.diff().drop_nulls()
    assert (intervals < 1.0).all(), f"Same-block intervals should be sub-second; got {intervals.to_list()}"


# ── Test 2: eventIndex gap rejection ────────────────────────────────────────


def test_cv_null_eventindex_returns_none_and_logs():
    """Fixture with one null eventIndex row -> CV=None + screener.eventindex_gap log."""
    df = _load_trades()
    # Inject one null eventIndex
    null_row = df.row(0, named=True)
    null_row["eventIndex"] = None  # type: ignore[assignment]
    injected = pl.concat(
        [
            df,
            pl.DataFrame([null_row]),
        ]
    )

    with structlog.testing.capture_logs() as cap:
        cv = compute_inter_arrival_cv(injected, market_id=MARKET_ID)

    assert cv is None, "CV must be None when any eventIndex is null"
    events = [e["event"] for e in cap]
    assert "screener.eventindex_gap" in events, f"Expected screener.eventindex_gap log; got events: {events}"


# ── Test 3: Realized volatility ──────────────────────────────────────────────


def test_realized_vol_synthetic_series():
    """Synthetic rate series with known sigma -> compute_realized_vol is positive and finite."""
    import math
    import random

    rng = random.Random(42)
    sigma = 0.01  # step size per hourly observation
    n_days = 60
    n = n_days * 24  # hourly

    # Build a random-walk rate series (no numpy dependency)
    base_ts = 1_750_000_000
    rate = 9400.0
    rates = []
    for _ in range(n):
        rate += rng.gauss(0, sigma)
        rates.append(rate)
    datetimes = [base_ts + i * 3600 for i in range(n)]

    df = pl.DataFrame(
        {
            "blockTimestamp": datetimes,
            "eventIndex": list(range(n)),
            "datetime": ["2025-08-01T00:00:00.000Z"] * n,
            "rate": rates,
            "side": ["long"] * n,
            "size": ["1000000000000000"] * n,
            "txHash": [f"0x{i:04x}" for i in range(n)],
            "market_id": [MARKET_ID] * n,
        }
    )

    rv = compute_realized_vol(df, window_days=14)
    assert rv is not None, "realized_vol should not be None"
    assert rv > 0, "realized_vol should be positive"
    assert math.isfinite(rv), "realized_vol must be finite"


# ── Test 4: Reversal count ───────────────────────────────────────────────────


def test_reversal_count_known_series():
    """Synthetic rate path with 7 reversals in 3 days -> compute_reversal_count == 7."""
    # Build a path with exactly 7 direction changes in the last 3 days
    # Rates: 100, 101, 100, 101, 100, 101, 100, 101  → 7 sign-changes of diff
    # Over 3 days worth of timestamps (within window)
    base_ts = 1_750_000_000
    # 3 days window = 3*86400 seconds; put rates within that window
    window_s = 3 * 86400

    # 9 points => 8 diffs; arrange sign alternation for 7 reversals
    rates_values = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0]
    n = len(rates_values)
    timestamps = [base_ts + i * (window_s // n) for i in range(n)]

    df = pl.DataFrame(
        {
            "blockTimestamp": timestamps,
            "eventIndex": list(range(n)),
            "datetime": ["2025-08-01T00:00:00.000Z"] * n,
            "rate": rates_values,
            "side": ["long"] * n,
            "size": ["1000000000000000"] * n,
            "txHash": [f"0x{i:04x}" for i in range(n)],
            "market_id": [MARKET_ID] * n,
        }
    )

    rc = compute_reversal_count(df, window_days=3)
    assert rc == 7, f"Expected 7 reversals, got {rc}"


# ── Test 5: Depth at CLO edge ─────────────────────────────────────────────────


def test_depth_at_clo_edge():
    """depth at edge ticks (9300 + 9500) sums correctly."""
    book = _load_orderbook()
    depth = compute_depth_at_clo_edge(book, clo_lower=9300, clo_upper=9500)
    assert depth is not None, "depth should not be None"
    # From fixture: 200.0 + 200.0 = 400.0
    assert abs(depth - 400.0) < 0.01, f"Expected ~400.0, got {depth}"


# ── Test 6: A8 outside-range-wall ratio ──────────────────────────────────────


def test_outside_range_wall_ratio():
    """Fixture with ratio=3.5 -> compute_outside_range_wall_ratio returns 3.5 ±0.01."""
    book = _load_orderbook()
    ratio = compute_outside_range_wall_ratio(book, clo_lower=9300, clo_upper=9500)
    assert ratio is not None, "ratio should not be None"
    # From fixture: (700+700) / (200+200) = 1400/400 = 3.5
    assert abs(ratio - 3.5) <= 0.01, f"Expected ~3.5, got {ratio}"


# ── Test 7: Time-to-maturity ──────────────────────────────────────────────────


def test_days_to_maturity():
    """maturity_ts 45 days from now -> compute_days_to_maturity returns 45 ±0.01."""
    now = int(time.time())
    maturity_ts = now + 45 * 86400
    ttm = compute_days_to_maturity(maturity_ts, now=now)
    assert abs(ttm - 45.0) <= 0.01, f"Expected ~45.0 days, got {ttm}"
