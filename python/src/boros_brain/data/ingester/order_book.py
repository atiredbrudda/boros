"""DATA-02 — order-book ingester. Two shapes:
- raw: per-tick snapshot of the native Boros order book.
- combined_{tickSize}: book merged with AMM liquidity for a given tick size.

Real archive NDJSON shape (per [[boros-historical-data-archive-layout]]):
- raw: each line = one hourly snapshot
       {blockNumber, blockTimestamp, dateTime, long: [{t, sz}], short: [{t, sz}], ammState}
- combined: each line = one hourly snapshot
       {timestamp, datetime, blockNumber, long: [{rate, size}], short: [{rate, size}]}

The ingester explodes the long/short arrays into one row per (snapshot_ts, side, tick).
After ingest, the parquet schema is:

  raw      → (snapshot_ts: Utf8, side: Utf8, t: Int64, tick: Int64,
              sz_wei: UInt128, sz_float: Float64, market_id, ...)
  combined → (snapshot_ts: Utf8, side: Utf8, rate: Float64, tick: Int64,
              sz_combined_float: Float64, market_id, tick_size, ...)

Tick semantics:
  - raw `t` is in 1bp units (e.g. t=137 ≈ 1.37% APR). `tick` mirrors `t` for raw.
  - combined `rate` is decimal APR. We compute an integer `tick` on the combined
    grid (tick_size resolution) as `tick = round(rate / tick_size)`.

DATA-05 AMM conservation check:
`assert_amm_conservation(raw_df, combined_df)` raises `AMMConservationError` if
total combined liquidity per snapshot < total raw liquidity per snapshot
(the per-tick variant is not meaningful when raw and combined are on different
tick grids; the per-snapshot total is the actual conservation invariant — AMM
can only ADD liquidity, never remove it).
PITFALLS §B3: silently absorbing negative AMM share poisons every fill-probability
model downstream. The check runs BEFORE the parquet write (fail fast).
No try/except around it in the caller — let it propagate all the way to process exit.

Historical note: prior to 2026-04-27 the schemas described a flat per-tick row
shape that did not match the real archive output. The Wave-1 bulk ingest (Phase
5.1) produced parquet with all-NULL data columns. See debug session
.planning/debug/order-book-combined-null.md.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from .base import IngestResult, write_partitioned_parquet
from .exceptions import AMMConservationError
from .schemas import ORDER_BOOK_COMBINED_SCHEMA, ORDER_BOOK_RAW_SCHEMA

log = structlog.get_logger(__name__)


def _explode_raw(df: pl.DataFrame) -> pl.DataFrame:
    """Explode raw NDJSON snapshots into per-(snapshot, side, tick) rows.

    Input columns: blockNumber, blockTimestamp, dateTime, long, short, ammState
    Output columns: snapshot_ts (UInt64), blockNumber, side (Utf8), t (Int64),
                    sz (Utf8 wei), tick (Int64).
    Drops snapshots whose long+short arrays are both empty (no liquidity to record).
    """
    parts: list[pl.DataFrame] = []
    for side in ("long", "short"):
        side_df = (
            df.select(
                pl.col("blockTimestamp").alias("snapshot_ts"),
                pl.col("blockNumber"),
                pl.col(side).alias("entries"),
            )
            .with_columns(pl.lit(side).alias("side"))
            .filter(pl.col("entries").list.len() > 0)
            .explode("entries")
            .with_columns(
                pl.col("entries").struct.field("t").alias("t"),
                pl.col("entries").struct.field("sz").alias("sz"),
            )
            .drop("entries")
        )
        parts.append(side_df)
    if not parts or all(p.height == 0 for p in parts):
        # Return empty frame with the expected columns so downstream code is uniform
        return pl.DataFrame(
            schema={
                "snapshot_ts": pl.UInt64,
                "blockNumber": pl.UInt64,
                "side": pl.Utf8,
                "t": pl.Int64,
                "sz": pl.Utf8,
                "tick": pl.Int64,
            }
        )
    out = pl.concat([p for p in parts if p.height > 0], how="vertical_relaxed")
    # `tick` mirrors `t` for raw (raw is 1bp-tick native).
    out = out.with_columns(pl.col("t").alias("tick"))
    return out


def _explode_combined(df: pl.DataFrame, tick_size: float) -> pl.DataFrame:
    """Explode combined NDJSON snapshots into per-(snapshot, side, rate) rows.

    Input columns: timestamp, datetime, blockNumber, long, short
    Output columns: snapshot_ts (UInt64), blockNumber, side (Utf8), rate (Float64),
                    size (Float64), tick (Int64 — rate/tick_size rounded).
    """
    parts: list[pl.DataFrame] = []
    for side in ("long", "short"):
        side_df = (
            df.select(
                pl.col("timestamp").alias("snapshot_ts"),
                pl.col("blockNumber"),
                pl.col(side).alias("entries"),
            )
            .with_columns(pl.lit(side).alias("side"))
            .filter(pl.col("entries").list.len() > 0)
            .explode("entries")
            .with_columns(
                pl.col("entries").struct.field("rate").alias("rate"),
                pl.col("entries").struct.field("size").alias("size"),
            )
            .drop("entries")
        )
        parts.append(side_df)
    if not parts or all(p.height == 0 for p in parts):
        return pl.DataFrame(
            schema={
                "snapshot_ts": pl.UInt64,
                "blockNumber": pl.UInt64,
                "side": pl.Utf8,
                "rate": pl.Float64,
                "size": pl.Float64,
                "tick": pl.Int64,
            }
        )
    out = pl.concat([p for p in parts if p.height > 0], how="vertical_relaxed")
    # tick = round(rate / tick_size) — integer index on the tick-size grid.
    out = out.with_columns(((pl.col("rate") / tick_size).round(0).cast(pl.Int64)).alias("tick"))
    return out


def assert_amm_conservation(raw: pl.DataFrame, combined: pl.DataFrame) -> None:
    """DATA-05: per-snapshot total combined liquidity ≥ total raw liquidity.

    Formula: SUM(combined_size) >= SUM(raw_size) per snapshot_ts.
    Violation => raise AMMConservationError.

    Per-tick comparison is not used here because raw is on a 1bp tick grid and
    combined is on the user-specified tick_size grid; the per-snapshot total
    invariant is the actual physical constraint (AMM can only ADD liquidity to
    the raw book, never remove it).

    PITFALLS §B3: negative AMM share poisons every fill-probability model
    downstream. This MUST NOT be caught and skipped — let it propagate to a
    non-zero process exit.

    Parameters
    ----------
    raw:
        DataFrame from `_explode_raw` — must have columns [snapshot_ts, sz_float].
    combined:
        DataFrame from `_explode_combined` — must have columns
        [snapshot_ts, sz_combined_float].
    """
    if raw.height == 0 or combined.height == 0:
        return  # nothing to check

    raw_tot = raw.group_by("snapshot_ts").agg(pl.col("sz_float").sum().alias("raw_total"))
    combined_tot = combined.group_by("snapshot_ts").agg(pl.col("sz_combined_float").sum().alias("combined_total"))

    joined = raw_tot.join(combined_tot, on="snapshot_ts", how="full", coalesce=True)
    joined = joined.with_columns(
        pl.col("raw_total").fill_null(0.0),
        pl.col("combined_total").fill_null(0.0),
    )
    # Allow a small relative tolerance (1% of raw or 1e-9 absolute) for floating
    # rounding in the combined-side bucketing performed by the upstream archive.
    neg = joined.filter((pl.col("combined_total") - pl.col("raw_total")) < -((pl.col("raw_total").abs() * 0.01) + 1e-9))
    if neg.height > 0:
        raise AMMConservationError(
            f"AMM conservation violated on {neg.height} snapshots; first 5: {neg.head(5).to_dicts()}"
        )


def _wei_str_to_float(df: pl.DataFrame, col: str, out_wei: str, out_float: str) -> pl.DataFrame:
    """Convert wei-string column to UInt128 + Float64 derived. strict=False to
    tolerate occasional malformed entries (logged as nulls)."""
    return (
        df.with_columns(pl.col(col).cast(pl.UInt128, strict=False).alias(out_wei))
        .with_columns((pl.col(out_wei).cast(pl.Float64) / 1e18).alias(out_float))
        .drop(col)
    )


def ingest_order_book_raw(
    ndjson_path: Path,
    market_id: str,
    out_root: Path,
) -> IngestResult:
    """Ingest a single hourly raw snapshot NDJSON.

    Writes to: {out_root}/order_book_raw/market_id={market_id}/snapshot_ts={ts}/
    Join key with combined: (market_id, snapshot_ts).
    """
    snapshots = pl.read_ndjson(str(ndjson_path), schema=ORDER_BOOK_RAW_SCHEMA)
    rows_in = snapshots.height

    df = _explode_raw(snapshots)
    df = _wei_str_to_float(df, "sz", "sz_wei", "sz_float")
    df = df.with_columns(pl.lit(market_id).alias("market_id"))

    # snapshot_ts must be a string for Hive partition directory names
    df = (
        df.with_columns(pl.col("snapshot_ts").cast(pl.Utf8).alias("snapshot_ts_str"))
        .drop("snapshot_ts")
        .rename({"snapshot_ts_str": "snapshot_ts"})
    )

    if df.height == 0:
        log.warning(
            "ingester.order_book_raw.empty_after_explode",
            ndjson_path=str(ndjson_path),
            market_id=market_id,
            rows_in=rows_in,
        )
        return IngestResult(rows_in=rows_in, rows_written=0, path_out="")

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
    snapshots = pl.read_ndjson(str(ndjson_path), schema=ORDER_BOOK_COMBINED_SCHEMA)
    rows_in = snapshots.height

    tick_size_f = float(tick_size)
    df = _explode_combined(snapshots, tick_size_f)
    df = df.rename({"size": "sz_combined_float"})
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
        raw_snap = pl.read_ndjson(str(raw_ndjson_path), schema=ORDER_BOOK_RAW_SCHEMA)
        raw_df = _explode_raw(raw_snap)
        raw_df = _wei_str_to_float(raw_df, "sz", "sz_wei", "sz_float")
        raw_df = (
            raw_df.with_columns(pl.col("snapshot_ts").cast(pl.Utf8).alias("snapshot_ts_str"))
            .drop("snapshot_ts")
            .rename({"snapshot_ts_str": "snapshot_ts"})
        )
        assert_amm_conservation(raw_df, df)

    if df.height == 0:
        log.warning(
            "ingester.order_book_combined.empty_after_explode",
            ndjson_path=str(ndjson_path),
            market_id=market_id,
            rows_in=rows_in,
        )
        return IngestResult(rows_in=rows_in, rows_written=0, path_out="")

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
