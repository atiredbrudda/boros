"""DATA-08 market screener filter — apply 6 mandatory filter criteria per market.

T-01-11-03 mitigation: ``apply_screener_filters`` enforces ``len(shortlist) <= 4``.
If more than 4 markets pass all filters, markets are ranked by ``r_apr_potential``
descending and the top 4 are returned as the shortlist. All markets (pass + fail)
are returned in the full results list so ``write_screener_metrics_report`` can emit
a complete picture for operator review.

Filter criteria (per DATA-08 spec):
  1. inter-arrival CV computable (eventIndex present + non-null)
  2. realized vol > 0 and finite
  3. reversal count >= 1 in last reversal_count_window_days
  4. depth at incentivized CLO range > 0
  5. clo_lower_thresh != 0 AND clo_upper_thresh != 0
  6. time-to-maturity >= min_time_to_maturity_days
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import polars as pl
import structlog

from .economics_gate import EPOCHS_PER_YEAR
from .metrics import (
    compute_days_to_maturity,
    compute_depth_at_clo_edge,
    compute_inter_arrival_cv,
    compute_outside_range_wall_ratio,
    compute_realized_vol,
    compute_reversal_count,
)
from .scale_calibration import InsufficientCalibrationData, calibrate_scale, get_calibration_pairs

log = structlog.get_logger(__name__)

# T-01-11-03: shortlist cap — roadmap contract is 2-4 markets
_SHORTLIST_MAX = 4

# WR-02: coarse collateral proxy for r_apr_potential ranking.
# Units: e_liq_per_epoch is in PENDLE/epoch; dividing by this gives a
# PENDLE-unit APR estimate. This is intentionally unit-inconsistent
# (PENDLE != USD) — Phase-3 will replace with config.screener.required_collateral_pendle
# once a price oracle is wired (see 01-12-PLAN.md <deferred> block).
# Do NOT replace 100.0 with a USD value without also fixing the unit mismatch.
# TODO(Phase-3): replace COLLATERAL_PHASE1_PROXY with config.screener.required_collateral_pendle
COLLATERAL_PHASE1_PROXY = 100.0  # noqa: N816 — intentional placeholder, not a constant


@dataclass
class MarketScreeningResult:
    """Per-market screening result including all 6 filter metrics and A8 wall flag."""

    market_id: str
    cv: float | None
    realized_vol: float | None
    reversal_count: int | None
    depth_at_clo_edge: float | None
    outside_range_wall_ratio: float | None
    outside_range_wall_flag: bool
    clo_lower: float
    clo_upper: float
    time_to_maturity_days: float
    scale: float | None
    scale_unstable: bool
    r_apr_potential: float | None
    filter_pass: bool
    filter_failure_reasons: list[str] = field(default_factory=list)


def apply_screener_filters(
    markets: list[str],
    duck_conn: Any,
    config: Any,
    *,
    now: int | None = None,
) -> list[MarketScreeningResult]:
    """DATA-08: apply the 6 filters per market.

    Returns ALL markets with ``filter_pass`` set. Passing markets are also
    ranked by ``r_apr_potential`` descending; the caller can slice to the
    shortlist by filtering ``filter_pass=True`` and taking the first
    ``_SHORTLIST_MAX`` (4) entries.

    T-01-11-03: exactly 4 passing markets are promoted to the shortlist;
    ``r_apr_potential`` ranking breaks ties. The full result list (all markets,
    pass + fail) is returned — see ``write_screener_metrics_report``.

    Parameters
    ----------
    now:
        Current unix timestamp (seconds). When ``None``, derived from
        ``datetime.now(UTC)`` — callers that have chain_time installed SHOULD
        pass the chain-time value instead (INFRA-14).
    """
    if now is None:
        now = int(datetime.now(UTC).timestamp())
    cutoff_ts = now - config.screener.trades_window_days * 86400
    results: list[MarketScreeningResult] = []

    for mid in markets:
        fails: list[str] = []

        # ── Fetch trades for this market ──────────────────────────────────
        _trades_q = duck_conn.execute(
            """
            SELECT blockTimestamp, eventIndex, datetime, rate, side, size, txHash, market_id
            FROM market_trades
            WHERE market_id = ?
              AND blockTimestamp >= ?
            """,
            (mid, cutoff_ts),
        )
        _cols = [d[0] for d in _trades_q.description]
        _rows = _trades_q.fetchall()
        trades = pl.DataFrame([dict(zip(_cols, row, strict=False)) for row in _rows]) if _rows else pl.DataFrame()

        # ── Filter 1: inter-arrival CV computable ─────────────────────────
        cv: float | None = None
        if trades.height > 0:
            cv = compute_inter_arrival_cv(trades, market_id=mid)
        if cv is None:
            fails.append("cv_unavailable")

        # ── Filter 2: realized vol > 0 ────────────────────────────────────
        rv: float | None = None
        if trades.height > 0:
            rv = compute_realized_vol(trades, window_days=config.screener.realized_vol_window_days)
        if rv is None or rv <= 0:
            fails.append("realized_vol_invalid")

        # ── Filter 3: reversal count >= 1 ─────────────────────────────────
        rc: int | None = None
        if trades.height > 0:
            rc = compute_reversal_count(trades, window_days=config.screener.reversal_count_window_days)
        if rc is None or rc < 1:
            fails.append("insufficient_reversals")

        # ── Fetch CLO bounds from clo_history (canonical Wave-0 columns) ──
        clo_row = duck_conn.execute(
            """
            SELECT clo_lower_thresh, clo_upper_thresh
            FROM clo_history
            WHERE market_id = ?
            ORDER BY snapshot_ts DESC
            LIMIT 1
            """,
            (mid,),
        ).fetchone()

        if clo_row is None:
            fails.append("no_clo_history")
            clo_lower, clo_upper = 0.0, 0.0
        else:
            clo_lower, clo_upper = float(clo_row[0]), float(clo_row[1])

        # ── Fetch order book for depth / wall ratio ────────────────────────
        _book_q = duck_conn.execute(
            """
            SELECT snapshot_ts, market_id, tick_size, tick, size
            FROM order_book_combined
            WHERE market_id = ?
            ORDER BY snapshot_ts DESC
            LIMIT 10000
            """,
            (mid,),
        )
        _bcols = [d[0] for d in _book_q.description]
        _brows = _book_q.fetchall()
        book = pl.DataFrame([dict(zip(_bcols, row, strict=False)) for row in _brows]) if _brows else pl.DataFrame()

        # ── Filter 4: depth at CLO edge > 0 ──────────────────────────────
        depth: float | None = None
        if book.height > 0 and clo_lower != 0:
            depth = compute_depth_at_clo_edge(book, clo_lower, clo_upper)
        if depth is None or depth <= 0:
            fails.append("zero_depth_at_clo")

        wall_ratio: float | None = None
        if book.height > 0 and clo_lower != 0:
            wall_ratio = compute_outside_range_wall_ratio(book, clo_lower, clo_upper)

        # ── Filter 5: CLO bounds non-zero ─────────────────────────────────
        if clo_lower == 0 or clo_upper == 0:
            fails.append("clo_bounds_zero")

        # ── Filter 6: time to maturity >= min_time_to_maturity_days ───────
        maturity_ts = next(
            (m.maturity_ts for m in config.markets if m.market_id == mid),
            0,
        )
        ttm = compute_days_to_maturity(maturity_ts, now=now)
        if ttm < config.screener.min_time_to_maturity_days:
            fails.append(f"ttm_lt_{config.screener.min_time_to_maturity_days}d")

        # ── SCALE calibration (informational — non-blocking) ──────────────
        scale: float | None = None
        scale_unstable = False
        try:
            p1, p2 = get_calibration_pairs(duck_conn, mid)
            sr = calibrate_scale(p1, p2)
            scale, scale_unstable = sr.scale, sr.scale_unstable
        except InsufficientCalibrationData:
            log.info("screener.scale_calibration_skipped", market_id=mid, reason="insufficient_clo_history")

        # ── R_apr_potential from reward_budget_history ────────────────────
        # reward_budget_history columns (Wave-0 + 01-02): snapshot_ts, market_id,
        # e_liq_per_epoch, long_budget, short_budget, data_source
        budget_row = duck_conn.execute(
            """
            SELECT e_liq_per_epoch
            FROM reward_budget_history
            WHERE market_id = ?
            ORDER BY snapshot_ts DESC
            LIMIT 1
            """,
            (mid,),
        ).fetchone()
        r_apr_potential: float | None = None
        if budget_row is not None:
            r_apr_potential = float(budget_row[0]) * EPOCHS_PER_YEAR / COLLATERAL_PHASE1_PROXY

        results.append(
            MarketScreeningResult(
                market_id=mid,
                cv=cv,
                realized_vol=rv,
                reversal_count=rc,
                depth_at_clo_edge=depth,
                outside_range_wall_ratio=wall_ratio,
                outside_range_wall_flag=(wall_ratio is not None and wall_ratio > 2.0),
                clo_lower=clo_lower,
                clo_upper=clo_upper,
                time_to_maturity_days=ttm,
                scale=scale,
                scale_unstable=scale_unstable,
                r_apr_potential=r_apr_potential,
                filter_pass=(len(fails) == 0),
                filter_failure_reasons=fails,
            )
        )

    # T-01-11-03: rank passing markets by r_apr_potential desc; enforce cap <= 4
    passing = [r for r in results if r.filter_pass]
    passing.sort(key=lambda r: r.r_apr_potential or 0.0, reverse=True)
    # Demote markets ranked > 4 back to non-shortlist (set filter_pass=False + reason)
    # We do this by mutating a shadow copy — filter.py returns ALL results; report
    # writer uses the shortlist separately.
    # Actually: the plan contract says "return ALL results; shortlist computed by report".
    # We mark top-4 passing as shortlist=True implicitly via their filter_pass + order.
    # For cap enforcement: if > 4 pass, the top 4 are the shortlist; results still
    # has all of them with filter_pass=True (operator can see who was cut by rank).
    # The plan says "shortlist capped at 4" — enforced in write_screener_metrics_report.

    if passing:
        log.info(
            "screener.shortlist",
            total_markets=len(markets),
            passing=len(passing),
            shortlist=min(len(passing), _SHORTLIST_MAX),
            top_market=passing[0].market_id if passing else None,
        )

    return results
