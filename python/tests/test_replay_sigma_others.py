"""Phase 05.2 Wave 3: sigma_others parquet-read acceptance tests.

Tests Bug #3 fix: _read_sigma_others_from_parquet_at_ts replaces the silent
bare-except sigma_others=0 path that was in replay.py:489-500.

Tests:
1. test_sigma_others_reads_from_parquet_not_sqlite: populated parquet + empty competition_history
   → sigma_others > sigma_others_min_pendle (data flows from parquet, not SQLite).
2. test_replay_empty_pool_raises: no order_book_raw partition → EmptyCompetitionPoolError.
3. test_sigma_others_floor_applied_after_guard: sum in-range < floor → returns floor value.
4. test_sigma_others_matches_live_competition_tracker: identical parquet seed → same float.
5. test_sigma_others_matches_dapp_probe_pool_size: xfail(strict=False) Bug #6 falsifier.
6. test_replay_no_silent_zero_sigma: regression guard — grep replay.py for sigma_others=0 literal.

[[backtest-sigma-others-parquet-read-2026-04-30]]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import polars as pl
import pytest

from boros_brain.backtest.exceptions import EmptyCompetitionPoolError
from boros_brain.backtest.replay import ReplayEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MARKET_ID = "BINANCE-ETHUSDT-25SEP2026"
ARCHIVE_PREFIX_MARKET_ID = f"101-{MARKET_ID}"
# CLO bounds from plan context (binding market).
CLO_LOWER = 9300.0
CLO_UPPER = 9500.0
BASE_TS = 1_700_000_000


def _make_config(
    market_id: str = MARKET_ID,
    clo_lower: float = CLO_LOWER,
    clo_upper: float = CLO_UPPER,
    sigma_others_min_pendle: float = 1e-6,
) -> Any:
    """Build a MagicMock BotConfig sufficient for ReplayEngine tests."""
    cfg = MagicMock()
    market = MagicMock()
    market.market_id = market_id
    market.clo_lower_thresh = clo_lower
    market.clo_upper_thresh = clo_upper
    cfg.markets = [market]
    cfg.reward_share_model.sigma_others_min_pendle = sigma_others_min_pendle
    cfg.decision.decision_loop_interval_s = 1.0
    cfg.decision.cancel_cost_default_pendle = 0.001
    cfg.decision.p_purge_default = 0.01
    cfg.sizer.q_min_pendle = 0.001
    cfg.fill_model.covariate_whitelist = ["sigma_5min"]
    return cfg


def _make_engine(
    tmp_path: Path,
    *,
    market_id: str = MARKET_ID,
    sigma_others_min_pendle: float = 1e-6,
    sigma_others_multiplier: float = 1.0,
) -> ReplayEngine:
    """Build a minimal ReplayEngine pointing at tmp_path as parquet_root."""
    sqlite_path = tmp_path / "state.sqlite"
    return ReplayEngine(
        config=_make_config(
            market_id=market_id,
            sigma_others_min_pendle=sigma_others_min_pendle,
        ),
        market_id=market_id,
        side="long",
        parquet_root=tmp_path,
        sqlite_path=sqlite_path,
        cancel_latency_s=2.0,
        run_id="test_run",
        sigma_others_multiplier=sigma_others_multiplier,
    )


def _write_order_book_parquet(
    parquet_root: Path,
    market_id: str = ARCHIVE_PREFIX_MARKET_ID,
    *,
    snapshot_ts: int = BASE_TS,
    ticks_and_sizes: list[tuple[int, float]] | None = None,
) -> Path:
    """Write a minimal order_book_raw parquet partition."""
    if ticks_and_sizes is None:
        ticks_and_sizes = [
            (9300, 10.0),
            (9400, 20.0),
            (9500, 30.0),
        ]
    partition_dir = parquet_root / "order_book_raw" / f"market_id={market_id}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = partition_dir / "data.parquet"

    df = pl.DataFrame(
        {
            "snapshot_ts": [snapshot_ts] * len(ticks_and_sizes),
            "tick": [t for t, _ in ticks_and_sizes],
            "sz_float": [s for _, s in ticks_and_sizes],
            "market_id": [market_id] * len(ticks_and_sizes),
        }
    )
    df.write_parquet(parquet_path)
    return partition_dir


# ---------------------------------------------------------------------------
# Test 1: reads from parquet not SQLite
# ---------------------------------------------------------------------------


def test_sigma_others_reads_from_parquet_not_sqlite(tmp_path: Path) -> None:
    """Populated parquet + empty competition_history SQLite → sigma_others from parquet.

    The engine's _read_sigma_others_from_parquet_at_ts must return a value
    strictly above sigma_others_min_pendle (i.e. data came from parquet, not
    from a silent default).
    """
    _write_order_book_parquet(tmp_path)

    engine = _make_engine(tmp_path, sigma_others_min_pendle=1e-6)

    result = engine._read_sigma_others_from_parquet_at_ts(
        chain_ts=BASE_TS,
        q_me_pendle=0.0,
    )

    # sum of sizes at ticks 9300..9500 = 10 + 20 + 30 = 60 PENDLE-YU
    # sigma_others_raw = max(0, 60 - 0) * 1.0 = 60 >> 1e-6 floor
    assert result > 1e-6, f"Expected parquet-derived value >> floor; got {result}"
    assert abs(result - 60.0) < 1e-9, f"Expected 60.0 from sum, got {result}"


# ---------------------------------------------------------------------------
# Test 2: empty pool raises EmptyCompetitionPoolError
# ---------------------------------------------------------------------------


def test_replay_empty_pool_raises(tmp_path: Path) -> None:
    """No order_book_raw partition for the market → EmptyCompetitionPoolError raised."""
    # No parquet written — the order_book_raw dir simply does not exist.
    engine = _make_engine(tmp_path)

    with pytest.raises(EmptyCompetitionPoolError) as exc_info:
        engine._read_sigma_others_from_parquet_at_ts(
            chain_ts=BASE_TS,
            q_me_pendle=0.0,
        )

    err = exc_info.value
    assert MARKET_ID in str(err), f"market_id missing from error: {err}"
    assert str(BASE_TS) in str(err), f"chain_ts missing from error: {err}"
    assert err.market_id == MARKET_ID
    assert err.chain_ts == BASE_TS


# ---------------------------------------------------------------------------
# Test 3: floor applied after guard (not as substitute)
# ---------------------------------------------------------------------------


def test_sigma_others_floor_applied_after_guard(tmp_path: Path) -> None:
    """Sum in [clo_lower, clo_upper] < floor → returned value equals floor.

    The floor is active because read succeeded (not because pool was empty).
    """
    # Write parquet with sizes tiny enough that in-range sum < 0.001 floor.
    _write_order_book_parquet(
        tmp_path,
        ticks_and_sizes=[
            (9300, 0.0001),
            (9400, 0.00005),
            (9500, 0.00003),
        ],
    )

    floor_value = 0.001  # larger than the sum of ~0.00018
    engine = _make_engine(tmp_path, sigma_others_min_pendle=floor_value)

    result = engine._read_sigma_others_from_parquet_at_ts(
        chain_ts=BASE_TS,
        q_me_pendle=0.0,
    )

    assert result == pytest.approx(floor_value, rel=1e-9), (
        f"Expected floor={floor_value}, got {result}"
    )


# ---------------------------------------------------------------------------
# Test 4: matches live CompetitionTracker (same inputs → same float)
# ---------------------------------------------------------------------------


def test_sigma_others_matches_live_competition_tracker(tmp_path: Path) -> None:
    """Identical parquet seed → backtest helper and live tracker return same value.

    The live CompetitionTracker._read_sigma_others_from_parquet uses DuckDB
    with the WITH-latest-CTE. The backtest helper uses polars. Both must agree
    to rel=1e-6 for identical input.

    This test bypasses the live tracker's REST + SQLite clo_history path by
    computing the expected value directly from the parquet data, and verifies
    that our helper matches.
    """
    ticks_and_sizes = [
        (9300, 15.5),
        (9400, 24.75),
        (9500, 35.25),
        (9200, 100.0),   # outside CLO range — must be excluded
        (9600, 200.0),   # outside CLO range — must be excluded
    ]
    _write_order_book_parquet(tmp_path, ticks_and_sizes=ticks_and_sizes)

    q_me = 5.0
    engine = _make_engine(tmp_path)

    result = engine._read_sigma_others_from_parquet_at_ts(
        chain_ts=BASE_TS,
        q_me_pendle=q_me,
    )

    # Expected: sum of ticks in [9300, 9500] minus q_me
    in_range_sum = 15.5 + 24.75 + 35.25  # = 75.5
    expected = max(0.0, in_range_sum - q_me)  # = 70.5
    expected = max(expected, 1e-6)            # floor
    assert result == pytest.approx(expected, rel=1e-6), (
        f"Expected {expected}, got {result}"
    )


# ---------------------------------------------------------------------------
# Test 5: xfail Bug #6 probe — binding market empirical pool size
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Bug #6 hypothesis A — Pendle effective-pool weighting may differ from "
        "raw parquet sum. CONTEXT.md empirical long pool ~75 YU vs orderbook "
        "cumulative ~165 YU. xfail means both XFAIL and XPASS are acceptable."
    ),
)
def test_sigma_others_matches_dapp_probe_pool_size() -> None:
    """Bug #6 falsifier: binding market long pool ≈ 75 YU within rel=2.0.

    Loads REAL data/parquet/order_book_raw/market_id=*BINANCE-ETHUSDT-25SEP2026*/
    if present. Skips if absent. On binding market mid-window, the parquet-summed
    sigma should be approximately 75 YU (empirical effective pool from CONTEXT.md).

    If this test XFAILS: parquet sum differs from effective pool → Bug #6 is real.
    If this test XPASSES: parquet sum ≈ effective pool → parquet proxy is valid.

    strict=False: either outcome is tolerated. The test surfaces the data, not the verdict.
    """
    repo_root = Path(__file__).resolve().parents[2]
    raw_dir = repo_root / "data" / "parquet" / "order_book_raw"

    # Find any partition ending in BINANCE-ETHUSDT-25SEP2026.
    target_partitions = [
        d for d in raw_dir.iterdir()
        if d.is_dir() and d.name.endswith("BINANCE-ETHUSDT-25SEP2026")
    ] if raw_dir.exists() else []

    if not target_partitions:
        pytest.skip("Real order_book_raw parquet not present; skipping Bug #6 probe")

    # Load parquet and pick a mid-window timestamp.
    parquet_files = [str(p) for part in target_partitions for p in part.rglob("*.parquet")]
    if not parquet_files:
        pytest.skip("No parquet files in BINANCE-ETHUSDT-25SEP2026 partitions")

    df = pl.read_parquet(parquet_files)
    col_map = {}
    if "sz_float" in df.columns and "size" not in df.columns:
        col_map["sz_float"] = "size"
    elif "sz" in df.columns and "size" not in df.columns:
        col_map["sz"] = "size"
    if col_map:
        df = df.rename(col_map)
    if df["snapshot_ts"].dtype == pl.String:
        df = df.with_columns(pl.col("snapshot_ts").cast(pl.Int64))

    timestamps = df.select("snapshot_ts").unique().sort("snapshot_ts").to_series().to_list()
    if not timestamps:
        pytest.skip("No snapshots in parquet")

    # Mid-window timestamp.
    mid_ts = timestamps[len(timestamps) // 2]

    # Sum in-range at the latest snapshot <= mid_ts.
    snap_df = df.filter(pl.col("snapshot_ts") <= mid_ts)
    latest_ts = snap_df.select(pl.max("snapshot_ts")).item()
    in_range = snap_df.filter(
        (pl.col("snapshot_ts") == latest_ts)
        & (pl.col("tick") >= CLO_LOWER)
        & (pl.col("tick") <= CLO_UPPER)
    )
    sigma_raw = float(in_range.select(pl.sum("size")).item() or 0.0)

    # Bug #6 hypothesis A: should be ≈ 75 YU within rel=2.0 (i.e. in [25, 225]).
    EXPECTED_POOL = 75.0
    REL_TOLERANCE = 2.0
    assert abs(sigma_raw - EXPECTED_POOL) <= REL_TOLERANCE * EXPECTED_POOL, (
        f"Parquet sum={sigma_raw:.2f} YU at ts={mid_ts} deviates from "
        f"empirical pool={EXPECTED_POOL} by >{REL_TOLERANCE}× — "
        f"Bug #6 effective-pool weighting likely active"
    )


# ---------------------------------------------------------------------------
# Test 6: regression guard — no silent zero literal in replay.py
# ---------------------------------------------------------------------------


def test_replay_no_silent_zero_sigma() -> None:
    """Regression guard: grep replay.py for sigma_others=0 literal.

    Ensures the Bug #3 bare-except silent-zero path is not re-introduced.
    Also confirms EmptyCompetitionPoolError import is present.
    """
    repo_root = Path(__file__).resolve().parents[2]
    replay_path = repo_root / "python" / "src" / "boros_brain" / "backtest" / "replay.py"
    source = replay_path.read_text()

    # No literal silent-zero assignment in actual code (not comments).
    # Check each line: strip comment portion before checking for the assignment pattern.
    for lineno, line in enumerate(source.splitlines(), start=1):
        code_part = line.split("#")[0]  # remove inline comments
        if re.search(r"\bsigma_others\s*=\s*0(?:\.0)?\b", code_part):
            pytest.fail(
                f"Bug #3 regression: found `sigma_others = 0` or `sigma_others = 0.0` "
                f"in replay.py code (not a comment) at line {lineno}: {line.strip()!r}"
            )

    # The fix is present.
    assert "_read_sigma_others_from_parquet_at_ts" in source, (
        "Expected _read_sigma_others_from_parquet_at_ts to be defined in replay.py"
    )
    assert "EmptyCompetitionPoolError" in source, (
        "Expected EmptyCompetitionPoolError import in replay.py"
    )
