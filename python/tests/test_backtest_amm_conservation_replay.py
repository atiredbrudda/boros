"""BACK-01 / B3 — AMM conservation invariant in backtest replay.

Test functions:
  - test_amm_conservation_holds_per_window: small replay window; assert_epoch_conservation invoked
  - test_amm_conservation_violation_propagates: combined < raw fixture raises AMMConsumptionIdentityError (NEVER swallow)

[[backtest-replay-engine-v05]]
[[amm-consumption-model-v05]]
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from boros_brain.backtest.replay import AMMConsumptionIdentityError, ReplayEngine
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
# Snapshot timestamps that straddle one SNAPSHOT_INTERVAL_S (3600 s) boundary
# so that _maybe_anchor_snapshot triggers _check_amm_conservation.
_TS_0 = 1_700_000_000
_TS_1 = _TS_0 + 3601  # 1 second past the hourly boundary


def _seed_trades(tmp_path: Path, market_id: str, timestamps: list[int]) -> Path:
    """Write a minimal market_trades parquet at timestamps that span a snapshot boundary."""
    root = tmp_path / "parquet"
    out_dir = root / "market_trades" / f"market_id={market_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "market_id": [market_id] * len(timestamps),
        "blockTimestamp": timestamps,
        "eventIndex": list(range(len(timestamps))),
        "rate": [0.05] * len(timestamps),
        "size_wei": [10**18] * len(timestamps),
        "side": ["buy"] * len(timestamps),
    }).write_parquet(out_dir / "snap.parquet")
    return root


def _seed_order_book_raw(parquet_root: Path, market_id: str, snapshot_ts: int, ticks: dict[int, int]) -> None:
    out_dir = parquet_root / "order_book_raw" / f"market_id={market_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    tick_list = sorted(ticks.keys())
    pl.DataFrame({
        "market_id": [market_id] * len(tick_list),
        "snapshot_ts": [snapshot_ts] * len(tick_list),
        "t": tick_list,
        "sz": [ticks[t] for t in tick_list],
    }).write_parquet(out_dir / f"snap_{snapshot_ts}.parquet")


def _seed_order_book_combined(parquet_root: Path, market_id: str, snapshot_ts: int, ticks: dict[int, int]) -> None:
    out_dir = parquet_root / "order_book_combined" / f"market_id={market_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    tick_list = sorted(ticks.keys())
    pl.DataFrame({
        "market_id": [market_id] * len(tick_list),
        "snapshot_ts": [snapshot_ts] * len(tick_list),
        "t": tick_list,
        "sz": [ticks[t] for t in tick_list],
    }).write_parquet(out_dir / f"snap_{snapshot_ts}.parquet")


@pytest.mark.asyncio
async def test_amm_conservation_holds_per_window(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """BACK-01 / B3: AMM conservation invariant holds across a small replay window.

    combined_sizes >= raw_sizes at each tick (AMM share = combined - raw >= 0).
    No AMMConsumptionIdentityError should be raised.
    """
    # Two events that span a 1-hour boundary, so _maybe_anchor_snapshot triggers.
    parquet_root = _seed_trades(tmp_path, MARKET_ID, [_TS_0, _TS_1])
    # combined >= raw at every tick (AMM share non-negative)
    _seed_order_book_raw(parquet_root, MARKET_ID, _TS_0, {0: 10**18, 1: 2 * 10**18})
    _seed_order_book_combined(parquet_root, MARKET_ID, _TS_0, {0: 15 * 10**17, 1: 25 * 10**17})

    sqlite_path = seed_market_reward_calibration([{
        "market_id": MARKET_ID,
        "e_liq_per_epoch_pendle": 100.0,
        "long_side_split": 0.5,
        "short_side_split": 0.5,
        "calibrated_at_utc": "2026-04-25T00:00:00Z",
        "source": "dapp_ui",
    }])
    seed_competition_history(
        [("2026-04-25T00:00:00Z", _TS_0, 10.0, 100.0)],
        market_id=MARKET_ID,
    )

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-amm-conservation",
        manifest=None,
    )

    # Should complete without raising AMMConsumptionIdentityError
    result = await engine.run()
    assert result is not None


@pytest.mark.asyncio
async def test_amm_conservation_violation_propagates(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
    seed_competition_history,
) -> None:
    """BACK-01 / B3: combined < raw at any tick raises AMMConsumptionIdentityError (NEVER swallow).

    Seeds raw={0: 10**18} but combined={0: 5*10**17} — combined < raw.
    The replay engine MUST propagate this error, not swallow it.
    """
    # Two events spanning a 1-hour boundary so the snapshot anchor is triggered.
    parquet_root = _seed_trades(tmp_path, MARKET_ID, [_TS_0, _TS_1])
    # combined < raw — violation triggers AMMConsumptionIdentityError
    _seed_order_book_raw(parquet_root, MARKET_ID, _TS_0, {0: 10**18})
    _seed_order_book_combined(parquet_root, MARKET_ID, _TS_0, {0: 5 * 10**17})

    sqlite_path = seed_market_reward_calibration([{
        "market_id": MARKET_ID,
        "e_liq_per_epoch_pendle": 100.0,
        "long_side_split": 0.5,
        "short_side_split": 0.5,
        "calibrated_at_utc": "2026-04-25T00:00:00Z",
        "source": "dapp_ui",
    }])
    seed_competition_history(
        [("2026-04-25T00:00:00Z", _TS_0, 10.0, 100.0)],
        market_id=MARKET_ID,
    )

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-amm-violation",
        manifest=None,
    )

    with pytest.raises(AMMConsumptionIdentityError):
        await engine.run()
