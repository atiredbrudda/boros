"""BACK-01 / B3 — AMM conservation invariant in backtest replay.

Test functions:
  - test_amm_conservation_holds_per_window: small replay window; assert_epoch_conservation invoked
  - test_amm_conservation_violation_propagates: combined < raw fixture raises AMMConsumptionIdentityError (NEVER swallow)

Turns GREEN in Plan 05-02 when boros_brain.backtest.replay lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-02.
replay = pytest.importorskip("boros_brain.backtest.replay")
ReplayEngine = replay.ReplayEngine
AMMConsumptionIdentityError = replay.AMMConsumptionIdentityError

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_amm_conservation_holds_per_window(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01 / B3: AMM conservation invariant holds across a small replay window.

    combined_sizes >= raw_sizes at each tick (AMM share = combined - raw >= 0).
    No AMMConsumptionIdentityError should be raised.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    # Default fixtures: combined >= raw at every tick
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-amm-conservation",
        manifest=None,
    )

    # Should complete without raising AMMConsumptionIdentityError
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(engine.run())
    assert result is not None


def test_amm_conservation_violation_propagates(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01 / B3: combined < raw at any tick raises AMMConsumptionIdentityError (NEVER swallow).

    Seeds raw={0: 10**18} but combined={0: 5*10**17} — combined < raw.
    The replay engine MUST propagate this error, not swallow it.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(
        market_id=MARKET_ID,
        ticks_with_sizes={0: 10**18},
        parquet_root=parquet_root,
    )
    seed_order_book_combined_parquet(
        market_id=MARKET_ID,
        combined_sizes={0: 5 * 10**17},  # combined < raw — violation
        parquet_root=parquet_root,
    )

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-amm-violation",
        manifest=None,
    )

    import asyncio
    with pytest.raises(AMMConsumptionIdentityError):
        asyncio.get_event_loop().run_until_complete(engine.run())
