---
phase: 04-decision-engine-predictive-circuit-breakers
fixed_at: 2026-04-26T00:00:00Z
review_path: .planning/phases/04-decision-engine-predictive-circuit-breakers/04-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 4: Code Review Fix Report

**Fixed at:** 2026-04-26
**Source review:** `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (fix_scope=all — WR-01, WR-02, IN-01, IN-02)
- Fixed: 4 (2 already_fixed from prior pass dd8607b, 2 newly fixed this pass)
- Skipped: 0

## Fixed Issues

### WR-01: `_gas_cache` null-guard at construction time

**Files modified:** `python/src/boros_brain/decision/breakers/maturity.py`
**Commit:** dd8607b (prior pass)
**Status:** already_fixed
**Applied fix:** `if gas_cache is None: raise TypeError(...)` present in `MaturityBreaker.__init__()` (lines 60–65). Converts a confusing mid-`check()` `AttributeError` into a clear `TypeError` at the call site, consistent with the module's documented DECIDE-03 contract.

---

### WR-02: `epoch_days` zero-division guard

**Files modified:** `python/src/boros_brain/decision/breakers/maturity.py`
**Commit:** dd8607b (prior pass)
**Status:** already_fixed
**Applied fix:** `assert config.reward_share_model.epoch_days > 0` with descriptive message present at line 89. The `epoch_days` Pydantic field carries `ge=1.0` so it can never be zero at runtime; the assert documents that reliance explicitly rather than adding dead-code guard logic — the alternative fix path the reviewer endorsed.

---

### IN-01: `market_matured` branch is not covered by any test case

**Files modified:** `python/tests/test_breaker_maturity.py`
**Commit:** 0a18453
**Status:** fixed
**Applied fix:** Added `test_fires_when_market_already_matured` as a fourth async test case. Uses `_config_with_market(default_config, CURRENT_TS - 1)` to place maturity_ts one second in the past, then asserts `tripped=True`, `reason="market_matured"`, and `kill_command_kind="ROLL_POSITION"`. Covers the `time_to_mat_s <= 0` early-return branch (maturity.py lines 82–87) which was previously uncovered by any test.

---

### IN-02: `test_decision_loop_task_created` does not actually call `brain_main.run()` — structural test only

**Files modified:** `python/tests/test_main_decision_loop_spawn.py`
**Commit:** f9900bb
**Status:** fixed
**Applied fix:** Added a `STRUCTURAL PROXY NOTE` block to the docstring of `test_decision_loop_task_created` making explicit that (a) the test runs its own local `_fast_boot` coroutine rather than `brain_main.run()`, (b) the intent is to validate asyncio task-spawn plumbing in isolation, and (c) `test_decision_loop_function_defined` is the primary contract guard for `run()`. Also removed a pre-existing unused `mock_w3 = MagicMock()` assignment (F841) that ruff flagged during the commit hook — a latent issue in the file, not introduced by this change, but required to be cleaned for the commit to pass.

## Skipped Issues

None.

---

_Fixed: 2026-04-26_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
