"""BACK-08 — 2D contour grid over two operator-chosen knobs.

Test functions:
  - test_2d_contour_grid_is_5x5: 5×5 = 25 cells
  - test_2d_contour_no_nan_cells: no NaN p5_pnl values
  - test_2d_contour_default_knobs_present_in_dumped_config: default knobs verified
  - test_2d_contour_operator_override: alt_yield × p_purge grid works
  - test_2d_contour_raises_on_unknown_knob: ValueError on missing knob path
  - test_2d_contour_parquet_roundtrip: 25 rows × 3 cols parquet

[[backtest-perturbation-grid-pydantic-reflection]]
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from boros_brain.backtest.contour_2d import (
    contour_grid_to_parquet,
    run_2d_contour_grid,
)
from boros_brain.backtest.perturbation import ReplayInputs
from boros_brain.backtest.schemas import ReplayOutput
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _make_replay_inputs(tmp_path: Path) -> ReplayInputs:
    return ReplayInputs(
        market_id=MARKET_ID,
        side="long",
        parquet_root=tmp_path / "parquet",
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=1.0,
        voluntary_cancel_branch="benign",
    )


def _install_replay_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch ReplayEngine.run to return positive daily_pnl stub."""

    async def _stub_run(self: object) -> ReplayOutput:
        return ReplayOutput(
            rows=[],
            decision_log=[],
            daily_pnl=np.array([0.001] * 30, dtype=np.float64),
            n_amm_violations=0,
            event_index_coverage="full",
        )

    monkeypatch.setattr(
        "boros_brain.backtest.replay.ReplayEngine.run",
        _stub_run,
        raising=True,
    )


@pytest.mark.asyncio
async def test_2d_contour_grid_is_5x5(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: 2D contour grid has 5×5 = 25 cells."""
    _install_replay_stub(monkeypatch)

    parent_manifest = build_run_manifest(default_config)
    grid = await run_2d_contour_grid(
        default_config,
        _make_replay_inputs(tmp_path),
        parent_manifest=parent_manifest,
    )

    assert len(grid) == 5, f"Expected 5 rows, got {len(grid)}"
    assert all(len(row) == 5 for row in grid), f"Not all rows have 5 cells: {[len(r) for r in grid]}"


@pytest.mark.asyncio
async def test_2d_contour_no_nan_cells(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: no NaN p5_pnl values in the 2D grid."""
    _install_replay_stub(monkeypatch)

    parent_manifest = build_run_manifest(default_config)
    grid = await run_2d_contour_grid(
        default_config,
        _make_replay_inputs(tmp_path),
        parent_manifest=parent_manifest,
    )

    nan_cells = [
        (a_idx, b_idx) for a_idx, row in enumerate(grid) for b_idx, cell in enumerate(row) if math.isnan(cell.p5_pnl)
    ]
    assert len(nan_cells) == 0, f"NaN cells found at indices: {nan_cells}"


def test_2d_contour_default_knobs_present_in_dumped_config(
    default_config: BotConfig,
) -> None:
    """BACK-08: default contour_2d_knobs verified against RESEARCH L1049-1053."""
    expected = [
        "execution.cancel_latency_budget_s",
        "decision.p_purge_default",
    ]
    assert default_config.backtest.contour_2d_knobs == expected, (
        f"Default contour_2d_knobs mismatch: " f"got {default_config.backtest.contour_2d_knobs}, expected {expected}"
    )


@pytest.mark.asyncio
async def test_2d_contour_operator_override(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: operator can override contour_2d_knobs to any two numeric leaves."""
    _install_replay_stub(monkeypatch)

    # Override to screener.alt_yield × decision.p_purge_default
    new_backtest = default_config.backtest.model_copy(
        update={"contour_2d_knobs": ["screener.alt_yield", "decision.p_purge_default"]}
    )
    override_config = default_config.model_copy(update={"backtest": new_backtest})

    parent_manifest = build_run_manifest(override_config)
    grid = await run_2d_contour_grid(
        override_config,
        _make_replay_inputs(tmp_path),
        parent_manifest=parent_manifest,
    )

    assert len(grid) == 5 and all(len(row) == 5 for row in grid)
    # Verify knob_a_value is in the alt_yield range
    from boros_brain.backtest.perturbation import enumerate_perturbable_leaves

    leaves = enumerate_perturbable_leaves(override_config)
    alt_yield_leaf = next(lf for lf in leaves if lf.path == "screener.alt_yield")
    pct = override_config.backtest.perturbation_pct
    a_low = alt_yield_leaf.value * (1.0 - pct)
    a_high = alt_yield_leaf.value * (1.0 + pct)
    assert a_low <= grid[0][0].knob_a_value <= a_high, (
        f"grid[0][0].knob_a_value={grid[0][0].knob_a_value} outside " f"alt_yield range [{a_low}, {a_high}]"
    )


@pytest.mark.asyncio
async def test_2d_contour_raises_on_unknown_knob(
    default_config: BotConfig,
    tmp_path: Path,
) -> None:
    """BACK-08: ValueError when a contour_2d_knobs path is not a numeric leaf."""
    new_backtest = default_config.backtest.model_copy(
        update={"contour_2d_knobs": ["nonexistent.path", "decision.p_purge_default"]}
    )
    bad_config = default_config.model_copy(update={"backtest": new_backtest})

    parent_manifest = build_run_manifest(bad_config)
    with pytest.raises(ValueError, match="not found in BotConfig numeric leaves"):
        await run_2d_contour_grid(
            bad_config,
            _make_replay_inputs(tmp_path),
            parent_manifest=parent_manifest,
        )


@pytest.mark.asyncio
async def test_2d_contour_parquet_roundtrip(
    default_config: BotConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BACK-08: contour_grid_to_parquet writes 25 rows × 3 cols."""
    _install_replay_stub(monkeypatch)

    parent_manifest = build_run_manifest(default_config)
    grid = await run_2d_contour_grid(
        default_config,
        _make_replay_inputs(tmp_path),
        parent_manifest=parent_manifest,
    )

    knob_a, knob_b = default_config.backtest.contour_2d_knobs[:2]
    parquet_root = tmp_path / "parquet" / "backtest_results"
    out_path = contour_grid_to_parquet(
        grid,
        run_id=parent_manifest.run_id,
        knob_a_path=knob_a,
        knob_b_path=knob_b,
        parquet_root=parquet_root,
    )

    assert out_path.exists(), f"Parquet file not created at {out_path}"
    df = pl.read_parquet(out_path)
    assert df.shape == (25, 3), f"Expected (25, 3), got {df.shape}"
    assert set(df.columns) == {"a_value", "b_value", "p5_pnl"}
