---
phase: 05-event-driven-backtest-ship-gate
plan: 04
subsystem: backtest
tags: [backtest, sweeps, cancel-latency, competition, finite-difference, BACK-03, BACK-04]

# Dependency graph
requires:
  - phase: 05-event-driven-backtest-ship-gate plan 05-02
    provides: ReplayEngine, ReplayConfig, BacktestRunOutput, ReplayOutput
  - phase: 05-event-driven-backtest-ship-gate plan 05-03
    provides: LatencyScheduler + ScheduledClose wired into ReplayEngine
  - phase: 05-event-driven-backtest-ship-gate plan 05-01
    provides: BacktestConfig with cancel_latency_grid + competition_multipliers knobs

provides:
  - run_cancel_latency_sweep: 6-point L grid sweep (BACK-03), one BacktestRunOutput per L value
  - compute_dpnl_dl: central finite-difference dP&L/dL + unexpected_monotonicity warning
  - run_competition_sweep: 6-point m grid sweep (BACK-04), one BacktestRunOutput per m value
  - compute_dpnl_dq: central finite-difference dP&L/dQ + unexpected_monotonicity warning
  - Wave 1 + Wave 2 architecture nodes registered (5 carried-over + 3 new)

affects:
  - 05-05 (feature builder — will wire real features into sweep rows)
  - 05-09 (CLI/ship-gate report — surfaces unexpected_monotonicity flags)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sweep dispatcher pattern: iterate config grid, fresh manifest per child (parent_run_id), tag rows with sweep_axis/sweep_value"
    - "Central finite-difference: forward/backward endpoints, interior central, sign-check with unexpected_monotonicity log"
    - "PROTO-01 D2 guard: build_run_manifest(config, parent_run_id=parent_manifest.run_id) per child run"
    - "Architecture update co-committed with code (PROTOCOL 2 atomic — pre-commit hook enforces)"

key-files:
  created:
    - python/src/boros_brain/backtest/sweeps/__init__.py
    - python/src/boros_brain/backtest/sweeps/cancel_latency.py
    - python/src/boros_brain/backtest/sweeps/competition.py
    - python/tests/test_backtest_sweep_cancel_latency.py
    - python/tests/test_backtest_dpnl_dl_sign.py
    - python/tests/test_backtest_sweep_competition.py
  modified:
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
    - python/src/boros_brain/backtest/replay.py

key-decisions:
  - "Architecture update co-committed with Task 1/2 code (not deferred to Task 4) because pre-commit hook blocks code commits without architecture.yml in sync"
  - "Sweep dispatchers pass flat kwargs to ReplayEngine (not replay_config=) to satisfy mypy — ReplayConfig values unpacked at call site"
  - "Sign tests use synthetic deterministic rows (pnl=-x*0.01) injected directly into compute_dpnl_dl/dq — no engine call needed"
  - "Wave 1 architecture nodes (brain.backtest.config/schemas/synthetic_orders/cancel_latency/replay) registered alongside Wave 2 nodes in single Task 4"

patterns-established:
  - "Sweep child run gets fresh manifest via build_run_manifest(config, parent_run_id=parent.run_id)"
  - "compute_dpnl_dl/dq: forward diff at i=0, backward at i=n-1, central elsewhere"
  - "unexpected_monotonicity: one warning per sweep on first reversal; breaks after first to avoid log flood"

requirements-completed: [BACK-03, BACK-04]

# Metrics
duration: 7min
completed: 2026-04-26
---

# Phase 05 Plan 04: Sweep Dispatchers Summary

**Cancel-latency sweep (BACK-03) and competition sweep (BACK-04) with central-finite-difference dP&L/dL and dP&L/dQ curves, fresh per-child-run manifests (PROTO-01), and full Wave 1+2 architecture registration**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-26T16:22:42Z
- **Completed:** 2026-04-26T16:29:19Z
- **Tasks:** 4 (Tasks 1+2+4 combined in one commit due to pre-commit hook constraint; Task 3 separate)
- **Files modified:** 9

## Accomplishments

- `run_cancel_latency_sweep`: iterates `config.backtest.cancel_latency_grid` (default 6 points), each child run gets fresh manifest with `parent_run_id`, rows tagged `sweep_axis="cancel_latency"`
- `run_competition_sweep`: structural twin iterating `config.backtest.competition_multipliers`, `sigma_others_multiplier=m` substitution via `dataclasses.replace`
- `compute_dpnl_dl` / `compute_dpnl_dq`: central finite-difference with forward/backward endpoint handling; `_check_monotonicity` emits `unexpected_monotonicity` warning on first reversal
- All 6 BACK-03/04 tests GREEN; full suite 356 passed, 12 skipped
- Architecture lint exits 0: cleared 5 Wave 1 violations (brain.backtest.config/schemas/synthetic_orders/cancel_latency/replay) + registered 3 Wave 2 nodes

## Task Commits

1. **Tasks 1+2+4: sweep dispatchers + architecture update** - `698d7d4` (feat)
   - sweeps/__init__.py, cancel_latency.py, competition.py
   - docs/architecture.yml (Wave 1 + Wave 2 nodes + edges)
   - docs/ARCHITECTURE.md (phase5_wave1 + phase5_wave2_sweeps subgraphs)
   - replay.py (Rule 1 fixes: getattr + yield from)
2. **Task 3: turn BACK-03/04 RED tests GREEN** - `2b1682e` (feat)
   - 3 test files implemented and passing

## Files Created/Modified

- `python/src/boros_brain/backtest/sweeps/__init__.py` - Package marker documenting all 4 sweep dispatchers
- `python/src/boros_brain/backtest/sweeps/cancel_latency.py` - BACK-03: run_cancel_latency_sweep + compute_dpnl_dl + _check_monotonicity
- `python/src/boros_brain/backtest/sweeps/competition.py` - BACK-04: run_competition_sweep + compute_dpnl_dq + _check_monotonicity
- `python/tests/test_backtest_sweep_cancel_latency.py` - 3 tests: emits-6-rows, uses-config-grid, parent_run_id
- `python/tests/test_backtest_dpnl_dl_sign.py` - 1 test: synthetic always-fills slopes < 0
- `python/tests/test_backtest_sweep_competition.py` - 2 tests: emits-6-rows + dpnl/dq sign
- `docs/architecture.yml` - Wave 1 (5 nodes) + Wave 2 (3 nodes) + 13 edges
- `docs/ARCHITECTURE.md` - phase5_wave1 + phase5_wave2_sweeps Mermaid subgraphs
- `python/src/boros_brain/backtest/replay.py` - Rule 1 fixes (getattr, yield from)

## Decisions Made

- Architecture update co-committed with Task 1/2 code because pre-commit hook enforces same-commit architecture sync (PROTOCOL 2). Task 4 content landed in Task 1 commit — documented as deviation.
- Sweep dispatchers pass flat kwargs to `ReplayEngine` (not `replay_config=`) to satisfy mypy's exhaustive required-arg check. `ReplayConfig` fields are unpacked at call site.
- Sign tests use synthetic deterministic rows injected directly into `compute_dpnl_dl`/`compute_dpnl_dq` — no engine call needed for correctness proof.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mypy error: cancel_cost_default_pendle does not exist on DecisionEngineConfig**
- **Found during:** Task 1 (pre-commit hook failed on first commit attempt)
- **Issue:** `replay.py:150` used `self.config.decision.cancel_cost_default_pendle` which mypy flagged as `attr-defined` error. The attribute doesn't exist in `DecisionEngineConfig`; code had `except AttributeError` fallback but mypy caught the reference.
- **Fix:** Replaced `try/except` with `getattr(self.config.decision, "cancel_cost_default_pendle", None)` guard
- **Files modified:** `python/src/boros_brain/backtest/replay.py`
- **Committed in:** `698d7d4`

**2. [Rule 1 - Bug] ruff UP028: replace yield-in-for-loop with yield from**
- **Found during:** Task 1 (pre-commit ruff hook)
- **Issue:** `replay.py:191` used `for row in df.iter_rows(named=True): yield row` — ruff UP028 flag
- **Fix:** Replaced with `yield from df.iter_rows(named=True)`
- **Files modified:** `python/src/boros_brain/backtest/replay.py`
- **Committed in:** `698d7d4`

**3. [Rule 3 - Blocking] Architecture update co-committed with Tasks 1+2 (not deferred to Task 4)**
- **Found during:** Task 1 (pre-commit architecture-lint hook blocked commit)
- **Issue:** Pre-commit hook enforces architecture.yml must be in sync with every code commit. Tasks 1+2 added new modules; hook blocked without architecture update.
- **Fix:** Updated docs/architecture.yml and docs/ARCHITECTURE.md in same commit as Task 1+2 files. Wave 1 + Wave 2 nodes added together.
- **Impact:** Task 4 content delivered earlier than planned (in Task 1 commit). No correctness impact.
- **Committed in:** `698d7d4`

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 3)
**Impact on plan:** All auto-fixes necessary for correctness and compliance. Task reordering (Task 4 content in Task 1 commit) is purely cosmetic — all content was delivered.

## Issues Encountered

None beyond the deviations documented above.

## Known Stubs

None — all sweep dispatchers are fully wired to ReplayEngine. Rows emitted with real engine output (even if P&L is zero on minimal fixtures due to no fills in 1-tick parquet).

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All sweep child runs are in-process calls to ReplayEngine with no external I/O beyond what the engine already does.

## Next Phase Readiness

- Plan 05-05 (feature builder) can now call `run_cancel_latency_sweep` / `run_competition_sweep` with real calibration data
- `unexpected_monotonicity` warnings wired and ready for Plan 05-09 ship-gate report to surface
- Plans 05-06 (forfeit_branch sweep) and 05-08 (perturbation sweep) follow the same pattern as this plan

## Self-Check: PASSED

Files exist:
- `python/src/boros_brain/backtest/sweeps/__init__.py` ✓
- `python/src/boros_brain/backtest/sweeps/cancel_latency.py` ✓
- `python/src/boros_brain/backtest/sweeps/competition.py` ✓

Commits exist:
- `698d7d4` ✓
- `2b1682e` ✓

Architecture lint: exits 0 ✓

---
*Phase: 05-event-driven-backtest-ship-gate*
*Completed: 2026-04-26*
