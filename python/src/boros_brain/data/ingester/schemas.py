"""Polars schemas for all five NDJSON input shapes.

Sources:
- market_trades:   {eventIndex, blockTimestamp, datetime, rate, side, size, txHash}
                   per PROJECT.md L70 + LLM Wiki [[eventindex-coverage]] sample.
                   size may be wei-string OR JSON-number — both handled in ingester.
- order_book_raw:  hourly snapshot; {snapshot_ts, tick, t, sz} per-tick, size as wei string.
- order_book_combined_{tickSize}: book + AMM merged per tick.
- underlying_apr:  per-exchange funding rate history.
- settlement:      funding-rate settlement events.
- market_data:     on-chain event snapshots.

Note on `size` in market_trades:
  The LLM Wiki [[eventindex-coverage]] sample shows size as a JSON number (0.005).
  PROJECT.md L72 documents it as a wei string. In practice, polars `read_ndjson`
  will infer Utf8 for both if the schema declares `size: pl.Utf8` — float values
  get coerced to string representations, integer wei strings stay as strings.
  The ingester handles both via the _parse_size_column() fallback logic.
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

ORDER_BOOK_RAW_SCHEMA = pl.Schema(
    {
        "snapshot_ts": pl.UInt64,
        "tick": pl.Int64,
        "t": pl.Int64,  # tick value (signed; same as tick? — keep both if present)
        "sz": pl.Utf8,  # wei string
    }
)

ORDER_BOOK_COMBINED_SCHEMA = pl.Schema(
    {
        "snapshot_ts": pl.UInt64,
        "tick": pl.Int64,
        "sz_combined": pl.Utf8,  # wei string
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
