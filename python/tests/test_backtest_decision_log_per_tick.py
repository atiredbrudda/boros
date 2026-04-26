"""BACK-01 — decision log density: one row per in-flight order per tick.

Test functions:
  - test_one_decision_log_per_in_flight_order_per_tick: 2 synthetic orders × 60 simulated seconds → 120 decision log rows

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


def test_one_decision_log_per_in_flight_order_per_tick(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01: replay emits exactly one decision log row per in-flight order per tick.

    With 2 synthetic orders running for 60 simulated seconds (60 1 Hz ticks),
    the decision_log output must contain exactly 2 * 60 = 120 rows.
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
        run_id="test-decision-log-density",
        manifest=None,
    )

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        engine.run(_n_synthetic_orders=2, _sim_duration_s=60)
    )

    # 2 orders × 60 ticks = 120 decision log rows
    assert hasattr(result, "decision_log"), "ReplayOutput must have decision_log"
    assert len(result.decision_log) == 120, (
        f"Expected 120 decision log rows (2 orders × 60 ticks), "
        f"got {len(result.decision_log)}"
    )
