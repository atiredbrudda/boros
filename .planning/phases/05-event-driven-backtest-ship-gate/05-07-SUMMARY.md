---
phase: 05-event-driven-backtest-ship-gate
plan: 07
subsystem: backtest
tags: [backtest, bootstrap, ship-gate, BACK-07, determinism, pitfall-6]

# Dependency graph
requires:
  - phase: 05-event-driven-backtest-ship-gate plan 05-01
    provides: BacktestConfig (bootstrap_n_resamples, bootstrap_block_seconds, all_fees_threshold)
  - phase: 05-event-driven-backtest-ship-gate plan 05-02
    provides: schemas.py (StrictBase, BacktestRunOutput)
  - phase: 05-event-driven-backtest-ship-gate plan 05-05
    provides: write_ship_gate_verdict_json (consumes ShipGateVerdict shape)

provides:
  - bootstrap.py: seed_from_manifest, make_rng, block_bootstrap_pnl (BACK-07)
  - ship_gate.py: ShipGateHalt, assemble_threshold, evaluate_ship_gate, write_ship_gate_report
  - schemas.py extended: ThresholdComponents + ShipGateVerdict (frozen StrictBase)
  - 4 BACK-07 RED tests GREEN (374 passed / 6 skipped)

affects:
  - 05-09 (CLI raises ShipGateHalt when verdict.passed=False)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ulid.ULID.from_str(run_id) — class method, not module-level function (python-ulid API)"
    - "np.random.default_rng(seed) with explicit Generator passed to block_bootstrap_pnl — PITFALL #6 prevention"
    - "ShipGateHalt(SystemExit) mirrors ProjectHalt pattern from screener/economics_gate.py"
    - "evaluate_ship_gate is pure (no I/O) — CLI in 05-09 inspects verdict.passed and raises"

key-files:
  created:
    - python/src/boros_brain/backtest/bootstrap.py
    - python/src/boros_brain/backtest/ship_gate.py
  modified:
    - python/src/boros_brain/backtest/schemas.py
    - docs/architecture.yml
    - docs/ARCHITECTURE.md

key-decisions:
  - "ulid.ULID.from_str() not ulid.from_str() — python-ulid library exposes from_str as a class method on ULID, not a module-level function"
  - "evaluate_ship_gate is pure (no I/O, no halt) — plan spec confirmed; CLI in 05-09 raises ShipGateHalt(SystemExit) when passed=False"
  - "All tasks committed atomically — pre-commit architecture-lint blocks any commit that introduces an undeclared module without docs/architecture.yml update (same pattern as Plans 05-04/05-05/05-06)"

requirements-completed: [BACK-07]

# Metrics
duration: 5min
completed: 2026-04-26
---

# Phase 05 Plan 07: Bootstrap + Ship-Gate Verdict Summary

**Block-bootstrap (N=2000, block_seconds=86400) over per-day P&L seeded deterministically from RUN_MANIFEST.run_id ULID tail; 5th-percentile annualized P&L vs alt_yield + all_fees threshold (default 0.06); pass/fail Markdown report; PITFALL #6 (explicit RNG) enforced architecturally**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-26T16:50:34Z
- **Completed:** 2026-04-26T16:54:11Z
- **Tasks:** 4 (committed atomically — pre-commit architecture-lint enforcement)
- **Files modified:** 5

## Accomplishments

- `bootstrap.py`: `seed_from_manifest` (ULID tail bytes → uint64 via `int.from_bytes(..., 'big') & ((1<<64)-1)`), `make_rng` (returns `np.random.default_rng(seed)`), `block_bootstrap_pnl` (N=2000 day-resamples with explicit Generator)
- `ship_gate.py`: `ShipGateHalt(SystemExit)` mirrors `screener.economics_gate.ProjectHalt`; `assemble_threshold` sums `config.screener.alt_yield + config.backtest.all_fees_threshold`; `evaluate_ship_gate` is a pure function (no I/O, no halt — testable in isolation); `write_ship_gate_report` writes Markdown with status PASSED/FAILED + threshold components + manifest excerpt + full BotConfig JSON knob tree
- `schemas.py` extended with `ThresholdComponents` (alt_yield, all_fees, total, components dict) and `ShipGateVerdict` (p5_annualized_pnl, threshold, passed, n_resamples, block_seconds, seed, manifest_run_id) — both frozen StrictBase
- 4 previously RED/skipped BACK-07 tests turned GREEN: `test_backtest_bootstrap_idempotent.py` (3 tests), `test_backtest_ship_gate_threshold_assembly.py` (3 tests), `test_backtest_ship_gate_pass_path.py` (1 test), `test_backtest_ship_gate_fail_path.py` (1 test)
- Full suite: 374 passed, 6 skipped (up from 366/10 in Plan 05-06)
- Architecture: `brain.backtest.bootstrap` + `brain.backtest.ship_gate` nodes + 7 edges added to `docs/architecture.yml` + `phase5_wave3_shipgate` subgraph in `docs/ARCHITECTURE.md` (PROTOCOL 2)
- Architecture lint exits 0

## Task Commits

1. **Tasks 1+2+3+4: bootstrap.py + ship_gate.py + schemas extension + BACK-07 tests GREEN + architecture update** — `b37944f` (feat)
   - python/src/boros_brain/backtest/bootstrap.py (created)
   - python/src/boros_brain/backtest/ship_gate.py (created)
   - python/src/boros_brain/backtest/schemas.py (ThresholdComponents + ShipGateVerdict appended)
   - docs/architecture.yml (brain.backtest.bootstrap + brain.backtest.ship_gate nodes + 7 edges)
   - docs/ARCHITECTURE.md (phase5_wave3_shipgate subgraph)

## Files Created/Modified

- `python/src/boros_brain/backtest/bootstrap.py` — 3 public functions: `seed_from_manifest`, `make_rng`, `block_bootstrap_pnl`; ~55 LoC
- `python/src/boros_brain/backtest/ship_gate.py` — 4 public exports: `ShipGateHalt`, `assemble_threshold`, `evaluate_ship_gate`, `write_ship_gate_report`; ~160 LoC
- `python/src/boros_brain/backtest/schemas.py` — +`ThresholdComponents`, +`ShipGateVerdict`, `__all__` updated
- `docs/architecture.yml` — Plan 05-07 nodes (brain.backtest.bootstrap, brain.backtest.ship_gate) + 7 edges
- `docs/ARCHITECTURE.md` — phase5_wave3_shipgate subgraph

## Decisions Made

- `ulid.ULID.from_str(run_id)` not `ulid.from_str(run_id)` — the plan specified `ulid.from_str()` but the installed python-ulid library exposes `from_str` as a class method on `ULID`, not a module-level function. Auto-fixed (Rule 1) on first test run.
- All tasks committed atomically because the pre-commit architecture-lint hook blocks any commit that introduces an undeclared module. Adding `bootstrap.py` + `ship_gate.py` requires `docs/architecture.yml` to be updated in the same commit (same constraint as Plans 05-04, 05-05, 05-06).
- `evaluate_ship_gate` is deliberately pure (no I/O, no halt). The CLI (Plan 05-09) inspects `verdict.passed` and raises `ShipGateHalt(SystemExit)` with exit code 1. This keeps the function testable in isolation without mocking filesystem or process exit.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `ulid.from_str()` is not a module-level function**
- **Found during:** Task 3 (first test run — `AttributeError: module 'ulid' has no attribute 'from_str'`)
- **Issue:** Plan specified `ulid.from_str(manifest.run_id)` but the installed python-ulid package exposes `from_str` as a class method: `ulid.ULID.from_str(run_id)`.
- **Fix:** Changed `ulid.from_str(manifest.run_id)` → `ulid.ULID.from_str(manifest.run_id)` in `bootstrap.py`.
- **Files modified:** `python/src/boros_brain/backtest/bootstrap.py`
- **Committed in:** `b37944f`

**Total deviations:** 1 auto-fixed (Rule 1 bug in plan's suggested implementation)
**Impact on plan:** Zero behavioral change — `ULID.from_str` produces identical byte representation.

## Threat Model Mitigations Applied

- **T-05-08 (Repudiation — RNG seed drift):** `seed_from_manifest` is deterministic from ULID bytes; `test_seed_from_manifest_is_deterministic` + `test_same_manifest_yields_same_p5` assert idempotence.
- **T-05-16 (Tampering — top-level numpy.random.* contamination):** `block_bootstrap_pnl` signature requires explicit `rng: np.random.Generator`; never imports `numpy.random.choice`; `test_explicit_rng_no_global_state_contamination` guards.
- **T-05-17 (Info disclosure — silent pass on fail path):** `evaluate_ship_gate` returns `ShipGateVerdict.passed` bool; `write_ship_gate_report` writes Markdown on either branch; CLI in Plan 05-09 raises `ShipGateHalt(SystemExit)` with exit 1 when `passed=False`.

## Known Stubs

None — `bootstrap.py` and `ship_gate.py` are fully implemented. `ShipGateHalt` raise is deferred to the CLI (Plan 05-09) by design (evaluate_ship_gate is pure).

## Wiki Pages

Wiki pages cited in source:
- `[[backtest-bootstrap-methodology-v05]]` — in `bootstrap.py` module docstring and `ship_gate.py`
- `[[backtest-ship-gate-threshold-assembly]]` — in `schemas.py` ThresholdComponents docstring and `ship_gate.py`
- `[[backtest-reproducibility-rng-seed-from-manifest]]` — in `bootstrap.py` module docstring

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced beyond what the plan's threat model covers. `write_ship_gate_report` writes to `var/backtest/<run_id>/ship-gate-report.md` — this is the intended file-write path documented in the plan.

## Self-Check: PASSED

Files exist:
- `python/src/boros_brain/backtest/bootstrap.py` — checked
- `python/src/boros_brain/backtest/ship_gate.py` — checked
- `python/src/boros_brain/backtest/schemas.py` (ShipGateVerdict + ThresholdComponents present) — checked
- `docs/architecture.yml` (brain.backtest.bootstrap + brain.backtest.ship_gate nodes present) — checked
- `docs/ARCHITECTURE.md` (phase5_wave3_shipgate present) — checked

Commits exist:
- `b37944f` — checked (git log confirms)

Architecture lint: exits 0 — checked
Full test suite: 374 passed, 6 skipped — checked

---
*Phase: 05-event-driven-backtest-ship-gate*
*Completed: 2026-04-26*
