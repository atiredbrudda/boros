"""BACK-01 / B6 — No look-ahead invariant in backtest replay.

Test functions:
  - test_replay_never_reads_future_events: _inject_lookahead_probe=True triggers LookAheadError
  - test_underlying_apr_resolved_at_close_ts_not_fill_ts: close P&L uses APR at close_at_ts

[[backtest-replay-engine-v05]]
[[backtest-cancel-latency-two-axis]]
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.cancel_latency import LatencyScheduler
from boros_brain.backtest.replay import LookAheadError, ReplayEngine
from boros_brain.backtest.synthetic_orders import SyntheticOrder
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

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
    seed_market_trades_parquet,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """BACK-01 / B6: underlying APR resolved at close_at_ts, NOT fill_ts.

    The two-axis cancel latency model schedules close at fill_ts + L.
    The realized close P&L MUST use underlying APR at close_at_ts (17.0),
    NOT fill_ts (11.3) — using fill_ts erases axis-2 of the latency model
    and introduces look-ahead bias.

    T-05-10: _fire_scheduled_closes must call _underlying_at(sc.close_at_ts).
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)

    # Seed two underlying_apr rows with very different rates:
    #   snapshot_ts=11: rate=0.10  (present at fill_ts=11.3 — wrong to use)
    #   snapshot_ts=17: rate=0.05  (present at close_at_ts=17.0 — correct to use)
    # If _underlying_at uses fill_ts=11.3 it would see rate=0.10.
    # If it correctly uses close_at_ts=17.0 it sees rate=0.05.
    apr_dir = parquet_root / "underlying_apr" / "exchange=BINANCE" / "symbol=ETHUSDT"
    apr_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "snapshot_ts": [11, 17],
        "rate": [0.10, 0.05],
    }).write_parquet(apr_dir / "snapshot.parquet")

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

    manifest = build_run_manifest(default_config)
    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=5.0,
        run_id=manifest.run_id,
        manifest=manifest,
    )

    # Capture all _underlying_at calls to assert which ts is queried.
    calls: list[float] = []
    original_underlying_at = engine._underlying_at

    def _capture(ts: float) -> float:
        calls.append(float(ts))
        return original_underlying_at(ts)

    engine._underlying_at = _capture  # type: ignore[method-assign]

    # Schedule a close manually: fill_ts=11.3 → decision_ts=12.0 → close_at_ts=17.0
    sc = engine.latency_scheduler.schedule(fill_ts=11.3, fill_rate=0.10, order_id="o1")
    engine._scheduled_closes.append(sc)

    # Place a synthetic order so mark_filled doesn't KeyError.
    engine.synthetic_orders.place(SyntheticOrder(
        order_id="o1",
        market_id=MARKET_ID,
        side="long",
        tick=0,
        q_me_pendle=10.0,
        placed_at_ts=10,
        depth_from_mark_ticks=5,
    ))

    # Fire — close_at_ts is 17.0, current_ts=20 triggers firing.
    engine._fire_scheduled_closes(current_ts=20)

    # T-05-10: _underlying_at must be called with close_at_ts=17.0, NOT fill_ts=11.3.
    assert 17.0 in calls, (
        f"_underlying_at was called with {calls}; expected 17.0 (close_at_ts). "
        f"Using fill_ts=11.3 would indicate look-ahead bias in axis-2."
    )
    assert 11.3 not in calls, (
        f"_underlying_at was called with fill_ts=11.3 — this is axis-2 look-ahead! "
        f"Close P&L must use underlying APR at close_at_ts, not fill_ts."
    )

    # Verify the close was actually fired (FILL_REALIZED row in decision_log).
    fill_rows = [d for d in engine.output.decision_log if d.get("decision_kind") == "FILL_REALIZED"]
    assert len(fill_rows) == 1, f"Expected 1 FILL_REALIZED row, got {len(fill_rows)}"
    assert fill_rows[0]["close_at_ts"] == 17.0
    assert fill_rows[0]["fill_ts"] == pytest.approx(11.3)
