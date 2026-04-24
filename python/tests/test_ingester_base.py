"""Tests for boros_brain.data.ingester.base — shared ingester primitives.

Cases:
1. test_ingest_result_dataclass_fields — frozen dataclass with expected fields
2. test_write_partitioned_parquet_basic — Hive partition write + readback
3. test_ingester_schema_violation_raises — exception propagates
4. test_partition_cols_never_include_raw_path — bogus col raises ValueError
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from boros_brain.data.ingester.base import (
    IngesterSchemaViolation,
    IngestResult,
    write_partitioned_parquet,
)


def test_ingest_result_dataclass_fields() -> None:
    r = IngestResult(rows_in=10, rows_written=9, path_out="some/path", eventIndex_missing=1, assertion_failures=0)
    assert r.rows_in == 10
    assert r.rows_written == 9
    assert r.path_out == "some/path"
    assert r.eventIndex_missing == 1
    assert r.assertion_failures == 0
    # frozen — must raise on mutation
    with pytest.raises((AttributeError, TypeError)):
        r.rows_in = 99  # type: ignore[misc]


def test_write_partitioned_parquet_basic(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {
            "market_id": ["ETH", "ETH"],
            "year_month": ["2025-08", "2025-08"],
            "value": [1.0, 2.0],
        }
    )
    out_path = write_partitioned_parquet(
        df,
        out_root=tmp_path,
        partition_cols=["market_id", "year_month"],
        subdir="market_trades",
    )
    # Partition directory structure must exist
    assert (out_path / "market_id=ETH" / "year_month=2025-08").exists()
    # Round-trip via scan_parquet with hive_partitioning=True
    readback = pl.scan_parquet(str(out_path) + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == 2
    assert set(readback["market_id"].to_list()) == {"ETH"}


def test_ingester_schema_violation_raises() -> None:
    exc = IngesterSchemaViolation("test message")
    with pytest.raises(IngesterSchemaViolation, match="test message"):
        raise exc


def test_partition_cols_never_include_raw_path(tmp_path: Path) -> None:
    """write_partitioned_parquet raises ValueError if a partition col is absent from df."""
    df = pl.DataFrame({"market_id": ["ETH"], "value": [1]})
    with pytest.raises(ValueError, match="partition_cols"):
        write_partitioned_parquet(
            df,
            out_root=tmp_path,
            partition_cols=["market_id", "nonexistent_col"],
            subdir="test",
        )
