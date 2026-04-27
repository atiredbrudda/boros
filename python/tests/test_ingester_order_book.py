"""Tests for boros_brain.data.ingester.order_book — DATA-02 ingesters.

Real archive NDJSON shape: each line is one hourly snapshot containing two
arrays (long, short) of per-tick liquidity entries. The ingester explodes the
arrays into one parquet row per (snapshot_ts, side, tick).

Cases:
1. test_ingest_order_book_raw_happy_path
2. test_ingest_order_book_raw_preserves_negative_ticks
3. test_ingest_order_book_combined_happy_path
4. test_ingest_order_book_raw_returns_IngestResult
5. test_raw_and_combined_share_join_key
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from boros_brain.data.ingester.base import IngestResult
from boros_brain.data.ingester.order_book import ingest_order_book_combined, ingest_order_book_raw

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT_TS = "1754021093"  # as string — partition col stored as Utf8
# Fixture shapes: 2 hourly snapshots; first has 3 long+short tick entries (2 long + 1 short),
# second is empty (long=[], short=[]) — exercises the "empty arrays" guard.
EXPECTED_TICK_ROWS = 3


def test_ingest_order_book_raw_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_raw.ndjson"
    result = ingest_order_book_raw(fixture, market_id="ETH", out_root=tmp_path)
    # rows_in counts hourly snapshots in the NDJSON (2)
    assert result.rows_in == 2
    # rows_written counts exploded per-tick rows (3)
    assert result.rows_written == EXPECTED_TICK_ROWS
    # Hive partition path: order_book_raw/market_id=ETH/snapshot_ts=1754021093/
    part_dir = tmp_path / "order_book_raw" / "market_id=ETH" / f"snapshot_ts={SNAPSHOT_TS}"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(str(tmp_path / "order_book_raw") + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == EXPECTED_TICK_ROWS
    # sz_wei and sz_float must be present
    assert "sz_wei" in readback.columns
    assert "sz_float" in readback.columns
    # No NULL data after explode
    assert readback["sz_float"].null_count() == 0
    assert readback["tick"].null_count() == 0


def test_ingest_order_book_raw_preserves_negative_ticks(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_raw.ndjson"
    ingest_order_book_raw(fixture, market_id="ETH", out_root=tmp_path)
    readback = pl.scan_parquet(str(tmp_path / "order_book_raw") + "/**/*.parquet", hive_partitioning=True).collect()
    ticks = sorted(readback["tick"].to_list())
    assert -50 in ticks, f"Negative tick -50 missing from {ticks}"


def test_ingest_order_book_combined_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_combined.ndjson"
    result = ingest_order_book_combined(fixture, market_id="ETH", tick_size="0.01", out_root=tmp_path)
    assert result.rows_in == 2
    assert result.rows_written == EXPECTED_TICK_ROWS
    # Hive partition: order_book_combined/market_id=ETH/tick_size=0.01/snapshot_ts=1754021093/
    part_dir = tmp_path / "order_book_combined" / "market_id=ETH" / "tick_size=0.01" / f"snapshot_ts={SNAPSHOT_TS}"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(
        str(tmp_path / "order_book_combined") + "/**/*.parquet", hive_partitioning=True
    ).collect()
    assert readback.height == EXPECTED_TICK_ROWS
    assert readback["sz_combined_float"].null_count() == 0
    assert readback["tick"].null_count() == 0


def test_ingest_order_book_raw_returns_IngestResult(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_raw.ndjson"
    result = ingest_order_book_raw(fixture, market_id="ETH", out_root=tmp_path)
    assert isinstance(result, IngestResult)
    assert result.rows_in == 2
    assert result.rows_written == EXPECTED_TICK_ROWS


def test_raw_and_combined_share_join_key(tmp_path: Path) -> None:
    """After ingesting both fixtures for the same snapshot, joining on
    (snapshot_ts) produces a non-empty frame — confirms snapshot_ts alignment.

    Note: per-tick join is not used (raw is on a 1bp grid, combined is on the
    user-specified tick_size grid). The shared join key is `snapshot_ts`.
    """
    raw_fixture = FIXTURES / "sample_order_book_raw.ndjson"
    combined_fixture = FIXTURES / "sample_order_book_combined.ndjson"
    ingest_order_book_raw(raw_fixture, market_id="ETH", out_root=tmp_path)
    ingest_order_book_combined(combined_fixture, market_id="ETH", tick_size="0.01", out_root=tmp_path)

    raw_lf = pl.scan_parquet(str(tmp_path / "order_book_raw") + "/**/*.parquet", hive_partitioning=True)
    combined_lf = pl.scan_parquet(str(tmp_path / "order_book_combined") + "/**/*.parquet", hive_partitioning=True)
    # Join on snapshot_ts: every snapshot_ts in raw should be in combined and vice versa.
    raw_ts = set(raw_lf.select("snapshot_ts").unique().collect()["snapshot_ts"].to_list())
    combined_ts = set(combined_lf.select("snapshot_ts").unique().collect()["snapshot_ts"].to_list())
    assert raw_ts == combined_ts, f"snapshot_ts mismatch raw={raw_ts} combined={combined_ts}"
