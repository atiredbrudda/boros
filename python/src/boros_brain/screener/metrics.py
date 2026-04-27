"""DATA-08 screener metrics — six per-market filter metrics + A8 outside-range-wall ratio.

All inter-arrival CV computations use ``eventIndex``-ordered intervals (NOT raw
``blockTimestamp``). Arbitrum blocks are ~250ms; ``blockTimestamp`` ties at the
second and would collapse intra-block ordering. See CLAUDE.md strategy
non-negotiables and [[eventIndex coverage]].

T-01-11-01 mitigation: any null ``eventIndex`` row causes the market's CV to
return ``None`` — the market fails the screener's CV filter rather than
silently computing a wrong value.
"""

from __future__ import annotations

import math

import polars as pl
import structlog

log = structlog.get_logger(__name__)


def compute_inter_arrival_cv(
    trades: pl.DataFrame,
    *,
    market_id: str = "",
) -> float | None:
    """Compute the coefficient of variation of inter-arrival times.

    Uses ``(blockTimestamp, eventIndex)``-ordered trades. When two trades share
    the same ``blockTimestamp`` (same Arbitrum block), we assign a
    pseudo-continuous time via::

        t_continuous = blockTimestamp + eventIndex * 1e-6

    This preserves strict intra-block ordering without clamping sub-second
    intervals to zero (as plain ``diff(blockTimestamp)`` would).

    T-01-11-01: if ANY row has a null ``eventIndex``, this function returns
    ``None`` and emits a structured log event ``screener.eventindex_gap``.
    """
    if trades.is_empty():
        return None

    # Sort by blockTimestamp then eventIndex (canonical ordering for this project)
    df = trades.sort(["blockTimestamp", "eventIndex"])

    # T-01-11-01: reject markets with any null eventIndex
    null_count = df["eventIndex"].is_null().sum()
    if null_count > 0:
        log.warning(
            "screener.eventindex_gap",
            market_id=market_id,
            null_rows=int(null_count),
        )
        return None

    # Pseudo-continuous time: blockTimestamp + eventIndex * 1e-6
    # eventIndex is strictly ordered within a block so this is a valid total order.
    t_continuous = df["blockTimestamp"].cast(pl.Float64) + df["eventIndex"].cast(pl.Float64) * 1e-6
    intervals = t_continuous.diff().drop_nulls()

    if intervals.is_empty() or intervals.mean() == 0:
        return None

    mean_val = float(intervals.mean())
    std_val = float(intervals.std())
    if mean_val == 0:
        return None

    return std_val / mean_val


def compute_realized_vol(
    trades: pl.DataFrame,
    *,
    window_days: int = 14,
) -> float | None:
    """Compute realized volatility of the ``rate`` column over ``window_days``.

    Uses the standard deviation of first differences of consecutive ``rate``
    observations sorted by ``(blockTimestamp, eventIndex)``. Returns the std
    of rate differences in native units (e.g. APR units). Uses the
    ``blockTimestamp`` column only for window cutoff (not for interval
    spacing).

    Why differences (not log-returns): Boros implied APR rates oscillate
    around zero (observed range -0.013 to +0.011 with ~600/360 neg/pos
    split on ETHUSDT-29MAY). A log-return formula ``log(r_t / r_{t-1})``
    is undefined when the ratio is non-positive — every sign change or
    zero-crossing produces NaN, and the resulting ``std()`` collapses to
    NaN, which propagates as ``None`` from this function. Rate
    differences are sign-agnostic and well-defined for a series that
    crosses zero, which is the actual data-generating process for Boros
    implied APR.
    """
    if trades.is_empty():
        return None

    df = trades.sort(["blockTimestamp", "eventIndex"])

    # Filter to last window_days by blockTimestamp
    if df.height < 2:
        return None

    max_ts = df["blockTimestamp"].max()
    cutoff_ts = max_ts - window_days * 86400
    window_df = df.filter(pl.col("blockTimestamp") >= cutoff_ts)

    if window_df.height < 2:
        return None

    rates = window_df["rate"].cast(pl.Float64)
    # First differences in native rate units — sign-agnostic, defined for
    # rate series that cross zero (real Boros implied APR behaviour).
    diffs = rates.diff().drop_nulls()

    if diffs.is_empty():
        return None

    rv = float(diffs.std())
    if not math.isfinite(rv) or rv <= 0:
        return None

    return rv


def compute_reversal_count(
    trades: pl.DataFrame,
    *,
    window_days: int = 3,
) -> int | None:
    """Count sign changes in ``diff(rate)`` over the last ``window_days``.

    A reversal is defined as a sign change in the first difference of the rate
    series. Uses ``(blockTimestamp, eventIndex)`` ordering.
    """
    if trades.is_empty():
        return None

    df = trades.sort(["blockTimestamp", "eventIndex"])

    max_ts = df["blockTimestamp"].max()
    cutoff_ts = max_ts - window_days * 86400
    window_df = df.filter(pl.col("blockTimestamp") >= cutoff_ts)

    if window_df.height < 2:
        return 0

    rates = window_df["rate"].cast(pl.Float64)
    diffs = rates.diff().drop_nulls()

    if diffs.is_empty():
        return 0

    # Count sign changes: consecutive diff values with opposite signs
    signs = diffs.sign()
    sign_changes = (signs.shift(1) * signs < 0).drop_nulls().sum()
    return int(sign_changes)


def compute_depth_at_clo_edge(
    book: pl.DataFrame,
    clo_lower: float,
    clo_upper: float,
) -> float | None:
    """Sum ``size`` for ticks at exactly ``clo_lower`` and ``clo_upper`` (inclusive).

    Uses the most-recent combined-book snapshot (highest ``snapshot_ts``).
    The ``size`` column is expected to be a numeric float (the ingester converts
    from wei strings before writing to parquet).
    """
    if book.is_empty():
        return None

    # Most recent snapshot
    max_ts = book["snapshot_ts"].max()
    snap = book.filter(pl.col("snapshot_ts") == max_ts)

    edge = snap.filter((pl.col("tick") == int(clo_lower)) | (pl.col("tick") == int(clo_upper)))

    if edge.is_empty():
        return None

    total = float(edge["size"].cast(pl.Float64).sum())
    return total


def compute_outside_range_wall_ratio(
    book: pl.DataFrame,
    clo_lower: float,
    clo_upper: float,
) -> float | None:
    """Compute the A8 outside-range-wall ratio.

    ``ratio = depth_one_tick_outside / depth_at_edge``

    where:
    - ``depth_at_edge`` = sum(size for tick in {clo_lower, clo_upper})
    - ``depth_one_tick_outside`` = sum(size for tick in {clo_lower-1, clo_upper+1})

    Returns ``None`` if either side sums to zero (avoids divide-by-zero).
    A ratio > 2 indicates a significant outside-range wall (A8 flag).
    """
    if book.is_empty():
        return None

    # Most recent snapshot
    max_ts = book["snapshot_ts"].max()
    snap = book.filter(pl.col("snapshot_ts") == max_ts)

    lower_tick = int(clo_lower)
    upper_tick = int(clo_upper)

    edge = snap.filter((pl.col("tick") == lower_tick) | (pl.col("tick") == upper_tick))
    outside = snap.filter((pl.col("tick") == lower_tick - 1) | (pl.col("tick") == upper_tick + 1))

    depth_edge = float(edge["size"].cast(pl.Float64).sum()) if not edge.is_empty() else 0.0
    depth_outside = float(outside["size"].cast(pl.Float64).sum()) if not outside.is_empty() else 0.0

    if depth_edge == 0:
        return None

    return depth_outside / depth_edge


def compute_days_to_maturity(
    maturity_ts: int,
    now: int,
) -> float:
    """Compute days remaining to maturity.

    Parameters
    ----------
    maturity_ts:
        Unix timestamp (seconds) of market maturity.
    now:
        Current unix timestamp. Callers MUST supply this from
        ``chain_time.now_cached()`` (INFRA-14). The no_time_time_lint
        pre-commit hook forbids wall-clock reads in screener/ — callers
        must always pass this value explicitly.
    """
    return (maturity_ts - now) / 86400.0
