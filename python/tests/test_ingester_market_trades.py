"""Tests for boros_brain.data.ingester.market_trades — DATA-01 ingester.

Cases:
1. test_ingest_market_trades_happy_path
2. test_ingest_market_trades_preserves_eventIndex
3. test_ingest_market_trades_wei_to_float_explicit
4. test_ingest_market_trades_fallback_size_float_from_number
5. test_ingest_market_trades_missing_eventIndex_raises
6. test_ingest_market_trades_null_eventIndex_raises
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from boros_brain.data.ingester.base import IngesterSchemaViolation
from boros_brain.data.ingester.market_trades import ingest_market_trades

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_market_trades_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_market_trades.ndjson"
    result = ingest_market_trades(fixture, market_id="ETH", out_root=tmp_path)
    assert result.rows_in == 3
    assert result.rows_written == 3
    assert result.eventIndex_missing == 0
    # Hive partition path must exist
    part_dir = tmp_path / "market_trades" / "market_id=ETH" / "year_month=2025-08"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    # Parquet files should be present
    parquet_files = list(part_dir.glob("*.parquet"))
    assert parquet_files, "No .parquet files written"
    # Read back
    readback = pl.scan_parquet(str(tmp_path / "market_trades") + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == 3


def test_ingest_market_trades_preserves_eventIndex(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_market_trades.ndjson"
    ingest_market_trades(fixture, market_id="ETH", out_root=tmp_path)
    readback = pl.scan_parquet(str(tmp_path / "market_trades") + "/**/*.parquet", hive_partitioning=True).collect()
    event_indices = sorted(readback["eventIndex"].to_list())
    assert event_indices == [363716829000015, 363716829000016, 363716829000017]


def test_ingest_market_trades_wei_to_float_explicit(tmp_path: Path) -> None:
    """Fixture row with size as wei string → size_wei + size_float both present."""
    # size="5000000000000000" is 5e15 wei = 0.005 ETH
    fixture = FIXTURES / "sample_market_trades.ndjson"
    ingest_market_trades(fixture, market_id="ETH", out_root=tmp_path)
    readback = pl.scan_parquet(str(tmp_path / "market_trades") + "/**/*.parquet", hive_partitioning=True).collect()
    # Row 0: size="5000000000000000"
    row = readback.filter(pl.col("eventIndex") == 363716829000015)
    assert row.height == 1
    # size_wei should be the integer value
    assert row["size_wei"][0] == 5_000_000_000_000_000
    # size_float should be 5e15 / 1e18 = 0.005
    assert abs(row["size_float"][0] - 0.005) < 1e-12


def test_ingest_market_trades_fallback_size_float_from_number(tmp_path: Path) -> None:
    """Fixture row with size as JSON number (not string) → float_direct branch."""
    # Per LLM Wiki [[eventIndex coverage]] sample: size is 0.005 (JSON number)
    record = {
        "eventIndex": 999000001,
        "blockTimestamp": 1754021093,
        "datetime": "2025-08-01T04:04:53.000Z",
        "rate": 0.07332,
        "side": "short",
        "size": 0.005,  # JSON number, not string
        "txHash": "0xaabbcc",
    }
    fixture = tmp_path / "float_size.ndjson"
    fixture.write_text(json.dumps(record) + "\n")
    result = ingest_market_trades(fixture, market_id="ETH", out_root=tmp_path / "out")
    assert result.rows_in == 1
    assert result.rows_written == 1
    readback = pl.scan_parquet(
        str(tmp_path / "out" / "market_trades") + "/**/*.parquet", hive_partitioning=True
    ).collect()
    assert readback.height == 1
    assert abs(readback["size_float"][0] - 0.005) < 1e-12
    # float-direct branch: size_wei may be None / null
    # (it's acceptable for size_wei to be null or the float cast as int)


def test_ingest_market_trades_missing_eventIndex_raises(tmp_path: Path) -> None:
    """Fixture with row missing eventIndex key → IngesterSchemaViolation (DATA-01 PITFALL §B2)."""
    record = {
        # eventIndex deliberately omitted
        "blockTimestamp": 1754021093,
        "datetime": "2025-08-01T04:04:53.000Z",
        "rate": 0.07332,
        "side": "short",
        "size": "5000000000000000",
        "txHash": "0xabcd",
    }
    fixture = tmp_path / "missing_ei.ndjson"
    fixture.write_text(json.dumps(record) + "\n")
    with pytest.raises(IngesterSchemaViolation, match="eventIndex"):
        ingest_market_trades(fixture, market_id="ETH", out_root=tmp_path / "out")


def test_ingest_market_trades_null_eventIndex_raises(tmp_path: Path) -> None:
    """Fixture with eventIndex=null → IngesterSchemaViolation."""
    record = {
        "eventIndex": None,
        "blockTimestamp": 1754021093,
        "datetime": "2025-08-01T04:04:53.000Z",
        "rate": 0.07332,
        "side": "short",
        "size": "5000000000000000",
        "txHash": "0xabcd",
    }
    fixture = tmp_path / "null_ei.ndjson"
    fixture.write_text(json.dumps(record) + "\n")
    with pytest.raises(IngesterSchemaViolation, match="eventIndex"):
        ingest_market_trades(fixture, market_id="ETH", out_root=tmp_path / "out")
