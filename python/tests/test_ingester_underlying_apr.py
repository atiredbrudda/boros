"""Tests for boros_brain.data.ingester.underlying_apr — DATA-03 ingester.

Cases:
1. test_ingest_underlying_apr_happy_path
2. test_ingest_underlying_apr_multi_month_partitions
3. test_ingest_underlying_apr_return_value
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from boros_brain.data.ingester.base import IngestResult
from boros_brain.data.ingester.underlying_apr import ingest_underlying_apr

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_underlying_apr_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_underlying_apr.ndjson"
    result = ingest_underlying_apr(fixture, exchange="binance", out_root=tmp_path)
    assert result.rows_in == 3
    assert result.rows_written == 3
    # At least one partition under exchange=binance/year_month=2025-08
    part_dir = tmp_path / "underlying_apr" / "exchange=binance" / "year_month=2025-08"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(str(tmp_path / "underlying_apr") + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == 3


def test_ingest_underlying_apr_multi_month_partitions(tmp_path: Path) -> None:
    """Fixture rows span 2025-08 AND 2025-09 — two partition dirs must be created."""
    # Timestamps:
    #   1754021093 → 2025-08 (row 1)
    #   1754107493 → 2025-08 (row 2)
    #   1756699493 → 2025-09 (row 3)
    fixture = FIXTURES / "sample_underlying_apr.ndjson"
    ingest_underlying_apr(fixture, exchange="binance", out_root=tmp_path)
    base = tmp_path / "underlying_apr" / "exchange=binance"
    aug_dir = base / "year_month=2025-08"
    sep_dir = base / "year_month=2025-09"
    assert aug_dir.exists(), f"Missing 2025-08 partition: {aug_dir}"
    assert sep_dir.exists(), f"Missing 2025-09 partition: {sep_dir}"
    # Aug partition: 2 rows; Sep partition: 1 row
    aug_df = pl.scan_parquet(str(aug_dir) + "/*.parquet").collect()
    sep_df = pl.scan_parquet(str(sep_dir) + "/*.parquet").collect()
    assert aug_df.height == 2
    assert sep_df.height == 1


def test_ingest_underlying_apr_return_value(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_underlying_apr.ndjson"
    result = ingest_underlying_apr(fixture, exchange="binance", out_root=tmp_path)
    assert isinstance(result, IngestResult)
    assert result.rows_in == result.rows_written
