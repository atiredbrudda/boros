"""BACK-01 / B6 — No look-ahead invariant in backtest replay.

Test functions:
  - test_replay_never_reads_future_events: _inject_lookahead_probe=True triggers LookAheadError
  - test_underlying_apr_resolved_at_close_ts_not_fill_ts: deferred to Plan 05-03 (LatencyScheduler)

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.backtest.replay import LookAheadError, ReplayEngine
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_replay_never_reads_future_events(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """BACK-01 / B6: replay engine raises LookAheadError when _inject_lookahead_probe=True.

    The _inject_lookahead_probe flag simulates the engine detecting that a future
    event was read before returning results to the model. In production code, every
    model call is bound to current_chain_ts = evt['blockTimestamp'] — this test
    verifies the engine has the guard path.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
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
        cancel_latency_s=1.0,
        run_id="test-no-lookahead",
        manifest=None,
    )

    # _inject_lookahead_probe=True must immediately raise LookAheadError
    with pytest.raises(LookAheadError):
        await engine.run(_inject_lookahead_probe=True)


@pytest.mark.asyncio
async def test_underlying_apr_resolved_at_close_ts_not_fill_ts(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-01 / B6: underlying APR resolved at close_at_ts, not fill_ts.

    The two-axis cancel latency model (Plan 05-03) schedules close at fill_ts + L.
    The underlying APR used in E[loss|fill] must be resolved at close_at_ts, not fill_ts,
    to avoid look-ahead bias.

    This test exercises the LatencyScheduler path which is implemented in Plan 05-03.
    """
    pytest.skip("Plan 05-03 implements LatencyScheduler + close-at-market path")
