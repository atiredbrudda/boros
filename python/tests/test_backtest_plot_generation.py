"""BACK-05 — plot generation via backtest CLI plot subcommand.

Test functions:
  - test_plot_subcommand_creates_calibration_dpnl_dl_dpnl_dq: invoke CLI via subprocess; assert PNGs exist

Turns GREEN in Plan 05-05 when boros_brain.backtest.report and CLI land.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-05.
report_mod = pytest.importorskip("boros_brain.backtest.report")

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_plot_subcommand_creates_calibration_dpnl_dl_dpnl_dq(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-05: `python -m boros_brain.backtest plot --run-id <ulid>` creates calibration + dP&L PNGs."""
    pytest.skip("Plan 05-05 implements this — currently RED")
