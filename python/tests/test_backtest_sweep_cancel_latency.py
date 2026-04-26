"""BACK-03 — cancel latency sweep: one run per grid point.

Test functions:
  - test_sweep_emits_six_rows_on_default_grid: len(rows) == 6 matching [0.5, 1, 2, 3, 5, 10]
  - test_sweep_uses_config_backtest_cancel_latency_grid: operator-overridden grid takes effect

Turns GREEN in Plan 05-04 when boros_brain.backtest.sweeps.cancel_latency lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-04.
sweep_mod = pytest.importorskip("boros_brain.backtest.sweeps.cancel_latency")
run_cancel_latency_sweep = sweep_mod.run_cancel_latency_sweep

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_sweep_emits_six_rows_on_default_grid(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-03: cancel latency sweep produces one BacktestRunOutput per grid point.

    Default BacktestConfig.cancel_latency_grid = [0.5, 1, 2, 3, 5, 10] → 6 rows.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-04 implements this — currently RED")


def test_sweep_uses_config_backtest_cancel_latency_grid(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-03: operator-overridden cancel_latency_grid is used instead of default."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-04 implements this — currently RED")
