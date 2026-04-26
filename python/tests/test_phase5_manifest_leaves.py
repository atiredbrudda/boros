"""PROTO-04 / Phase 5: BotConfig.backtest leaves surface in manifest reflection.

Covers:
  - test_phase5_backtest_leaves_surfaced: >=8 backtest.* leaves in BotConfig manifest
    with spot-checks on 5 specific leaf paths.

The BacktestConfig sub-model is the PROTO-04 SSoT for every Phase-5 knob. Adding a
knob in backtest/ code without adding it to BacktestConfig is a bug — this test
verifies the leaf count and specific required knobs are present.
"""

from __future__ import annotations

from pydantic import BaseModel

from boros_brain.config.schema import BotConfig


def _collect_leaf_paths(model_cls: type[BaseModel], prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Walk every nested Pydantic sub-model recursively, returning leaf field paths.

    A leaf is a field whose annotation is NOT a BaseModel subclass (list, scalar, etc).
    Copied verbatim from test_manifest_contains_all_knobs.py._collect_leaf_paths.
    """
    leaves: set[tuple[str, ...]] = set()
    for name, info in model_cls.model_fields.items():
        ann = info.annotation
        # Recurse into nested Pydantic models.
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            leaves |= _collect_leaf_paths(ann, prefix + (name,))
            continue
        # Recurse into list[Model] (MarketCalibration list case).
        origin = getattr(ann, "__origin__", None)
        args = getattr(ann, "__args__", ())
        if origin in (list, tuple) and args:
            inner = args[0]
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                leaves.add(prefix + (name,))  # list itself is a leaf in the manifest dict
                continue
        leaves.add(prefix + (name,))
    return leaves


def test_phase5_backtest_leaves_surfaced(default_config: BotConfig) -> None:
    """PROTO-04 (Plan 05-01): every Phase-5 backtest.* knob auto-surfaces via reflection.

    Expected leaf count: >=8 under backtest.* prefix, covering all BacktestConfig
    knobs declared in python/src/boros_brain/backtest/config.py.

    Spot-check 5 specific required leaf paths that Wave 1+ plans rely on:
      1. backtest.bootstrap_n_resamples       (BACK-07 bootstrap determinism)
      2. backtest.bootstrap_block_seconds     (BACK-07 block bootstrap config)
      3. backtest.all_fees_threshold          (BACK-07 ship-gate threshold assembly)
      4. backtest.perturbation_pct            (BACK-08 perturbation grid)
      5. backtest.output_parquet_root         (BACK-05 report writer root path)
    """
    leaves = _collect_leaf_paths(BotConfig)
    leaf_strs = [".".join(leaf) for leaf in leaves]

    backtest_leaves = [s for s in leaf_strs if s.startswith("backtest.")]

    assert len(backtest_leaves) >= 8, (
        f"expected >=8 backtest.* leaves (Phase 5 BacktestConfig not yet wired), "
        f"got {len(backtest_leaves)}: {backtest_leaves}"
    )

    # Spot-check 5 specific required leaf paths.
    required = {
        "backtest.bootstrap_n_resamples",
        "backtest.bootstrap_block_seconds",
        "backtest.all_fees_threshold",
        "backtest.perturbation_pct",
        "backtest.output_parquet_root",
    }
    missing = required - set(leaf_strs)
    assert not missing, (
        f"Required spot-check leaves missing from BotConfig reflection: {missing}. "
        "Plan 05-01 must register these knobs in BacktestConfig."
    )
