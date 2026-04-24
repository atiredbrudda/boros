"""Tests for boros_brain.data.ingester.order_book — DATA-02 ingesters.

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


def test_ingest_order_book_raw_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_raw.ndjson"
    result = ingest_order_book_raw(fixture, market_id="ETH", out_root=tmp_path)
    assert result.rows_in == 3
    assert result.rows_written == 3
    # Hive partition path: order_book_raw/market_id=ETH/snapshot_ts=1754021093/
    part_dir = tmp_path / "order_book_raw" / "market_id=ETH" / f"snapshot_ts={SNAPSHOT_TS}"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(str(tmp_path / "order_book_raw") + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == 3
    # sz_wei and sz_float must be present
    assert "sz_wei" in readback.columns
    assert "sz_float" in readback.columns


def test_ingest_order_book_raw_preserves_negative_ticks(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_raw.ndjson"
    ingest_order_book_raw(fixture, market_id="ETH", out_root=tmp_path)
    readback = pl.scan_parquet(str(tmp_path / "order_book_raw") + "/**/*.parquet", hive_partitioning=True).collect()
    ticks = sorted(readback["tick"].to_list())
    assert -50 in ticks, f"Negative tick -50 missing from {ticks}"


def test_ingest_order_book_combined_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_combined.ndjson"
    result = ingest_order_book_combined(fixture, market_id="ETH", tick_size="0.01", out_root=tmp_path)
    assert result.rows_in == 3
    assert result.rows_written == 3
    # Hive partition: order_book_combined/market_id=ETH/tick_size=0.01/snapshot_ts=1754021093/
    part_dir = tmp_path / "order_book_combined" / "market_id=ETH" / "tick_size=0.01" / f"snapshot_ts={SNAPSHOT_TS}"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(
        str(tmp_path / "order_book_combined") + "/**/*.parquet", hive_partitioning=True
    ).collect()
    assert readback.height == 3


def test_ingest_order_book_raw_returns_IngestResult(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_order_book_raw.ndjson"
    result = ingest_order_book_raw(fixture, market_id="ETH", out_root=tmp_path)
    assert isinstance(result, IngestResult)
    assert result.rows_in == result.rows_written == 3


def test_raw_and_combined_share_join_key(tmp_path: Path) -> None:
    """After ingesting both fixtures for the same snapshot, inner-join on
    (snapshot_ts, tick) produces a non-empty frame — confirms DATA-05 join-compatibility.

    Note: snapshot_ts is stored as Utf8 in both parquet trees (partition col).
    The join is on the string representation, which is consistent across both sides.
    """
    raw_fixture = FIXTURES / "sample_order_book_raw.ndjson"
    combined_fixture = FIXTURES / "sample_order_book_combined.ndjson"
    ingest_order_book_raw(raw_fixture, market_id="ETH", out_root=tmp_path)
    ingest_order_book_combined(combined_fixture, market_id="ETH", tick_size="0.01", out_root=tmp_path)

    raw_lf = pl.scan_parquet(str(tmp_path / "order_book_raw") + "/**/*.parquet", hive_partitioning=True)
    combined_lf = pl.scan_parquet(str(tmp_path / "order_book_combined") + "/**/*.parquet", hive_partitioning=True)
    joined = raw_lf.join(combined_lf, on=["snapshot_ts", "tick"], how="inner").collect()
    assert joined.height > 0, "Join of raw and combined on (snapshot_ts, tick) produced no rows"
    # All 3 ticks should be present in the join (100, -50, 200)
    assert joined.height == 3
