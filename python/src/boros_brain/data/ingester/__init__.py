"""boros_brain.data.ingester — NDJSON → Hive-partitioned parquet ingester framework.

DATA-01: market_trades (preserves eventIndex, asserts presence, wei→float conversion)
DATA-02: order_book_raw + order_book_combined (join key = (snapshot_ts, tick))
DATA-03: underlying_apr (per-exchange funding rate histories)
DATA-04: settlement + market_data (separate parquet subdirs)
"""

from .base import IngesterSchemaViolation, IngestResult, write_partitioned_parquet
from .market_trades import ingest_market_trades

# Tasks 2 and 3 add these — imported after their modules exist
from .order_book import ingest_order_book_combined, ingest_order_book_raw
from .settlement_md import ingest_settlement_md
from .underlying_apr import ingest_underlying_apr

__all__ = [
    "IngestResult",
    "IngesterSchemaViolation",
    "write_partitioned_parquet",
    "ingest_market_trades",
    "ingest_order_book_raw",
    "ingest_order_book_combined",
    "ingest_underlying_apr",
    "ingest_settlement_md",
]
