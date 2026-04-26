"""BACK-04 — competition multiplier sweep.

Test functions:
  - test_competition_sweep_emits_six_rows: one row per default competition multiplier
  - test_dpnl_dq_competing_negative: dP&L/dQ_competing < 0 (more competition → worse P&L)

Turns GREEN in Plan 05-04 when boros_brain.backtest.sweeps.competition lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-04.
sweep_mod = pytest.importorskip("boros_brain.backtest.sweeps.competition")
run_competition_sweep = sweep_mod.run_competition_sweep

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_competition_sweep_emits_six_rows(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-04: competition sweep emits one row per default competition_multipliers value.

    Default BacktestConfig.competition_multipliers = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0] → 6 rows.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-04 implements this — currently RED")


def test_dpnl_dq_competing_negative(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-04: dP&L/dQ_competing < 0 — more competition always reduces P&L."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-04 implements this — currently RED")
