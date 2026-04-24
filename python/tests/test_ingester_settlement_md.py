"""Tests for boros_brain.data.ingester.settlement_md — DATA-04 ingester.

Cases:
1. test_ingest_settlement_happy_path
2. test_ingest_market_data_happy_path
3. test_ingest_settlement_md_dispatches_both
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from boros_brain.data.ingester.base import IngestResult
from boros_brain.data.ingester.settlement_md import ingest_settlement_md

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_settlement_happy_path(tmp_path: Path) -> None:
    fixture = FIXTURES / "sample_settlement.ndjson"
    result = ingest_settlement_md(fixture, None, market_id="ETH", out_root=tmp_path)
    assert "settlement" in result
    assert result["settlement"].rows_in == 2
    assert result["settlement"].rows_written == 2
    part_dir = tmp_path / "settlement" / "market_id=ETH" / "year_month=2025-08"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(str(tmp_path / "settlement") + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == 2


def test_ingest_market_data_happy_path(tmp_path: Path) -> None:
    md_fixture = FIXTURES / "sample_market_data.ndjson"
    result = ingest_settlement_md(None, md_fixture, market_id="ETH", out_root=tmp_path)
    assert "market_data" in result
    assert result["market_data"].rows_in == 2
    assert result["market_data"].rows_written == 2
    part_dir = tmp_path / "market_data" / "market_id=ETH" / "year_month=2025-08"
    assert part_dir.exists(), f"Expected partition dir: {part_dir}"
    readback = pl.scan_parquet(str(tmp_path / "market_data") + "/**/*.parquet", hive_partitioning=True).collect()
    assert readback.height == 2


def test_ingest_settlement_md_dispatches_both(tmp_path: Path) -> None:
    """ingest_settlement_md with both paths → dict with both IngestResults."""
    sett_fixture = FIXTURES / "sample_settlement.ndjson"
    md_fixture = FIXTURES / "sample_market_data.ndjson"
    result = ingest_settlement_md(sett_fixture, md_fixture, market_id="ETH", out_root=tmp_path)
    assert set(result.keys()) == {"settlement", "market_data"}
    assert isinstance(result["settlement"], IngestResult)
    assert isinstance(result["market_data"], IngestResult)
    assert result["settlement"].rows_in == 2
    assert result["market_data"].rows_in == 2
