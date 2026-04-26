"""PROTO-04 — Phase 4 decision.* config knobs auto-surface via BotConfig reflection.

Covers:
  - test_phase4_leaves_surfaced: >=25 decision.* leaves in BotConfig manifest
    with spot-checks on 10 specific leaf paths.

This test is RED until Plan 04-03 lands DecisionConfig + BreakerConfig sub-models
inside BotConfig. The test COLLECTS cleanly (no importorskip needed — it only
needs BotConfig which already exists) but will FAIL the assertion until the
decision.* knobs are wired into the Pydantic schema.

The _collect_leaf_paths helper is copied verbatim from test_manifest_contains_all_knobs.py
(lines 53-76) so this test is self-contained.
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


def test_phase4_leaves_surfaced(default_config: BotConfig) -> None:
    """PROTO-04 (Plan 04-03): every Phase-4 decision.* knob auto-surfaces via reflection.

    Expected leaf count: >=25 under decision.* prefix, covering:
      - DecisionConfig top-level knobs (cancel_cost_ewma_alpha, decision_loop_interval_s, etc.)
      - BreakerConfig sub-model families for SAFE-01..09 + B5

    This test is RED until Plan 04-03 wires DecisionConfig into BotConfig.

    Spot-check 10 specific leaves that Plans 04-03..06 must register:
      1. decision.cancel_cost_ewma_alpha               (DECIDE-03 GasHistoryCache)
      2. decision.breakers.margin.window_s             (SAFE-01 MarginTrajectoryBreaker)
      3. decision.breakers.oracle_stale.fraction_of_max (SAFE-02 OracleStaleBreaker)
      4. decision.breakers.clo_shift.n_ticks           (SAFE-04 CloShiftBreaker)
      5. decision.breakers.fill_rate.k_fills_per_hour  (SAFE-05 FillRateBreaker)
      6. decision.breakers.competition.drop_threshold  (SAFE-06 CompetitionBreaker)
      7. decision.breakers.maturity.migration_cost_buffer_pct (SAFE-07 MaturityBreaker)
      8. decision.breakers.side_budget.drift_threshold (SAFE-08 SideBudgetBreaker)
      9. decision.breakers.underlying_stale.expected_cadence_s_per_exchange (SAFE-09)
      10. decision.decision_loop_interval_s             (main.py decision loop knob)
    """
    leaves = _collect_leaf_paths(BotConfig)
    leaf_strs = [".".join(leaf) for leaf in leaves]

    decision_leaves = [s for s in leaf_strs if s.startswith("decision.")]

    assert len(decision_leaves) >= 25, (
        f"expected >=25 decision.* leaves (Phase 4 DecisionConfig not yet wired), "
        f"got {len(decision_leaves)}: {decision_leaves}"
    )

    # Spot-check 10 specific required leaf paths.
    required_spot_checks = [
        "decision.cancel_cost_ewma_alpha",
        "decision.breakers.margin.window_s",
        "decision.breakers.oracle_stale.fraction_of_max",
        "decision.breakers.clo_shift.n_ticks",
        "decision.breakers.fill_rate.k_fills_per_hour",
        "decision.breakers.competition.drop_threshold",
        "decision.breakers.maturity.migration_cost_buffer_pct",
        "decision.breakers.side_budget.drift_threshold",
        "decision.breakers.underlying_stale.expected_cadence_s_per_exchange",
        "decision.decision_loop_interval_s",
    ]
    missing_spots = [s for s in required_spot_checks if s not in leaf_strs]
    assert not missing_spots, (
        f"Required spot-check leaves missing from BotConfig reflection: {missing_spots}. "
        "Plan 04-03 must register these knobs in DecisionConfig / BreakerConfig sub-models."
    )
