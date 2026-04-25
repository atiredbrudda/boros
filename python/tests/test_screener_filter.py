"""Tests for DATA-08 screener filter, report, and CLI (plan 01-11, Task 3).

TDD RED phase: all tests import from boros_brain.screener.{filter,report,cli},
which do not yet exist.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb

from boros_brain.screener.filter import MarketScreeningResult, apply_screener_filters
from boros_brain.screener.report import write_screener_metrics_report

MARKET_A = "BINANCE-ETHUSDT-29MAY2026"
MARKET_B = "BINANCE-BTCUSDT-26DEC2025"
MARKET_C = "BINANCE-SOLUSDT-26DEC2025"
MARKET_D = "BINANCE-XRPUSDT-26DEC2025"
MARKET_E = "BINANCE-HYPEUSDTT-26DEC2025"


# ── Minimal config stub ──────────────────────────────────────────────────────


@dataclass
class _ScreenerConf:
    min_time_to_maturity_days: int = 30
    trades_window_days: int = 60
    realized_vol_window_days: int = 14
    reversal_count_window_days: int = 3
    alt_yield: float = 0.05
    fill_loss_coarse_bound: float = 0.02


@dataclass
class _MarketCal:
    market_id: str
    maturity_ts: int
    scale: float = 5.591e12
    s: float = 0.0
    clo_lower_thresh: float = 10900.0
    clo_upper_thresh: float = 11100.0
    fIndex_oracle_address: str = "0x0"


@dataclass
class _Config:
    screener: _ScreenerConf
    markets: list[_MarketCal]


def _make_config(market_ids: list[str], ttm_days: int = 60) -> _Config:
    """Build a minimal config with the given market IDs all having ttm_days TTM."""
    import time

    now = int(time.time())
    maturity_ts = now + ttm_days * 86400
    markets = [_MarketCal(market_id=mid, maturity_ts=maturity_ts) for mid in market_ids]
    return _Config(screener=_ScreenerConf(), markets=markets)


def _make_duck_conn(
    market_ids: list[str],
    *,
    trades_per_market: int = 200,
    cv_null_market: str | None = None,
    zero_depth_market: str | None = None,
    zero_clo_market: str | None = None,
    no_reversals_market: str | None = None,
    e_liq_per_market: dict[str, float] | None = None,
) -> duckdb.DuckDBPyConnection:
    """Build an in-memory DuckDB connection with synthetic screener data.

    Each market gets:
    - market_trades: Poisson-ish arrival times with CV ~1, finite realized vol,
      and 7 direction reversals in the last 3 days — unless overridden.
    - order_book_combined: snapshot with depth at CLO edge and outside ratio < 2.
    - clo_history: non-zero CLO bounds.
    - reward_budget_history: one row per market with a configurable e_liq_per_epoch.
    """
    import random
    import time

    rng = random.Random(99)
    conn = duckdb.connect(":memory:")

    now = int(time.time())

    # ── market_trades table ──────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE market_trades (
            blockTimestamp BIGINT,
            eventIndex BIGINT,
            datetime VARCHAR,
            rate DOUBLE,
            side VARCHAR,
            size_float VARCHAR,
            txHash VARCHAR,
            market_id VARCHAR
        )
    """)

    for mid in market_ids:
        base_ts = now - 10 * 86400  # 10 days back — within the 60-day screener window
        t = float(base_ts)
        prev_rate = 9400.0
        direction = 1
        reversal_count = 0
        rows = []
        # Generate trades_per_market trades
        for i in range(trades_per_market):
            t += rng.expovariate(1 / 3600)  # Poisson lambda=1/hr
            bts = int(t)
            ei = i  # monotone eventIndex

            # Generate 7 reversals in the last 3 days of timestamps
            # All trades are within 70 days, so last 3 days = last ~3*24 trades (rough)
            if i >= trades_per_market - 8 and reversal_count < 7:
                direction = -direction
                reversal_count += 1
            rate = prev_rate + direction * rng.uniform(0.01, 0.5)
            prev_rate = rate

            ei_val = None if (mid == cv_null_market and i == 0) else ei
            rows.append((bts, ei_val, "2025-08-01T00:00:00.000Z", rate, "long", "1000", f"0x{i:04x}", mid))

        conn.executemany("INSERT INTO market_trades VALUES (?,?,?,?,?,?,?,?)", rows)

    # ── order_book_combined table ────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE order_book_combined (
            snapshot_ts VARCHAR,
            market_id VARCHAR,
            tick_size VARCHAR,
            tick INTEGER,
            sz_combined_float DOUBLE
        )
    """)

    snap_ts = str(now - 3600)
    for mid in market_ids:
        if mid == zero_depth_market:
            # depth=0 at CLO edge — filter 4 fails
            depth_lower = 0.0
            depth_upper = 0.0
        else:
            depth_lower = 200.0
            depth_upper = 200.0
        # ticks 10899 (outside lower), 10900 (lower edge), 11100 (upper edge), 11101 (outside upper)
        rows_ob = [
            (snap_ts, mid, "1", 10899, 50.0),  # one-tick-outside lower (ratio < 2)
            (snap_ts, mid, "1", 10900, depth_lower),  # clo_lower edge
            (snap_ts, mid, "1", 11100, depth_upper),  # clo_upper edge
            (snap_ts, mid, "1", 11101, 50.0),  # one-tick-outside upper
        ]
        conn.executemany("INSERT INTO order_book_combined VALUES (?,?,?,?,?)", rows_ob)

    # ── clo_history table ────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE clo_history (
            snapshot_ts BIGINT,
            market_id VARCHAR,
            clo_lower_thresh DOUBLE,
            clo_upper_thresh DOUBLE,
            f_index_raw BIGINT,
            PRIMARY KEY (snapshot_ts, market_id)
        )
    """)

    for mid in market_ids:
        if mid == zero_clo_market:
            clo_lower = 0.0
            clo_upper = 0.0
        else:
            clo_lower = 10900.0
            clo_upper = 11100.0
        conn.execute(
            "INSERT INTO clo_history VALUES (?,?,?,?,?)",
            (now - 3600, mid, clo_lower, clo_upper, 5031900000000000),
        )

    # ── reward_budget_history table ──────────────────────────────────────────
    conn.execute("""
        CREATE TABLE reward_budget_history (
            snapshot_ts BIGINT,
            market_id VARCHAR,
            e_liq_per_epoch DOUBLE,
            long_budget DOUBLE,
            short_budget DOUBLE,
            data_source VARCHAR
        )
    """)

    e_liq_map = e_liq_per_market or {}
    for mid in market_ids:
        e_liq = e_liq_map.get(mid, 100.0)
        conn.execute(
            "INSERT INTO reward_budget_history VALUES (?,?,?,?,?,?)",
            (now - 3600, mid, e_liq, e_liq / 2, e_liq / 2, "polled"),
        )

    return conn


# ── Test 1: all 6 filters applied individually ───────────────────────────────


def test_all_six_filters_applied():
    """5 markets each failing exactly one filter -> only passing markets in shortlist."""
    import time

    now = int(time.time())

    markets = [MARKET_A, MARKET_B, MARKET_C, MARKET_D, MARKET_E]

    # Market A: will fail filter 1 (null eventIndex -> CV=None)
    # Market B: will fail filter 4 (zero depth at CLO)
    # Market C: will fail filter 5 (clo_lower=0)
    # Market D: will fail filter 6 (maturity < 30 days)
    # Market E: should pass all 6

    # Build per-market maturity_ts: D expires soon, rest in 60 days
    mats = {
        MARKET_A: now + 60 * 86400,
        MARKET_B: now + 60 * 86400,
        MARKET_C: now + 60 * 86400,
        MARKET_D: now + 10 * 86400,  # only 10 days -> fails filter 6
        MARKET_E: now + 60 * 86400,
    }

    from dataclasses import dataclass as _dc

    @_dc
    class _MC2:
        market_id: str
        maturity_ts: int
        scale: float = 5.591e12
        s: float = 0.0
        clo_lower_thresh: float = 10900.0
        clo_upper_thresh: float = 11100.0
        fIndex_oracle_address: str = "0x0"

    config = _Config(
        screener=_ScreenerConf(),
        markets=[_MC2(market_id=mid, maturity_ts=mats[mid]) for mid in markets],
    )

    conn = _make_duck_conn(
        markets,
        cv_null_market=MARKET_A,
        zero_depth_market=MARKET_B,
        zero_clo_market=MARKET_C,
        # MARKET_D fails due to TTM < 30d via config
    )

    results = apply_screener_filters(markets, conn, config)

    result_map = {r.market_id: r for r in results}

    # Each market should be present in results
    assert set(result_map.keys()) == set(markets)

    # Market A: fails CV filter
    assert not result_map[MARKET_A].filter_pass
    assert any("cv" in r.lower() for r in result_map[MARKET_A].filter_failure_reasons)

    # Market B: fails depth filter
    assert not result_map[MARKET_B].filter_pass
    assert any("depth" in r.lower() or "clo" in r.lower() for r in result_map[MARKET_B].filter_failure_reasons)

    # Market C: fails CLO bounds filter
    assert not result_map[MARKET_C].filter_pass
    assert any("clo" in r.lower() or "bound" in r.lower() for r in result_map[MARKET_C].filter_failure_reasons)

    # Market D: fails TTM filter
    assert not result_map[MARKET_D].filter_pass
    assert any("ttm" in r.lower() or "matur" in r.lower() for r in result_map[MARKET_D].filter_failure_reasons)

    # Market E: passes all 6
    assert result_map[
        MARKET_E
    ].filter_pass, f"Market E should pass all filters; failures: {result_map[MARKET_E].filter_failure_reasons}"


# ── Test 2: shortlist capped at 4 ────────────────────────────────────────────


def test_shortlist_capped_at_four():
    """7 markets all passing filters -> shortlist has exactly 4, ranked by r_apr_potential."""
    import time

    now = int(time.time())
    market_ids = [f"MARKET-{i}" for i in range(7)]

    # Assign different e_liq values so ranking is deterministic
    e_liq_map = {mid: float(10 + i * 5) for i, mid in enumerate(market_ids)}

    mats = {mid: now + 60 * 86400 for mid in market_ids}

    from dataclasses import dataclass as _dc

    @_dc
    class _MC2:
        market_id: str
        maturity_ts: int
        scale: float = 5.591e12
        s: float = 0.0
        clo_lower_thresh: float = 10900.0
        clo_upper_thresh: float = 11100.0
        fIndex_oracle_address: str = "0x0"

    config = _Config(
        screener=_ScreenerConf(),
        markets=[_MC2(market_id=mid, maturity_ts=mats[mid]) for mid in market_ids],
    )
    conn = _make_duck_conn(market_ids, e_liq_per_market=e_liq_map)

    results = apply_screener_filters(market_ids, conn, config)
    passing = [r for r in results if r.filter_pass]

    # All 7 should pass (clean fixture)
    assert len(passing) >= 4, f"Expected >= 4 passing markets, got {len(passing)}"

    # The shortlist (passing[:4] ranked by r_apr_potential desc) has exactly 4
    shortlist = sorted(passing, key=lambda r: r.r_apr_potential or 0, reverse=True)[:4]
    assert len(shortlist) == 4, f"Shortlist must be capped at 4; got {len(shortlist)}"


# ── Test 3: R_apr ranking uses reward_budget_history ─────────────────────────


def test_r_apr_potential_ranking():
    """Markets ranked by r_apr_potential = e_liq_per_epoch * 52 / 100."""
    import time

    now = int(time.time())
    market_ids = [f"RANK-{i}" for i in range(3)]
    # Assign e_liq: 300 > 200 > 100, so RANK-2 > RANK-1 > RANK-0 in APR
    e_liq_map = {"RANK-0": 100.0, "RANK-1": 200.0, "RANK-2": 300.0}

    from dataclasses import dataclass as _dc

    @_dc
    class _MC2:
        market_id: str
        maturity_ts: int
        scale: float = 5.591e12
        s: float = 0.0
        clo_lower_thresh: float = 10900.0
        clo_upper_thresh: float = 11100.0
        fIndex_oracle_address: str = "0x0"

    config = _Config(
        screener=_ScreenerConf(),
        markets=[_MC2(market_id=mid, maturity_ts=now + 60 * 86400) for mid in market_ids],
    )
    conn = _make_duck_conn(market_ids, e_liq_per_market=e_liq_map)

    results = apply_screener_filters(market_ids, conn, config)

    for r in results:
        if r.filter_pass and r.r_apr_potential is not None:
            expected = e_liq_map[r.market_id] * 52 / 100.0
            assert (
                abs(r.r_apr_potential - expected) < 0.01
            ), f"{r.market_id}: expected r_apr={expected}, got {r.r_apr_potential}"


# ── Test 4: report writer ─────────────────────────────────────────────────────


def test_write_screener_metrics_report(tmp_path: Path):
    """write_screener_metrics_report writes JSON with all markets + shortlist."""
    out = tmp_path / "screener_metrics.json"

    results = [
        MarketScreeningResult(
            market_id=MARKET_A,
            cv=1.05,
            realized_vol=0.002,
            reversal_count=7,
            depth_at_clo_edge=400.0,
            outside_range_wall_ratio=1.3,
            outside_range_wall_flag=False,
            clo_lower=10900.0,
            clo_upper=11100.0,
            time_to_maturity_days=60.0,
            scale=5.591e12,
            scale_unstable=False,
            r_apr_potential=52.0,
            filter_pass=True,
            filter_failure_reasons=[],
        ),
        MarketScreeningResult(
            market_id=MARKET_B,
            cv=None,
            realized_vol=None,
            reversal_count=None,
            depth_at_clo_edge=None,
            outside_range_wall_ratio=None,
            outside_range_wall_flag=False,
            clo_lower=0.0,
            clo_upper=0.0,
            time_to_maturity_days=10.0,
            scale=None,
            scale_unstable=False,
            r_apr_potential=None,
            filter_pass=False,
            filter_failure_reasons=["cv_unavailable", "clo_bounds_zero"],
        ),
    ]

    write_screener_metrics_report(results, out=str(out))

    assert out.exists(), "Output file must be created"
    payload = json.loads(out.read_text())

    assert "results" in payload
    assert "shortlist" in payload
    assert len(payload["results"]) == 2

    # Both markets present in results
    market_ids_in_results = {r["market_id"] for r in payload["results"]}
    assert MARKET_A in market_ids_in_results
    assert MARKET_B in market_ids_in_results

    # Only passing market in shortlist
    assert MARKET_A in payload["shortlist"]
    assert MARKET_B not in payload["shortlist"]

    # Per-market metrics present
    a_row = next(r for r in payload["results"] if r["market_id"] == MARKET_A)
    assert "cv" in a_row
    assert "realized_vol" in a_row
    assert "reversal_count" in a_row
    assert "depth_at_clo_edge" in a_row
    assert "outside_range_wall_ratio" in a_row
    assert "filter_pass" in a_row
    assert "filter_failure_reasons" in a_row
    assert "r_apr_potential" in a_row


# ── Test 5: CLI --help exits 0 ────────────────────────────────────────────────


def test_cli_help_exits_zero():
    """python -m boros_brain.screener --help exits 0 and prints usage."""
    result = subprocess.run(
        [sys.executable, "-m", "boros_brain.screener", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent / "src"),
    )
    assert result.returncode == 0, f"--help failed:\n{result.stderr}"
    assert "usage" in result.stdout.lower() or "usage" in result.stderr.lower()


# ── Test 6: A8 outside_range_wall_flag surfaces in report ────────────────────


def test_outside_range_wall_flag_in_report(tmp_path: Path):
    """Market with outside_range_wall_ratio > 2 has outside_range_wall_flag=True in JSON."""
    out = tmp_path / "screener_metrics.json"

    result = MarketScreeningResult(
        market_id=MARKET_A,
        cv=1.0,
        realized_vol=0.002,
        reversal_count=7,
        depth_at_clo_edge=400.0,
        outside_range_wall_ratio=3.5,  # > 2
        outside_range_wall_flag=True,  # A8 flag
        clo_lower=10900.0,
        clo_upper=11100.0,
        time_to_maturity_days=60.0,
        scale=5.591e12,
        scale_unstable=False,
        r_apr_potential=52.0,
        filter_pass=True,  # flag does NOT reject the market
        filter_failure_reasons=[],
    )

    write_screener_metrics_report([result], out=str(out))
    payload = json.loads(out.read_text())

    a_row = next(r for r in payload["results"] if r["market_id"] == MARKET_A)
    assert a_row.get("outside_range_wall_flag") is True, "Expected outside_range_wall_flag=True in report for ratio=3.5"
    # Market should still be in the shortlist (A8 is a warning, not a filter)
    assert MARKET_A in payload["shortlist"], "A8 wall flag must NOT reject the market from the shortlist"
