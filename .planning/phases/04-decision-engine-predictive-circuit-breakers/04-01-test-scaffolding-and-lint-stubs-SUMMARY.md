---
phase: 04-decision-engine-predictive-circuit-breakers
plan: "01"
subsystem: test-scaffolding
tags: [tdd, red-tests, scaffolding, breakers, decision-engine, lint]
dependency_graph:
  requires: []
  provides:
    - python/tests/conftest.py (Phase 4 seed fixtures)
    - python/tests/test_decision_engine_ev_equation.py
    - python/tests/test_decision_engine_voluntary_branch.py
    - python/tests/test_gas_history_ewma.py
    - python/tests/test_no_threshold_dials_lint.py
    - python/tests/test_phase4_manifest_leaves.py
    - python/tests/test_main_decision_loop_spawn.py
    - python/tests/test_breaker_margin_trajectory.py
    - python/tests/test_breaker_oracle_stale.py
    - python/tests/test_breaker_clo_removal.py
    - python/tests/test_breaker_clo_shift.py
    - python/tests/test_breaker_fill_rate.py
    - python/tests/test_breaker_competition.py
    - python/tests/test_breaker_maturity.py
    - python/tests/test_breaker_side_budget.py
    - python/tests/test_breaker_underlying_stale.py
    - python/tests/test_breaker_loss_fit_degraded.py
    - python/tests/test_breaker_coordinator_exclusive.py
    - python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - python/tests/test_predeploy_gate_cli.py
    - scripts/no_hardcoded_cancel_cost_lint.py
    - scripts/no_threshold_dials_lint.py
  affects:
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
tech_stack:
  added: []
  patterns:
    - pytest.importorskip RED-state pattern for future module gating
    - fixture-factory pattern (returns callable, defers writer imports)
    - apply_migrations() module-level helper
key_files:
  created:
    - python/tests/test_decision_engine_ev_equation.py
    - python/tests/test_decision_engine_voluntary_branch.py
    - python/tests/test_gas_history_ewma.py
    - python/tests/test_no_threshold_dials_lint.py
    - python/tests/test_phase4_manifest_leaves.py
    - python/tests/test_main_decision_loop_spawn.py
    - python/tests/test_breaker_margin_trajectory.py
    - python/tests/test_breaker_oracle_stale.py
    - python/tests/test_breaker_clo_removal.py
    - python/tests/test_breaker_clo_shift.py
    - python/tests/test_breaker_fill_rate.py
    - python/tests/test_breaker_competition.py
    - python/tests/test_breaker_maturity.py
    - python/tests/test_breaker_side_budget.py
    - python/tests/test_breaker_underlying_stale.py
    - python/tests/test_breaker_loss_fit_degraded.py
    - python/tests/test_breaker_coordinator_exclusive.py
    - python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - python/tests/test_predeploy_gate_cli.py
    - scripts/no_hardcoded_cancel_cost_lint.py
    - scripts/no_threshold_dials_lint.py
  modified:
    - python/tests/conftest.py
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
decisions:
  - "pytest.importorskip at module top (not try/except ImportError) — SKIP status visible in pytest output; T-04-01-05 mitigation"
  - "Lint script type: external in architecture.yml — matches scripts.no_time_time_lint convention set in Plan 01-03"
  - "Writer imports deferred inside fixture inner functions — conftest imports cleanly before 04-02 lands"
  - "seed_tx_receipts_fills uses direct SQL INSERT (TEST_ONLY pattern) — event_type column lands in 04-02 migration"
metrics:
  duration_minutes: 17
  completed_date: "2026-04-25"
  tasks_completed: 5
  files_created: 21
  files_modified: 3
---

# Phase 4 Plan 01: Test Scaffolding and Lint Stubs Summary

Wave 0 TDD scaffolding: 19 RED test files + 7 conftest fixtures + apply_migrations helper + 2 lint script skeletons + atomic architecture.yml/Mermaid registration of new lint nodes, before any engine/breaker implementation.

## One-liner

19 RED pytest files (importorskip-driven skip until 04-03..06) + conftest 7 fixture-factories + 2 DECIDE-03/04 lint skeletons registered in architecture.yml as external nodes.

## What Was Built

### Test Files Created (19)

| File | Requirement | Lands GREEN |
|------|-------------|-------------|
| test_decision_engine_ev_equation.py | DECIDE-01 (5 tests incl. hypothesis) | 04-03 |
| test_decision_engine_voluntary_branch.py | DECIDE-02 (2 tests, parametrized forfeits) | 04-03 |
| test_gas_history_ewma.py | DECIDE-03 (4 tests, linter sub-tests) | 04-03 |
| test_no_threshold_dials_lint.py | DECIDE-04 (2 tests) | 04-03 |
| test_phase4_manifest_leaves.py | PROTO-04 (1 test, >=25 decision.* leaves) | 04-06 |
| test_main_decision_loop_spawn.py | main.py wiring (2 tests) | 04-06 |
| test_breaker_margin_trajectory.py | SAFE-01 (3 tests, Pitfall #4 sign guard) | 04-04 |
| test_breaker_oracle_stale.py | SAFE-02 (3 tests, 0.7× boundary) | 04-04 |
| test_breaker_clo_removal.py | SAFE-03 (1 parametrized test, 4 cases) | 04-04 |
| test_breaker_clo_shift.py | SAFE-04 (3 tests, A1×A3 compound) | 04-04 |
| test_breaker_fill_rate.py | SAFE-05 (2 tests, K=4 fires/K=3 silent) | 04-04 |
| test_breaker_loss_fit_degraded.py | B5 absorbed (2 tests, SHRINK_TO_Q_MIN) | 04-04 |
| test_breaker_competition.py | SAFE-06 (3 tests, >50% drop + zero_baseline) | 04-05 |
| test_breaker_maturity.py | SAFE-07 (2 tests, ROLL_POSITION) | 04-05 |
| test_breaker_side_budget.py | SAFE-08 (2 tests, >=30% drift) | 04-05 |
| test_breaker_underlying_stale.py | SAFE-09 (1 parametrized test, 4 cases) | 04-05 |
| test_breaker_coordinator_exclusive.py | SAFE-10 (3 tests, real ZMQ ipc://, Pitfall #6) | 04-06 |
| test_predeploy_gate_cli.py | A5 absorbed (3 tests, Pitfall #8 provenance) | 04-06 |
| test_breaker_coordinator_publishes_kill_lane_per_safe.py | SAFE-01..09+B5 composition (10 parametrized) | 04-06 Task 6 |

### Conftest Extensions (python/tests/conftest.py)

7 new fixture-factories + apply_migrations() module-level helper appended to the existing 63-line conftest (existing fixtures unchanged):

- `apply_migrations(db)` — module-level helper mirroring test_fill_model_predict_contract.py
- `seed_margin_history(slope, n)` — SAFE-01; deferred import of insert_margin_snapshot
- `seed_clo_history(rows)` — SAFE-03/04; uses existing insert_clo_snapshot
- `seed_competition_history(rows)` — SAFE-06; uses existing insert_competition_row
- `seed_market_reward_calibration(rows)` — SAFE-08; uses existing insert_market_reward_calibration
- `seed_loss_grid_artifact(fit_status)` — B5; uses existing insert_loss_grid_artifact + LossGridArtifact
- `seed_tx_receipts_fills(n_fills)` — SAFE-05; direct SQL INSERT (event_type column from 04-02)
- `seed_underlying_apr_parquet(last_ts, exchange)` — SAFE-09; polars DataFrame write_parquet

### Lint Script Skeletons

| Script | Enforces | PATTERN | Exit 0 now? |
|--------|----------|---------|-------------|
| scripts/no_hardcoded_cancel_cost_lint.py | DECIDE-03 | `cancel_cost(?:_pendle)?\s*=\s*\d+\.\d+` | Yes (no decision/ files exist yet) |
| scripts/no_threshold_dials_lint.py | DECIDE-04 | `\w+_(?:threshold\|dial\|cutoff)\s*[:=]` | Yes (no decision/ files exist yet) |

Both follow the `scripts/no_time_time_lint.py` structural template. Tightening in Plan 04-03 once `decision/gas_history.py` and `decision/config.py` exist.

### Architecture.yml/Mermaid Delta

Two new `type: external` nodes appended before `edges:` section:

- `scripts.no_hardcoded_cancel_cost_lint` — DECIDE-03 enforcement, path: `scripts/no_hardcoded_cancel_cost_lint.py`
- `scripts.no_threshold_dials_lint` — DECIDE-04 enforcement, path: `scripts/no_threshold_dials_lint.py`

Type `external` matches the convention for all other `scripts.*` nodes (set by `scripts.no_time_time_lint` in Plan 01-03). `python3 scripts/architecture_lint.py` exits 0.

ARCHITECTURE.md extended with a "Phase 4 additions" section citing `[[ev-cancel-rule]]` and `[[circuit-breakers-v05]]`.

### Wiki Write-back (Engineering Protocol 1)

Filed: `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/wave-0-test-scaffolding-phase4.md`

Status: Current. Contains: test→plan map, conftest fixture signatures, lint script summary, wave-0 invariant, key design decisions captured in tests (Pitfall #4, #6, #7, #8, A1×A3, DECIDE-02 dual branch).

## Wave-0 Verification

```
cd python && uv run pytest tests/ --collect-only -q
→ 258 tests collected, 0 errors (19 Phase 4 tests skip via importorskip)

python3 scripts/no_hardcoded_cancel_cost_lint.py → exit 0
python3 scripts/no_threshold_dials_lint.py → exit 0
python3 scripts/architecture_lint.py → exit 0

cd python && uv run pytest tests/test_fill_model_predict_contract.py tests/test_loss_model_replay.py tests/test_competition_tracker.py -x
→ 15 passed, 1 skipped (existing tests unaffected)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] architecture.yml node type: module → type: external for lint scripts**
- **Found during:** Task 4 verification
- **Issue:** The plan specified `type: module` for the two new lint script nodes in architecture.yml. The `architecture_lint.py` script validates `type: module` nodes by checking that the ID maps to a source file under `python/src/` or `ts/src/`. `scripts/` files don't map to either tree, so the lint reported 4 violations.
- **Fix:** Changed both nodes to `type: external` (matching the existing `scripts.no_time_time_lint` convention from Plan 01-03, which also uses `type: external`).
- **Files modified:** docs/architecture.yml
- **Commit:** 6a98bd3

**2. [Rule 1 - Bug] Typo in test_breaker_fill_rate.py**
- **Found during:** Task 3 (immediately after file creation)
- **Issue:** `from __future__ calls annotations` instead of `from __future__ import annotations` — Python syntax error
- **Fix:** Corrected the import statement
- **Files modified:** python/tests/test_breaker_fill_rate.py
- **Commit:** 85e3eb6

## Known Stubs

None. All test files are pure scaffolding (RED state is the intended output of this plan). No production code stubs.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan is pure test scaffolding and lint script additions.

## Self-Check: PASSED

All 22 created/modified files confirmed present on disk. All 4 task commits verified in git log.
