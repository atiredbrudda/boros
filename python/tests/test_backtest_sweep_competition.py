"""BACK-04 — competition multiplier sweep.

Test functions:
  - test_competition_sweep_emits_six_rows: one row per default competition multiplier
  - test_dpnl_dq_competing_negative: dP&L/dQ_competing < 0 (more competition → worse P&L)

[[backtest-competition-sweep]]
[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from boros_brain.backtest.schemas import BacktestRunOutput, ReplayConfig
from boros_brain.backtest.sweeps.competition import compute_dpnl_dq, run_competition_sweep
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

    base_run = _make_base_run(default_config, parquet_root, tmp_sqlite_path)
    parent_manifest = build_run_manifest(default_config)

    rows = asyncio.run(
        run_competition_sweep(
            base_run,
            parent_manifest=parent_manifest,
            config=default_config,
        )
    )

    assert len(rows) == len(default_config.backtest.competition_multipliers)
    assert len(rows) == 6

    sweep_values = {float(r.sweep_value) for r in rows}
    expected = {0.5, 0.75, 1.0, 1.5, 2.0, 3.0}
    assert sweep_values == expected

    for r in rows:
        assert r.sweep_axis == "competition"
        assert r.parent_run_id == parent_manifest.run_id


def test_dpnl_dq_competing_negative(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-04: dP&L/dQ_competing < 0 — more competition always reduces P&L.

    Synthetic high-fill-rate fixture: pnl(m) = -m * 0.01 → dP&L/dm = -0.01 < 0 everywhere.
    Uses compute_dpnl_dq directly (no engine call needed for sign test).
    """
    grid = [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]

    rows = [
        BacktestRunOutput(
            run_id=f"test-comp-{m}",
            parent_run_id="parent-comp-001",
            git_sha="abc1234",
            strategy_version="0.5.0",
            market_id=MARKET_ID,
            side="long",
            sweep_axis="competition",
            sweep_value=float(m),
            raw_pnl_pendle=float(-m * 0.01),
            raw_pnl_usd=float(-m * 0.01),
            annualized_pnl_pct=float(-m * 0.01),
            sharpe_equivalent=0.0,
            max_drawdown_pct=0.0,
            n_decisions=10,
            n_fills=10,
            n_cancels=0,
            n_purges=0,
            cumulative_fees_pendle=0.0,
            cumulative_gas_pendle=0.0,
            predicted_p_fill_mean=1.0,
            realized_fill_rate=1.0,
            calibration_residual=0.0,
            e_liq_calibrated_at="2026-01-01T00:00:00Z",
            event_index_coverage="full",
            voluntary_cancel_branch="benign",
            parquet_partition=f"run_id=test-comp-{m}/sweep_axis=competition",
        )
        for m in grid
    ]

    slopes = compute_dpnl_dq(rows)

    assert len(slopes) == len(grid)
    for m_i, slope in slopes:
        assert slope < 0, f"Expected dP&L/dm < 0 at m={m_i}, got slope={slope}"
