"""DATA-04 — settlement + market-data NDJSON ingester. Two shapes written to separate parquet subdirs."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .base import IngestResult, write_partitioned_parquet
from .schemas import MARKET_DATA_SCHEMA, SETTLEMENT_SCHEMA


def _ingest_settlement_one(path: Path, market_id: str, out_root: Path) -> IngestResult:
    df = pl.read_ndjson(str(path), schema=SETTLEMENT_SCHEMA)
    rows_in = df.height
    df = df.with_columns(
        pl.from_epoch(pl.col("blockTimestamp"), time_unit="s").dt.strftime("%Y-%m").alias("year_month"),
    )
    path_out = write_partitioned_parquet(
        df,
        out_root=out_root,
        partition_cols=["market_id", "year_month"],
        subdir="settlement",
    )
    return IngestResult(rows_in=rows_in, rows_written=df.height, path_out=str(path_out))


def _ingest_market_data_one(path: Path, market_id: str, out_root: Path) -> IngestResult:
    df = pl.read_ndjson(str(path), schema=MARKET_DATA_SCHEMA)
    rows_in = df.height
    df = df.with_columns(
        pl.from_epoch(pl.col("blockTimestamp"), time_unit="s").dt.strftime("%Y-%m").alias("year_month"),
    )
    path_out = write_partitioned_parquet(
        df,
        out_root=out_root,
        partition_cols=["market_id", "year_month"],
        subdir="market_data",
    )
    return IngestResult(rows_in=rows_in, rows_written=df.height, path_out=str(path_out))


def ingest_settlement_md(
    settlement_path: Path | None,
    market_data_path: Path | None,
    market_id: str,
    out_root: Path,
) -> dict[str, IngestResult]:
    """Ingest settlement + market-data NDJSON files into separate parquet subdirs.

    Both args may be None (skip that shape).
    Returns {'settlement': IngestResult, 'market_data': IngestResult}.
    """
    result: dict[str, IngestResult] = {}
    if settlement_path is not None:
        result["settlement"] = _ingest_settlement_one(settlement_path, market_id, out_root)
    if market_data_path is not None:
        result["market_data"] = _ingest_market_data_one(market_data_path, market_id, out_root)
    return result
