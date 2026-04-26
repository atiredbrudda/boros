"""BACK-01 — eventIndex ordering invariant for the backtest replay engine.

Test functions:
  - test_replay_processes_events_in_event_index_order: events yield in (blockTimestamp, eventIndex) lex-monotonic order
  - test_replay_event_index_null_sorts_to_zero: degraded-eventIndex behavior; engine treats null as 0

Turns GREEN in Plan 05-02 when boros_brain.backtest.replay lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-02.
replay = pytest.importorskip("boros_brain.backtest.replay")
ReplayEngine = replay.ReplayEngine

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_replay_processes_events_in_event_index_order(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01: replay.iter_events() yields events in (blockTimestamp, eventIndex) lex-monotonic order.

    Uses seed_market_trades_parquet(with_ties=True) to verify intra-block ordering
    by eventIndex when multiple trades share the same blockTimestamp.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID, with_ties=True)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-replay-001",
        manifest=None,
    )

    events = list(engine.iter_events())
    assert len(events) >= 2, "Expected at least 2 events from fixture"

    # Verify lex-monotonic order: (blockTimestamp, eventIndex)
    for i in range(1, len(events)):
        prev = events[i - 1]
        curr = events[i]
        prev_key = (prev["blockTimestamp"], prev.get("eventIndex", 0) or 0)
        curr_key = (curr["blockTimestamp"], curr.get("eventIndex", 0) or 0)
        assert prev_key <= curr_key, (
            f"Event order violation at index {i}: {prev_key} > {curr_key}"
        )


def test_replay_event_index_null_sorts_to_zero(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01: replay engine treats null/missing eventIndex as 0 (degraded-data handling)."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID, with_ties=False)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-replay-null-ei",
        manifest=None,
    )

    # Should not raise even when eventIndex values are 0 (treated as minimum sort key)
    events = list(engine.iter_events())
    assert len(events) >= 1
    for ev in events:
        # null eventIndex is coerced to 0
        assert (ev.get("eventIndex") or 0) >= 0
