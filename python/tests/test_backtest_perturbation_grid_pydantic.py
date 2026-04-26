"""BACK-08 — perturbation grid Pydantic reflection.

Test functions:
  - test_perturbation_grid_contains_all_numeric_leaves: >= 30 leaves; spot-check 5 known
  - test_perturbation_grid_excludes_booleans: voluntary_cancel_forfeits_accumulated not in grid
  - test_perturbation_grid_excludes_backtest_meta_knobs: runner filters backtest.* paths

Turns GREEN in Plan 05-08 when boros_brain.backtest.sweeps.perturbation lands.

[[backtest-perturbation-grid-pydantic-reflection]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-08.
perturbation_mod = pytest.importorskip("boros_brain.backtest.sweeps.perturbation")
enumerate_perturbable_leaves = perturbation_mod.enumerate_perturbable_leaves
KnobLeaf = perturbation_mod.KnobLeaf

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_perturbation_grid_contains_all_numeric_leaves(default_config: BotConfig) -> None:
    """BACK-08: enumerate_perturbable_leaves returns >= 30 numeric/float leaves."""
    leaves = enumerate_perturbable_leaves(default_config)
    leaf_paths = [leaf.path for leaf in leaves]

    assert len(leaf_paths) >= 30, (
        f"Expected >= 30 perturbable leaves (all numeric BotConfig knobs), "
        f"got {len(leaf_paths)}: {leaf_paths}"
    )

    # Spot-check 5 known leaves
    required = {
        "backtest.bootstrap_n_resamples",
        "execution.cancel_latency_budget_s",
        "screener.alt_yield",
        "strategy.target_share",
        "decision.p_purge_default",
    }
    missing = required - set(leaf_paths)
    assert not missing, f"Required perturbable leaves missing: {missing}"


def test_perturbation_grid_excludes_booleans(default_config: BotConfig) -> None:
    """BACK-08: boolean knobs (e.g. voluntary_cancel_forfeits_accumulated) NOT in perturbation grid."""
    leaves = enumerate_perturbable_leaves(default_config)
    leaf_paths = [leaf.path for leaf in leaves]

    assert "strategy.voluntary_cancel_forfeits_accumulated" not in leaf_paths, (
        "voluntary_cancel_forfeits_accumulated (bool) must NOT be in the perturbation grid. "
        "Perturbing booleans is not meaningful for the continuous sensitivity analysis."
    )


def test_perturbation_grid_excludes_backtest_meta_knobs(default_config: BotConfig) -> None:
    """BACK-08: backtest.* paths excluded via _PERTURBATION_EXCLUDE_PREFIXES = ('backtest.',).

    Perturbing backtest meta-knobs (bootstrap_n_resamples, etc.) would perturb
    the harness itself rather than the strategy. These are excluded by design.
    """
    leaves = enumerate_perturbable_leaves(default_config)
    backtest_leaves = [leaf.path for leaf in leaves if leaf.path.startswith("backtest.")]

    assert len(backtest_leaves) == 0, (
        f"backtest.* leaves must be excluded from perturbation grid, "
        f"but found: {backtest_leaves}"
    )
