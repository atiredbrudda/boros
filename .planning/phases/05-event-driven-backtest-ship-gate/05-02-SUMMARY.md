---
phase: 05-event-driven-backtest-ship-gate
plan: 02
subsystem: backtest
tags: [replay, eventIndex, AMM, duckdb, polars, BACK-01]

requires:
  - phase: 05-01
    provides: RED test scaffolds, conftest fixture-factories, BotConfig.backtest SSoT

provides:
  - ReplayEngine (BACK-01): eventIndex-ordered, AMM-conservation, look-ahead-prevented replay
  - BacktestRunOutput, ReplayConfig, ReplayOutput, SyntheticOrderLedger Pydantic schemas
  - SyntheticOrderLedger tracking active synthetic orders keyed by market + side
  - SQL-layer reward-budget lineage filter (LOCKED D-01 / B6 absorption)
  - 5 BACK-01 RED tests turned GREEN: eventIndex sort, AMM conservation, no-lookahead, decision log, lineage filter

affects: [05-03, 05-04, 05-05, 05-06, 05-07, 05-08, 05-09]

tech-stack:
  added: []
  patterns: [event-driven replay via DuckDB SQL, AMM conservation invariant check, look-ahead guard via event watermark]

key-files:
  created:
    - python/src/boros_brain/backtest/replay.py
    - python/src/boros_brain/backtest/schemas.py
    - python/src/boros_brain/backtest/synthetic_orders.py
  modified:
    - python/tests/test_backtest_replay_event_index_order.py
    - python/tests/test_backtest_amm_conservation_replay.py
    - python/tests/test_backtest_no_lookahead.py
    - python/tests/test_backtest_decision_log_per_tick.py
    - python/tests/test_backtest_reward_budget_lineage_filter.py

key-decisions:
  - "eventIndex (not blockTimestamp) for intra-block ordering — load-bearing per CLAUDE.md strategy non-negotiables"
  - "SQL-layer lineage filter: WHERE reward_budget_origin IS NOT NULL at DuckDB query time, not Python post-filter"
  - "AMM conservation checked as invariant after each trade event — violation raises ReplayInvariantError"
  - "Look-ahead prevented by watermark: engine refuses to process events with eventIndex <= last seen"

patterns-established:
  - "ReplayEngine.run() → yields BacktestRunOutput one row per decision tick"
  - "SyntheticOrderLedger: dict[tuple[market_id, side], SyntheticOrder] for O(1) hit detection"

requirements-completed: [BACK-01]

duration: 18min
completed: 2026-04-26
---

# Phase 05-02: Replay Engine Core Summary

**eventIndex-ordered replay engine (BACK-01): AMM conservation, look-ahead prevention, SQL lineage filter, 5 RED→GREEN tests**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-04-26
- **Tasks:** 3 (committed atomically)
- **Files modified:** 8

## Accomplishments

- Landed `replay.py` with `ReplayEngine` class: iterates trade events sorted by `eventIndex`, drives live `decision.engine.evaluate()` + `breaker_coordinator` against historical tape, records every decision the live bot would have made
- Implemented three load-bearing invariants: eventIndex sort (watermark guard), AMM conservation (checked after each event, raises `ReplayInvariantError` on violation), look-ahead prevention (watermark rejects out-of-order events)
- SQL-layer reward-budget lineage filter: `WHERE reward_budget_origin IS NOT NULL` in DuckDB query at read time — not Python post-filter (LOCKED D-01 / B6 absorption)
- Landed `schemas.py` with `BacktestRunOutput`, `ReplayConfig`, `ReplayOutput`, `SyntheticOrderLedger` Pydantic models
- Turned all 5 BACK-01 RED tests GREEN: eventIndex sort, AMM conservation, no-lookahead, decision-log-per-tick, reward-budget lineage filter

## Task Commits

1. **Task 1: schemas.py + synthetic_orders.py** - `a2a2e95` (feat)
2. **Task 2: replay.py — ReplayEngine core** - `12162c5` (feat)
3. **Task 3: 5 BACK-01 RED tests GREEN** - `a5b99a5` (feat)

## Files Created/Modified

- `python/src/boros_brain/backtest/replay.py` — ReplayEngine: BACK-01 core, 638 lines
- `python/src/boros_brain/backtest/schemas.py` — Pydantic schemas: BacktestRunOutput, ReplayConfig, ReplayOutput
- `python/src/boros_brain/backtest/synthetic_orders.py` — SyntheticOrderLedger for O(1) fill detection
- `python/tests/test_backtest_replay_event_index_order.py` — GREEN
- `python/tests/test_backtest_amm_conservation_replay.py` — GREEN
- `python/tests/test_backtest_no_lookahead.py` — GREEN
- `python/tests/test_backtest_decision_log_per_tick.py` — GREEN
- `python/tests/test_backtest_reward_budget_lineage_filter.py` — GREEN

## Decisions Made

- `eventIndex` sort watermark (not sort-then-slice) to minimize memory and enforce streaming invariant
- AMM conservation check uses relative tolerance (1e-9) rather than exact equality for floating-point safety

## Deviations from Plan

None — plan executed as written.

## Issues Encountered

None.

## Next Phase Readiness

- 05-03 (cancel-latency simulation) can proceed: `replay.py` is the entry point it patches
- 05-04 (sweep dispatchers) can proceed once 05-03 is complete
- All 5 BACK-01 tests are GREEN; remaining test files still skip until their modules land

---
*Phase: 05-event-driven-backtest-ship-gate*
*Completed: 2026-04-26*
