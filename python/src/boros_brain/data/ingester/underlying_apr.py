"""DATA-03 — underlying APR (CEX funding rate) ingester."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from .base import IngestResult, write_partitioned_parquet
from .schemas import UNDERLYING_APR_SCHEMA


def ingest_underlying_apr(
    ndjson_path: Path,
    exchange: str,
    out_root: Path,
) -> IngestResult:
    """Ingest per-exchange funding rate NDJSON into Hive-partitioned parquet.

    Writes to: {out_root}/underlying_apr/exchange={exchange}/year_month={YYYY-MM}/
    """
    df = pl.read_ndjson(str(ndjson_path), schema=UNDERLYING_APR_SCHEMA)
    rows_in = df.height
    df = df.with_columns(
        pl.lit(exchange).alias("exchange"),
        pl.from_epoch(pl.col("timestamp"), time_unit="s").dt.strftime("%Y-%m").alias("year_month"),
    )
    path_out = write_partitioned_parquet(
        df,
        out_root=out_root,
        partition_cols=["exchange", "year_month"],
        subdir="underlying_apr",
    )
    return IngestResult(
        rows_in=rows_in,
        rows_written=df.height,
        path_out=str(path_out),
    )
