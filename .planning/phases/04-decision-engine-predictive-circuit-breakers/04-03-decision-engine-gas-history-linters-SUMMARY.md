---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 03
subsystem: decision
tags: [decision-engine, gas-history, ewma, lint, ev-cancel-rule, architecture]

requires:
  - phase: 04-02-foundation-schema-migration-writers
    provides: EvaluateInput/Output schemas, DecisionConfig, Breaker ABC, BotConfig delta

provides:
  - engine.evaluate() implementing the EV cancel rule (DECIDE-01/02): composes predict() + expected_loss() + r_capped_curve() + cancel_cost_pendle()
  - GasHistoryCache EWMA cancel_cost_pendle() (DECIDE-03)
  - Hardened no_hardcoded_cancel_cost_lint.py and no_threshold_dials_lint.py — both exit 0 on clean tree, error on violations (DECIDE-04)
  - Architecture nodes registered for engine.py and gas_history.py

affects: [04-06-coordinator-mainpy-predeploy-gate-shipgate]

tech-stack:
  added: []
  patterns: [EV-cancel rule composition, EWMA gas history, lint enforcement via AST walk]

key-files:
  created:
    - python/src/boros_brain/decision/engine.py
    - python/src/boros_brain/decision/gas_history.py
  modified:
    - scripts/no_hardcoded_cancel_cost_lint.py
    - scripts/no_threshold_dials_lint.py
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
    - python/tests/conftest.py
    - python/tests/test_decision_engine_ev_equation.py
    - python/tests/test_decision_engine_voluntary_branch.py
    - python/tests/test_gas_history_ewma.py
    - python/tests/test_no_threshold_dials_lint.py

key-decisions:
  - "engine.evaluate() is async and composes Phase 2/3 callables via injected protocol interfaces — no direct imports from reward_model or fill_model to keep decision layer decoupled"
  - "GasHistoryCache uses EWMA (alpha from BotConfig) over recent gas price samples, not a rolling mean"
  - "Lint scripts use AST walk to detect hardcoded cancel costs and threshold dials — pattern is portable to CI"

patterns-established:
  - "EV cancel rule: EV_hold = R_share * P(no_fill) - E[loss|fill] * P(fill) - cancel_cost * P(purge); cancel iff EV_hold < 0"
  - "voluntary_cancel_forfeits_accumulated branch toggle controlled via DecisionConfig.voluntary_cancel_forfeits_accumulated"

requirements-completed: [DECIDE-01, DECIDE-02, DECIDE-03, DECIDE-04]

duration: ~22min
completed: 2026-04-25
---

# Phase 04-03: Decision Engine, Gas History, Linters Summary

**engine.evaluate() EV cancel rule + GasHistoryCache EWMA cancel_cost_pendle + hardened lint scripts — DECIDE-01..04 RED tests now GREEN**

## Performance

- **Duration:** ~22 min
- **Completed:** 2026-04-25
- **Tasks:** 5 (3 feature + 1 architecture + 1 lint tightening)
- **Files modified:** 10

## Accomplishments
- `engine.evaluate()` implements the EV cancel rule composing Phase 2 predict() + Phase 3 expected_loss() + r_capped_curve() + gas_history.cancel_cost_pendle() with voluntary_cancel_forfeits_accumulated branch toggle
- `GasHistoryCache` computes EWMA cancel_cost_pendle() from recent gas price history (DECIDE-03)
- `no_hardcoded_cancel_cost_lint.py` and `no_threshold_dials_lint.py` hardened to exit non-zero on violations, exit 0 on clean tree — lint test now GREEN
- Architecture nodes for engine and gas_history registered in architecture.yml + ARCHITECTURE.md

## Task Commits

1. **Task 1: GasHistoryCache EWMA cancel_cost** — `2c4fb1f`
2. **Task 2: Harden lint scripts + turn lint test GREEN** — `962cccc`
3. **Task 3: engine.evaluate() EV cancel rule** — `bc9d3f5`
4. **Task 4: Architecture nodes** — `199893e` (recovery commit)

## Files Created/Modified
- `python/src/boros_brain/decision/engine.py` — async evaluate() implementing EV cancel rule
- `python/src/boros_brain/decision/gas_history.py` — GasHistoryCache with EWMA cancel_cost_pendle()
- `scripts/no_hardcoded_cancel_cost_lint.py` — hardened to detect violations
- `scripts/no_threshold_dials_lint.py` — hardened to detect violations
- `docs/architecture.yml` — engine + gas_history nodes registered
- `docs/ARCHITECTURE.md` — engine + gas_history nodes registered

## Decisions Made
- engine.evaluate() uses injected protocol interfaces for predict() and expected_loss() — no direct coupling to reward_model or fill_model modules
- GasHistoryCache EWMA alpha configurable via DecisionConfig (not hardcoded)

## Deviations from Plan

### Auto-fixed Issues

**1. Architecture nodes uncommitted before agent returned**
- **Found during:** Orchestrator spot-check
- **Issue:** docs/ARCHITECTURE.md and docs/architecture.yml had 69 lines of uncommitted changes when agent returned
- **Fix:** Orchestrator committed them as recovery commit 199893e
- **Files modified:** docs/architecture.yml, docs/ARCHITECTURE.md

---

**Total deviations:** 1 auto-fixed (uncommitted architecture changes)
**Impact on plan:** No scope impact; all planned code was delivered correctly.

## Issues Encountered
- Agent completed 113 tool calls but returned "Prompt is too long" — architecture commit and SUMMARY.md recovered by orchestrator

## Self-Check: PASSED

---
*Phase: 04-decision-engine-predictive-circuit-breakers*
*Completed: 2026-04-25*
