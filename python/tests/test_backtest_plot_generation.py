"""BACK-05 — plot generation via backtest CLI plot subcommand.

Test functions:
  - test_plot_calibration_generates_png: 3 synthetic rows → calibration.png exists
  - test_plot_dpnl_dl_generates_png: synthetic slopes → dpnl_dl.png exists
  - test_plot_dpnl_dq_generates_png: synthetic slopes → dpnl_dq.png exists
  - test_plot_subcommand_creates_calibration_dpnl_dl_dpnl_dq: skipped for Plan 05-09

Turns GREEN in Plan 05-05 when boros_brain.backtest.report and CLI land.

[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.backtest.report import plot_calibration, plot_dpnl_dl, plot_dpnl_dq
from boros_brain.backtest.schemas import BacktestRunOutput
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _make_row(
    *,
    run_id: str = "01HWABCDEF1234567890ABCDE0",
    predicted_p_fill_mean: float = 0.03,
    realized_fill_rate: float = 0.02,
) -> BacktestRunOutput:
    """Build a minimal valid BacktestRunOutput for plot testing."""
    return BacktestRunOutput(
        run_id=run_id,
        parent_run_id=None,
        git_sha="abc1234",
        strategy_version="v0.5",
        market_id=MARKET_ID,
        side="long",
        sweep_axis="base",
        sweep_value=0.0,
        bootstrap_idx=None,
        raw_pnl_pendle=1.5,
        raw_pnl_usd=3.0,
        annualized_pnl_pct=0.12,
        sharpe_equivalent=1.5,
        max_drawdown_pct=0.05,
        n_decisions=100,
        n_fills=2,
        n_cancels=10,
        n_purges=0,
        cumulative_fees_pendle=0.01,
        cumulative_gas_pendle=0.005,
        predicted_p_fill_mean=predicted_p_fill_mean,
        realized_fill_rate=realized_fill_rate,
        calibration_residual=predicted_p_fill_mean - realized_fill_rate,
        e_liq_calibrated_at="2026-04-26T00:00:00Z",
        event_index_coverage="full",
        voluntary_cancel_branch="benign",
        parquet_partition="run_id=01HWABCDEF1234567890ABCDE0/sweep_axis=base",
        plots_dir=None,
    )


def test_plot_calibration_generates_png(tmp_path: Path) -> None:
    """BACK-05: plot_calibration writes a PNG > 100 bytes."""
    rows = [_make_row(predicted_p_fill_mean=0.01 * i, realized_fill_rate=0.015 * i) for i in range(1, 4)]
    out = tmp_path / "plots" / "calibration.png"
    result = plot_calibration(rows, out_path=out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 100


def test_plot_dpnl_dl_generates_png(tmp_path: Path) -> None:
    """BACK-05: plot_dpnl_dl writes a PNG > 100 bytes."""
    slopes = [(0.5, -0.05), (1.0, -0.08), (2.0, -0.12)]
    out = tmp_path / "plots" / "dpnl_dl.png"
    result = plot_dpnl_dl(slopes, out_path=out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 100


def test_plot_dpnl_dq_generates_png(tmp_path: Path) -> None:
    """BACK-05: plot_dpnl_dq writes a PNG > 100 bytes."""
    slopes = [(0.5, 0.04), (1.0, 0.00), (2.0, -0.06)]
    out = tmp_path / "plots" / "dpnl_dq.png"
    result = plot_dpnl_dq(slopes, out_path=out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 100


def test_plot_subcommand_creates_calibration_dpnl_dl_dpnl_dq(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-05: `python -m boros_brain.backtest plot --run-id <ulid>` creates calibration + dP&L PNGs."""
    pytest.skip("Plan 05-09 implements the plot subcommand")
