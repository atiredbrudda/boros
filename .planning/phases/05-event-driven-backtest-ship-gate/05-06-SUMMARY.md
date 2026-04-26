---
phase: 05-event-driven-backtest-ship-gate
plan: 06
subsystem: backtest
tags: [backtest, voluntary-cancel, sensitivity-sweep, sanity-check, BACK-06]

# Dependency graph
requires:
  - phase: 05-event-driven-backtest-ship-gate plan 05-02
    provides: BacktestRunOutput schema (schemas.py), ReplayConfig, ReplayOutput
  - phase: 05-event-driven-backtest-ship-gate plan 05-04
    provides: structural twin pattern (cancel_latency.py sweep runner)

provides:
  - run_forfeit_branch_sweep: 2-row A/B sweep over voluntary_cancel_forfeits_accumulated in {False=benign, True=punitive}
  - forfeit_branch.sanity_check_pass log: divergence < 10% threshold
  - forfeit_branch_load_bearing log: divergence >= 10% — operator signal for opportunistic contract-trace, NOT an auto-ship-gate-fail
  - BACK-06 tests GREEN (3 tests: two_branches_produced, divergence_under_threshold, divergence_over_threshold)

affects:
  - 05-07 (ship-gate evaluator ignores forfeit_branch_load_bearing — not a blocker)
  - 05-09 (CLI references forfeit_branch rows in parquet output)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Literal-typed branch list to satisfy mypy on dataclasses.replace — list[tuple[Literal['benign','punitive'], bool]]"
    - "structlog.testing.capture_logs() for asserting structured log events in tests (not caplog)"
    - "model_copy(update={...}) on frozen Pydantic StrictBase to create child BotConfig per branch"

key-files:
  created:
    - python/src/boros_brain/backtest/sweeps/forfeit_branch.py
  modified:
    - python/tests/test_backtest_voluntary_cancel_sensitivity.py
    - docs/architecture.yml
    - docs/ARCHITECTURE.md

key-decisions:
  - "P0-01 LOCKED 2026-04-23: voluntary_cancel_forfeits_accumulated=False by default. BACK-06 is a sanity check, not a blocker."
  - "structlog.testing.capture_logs() used in tests instead of caplog — more reliable for structured log event key assertions than stdlib caplog integration"
  - "All 3 tasks committed atomically due to pre-commit architecture-lint enforcement (same pattern as Plans 05-04/05-05)"
  - "Literal-typed branch list resolves mypy arg-type error on dataclasses.replace with Literal field in frozen dataclass"

requirements-completed: [BACK-06]

# Metrics
duration: 4min
completed: 2026-04-26
---

# Phase 05 Plan 06: Voluntary-Cancel Sensitivity Sweep Summary

**Two-row A/B sweep (BACK-06) over voluntary_cancel_forfeits_accumulated in {benign=False, punitive=True}: logs forfeit_branch.sanity_check_pass when divergence < 10%, forfeit_branch_load_bearing when >= 10% — never auto-fails ship-gate**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-26T16:42:32Z
- **Completed:** 2026-04-26T16:46:38Z
- **Tasks:** 3 (committed atomically — pre-commit architecture-lint enforcement)
- **Files modified:** 4

## Accomplishments

- `run_forfeit_branch_sweep`: structural twin of `cancel_latency.py`; iterates `[("benign", False), ("punitive", True)]`; builds child `BotConfig` via `model_copy(update={"strategy": ...})` (frozen Pydantic); tags each output row with `sweep_axis="forfeit_branch"`, `sweep_value=branch_name`, `voluntary_cancel_branch=branch_name`, `parent_run_id`
- Divergence check: `abs(benign.annualized_pnl_pct - punitive.annualized_pnl_pct)` vs `config.backtest.voluntary_cancel_divergence_warn_pct` (default 0.10)
- `forfeit_branch.sanity_check_pass` logged at INFO when divergence < threshold — P0-01 official-statement evidence intact
- `forfeit_branch_load_bearing` logged at WARNING when divergence >= threshold — operator signal for opportunistic contract-trace of `cancelOrder()` in pendle-finance/boros-core-public; NOT an auto-ship-gate-fail
- 3 previously RED stubs in `test_backtest_voluntary_cancel_sensitivity.py` turned GREEN
- Full suite: 366 passed, 10 skipped (up from 363/11 in Plan 05-05)
- Architecture: `brain.backtest.sweeps.forfeit_branch` module node + 3 edges added to `docs/architecture.yml` + `bt_sweeps_forfeit` Mermaid node in `docs/ARCHITECTURE.md` (PROTOCOL 2)
- Architecture lint exits 0

## Task Commits

1. **Tasks 1+2+3: forfeit_branch.py + BACK-06 tests GREEN + architecture update** — `da2c43a` (feat)
   - python/src/boros_brain/backtest/sweeps/forfeit_branch.py (created)
   - python/tests/test_backtest_voluntary_cancel_sensitivity.py (RED stubs replaced with GREEN tests)
   - docs/architecture.yml (brain.backtest.sweeps.forfeit_branch node + 3 edges)
   - docs/ARCHITECTURE.md (bt_sweeps_forfeit node added to phase5_wave2_sweeps subgraph)

## Files Created/Modified

- `python/src/boros_brain/backtest/sweeps/forfeit_branch.py` — 1 public function: `run_forfeit_branch_sweep`; ~115 LoC including type annotation fix
- `python/tests/test_backtest_voluntary_cancel_sensitivity.py` — 3 tests: two_branches_produced, divergence_under_threshold_logs_sanity_pass, divergence_over_threshold_emits_followup_flag
- `docs/architecture.yml` — Plan 05-06 node (brain.backtest.sweeps.forfeit_branch) + 3 edges
- `docs/ARCHITECTURE.md` — bt_sweeps_forfeit in phase5_wave2_sweeps subgraph

## Decisions Made

- All tasks committed atomically because the pre-commit architecture-lint hook blocks any commit that introduces an undeclared module. Adding `forfeit_branch.py` requires `docs/architecture.yml` to be updated in the same commit (same constraint as Plans 05-04 and 05-05).
- `structlog.testing.capture_logs()` used for log assertions instead of pytest `caplog`. The project's structlog configuration routes through a `WriteLoggerFactory` rather than stdlib logging, so `caplog` does not reliably capture structured events. `capture_logs()` intercepts at the structlog layer and returns the raw event dicts.
- Branch list typed as `list[tuple[Literal["benign", "punitive"], bool]]` to satisfy mypy's `arg-type` check on `dataclasses.replace` when the target field is `Literal["benign", "punitive"]`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's ReplayEngine(replay_config=cfg, ...) call fails — flat kwargs required**
- **Found during:** Task 1 (first test run)
- **Issue:** The plan's suggested implementation used `ReplayEngine(replay_config=cfg, run_id=..., manifest=...)` but the constructor requires all flat kwargs (`config`, `market_id`, `side`, `parquet_root`, `sqlite_path`, `cancel_latency_s`) even when `replay_config` is also passed. The `replay_config` path only overrides values after the constructor's signature validation.
- **Fix:** Switched to the same flat-kwargs pattern used by `cancel_latency.py`: unpack `cfg.*` fields directly.
- **Files modified:** `python/src/boros_brain/backtest/sweeps/forfeit_branch.py`
- **Committed in:** `da2c43a`

**2. [Rule 1 - Bug] Plan's fake_run uses self.replay_config.voluntary_cancel_branch — attribute doesn't exist**
- **Found during:** Task 2 (first test run — AttributeError)
- **Issue:** The plan's suggested test stub accessed `self.replay_config.voluntary_cancel_branch` but `ReplayEngine` stores the value as `self.voluntary_cancel_branch` (flat attribute).
- **Fix:** Changed all three `fake_run` stubs to `self.voluntary_cancel_branch`.
- **Files modified:** `python/tests/test_backtest_voluntary_cancel_sensitivity.py`
- **Committed in:** `da2c43a`

**3. [Rule 1 - Bug] mypy arg-type error on dataclasses.replace with str branch_name**
- **Found during:** Task 1 (pre-commit mypy hook)
- **Issue:** `branches = [("benign", False), ("punitive", True)]` inferred as `list[tuple[str, bool]]`; `dataclasses.replace(base_run, voluntary_cancel_branch=branch_name)` with `str` fails mypy because the field is `Literal["benign", "punitive"]`.
- **Fix:** Added `from typing import Literal` and typed the list as `list[tuple[Literal["benign", "punitive"], bool]]`.
- **Files modified:** `python/src/boros_brain/backtest/sweeps/forfeit_branch.py`
- **Committed in:** `da2c43a`

**Total deviations:** 3 auto-fixed (3 Rule 1 bugs in plan's suggested implementation)
**Impact on plan:** All auto-fixes necessary for correctness. No behavioral changes — the sweep logic, divergence check, and log events are exactly as specified.

## Known Stubs

None — `run_forfeit_branch_sweep` is fully implemented. The `forfeit_branch_load_bearing` log event surfaces in the Plan 05-09 ship-gate report consumer as specified.

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced. Threat model mitigations from plan frontmatter applied:
- T-05-14: `model_copy` creates a new frozen instance — no in-place mutation of `voluntary_cancel_forfeits_accumulated` default.
- T-05-15: `log.warning("forfeit_branch_load_bearing", ...)` surfaces material divergence; not silently ignored.

## Wiki Page

Wiki page `[[backtest-voluntary-cancel-sensitivity-row]]` cited in `forfeit_branch.py` module docstring and in the test file. Existing page `[[Voluntary cancel reward behavior]]` also cited (P0-01 resolution). Filing is required per PROTOCOL 1.

## Self-Check: PASSED

Files exist:
- `python/src/boros_brain/backtest/sweeps/forfeit_branch.py` — checked
- `python/tests/test_backtest_voluntary_cancel_sensitivity.py` — checked (3 GREEN tests)
- `docs/architecture.yml` (brain.backtest.sweeps.forfeit_branch node present) — checked
- `docs/ARCHITECTURE.md` (bt_sweeps_forfeit present) — checked

Commits exist:
- `da2c43a` — checked (git log confirms)

Architecture lint: exits 0 — checked
Full test suite: 366 passed, 10 skipped — checked

---
*Phase: 05-event-driven-backtest-ship-gate*
*Completed: 2026-04-26*
