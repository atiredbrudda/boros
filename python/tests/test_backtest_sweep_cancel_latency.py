"""BACK-03 — cancel latency sweep: one run per grid point.

Test functions:
  - test_sweep_emits_six_rows_on_default_grid: len(rows) == 6 matching [0.5, 1, 2, 3, 5, 10]
  - test_sweep_uses_config_backtest_cancel_latency_grid: operator-overridden grid takes effect
  - test_sweep_child_runs_have_parent_run_id: every row has parent_run_id == parent_manifest.run_id

[[backtest-cancel-latency-sweep]]
[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from boros_brain.backtest.schemas import ReplayConfig
from boros_brain.backtest.sweeps.cancel_latency import run_cancel_latency_sweep
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _make_base_run(
    config: BotConfig,
    parquet_root: Path,
    sqlite_path: Path,
) -> ReplayConfig:
    return ReplayConfig(
        config=config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=sqlite_path,
        cancel_latency_s=1.0,
    )


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

    base_run = _make_base_run(default_config, parquet_root, tmp_sqlite_path)
    parent_manifest = build_run_manifest(default_config)

    rows = asyncio.run(
        run_cancel_latency_sweep(
            base_run,
            parent_manifest=parent_manifest,
            config=default_config,
        )
    )

    assert len(rows) == len(default_config.backtest.cancel_latency_grid)
    assert len(rows) == 6

    sweep_values = {float(r.sweep_value) for r in rows}
    expected = {0.5, 1.0, 2.0, 3.0, 5.0, 10.0}
    assert sweep_values == expected

    for r in rows:
        assert r.sweep_axis == "cancel_latency"


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

    # Override config with a 3-point grid
    config_3pt = default_config.model_copy(
        update={"backtest": default_config.backtest.model_copy(update={"cancel_latency_grid": [1.0, 2.0, 4.0]})}
    )

    base_run = _make_base_run(config_3pt, parquet_root, tmp_sqlite_path)
    parent_manifest = build_run_manifest(config_3pt)

    rows = asyncio.run(
        run_cancel_latency_sweep(
            base_run,
            parent_manifest=parent_manifest,
            config=config_3pt,
        )
    )

    assert len(rows) == 3
    sweep_values = {float(r.sweep_value) for r in rows}
    assert sweep_values == {1.0, 2.0, 4.0}


def test_sweep_child_runs_have_parent_run_id(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-03: every child run row has parent_run_id == parent_manifest.run_id (T-05-11)."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    base_run = _make_base_run(default_config, parquet_root, tmp_sqlite_path)
    parent_manifest = build_run_manifest(default_config)

    rows = asyncio.run(
        run_cancel_latency_sweep(
            base_run,
            parent_manifest=parent_manifest,
            config=default_config,
        )
    )

    assert len(rows) > 0
    for r in rows:
        assert r.parent_run_id == parent_manifest.run_id, (
            f"row for L={r.sweep_value} has parent_run_id={r.parent_run_id!r}, " f"expected {parent_manifest.run_id!r}"
        )
