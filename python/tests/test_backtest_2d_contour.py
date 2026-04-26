"""BACK-08 — 2D contour grid over two operator-chosen knobs.

Test functions:
  - test_contour_grid_is_5x5_no_nan: len(grid) == 25; no NaN cells
  - test_contour_default_knobs_are_L_and_p_purge: default contour_2d_knobs checked

Turns GREEN in Plan 05-08 when boros_brain.backtest.sweeps.perturbation lands.

[[backtest-perturbation-grid-pydantic-reflection]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-08.
perturbation_mod = pytest.importorskip("boros_brain.backtest.sweeps.perturbation")

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_contour_grid_is_5x5_no_nan(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-08: 2D contour grid has 25 cells (5×5) and no NaN values."""
    pytest.skip("Plan 05-08 implements this — currently RED")


def test_contour_default_knobs_are_L_and_p_purge(
    default_config: BotConfig,
) -> None:
    """BACK-08: default contour_2d_knobs = [execution.cancel_latency_budget_s, decision.p_purge_default]."""
    expected = [
        "execution.cancel_latency_budget_s",
        "decision.p_purge_default",
    ]
    assert default_config.backtest.contour_2d_knobs == expected, (
        f"Default contour_2d_knobs mismatch: "
        f"got {default_config.backtest.contour_2d_knobs}, expected {expected}"
    )
