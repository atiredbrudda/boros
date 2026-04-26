"""BACK-08 — perturbation grid Pydantic reflection.

Test functions:
  - test_perturbation_grid_contains_all_numeric_leaves: >= 25 leaves; spot-check known paths
  - test_perturbation_excludes_backtest_meta_knobs: no leaf starts with "backtest."
  - test_adding_a_synthetic_leaf_extends_the_grid: PROTO-04 forcing function (fresh call)
  - test_excludes_booleans: voluntary_cancel_forfeits_accumulated not in grid

[[backtest-perturbation-grid-pydantic-reflection]]
"""

from __future__ import annotations

from boros_brain.backtest.perturbation import enumerate_perturbable_leaves
from boros_brain.config.schema import BotConfig


def test_perturbation_grid_contains_all_numeric_leaves(default_config: BotConfig) -> None:
    """BACK-08: enumerate_perturbable_leaves returns >= 25 numeric/float leaves.

    Spot-checks: at least decision.cancel_cost_ewma_alpha,
    decision.p_purge_default, screener.alt_yield must be present.
    """
    leaves = enumerate_perturbable_leaves(default_config)
    leaf_paths = [leaf.path for leaf in leaves]

    assert len(leaf_paths) >= 25, (
        f"Expected >= 25 perturbable leaves (all numeric BotConfig knobs), " f"got {len(leaf_paths)}: {leaf_paths}"
    )

    # Spot-check 3 known leaves (per BACK-08 spec)
    required = {
        "decision.cancel_cost_ewma_alpha",
        "decision.p_purge_default",
        "screener.alt_yield",
    }
    missing = required - set(leaf_paths)
    assert not missing, f"Required perturbable leaves missing: {missing}"


def test_perturbation_excludes_backtest_meta_knobs(default_config: BotConfig) -> None:
    """BACK-08: backtest.* paths excluded via _PERTURBATION_EXCLUDE_PREFIXES = ('backtest.',).

    Per RESEARCH §Open Question #3: strategy fragility is the question;
    backtest-method fragility (bootstrap_n_resamples etc.) is different and
    less critical.
    """
    leaves = enumerate_perturbable_leaves(default_config)
    backtest_leaves = [leaf.path for leaf in leaves if leaf.path.startswith("backtest.")]

    assert len(backtest_leaves) == 0, (
        f"backtest.* leaves must be excluded from perturbation grid, " f"but found: {backtest_leaves}"
    )


def test_adding_a_synthetic_leaf_extends_the_grid(default_config: BotConfig) -> None:
    """BACK-08 PROTO-04 forcing function: enumerate_perturbable_leaves reads
    model_dump FRESH on every call, so a changed knob value flows through.

    Since BotConfig is extra='forbid' + frozen=True, we can't inject a new leaf.
    Instead: verify a known leaf (screener.alt_yield) appears in enumeration,
    then model_copy the config with a different alt_yield value and assert the
    new value flows through the enumerator (proves no caching).
    """
    leaves_original = enumerate_perturbable_leaves(default_config)
    original_paths = {leaf.path for leaf in leaves_original}
    assert "screener.alt_yield" in original_paths, "screener.alt_yield should be present in the perturbable leaves"

    # Get original value
    original_leaf = next(lf for lf in leaves_original if lf.path == "screener.alt_yield")
    original_value = original_leaf.value

    # Build a config with a different alt_yield
    new_screener = default_config.screener.model_copy(update={"alt_yield": original_value + 0.01})
    new_config = default_config.model_copy(update={"screener": new_screener})

    leaves_new = enumerate_perturbable_leaves(new_config)
    new_leaf = next((lf for lf in leaves_new if lf.path == "screener.alt_yield"), None)
    assert new_leaf is not None, "screener.alt_yield should still be present after model_copy"
    assert abs(new_leaf.value - (original_value + 0.01)) < 1e-12, (
        f"Expected new screener.alt_yield = {original_value + 0.01}, "
        f"got {new_leaf.value}. "
        "enumerate_perturbable_leaves must read model_dump fresh on every call (PROTO-04)."
    )


def test_excludes_booleans(default_config: BotConfig) -> None:
    """BACK-08: boolean knobs (e.g. voluntary_cancel_forfeits_accumulated) NOT in grid.

    Booleans are handled by the BACK-06 forfeit-branch sweep; perturbing them
    as floats is not meaningful for continuous sensitivity analysis.
    """
    leaves = enumerate_perturbable_leaves(default_config)
    leaf_paths = [leaf.path for leaf in leaves]

    # Check no boolean field names appear — voluntary_cancel_forfeits_accumulated
    # is the canonical boolean in BotConfig.strategy
    bool_candidates = [p for p in leaf_paths if "voluntary_cancel" in p]
    assert len(bool_candidates) == 0, (
        f"Boolean knob(s) must NOT be in the perturbation grid, " f"but found: {bool_candidates}"
    )
