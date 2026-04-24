"""A8 mitigation: per-market SCALE calibration (plan 01-11, Task 2).

SCALE connects the packed fIndexOracle's floatingIndex_raw to display APR::

    fIndex_display = 10000 + floatingIndex_raw / SCALE

One value works for ETHUSDT (approximately 5.591e12), but other markets vary.
We calibrate from two observed (cloThresh, fIndex) pairs at least 1 day apart.

T-01-11-02 mitigation: if the two pairs yield SCALE estimates that diverge
by more than 1%, the result is flagged ``scale_unstable=True`` in the report
so the operator can review before trusting the APR conversion for that market.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class InsufficientCalibrationData(RuntimeError):
    """Raised when clo_history has fewer than 2 rows for the requested market."""


@dataclass(frozen=True)
class CalibrationPoint:
    """One observed (snapshot_ts, clo_lower_thresh, f_index_raw) triple.

    Column names match the Wave-0 canonical schema (01-02) with the
    f_index_raw addition populated by 01-09 MarketsPoller (checker issue #05).
    """

    snapshot_ts: int  # unix ts — matches Wave-0 column name
    clo_lower_thresh: float  # matches Wave-0 column name
    clo_upper_thresh: float  # matches Wave-0 column name
    f_index_raw: int  # decoded floatingIndex from bytes26 (01-02 schema + 01-09)
    market_id: str


@dataclass(frozen=True)
class ScaleResult:
    """Result of calibrate_scale()."""

    scale: float
    scale_unstable: bool  # True if the two pairs yield divergent SCALE > 1%


def calibrate_scale(p1: CalibrationPoint, p2: CalibrationPoint) -> ScaleResult:
    """Calibrate SCALE from two (clo_lower_thresh, f_index_raw) pairs.

    Formula per [[Boros fee schedule]] and boros_bot_guide.md §L505::

        fIndex_display = 10000 + floatingIndex_raw / SCALE
        => SCALE = f_index_raw / (clo_lower_thresh - 10000)

    For each point we compute an independent SCALE estimate, then average.
    T-01-11-02: if the two estimates diverge by > 1%, flag scale_unstable=True
    so the operator can inspect before relying on the APR conversion.
    """
    denom1 = p1.clo_lower_thresh - 10000.0
    denom2 = p2.clo_lower_thresh - 10000.0
    if denom1 == 0.0 or denom2 == 0.0:
        raise InsufficientCalibrationData(
            f"{p1.market_id}: clo_lower_thresh == 10000.0 — cannot invert SCALE formula "
            f"(denominator is zero). Market boundary sits exactly at fIndex center. (WR-01 fix)"
        )
    s1 = p1.f_index_raw / denom1
    s2 = p2.f_index_raw / denom2
    scale_avg = (s1 + s2) / 2.0
    divergence = abs(s1 - s2) / scale_avg if scale_avg != 0 else float("inf")
    unstable = divergence > 0.01

    if unstable:
        log.warning(
            "screener.scale_unstable",
            market_id=p1.market_id,
            scale_1=s1,
            scale_2=s2,
            divergence_pct=divergence * 100,
        )

    return ScaleResult(scale=scale_avg, scale_unstable=unstable)


def get_calibration_pairs(
    conn: Any,
    market_id: str,
) -> tuple[CalibrationPoint, CalibrationPoint]:
    """Query clo_history for the 2 most-distant-in-time rows with non-null f_index_raw.

    Columns queried match the Wave-0 canonical schema (01-02) with the
    f_index_raw addition from 01-09 MarketsPoller. Column names are
    snake_case per checker issue #05 (NOT the camelCase API wire names).

    Parameters
    ----------
    conn:
        A DB-API 2.0 connection (SQLite or DuckDB in sqlite_scanner mode).
        Must have ``clo_history`` visible.
    market_id:
        Market symbol string key (e.g. ``BINANCE-ETHUSDT-29MAY2026``).

    Raises
    ------
    InsufficientCalibrationData
        If fewer than 2 rows are available. The error message suggests
        waiting at least 1 day for a second poll cycle to complete.
    """
    rows = conn.execute(
        """
        SELECT snapshot_ts, clo_lower_thresh, clo_upper_thresh, f_index_raw
        FROM clo_history
        WHERE market_id = ? AND f_index_raw IS NOT NULL
        ORDER BY snapshot_ts ASC
        """,
        (market_id,),
    ).fetchall()

    if len(rows) < 2:
        raise InsufficientCalibrationData(
            f"{market_id}: need >= 2 clo_history rows with non-null f_index_raw, "
            f"have {len(rows)}. Wait >= 1 day for a second poll cycle."
        )

    # Use first + last for maximum time spread between the two calibration points
    first, last = rows[0], rows[-1]

    p1 = CalibrationPoint(
        snapshot_ts=int(first[0]),
        clo_lower_thresh=float(first[1]),
        clo_upper_thresh=float(first[2]),
        f_index_raw=int(first[3]),
        market_id=market_id,
    )
    p2 = CalibrationPoint(
        snapshot_ts=int(last[0]),
        clo_lower_thresh=float(last[1]),
        clo_upper_thresh=float(last[2]),
        f_index_raw=int(last[3]),
        market_id=market_id,
    )
    return (p1, p2)
