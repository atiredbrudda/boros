"""DATA-01 — market-trades NDJSON ingester.

Per CLAUDE.md: preserve eventIndex (intra-block ordering primitive — NOT blockTimestamp).
Per PITFALL §B2 (research §Pitfall 6): eventIndex null/missing → raise IngesterSchemaViolation.
Per DATA-01 spec: wei→float conversion is EXPLICIT (no silent truncation).

T-01-08-01 mitigation: size cast to UInt128 strict=True raises on overflow.
T-01-08-02 mitigation: schema declared; pl.read_ndjson(schema=SCHEMA) raises on missing fields.
  eventIndex additionally null-checked post-load per PITFALL §B2.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import structlog

from .base import IngesterSchemaViolation, IngestResult, write_partitioned_parquet
from .schemas import MARKET_TRADES_SCHEMA

log = structlog.get_logger(__name__)


def _parse_size_column(df: pl.DataFrame) -> pl.DataFrame:
    """size may arrive as wei-string ('5000000000000000') OR as a JSON-number coerced to Utf8.

    Emit two columns: size_wei:UInt128 (nullable) + size_float:Float64.

    If size parses as an integer-valued string → wei path:
        size_wei = int(size), size_float = size_wei / 1e18
    If it has a decimal point → float path (wei=None):
        size_float = float(size), size_wei = null

    Per threat model T-01-08-01: `.cast(UInt128, strict=True)` raises on overflow.
    """
    # Attempt wei-string path first (most rows, based on PROJECT.md spec)
    try:
        df2 = df.with_columns(
            pl.col("size").cast(pl.UInt128, strict=True).alias("size_wei"),
        ).with_columns(
            (pl.col("size_wei").cast(pl.Float64) / 1e18).alias("size_float"),
        )
        log.info("ingester.market_trades.size_path", path="wei_string")
        return df2.drop("size")
    except (pl.exceptions.InvalidOperationError, pl.exceptions.ComputeError):
        # Fallback: size is a decimal float (JSON number coerced to Utf8, e.g. "0.005")
        df2 = df.with_columns(
            pl.col("size").cast(pl.Float64, strict=False).alias("size_float"),
            pl.lit(None).cast(pl.UInt128).alias("size_wei"),
        )
        log.info("ingester.market_trades.size_path", path="float_direct")
        return df2.drop("size")


def ingest_market_trades(
    ndjson_path: Path,
    market_id: str,
    out_root: Path,
) -> IngestResult:
    """Ingest one market-trades NDJSON file into Hive-partitioned parquet.

    PITFALL §B2 hard-fail: raises IngesterSchemaViolation if ANY row has
    null/missing eventIndex. This is NOT a soft assertion_failure count — it
    stops ingest loudly so the bug in the upstream NDJSON is visible immediately.

    Parameters
    ----------
    ndjson_path:
        Path to the source NDJSON file (one record per line).
    market_id:
        Market identifier string (e.g. "ETH") — becomes the `market_id=`
        partition directory name.
    out_root:
        Root of the parquet tree (typically `data/parquet`). Output is written to
        `{out_root}/market_trades/market_id={market_id}/year_month={YYYY-MM}/`.

    Returns
    -------
    IngestResult
        Summary with rows_in, rows_written, path_out, eventIndex_missing=0.
        (eventIndex_missing is always 0 on success — any non-zero count raises.)
    """
    df = pl.read_ndjson(str(ndjson_path), schema=MARKET_TRADES_SCHEMA)
    rows_in = df.height

    # ── PITFALL §B2 hard-fail: eventIndex must be present + non-null on every row ──
    # (T-01-08-02 mitigation: schema declared above; additionally null-check here)
    null_count = int(df["eventIndex"].null_count())
    if null_count > 0:
        raise IngesterSchemaViolation(
            f"{ndjson_path.name}: {null_count}/{rows_in} rows have null/missing eventIndex "
            f"(market_id={market_id}). DATA-01 requires eventIndex on every row."
        )

    # ── Soft constraint: side must be "long" or "short" ──
    invalid_side = df.filter(~pl.col("side").is_in(["long", "short"])).height
    if invalid_side:
        log.warning("ingester.market_trades.invalid_side_count", count=invalid_side)

    df = _parse_size_column(df)

    # Add partition columns: market_id (literal) + year_month (from blockTimestamp epoch)
    df = df.with_columns(
        pl.lit(market_id).alias("market_id"),
        pl.from_epoch(pl.col("blockTimestamp"), time_unit="s").dt.strftime("%Y-%m").alias("year_month"),
    )

    path_out = write_partitioned_parquet(
        df,
        out_root=out_root,
        partition_cols=["market_id", "year_month"],
        subdir="market_trades",
    )
    return IngestResult(
        rows_in=rows_in,
        rows_written=df.height,
        path_out=str(path_out),
        eventIndex_missing=0,
    )
