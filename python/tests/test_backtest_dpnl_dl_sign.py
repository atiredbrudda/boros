"""BACK-03 — dP&L/dL sign: central-finite-difference is everywhere negative.

Test functions:
  - test_dpnl_dl_negative_on_synthetic_always_fills_scenario: central-finite-difference is everywhere negative

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


def test_dpnl_dl_negative_on_synthetic_always_fills_scenario(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-03: dP&L/dL < 0 everywhere in an always-fills synthetic scenario.

    When every order fills (worst case), increasing cancel latency L always
    worsens P&L. The central-finite-difference dP&L/dL must be negative at
    every interior grid point.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    pytest.skip("Plan 05-04 implements this — currently RED")
