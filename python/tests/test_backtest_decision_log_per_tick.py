"""BACK-01 — decision log density: one row per in-flight order per tick.

Test functions:
  - test_one_decision_log_per_in_flight_order_per_tick: 2 synthetic orders × 60 simulated seconds → 120 decision log rows

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.backtest.replay import ReplayEngine
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_one_decision_log_per_in_flight_order_per_tick(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet,
    seed_market_reward_calibration,
    seed_competition_history,
    seed_fill_model_fit,
    seed_loss_grid_artifact,
) -> None:
    """BACK-01: replay emits exactly one decision log row per in-flight order per tick.

    With 2 synthetic orders running for 60 simulated seconds (60 1 Hz ticks),
    the decision_log output must contain exactly 2 * 60 = 120 rows.

    Requires seeded fill_model_fit + loss_grid_artifact so evaluate_decision()
    returns without propagating FillModel*Error or LossModelNoFreshGridError.
    """
    # Seed parquet data (not used by _sim_duration_s path, but required for iter_events)
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)

    # Seed calibration — the engine reads this before the sim loop.
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

    # Seed fill model fit + loss grid artifact so evaluate_decision() succeeds.
    # Both fixtures write to tmp_sqlite_path (the same DB as seed_market_reward_calibration).
    seed_fill_model_fit(market_id=MARKET_ID, side="long")
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-decision-log-density",
        manifest=None,
    )

    # _n_synthetic_orders=2: pre-populate 2 in-flight orders before the sim loop.
    # _sim_duration_s=60: run 60 1 Hz ticks (1 decision per order per tick = 120 total).
    result = await engine.run(_n_synthetic_orders=2, _sim_duration_s=60)

    assert hasattr(result, "decision_log"), "ReplayOutput must have decision_log"
    assert len(result.decision_log) == 120, (
        f"Expected 120 decision log rows (2 orders × 60 ticks), "
        f"got {len(result.decision_log)}"
    )
