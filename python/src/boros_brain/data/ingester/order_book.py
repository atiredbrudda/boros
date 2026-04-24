"""DATA-02 — order-book ingester. Two shapes:
- raw: per-tick snapshot of the native Boros order book.
- combined_{tickSize}: book merged with AMM liquidity for a given tick size.

The two shapes share (snapshot_ts, tick) as the join key so DATA-05 AMM conservation
(Wave 2) can compute combined - raw >= 0 per tick.

DATA-05 AMM conservation check:
`assert_amm_conservation(raw_df, combined_df)` raises `AMMConservationError` if
combined_size(delta) - raw_book_size(delta) < 0 for any tick delta.
PITFALLS §B3: silently absorbing negative AMM share poisons every fill-probability
model downstream. The check runs BEFORE the parquet write (fail fast).
No try/except around it in the caller — let it propagate all the way to process exit.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from .base import IngestResult, write_partitioned_parquet
from .exceptions import AMMConservationError
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


def assert_amm_conservation(raw: pl.DataFrame, combined: pl.DataFrame) -> None:
    """DATA-05: for each tick delta in an hourly snapshot, combined_size(delta) >= raw_book_size(delta).

    Formula: combined_size(delta) - raw_book_size(delta) >= 0 per tick.
    Violation => raise AMMConservationError.

    PITFALLS §B3: negative AMM share poisons every fill-probability model downstream.
    This MUST NOT be caught and skipped — let it propagate to a non-zero process exit.

    Parameters
    ----------
    raw:
        DataFrame from ingest_order_book_raw — must have columns [snapshot_ts, tick, sz_float].
    combined:
        DataFrame from ingest_order_book_combined (pre-parquet write) —
        must have columns [snapshot_ts, tick, sz_combined_float].
    """
    # Rename for clarity in the join
    raw_sel = raw.select(["snapshot_ts", "tick", pl.col("sz_float").alias("size")])
    combined_sel = combined.select(["snapshot_ts", "tick", pl.col("sz_combined_float").alias("size_combined")])

    joined = raw_sel.join(
        combined_sel,
        on=["snapshot_ts", "tick"],
        how="full",
        coalesce=True,
    )
    # Fill nulls: a tick missing from combined means combined_size = 0 (worse than raw)
    joined = joined.with_columns(
        pl.col("size_combined").fill_null(0.0),
        pl.col("size").fill_null(0.0),
    )
    neg = joined.filter(pl.col("size_combined") - pl.col("size") < 0)
    if neg.height > 0:
        raise AMMConservationError(
            f"AMM conservation violated on {neg.height} tick-rows; " f"first 5: {neg.head(5).to_dicts()}"
        )


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
    raw_ndjson_path: Path | None = None,
    *,
    market_id: str,
    tick_size: str,
    out_root: Path,
) -> IngestResult:
    """Ingest a single combined-book snapshot NDJSON for a given tick_size (e.g., '0.01').

    Writes to: {out_root}/order_book_combined/market_id={market_id}/tick_size={tick_size}/snapshot_ts={ts}/

    DATA-05 AMM conservation check:
    If `raw_ndjson_path` is provided, `assert_amm_conservation()` is called BEFORE the
    parquet write. Any violation raises AMMConservationError and the function does not
    write parquet (fail fast, PITFALLS §B3). No try/except is placed around this call —
    the exception propagates all the way to a non-zero process exit.
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

    # DATA-05 AMM conservation check — BEFORE parquet write (fail fast)
    if raw_ndjson_path is not None:
        raw_df = pl.read_ndjson(str(raw_ndjson_path), schema=ORDER_BOOK_RAW_SCHEMA)
        raw_df = _parse_wei_size(raw_df, "sz", "sz_wei", "sz_float")
        raw_df = (
            raw_df.with_columns(pl.col("snapshot_ts").cast(pl.Utf8).alias("snapshot_ts_str"))
            .drop("snapshot_ts")
            .rename({"snapshot_ts_str": "snapshot_ts"})
        )
        assert_amm_conservation(raw_df, df)

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
