"""DATA-02 — order-book ingester. Two shapes:
- raw: per-tick snapshot of the native Boros order book.
- combined_{tickSize}: book merged with AMM liquidity for a given tick size.

The two shapes share (snapshot_ts, tick) as the join key so DATA-05 AMM conservation
(Wave 2) can compute combined - raw >= 0 per tick.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from .base import IngestResult, write_partitioned_parquet
from .schemas import ORDER_BOOK_COMBINED_SCHEMA, ORDER_BOOK_RAW_SCHEMA

log = structlog.get_logger(__name__)


def _parse_wei_size(df: pl.DataFrame, col: str, out_wei: str, out_float: str) -> pl.DataFrame:
    """Convert wei-string column to UInt128 + Float64 derived.

    T-01-08-01 mitigation: strict=False here because order_book sizes may occasionally
    be 0 or represented differently; use strict=False but log any nulls produced.
    """
    df2 = (
        df.with_columns(
            pl.col(col).cast(pl.UInt128, strict=False).alias(out_wei),
        )
        .with_columns(
            (pl.col(out_wei).cast(pl.Float64) / 1e18).alias(out_float),
        )
        .drop(col)
    )
    return df2


def ingest_order_book_raw(
    ndjson_path: Path,
    market_id: str,
    out_root: Path,
) -> IngestResult:
    """Ingest a single hourly raw snapshot NDJSON.

    Writes to: {out_root}/order_book_raw/market_id={market_id}/snapshot_ts={ts}/
    Join key with combined: (market_id, snapshot_ts, tick).
    """
    df = pl.read_ndjson(str(ndjson_path), schema=ORDER_BOOK_RAW_SCHEMA)
    rows_in = df.height

    df = _parse_wei_size(df, "sz", "sz_wei", "sz_float")
    df = df.with_columns(pl.lit(market_id).alias("market_id"))

    # snapshot_ts must be a string for Hive partition directory names
    df = (
        df.with_columns(pl.col("snapshot_ts").cast(pl.Utf8).alias("snapshot_ts_str"))
        .drop("snapshot_ts")
        .rename({"snapshot_ts_str": "snapshot_ts"})
    )

    path_out = write_partitioned_parquet(
        df,
        out_root=out_root,
        partition_cols=["market_id", "snapshot_ts"],
        subdir="order_book_raw",
    )
    return IngestResult(
        rows_in=rows_in,
        rows_written=df.height,
        path_out=str(path_out),
    )


def ingest_order_book_combined(
    ndjson_path: Path,
    market_id: str,
    tick_size: str,
    out_root: Path,
) -> IngestResult:
    """Ingest a single combined-book snapshot NDJSON for a given tick_size (e.g., '0.01').

    Writes to: {out_root}/order_book_combined/market_id={market_id}/tick_size={tick_size}/snapshot_ts={ts}/
    """
    df = pl.read_ndjson(str(ndjson_path), schema=ORDER_BOOK_COMBINED_SCHEMA)
    rows_in = df.height

    df = _parse_wei_size(df, "sz_combined", "sz_combined_wei", "sz_combined_float")
    df = df.with_columns(
        pl.lit(market_id).alias("market_id"),
        pl.lit(tick_size).alias("tick_size"),
    )
    # snapshot_ts as string partition col
    df = (
        df.with_columns(pl.col("snapshot_ts").cast(pl.Utf8).alias("snapshot_ts_str"))
        .drop("snapshot_ts")
        .rename({"snapshot_ts_str": "snapshot_ts"})
    )

    path_out = write_partitioned_parquet(
        df,
        out_root=out_root,
        partition_cols=["market_id", "tick_size", "snapshot_ts"],
        subdir="order_book_combined",
    )
    return IngestResult(
        rows_in=rows_in,
        rows_written=df.height,
        path_out=str(path_out),
    )
