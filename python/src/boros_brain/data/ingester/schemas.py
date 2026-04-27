"""Polars schemas for all five NDJSON input shapes.

Sources:
- market_trades:   {eventIndex, blockTimestamp, datetime, rate, side, size, txHash}
                   per PROJECT.md L70 + LLM Wiki [[eventindex-coverage]] sample.
                   size may be wei-string OR JSON-number — both handled in ingester.
- order_book_raw:  hourly snapshot. Real archive shape (per [[boros-historical-data-archive-layout]]):
                   {blockNumber, blockTimestamp, dateTime, long: [{t, sz}], short: [{t, sz}], ammState}
                   where `t` is integer tick (1bp units) and `sz` is wei-string PT-YT size.
- order_book_combined_{tickSize}: book + AMM merged per tick. Real archive shape:
                   {timestamp, datetime, blockNumber, long: [{rate, size}], short: [{rate, size}]}
                   where `rate` is decimal APR (0.01 = 1%) and `size` is float PT-YT (NOT wei).
- underlying_apr:  per-exchange funding rate history.
- settlement:      funding-rate settlement events.
- market_data:     on-chain event snapshots.

Note on `size` in market_trades:
  The LLM Wiki [[eventindex-coverage]] sample shows size as a JSON number (0.005).
  PROJECT.md L72 documents it as a wei string. In practice, polars `read_ndjson`
  will infer Utf8 for both if the schema declares `size: pl.Utf8` — float values
  get coerced to string representations, integer wei strings stay as strings.
  The ingester handles both via the _parse_size_column() fallback logic.

Historical note on order-book schemas:
  Pre-2026-04-27 these schemas described a flat per-tick row shape that did NOT
  match the real archive output. The Wave-1 bulk ingest (Phase 5.1) silently
  produced parquet with all-NULL data columns because polars' `read_ndjson` with
  a schema declaring nonexistent top-level fields creates one row per JSON line
  with all-null values. Fixed alongside an explode-step in `order_book.py`.
  See debug session `.planning/debug/order-book-combined-null.md`.
"""

from __future__ import annotations

import polars as pl

MARKET_TRADES_SCHEMA = pl.Schema(
    {
        "eventIndex": pl.UInt64,
        "blockTimestamp": pl.UInt64,
        "datetime": pl.Utf8,  # ISO 8601 string; parsed post-load if needed
        "rate": pl.Float64,
        "side": pl.Utf8,  # "long" | "short"; constrained post-load
        "size": pl.Utf8,  # may be wei string OR a JSON number coerced by read_ndjson
        "txHash": pl.Utf8,
    }
)

# Real archive shape for order-book/{market}/raw/{YYYY-MM}.ndjson.
# Each NDJSON line is one hourly snapshot containing two arrays of per-tick liquidity.
ORDER_BOOK_RAW_SCHEMA = pl.Schema(
    {
        "blockNumber": pl.UInt64,
        "blockTimestamp": pl.UInt64,
        "dateTime": pl.Utf8,  # ISO 8601
        "long": pl.List(
            pl.Struct(
                {
                    "t": pl.Int64,  # signed tick (1bp units)
                    "sz": pl.Utf8,  # wei string
                }
            )
        ),
        "short": pl.List(
            pl.Struct(
                {
                    "t": pl.Int64,
                    "sz": pl.Utf8,
                }
            )
        ),
        # ammState may be null or an object; declare permissively as Utf8 so
        # polars JSON-encodes it. We do not parse it in DATA-02; downstream
        # AMM-state ingest is a separate task.
        "ammState": pl.Utf8,
    }
)

# Real archive shape for order-book/{market}/combined_{tickSize}/{YYYY-MM}.ndjson.
ORDER_BOOK_COMBINED_SCHEMA = pl.Schema(
    {
        "timestamp": pl.UInt64,
        "datetime": pl.Utf8,
        "blockNumber": pl.UInt64,
        "long": pl.List(
            pl.Struct(
                {
                    "rate": pl.Float64,  # decimal APR (0.01 = 1%)
                    "size": pl.Float64,  # PT-YT size (already a float, NOT wei)
                }
            )
        ),
        "short": pl.List(
            pl.Struct(
                {
                    "rate": pl.Float64,
                    "size": pl.Float64,
                }
            )
        ),
    }
)

UNDERLYING_APR_SCHEMA = pl.Schema(
    {
        "timestamp": pl.UInt64,
        "exchange": pl.Utf8,  # binance | okx | hyperliquid | bybit | lighter
        "symbol": pl.Utf8,
        "funding_rate_apr": pl.Float64,
    }
)

SETTLEMENT_SCHEMA = pl.Schema(
    {
        "blockTimestamp": pl.UInt64,
        "market_id": pl.Utf8,
        "rate": pl.Float64,
        "settlement_period_s": pl.UInt64,
        "txHash": pl.Utf8,
    }
)

MARKET_DATA_SCHEMA = pl.Schema(
    {
        "blockTimestamp": pl.UInt64,
        "eventType": pl.Utf8,
        "market_id": pl.Utf8,
        "payload_json": pl.Utf8,
    }
)
