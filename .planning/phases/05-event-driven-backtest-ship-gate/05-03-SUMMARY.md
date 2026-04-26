---
phase: 05-event-driven-backtest-ship-gate
plan: 03
subsystem: backtest
tags: [cancel-latency, BACK-02, replay, OU, latency-simulator]

requires:
  - phase: 05-01
    provides: RED test scaffolds, conftest fixtures
  - phase: 05-02
    provides: ReplayEngine, schemas, replay.py — cancel_latency integrates into replay.py

provides:
  - LatencyScheduler (BACK-02): two-axis latency simulator (order-of-event + time-since-event)
  - ScheduledClose: deferred close record carrying fill_ts, close_at_ts, fill_basis, market_id, side
  - ReplayEngine wired to use LatencyScheduler on synthetic order hits
  - close P&L realized at close_at_ts basis NOT fill_ts basis (CLAUDE.md strategy non-negotiable)
  - BACK-02 tests GREEN: cancel_latency_two_axis (14 parametrized), underlying_apr_resolved_at_close_ts_not_fill_ts

affects: [05-04, 05-07, 05-08, 05-09]

tech-stack:
  added: []
  patterns: [ScheduledClose deferred-close pattern, _underlying_at() parquet snapshot lookup]

key-files:
  created:
    - python/src/boros_brain/backtest/cancel_latency.py
  modified:
    - python/src/boros_brain/backtest/replay.py
    - python/tests/test_backtest_cancel_latency_two_axis.py
    - python/tests/test_backtest_no_lookahead.py

key-decisions:
  - "close_at_ts = fill_ts + cancel_latency_budget_s (config knob, default 5.0s) — NOT fill_ts"
  - "_underlying_at() reads underlying_apr parquet with snapshot_ts <= ts ORDER BY snapshot_ts DESC LIMIT 1, falls back to 0.05"
  - "v0.5 fill detection: queue_ahead_wei <= evt_size (simplified approximation per PLAN)"
  - "Deviation: plan template used source='operator_manual' (invalid); corrected to source='dapp_ui'"

patterns-established:
  - "ScheduledClose: immutable dataclass with fill_ts, close_at_ts, fill_basis — fired when current_ts >= close_at_ts"
  - "_fire_scheduled_closes(): processes at-or-past closes in eventIndex order before each decision tick"

requirements-completed: [BACK-02]

duration: 15min
completed: 2026-04-26
---

# Phase 05-03: Cancel-Latency Simulation Summary

**Two-axis latency simulator (BACK-02): ScheduledClose + LatencyScheduler wired into ReplayEngine, close P&L at close_at_ts basis, BACK-02 tests GREEN**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-04-26
- **Tasks:** 3 (committed atomically)
- **Files modified:** 4

## Accomplishments

- Landed `cancel_latency.py` with `ScheduledClose` (immutable deferred-close record) and `LatencyScheduler` (schedules + fires closes by eventIndex watermark)
- Wired `LatencyScheduler` into `ReplayEngine`: `_handle_trade_event` detects fills (v0.5 queue-ahead approximation), schedules `ScheduledClose`; `_fire_scheduled_closes` fires when `current_ts >= close_at_ts`
- Implemented `_underlying_at(ts)`: reads underlying APR parquet snapshot at `ts` (not fill_ts) — enforces CLAUDE.md non-negotiable that close P&L is realized against the basis at `close_at_ts`
- Turned BACK-02 tests GREEN: 14 parametrized cancel-latency tests + underlying-APR-at-close-ts assertion (monkeypatch captures call args, asserts `close_at_ts` basis value used, not `fill_ts` value)

## Task Commits

1. **Task 1: cancel_latency.py — ScheduledClose + LatencyScheduler** - `065bfae` (feat)
2. **Task 2: wire LatencyScheduler into ReplayEngine + BACK-02 tests GREEN** - `4717854` (feat)

## Files Created/Modified

- `python/src/boros_brain/backtest/cancel_latency.py` — ScheduledClose + LatencyScheduler (109 lines)
- `python/src/boros_brain/backtest/replay.py` — _handle_trade_event, _fire_scheduled_closes, _underlying_at wired in (+95 lines)
- `python/tests/test_backtest_cancel_latency_two_axis.py` — 14 parametrized GREEN tests
- `python/tests/test_backtest_no_lookahead.py` — updated for LatencyScheduler presence

## Decisions Made

- `close_at_ts = fill_ts + config.execution.cancel_latency_budget_s` — the L parameter from PLAN
- Parquet fallback: if no underlying APR snapshot found before `close_at_ts`, use 0.05 (5% floor)

## Deviations from Plan

**1. [Rule — Schema correction] source field corrected from 'operator_manual' to 'dapp_ui'**
- Plan template contained `source='operator_manual'` which is not in the allowed sources list
- Corrected to `source='dapp_ui'` per schema validation

## Issues Encountered

None.

## Next Phase Readiness

- Wave 1 complete: ReplayEngine with cancel-latency simulation (BACK-01 + BACK-02) is the foundation for Wave 2 sweeps
- 05-04 (sweep dispatchers) depends on 05-02 + 05-03 — ready to proceed
- Untracked `cancel_latency.py` appeared in main working tree (executor wrote to both worktree and main); resolved by removing duplicate before merge

---
*Phase: 05-event-driven-backtest-ship-gate*
*Completed: 2026-04-26*
