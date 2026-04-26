"""BACK-01 — eventIndex ordering invariant for the backtest replay engine.

Test functions:
  - test_replay_processes_events_in_event_index_order: events yield in (blockTimestamp, eventIndex) lex-monotonic order
  - test_replay_event_index_null_sorts_to_zero: degraded-eventIndex behavior; engine treats null as 0

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_replay_processes_events_in_event_index_order(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """BACK-01: replay.iter_events() yields events in (blockTimestamp, eventIndex) lex-monotonic order.

    Uses seed_market_trades_parquet(with_ties=True) to verify intra-block ordering
    by eventIndex when multiple trades share the same blockTimestamp.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID, with_ties=True)
    sqlite_path = seed_market_reward_calibration([{
        "market_id": MARKET_ID,
        "e_liq_per_epoch_pendle": 100.0,
        "long_side_split": 0.5,
        "short_side_split": 0.5,
        "calibrated_at_utc": "2026-04-25T00:00:00Z",
        "source": "dapp_ui",
    }])
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=2.0,
        run_id="test-replay-001",
        manifest=None,
    )

    # Verify lex-monotonic order: (blockTimestamp, eventIndex)
    seen = (-1, -1)
    for evt in engine.iter_events():
        cur = (evt["blockTimestamp"], evt["eventIndex"] if evt["eventIndex"] is not None else 0)
        assert cur >= seen, f"out of order: {cur} after {seen}"
        seen = cur

    assert seen != (-1, -1), "Expected at least one event from fixture"


def test_replay_event_index_null_sorts_to_zero(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """BACK-01: null eventIndex sorts to position 0; output.event_index_coverage='degraded' is set."""
    root = tmp_path / "parquet"
    out_dir = root / "market_trades" / f"market_id={MARKET_ID}"
    out_dir.mkdir(parents=True, exist_ok=True)
    # Seed a parquet with one null eventIndex row
    pl.DataFrame({
        "market_id": [MARKET_ID, MARKET_ID],
        "blockTimestamp": [1_700_000_000, 1_700_000_001],
        "eventIndex": [None, 0],
        "rate": [0.05, 0.05],
        "size_wei": [10**18, 10**18],
        "side": ["buy", "buy"],
    }).write_parquet(out_dir / "snap.parquet")

    sqlite_path = seed_market_reward_calibration([{
        "market_id": MARKET_ID,
        "e_liq_per_epoch_pendle": 100.0,
        "long_side_split": 0.5,
        "short_side_split": 0.5,
        "calibrated_at_utc": "2026-04-25T00:00:00Z",
        "source": "dapp_ui",
    }])
    seed_competition_history(
        [("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)],
        market_id=MARKET_ID,
    )

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=root,
        sqlite_path=sqlite_path,
        cancel_latency_s=2.0,
        run_id="test-replay-null-ei",
        manifest=None,
    )

    events = list(engine.iter_events())
    assert len(events) >= 1, "Expected at least 1 event"
    # degraded flag set because at least one null eventIndex was present
    assert engine.output.event_index_coverage == "degraded"
    # Verify ordering is still monotonic (null sorts to 0)
    seen = (-1, -1)
    for evt in events:
        cur = (evt["blockTimestamp"], evt["eventIndex"] if evt["eventIndex"] is not None else 0)
        assert cur >= seen, f"out of order: {cur} after {seen}"
        seen = cur
