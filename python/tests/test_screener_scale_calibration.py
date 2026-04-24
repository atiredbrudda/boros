"""Tests for DATA-08 screener SCALE calibration (plan 01-11, Task 2).

TDD RED phase: tests import from boros_brain.screener.scale_calibration,
which does not yet exist.
"""

from __future__ import annotations

import sqlite3

import pytest

from boros_brain.screener.scale_calibration import (
    CalibrationPoint,
    InsufficientCalibrationData,
    ScaleResult,
    calibrate_scale,
    get_calibration_pairs,
)

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"

# Known SCALE for ETH: fIndex_display = 10000 + floatingIndex_raw / SCALE
# => SCALE = floatingIndex_raw / (clo_lower_thresh - 10000)
# Given clo_lower_thresh=9300 is INVALID (< 10000 would give negative denominator).
# Actual clo_lower_thresh must be > 10000.
# Use clo_lower_thresh=10900 (representative "borrow rate in bps") and
# f_index_raw chosen so SCALE = 5.591e12:
#   f_index_raw = SCALE * (clo_lower_thresh - 10000)
#               = 5.591e12 * (10900 - 10000) = 5.591e12 * 900 = 5.0319e15
KNOWN_SCALE = 5.591e12
CLO_LOWER = 10900.0  # bps-format clo threshold > 10000
F_INDEX_RAW = int(KNOWN_SCALE * (CLO_LOWER - 10000.0))  # = 5.0319e15


def _make_point(snapshot_ts: int, *, clo_lower: float = CLO_LOWER, f_index_raw: int = F_INDEX_RAW) -> CalibrationPoint:
    return CalibrationPoint(
        snapshot_ts=snapshot_ts,
        clo_lower_thresh=clo_lower,
        clo_upper_thresh=clo_lower + 200.0,
        f_index_raw=f_index_raw,
        market_id=MARKET_ID,
    )


# ── Test 1: Calibration from two identical-scale points ──────────────────────


def test_calibrate_scale_known_value():
    """Two points with known SCALE=5.591e12 -> calibrate_scale returns 5.591e12 ±0.1%."""
    p1 = _make_point(snapshot_ts=1_750_000_000)
    p2 = _make_point(snapshot_ts=1_750_086_400)  # 1 day later

    result = calibrate_scale(p1, p2)

    assert isinstance(result, ScaleResult)
    rel_err = abs(result.scale - KNOWN_SCALE) / KNOWN_SCALE
    assert rel_err <= 0.001, f"Expected SCALE ~{KNOWN_SCALE:.3e}, got {result.scale:.3e} (err={rel_err:.4%})"


# ── Test 2: Instability flag ──────────────────────────────────────────────────


def test_calibrate_scale_unstable_flag():
    """Two points with > 1% divergent SCALE -> scale_unstable=True; stable -> False."""
    p1 = _make_point(snapshot_ts=1_750_000_000)

    # Perturb p2's f_index_raw by +2% so SCALE diverges by 2%
    f_raw_drifted = int(F_INDEX_RAW * 1.02)
    p2_unstable = _make_point(snapshot_ts=1_750_086_400, f_index_raw=f_raw_drifted)

    result_unstable = calibrate_scale(p1, p2_unstable)
    assert result_unstable.scale_unstable is True, "Expected scale_unstable=True for 2% drift"

    # Same-scale points -> stable
    p2_stable = _make_point(snapshot_ts=1_750_086_400)
    result_stable = calibrate_scale(p1, p2_stable)
    assert result_stable.scale_unstable is False, "Expected scale_unstable=False for identical scale"


# ── Test 3: Insufficient data raises InsufficientCalibrationData ─────────────


def test_get_calibration_pairs_insufficient_data():
    """Only 1 clo_history row -> InsufficientCalibrationData with helpful message."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE clo_history (
            snapshot_ts INTEGER NOT NULL,
            market_id TEXT NOT NULL,
            clo_lower_thresh REAL NOT NULL,
            clo_upper_thresh REAL NOT NULL,
            f_index_raw INTEGER,
            PRIMARY KEY (snapshot_ts, market_id)
        )
    """)
    conn.execute(
        "INSERT INTO clo_history VALUES (?,?,?,?,?)",
        (1_750_000_000, MARKET_ID, CLO_LOWER, CLO_LOWER + 200.0, F_INDEX_RAW),
    )
    conn.commit()

    with pytest.raises(InsufficientCalibrationData) as exc_info:
        get_calibration_pairs(conn, MARKET_ID)

    msg = str(exc_info.value)
    assert (
        "wait" in msg.lower() or "day" in msg.lower()
    ), f"Error message should suggest waiting for a second row; got: {msg!r}"


# ── Test 4: get_calibration_pairs returns most-distant pair ──────────────────


def test_get_calibration_pairs_returns_first_and_last():
    """get_calibration_pairs returns the 2 most-distant-in-time rows >= 1 day apart."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE clo_history (
            snapshot_ts INTEGER NOT NULL,
            market_id TEXT NOT NULL,
            clo_lower_thresh REAL NOT NULL,
            clo_upper_thresh REAL NOT NULL,
            f_index_raw INTEGER,
            PRIMARY KEY (snapshot_ts, market_id)
        )
    """)
    # Insert 3 rows: day 0, day 1, day 2 (should pick day 0 + day 2)
    ts0 = 1_750_000_000
    ts1 = ts0 + 86400  # 1 day later
    ts2 = ts0 + 2 * 86400  # 2 days later

    conn.executemany(
        "INSERT INTO clo_history VALUES (?,?,?,?,?)",
        [
            (ts0, MARKET_ID, CLO_LOWER, CLO_LOWER + 200.0, F_INDEX_RAW),
            (ts1, MARKET_ID, CLO_LOWER, CLO_LOWER + 200.0, F_INDEX_RAW),
            (ts2, MARKET_ID, CLO_LOWER, CLO_LOWER + 200.0, F_INDEX_RAW),
        ],
    )
    conn.commit()

    pair = get_calibration_pairs(conn, MARKET_ID)
    assert len(pair) == 2, f"Expected a 2-tuple, got {len(pair)} items"

    p1, p2 = pair
    # Most-distant pair = first (ts0) and last (ts2)
    assert p1.snapshot_ts == ts0, f"Expected first row ts={ts0}, got {p1.snapshot_ts}"
    assert p2.snapshot_ts == ts2, f"Expected last row ts={ts2}, got {p2.snapshot_ts}"

    # Must be >= 1 day apart
    gap = p2.snapshot_ts - p1.snapshot_ts
    assert gap >= 86400, f"Expected gap >= 86400s, got {gap}"
