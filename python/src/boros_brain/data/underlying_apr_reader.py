"""DuckDB reader for underlying_apr parquet — SAFE-09 feed staleness support.

Provides read_underlying_apr_max_ts() which returns the maximum snapshot_ts
in the underlying_apr parquet partition for a given exchange/symbol pair.
Used by UnderlyingStaleBreaker to compare the latest snapshot age against
the per-exchange expected cadence.

STRIDE: T-04-05-04 — opens a fresh in-memory DuckDB conn per call (~1ms);
parquet glob is bounded to one exchange/symbol partition.

[[underlying-apr-cadence-by-exchange]]: cadence table by exchange
[[breaker-underlying-feed-stale]]: SAFE-09 spec, staleness threshold formula
"""
from __future__ import annotations

from pathlib import Path

__all__ = ["read_underlying_apr_max_ts"]


def read_underlying_apr_max_ts(parquet_root: Path, exchange: str, symbol: str) -> int | None:
    """Return MAX(snapshot_ts) from the underlying_apr parquet partition, or None.

    Parameters
    ----------
    parquet_root:
        Root of the partitioned parquet tree (e.g. data/parquet/).
        The function reads from:
          {parquet_root}/underlying_apr/exchange={exchange}/symbol={symbol}/*.parquet
    exchange:
        Exchange name (e.g. "binance", "hyperliquid"). Must match the
        Hive partition directory name after "exchange=".
    symbol:
        Symbol string (e.g. "ETHUSDT"). Must match "symbol=" partition.

    Returns
    -------
    int | None
        MAX(snapshot_ts) as an integer unix timestamp, or None if the partition
        directory does not exist or contains no rows with a non-null snapshot_ts.
    """
    import duckdb

    partition_path = parquet_root / "underlying_apr" / f"exchange={exchange}" / f"symbol={symbol}"
    if not partition_path.exists():
        return None

    glob = str(partition_path / "*.parquet")
    conn = duckdb.connect(":memory:")
    try:
        row = conn.execute(
            f"SELECT MAX(snapshot_ts) FROM read_parquet('{glob}')"
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()
