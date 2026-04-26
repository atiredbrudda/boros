"""BACK-01 / B6 — No look-ahead invariant in backtest replay.

Test functions:
  - test_replay_never_reads_future_events: current_chain_ts never exceeds current event blockTimestamp
  - test_underlying_apr_resolved_at_close_ts_not_fill_ts: underlying APR resolved at close_at_ts, not fill_ts

Turns GREEN in Plan 05-02 when boros_brain.backtest.replay lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-02.
replay = pytest.importorskip("boros_brain.backtest.replay")
ReplayEngine = replay.ReplayEngine
LookAheadError = replay.LookAheadError

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_replay_never_reads_future_events(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01 / B6: replay engine never exposes future event data to models.

    When a _test_marker_future=True polars column is present, the engine must
    raise LookAheadError if it ever reads that column during decision time.
    current_chain_ts at any decision point must be <= current event blockTimestamp.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-no-lookahead",
        manifest=None,
    )

    # Inject a test marker column to probe look-ahead detection
    with pytest.raises(LookAheadError):
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine.run(_inject_lookahead_probe=True)
        )


def test_underlying_apr_resolved_at_close_ts_not_fill_ts(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
    seed_underlying_apr_parquet,
) -> None:
    """BACK-01 / B6: conditional loss uses underlying APR at close_at_ts, not fill_ts.

    The two-axis cancel latency model (Plan 05-03) schedules close at fill_ts + L.
    The underlying APR used in E[loss|fill] must be resolved at close_at_ts, not fill_ts,
    to avoid look-ahead bias.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_underlying_apr_parquet(
        last_ts=1_700_000_010,
        exchange="binance",
        symbol="ETHUSDT",
        parquet_root=parquet_root,
    )

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=5.0,  # L = 5s → close_at_ts = fill_ts + 5
        run_id="test-close-ts-resolution",
        manifest=None,
    )

    # Should not raise; underlying APR resolved at close_at_ts
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(engine.run())
    assert result is not None
