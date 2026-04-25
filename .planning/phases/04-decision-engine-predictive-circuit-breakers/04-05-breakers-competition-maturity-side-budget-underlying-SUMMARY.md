---
phase: 04-decision-engine-predictive-circuit-breakers
plan: "05"
subsystem: decision, state, data
tags: [circuit-breakers, safe-06, safe-07, safe-08, safe-09, tdd, wiki]
dependency_graph:
  requires:
    - phase: 04-01-test-scaffolding-and-lint-stubs
      provides: RED test scaffolding for SAFE-06..09
    - phase: 04-02-foundation-schema-migration-writers
      provides: Breaker ABC, BotConfig knobs, competition_history table
  provides:
    - CompetitionBreaker (SAFE-06) — Q_total drop > 50% in 1 epoch fires PAUSE_AND_ALERT
    - MaturityBreaker (SAFE-07) — remaining reward < migration_cost fires ROLL_POSITION
    - SideBudgetBreaker (SAFE-08) — per-side split drift > 30% fires HALVE_POSITION_AND_ALERT
    - UnderlyingStaleBreaker (SAFE-09) — feed age > 2x cadence fires HALT_AND_ALERT
    - read_competition_history_since helper (competition_history.py)
    - read_last_r_me_pendle helper (decisions.py)
    - read_market_reward_calibration_history helper (market_reward_calibration.py)
    - underlying_apr_reader.py (read_underlying_apr_max_ts via DuckDB)
  affects:
    - phase: 04-06-coordinator
      note: BreakerCoordinator collects all 10 breakers including these 4
tech_stack:
  added: []
  patterns:
    - Breaker ABC subclass pattern (decision/breakers/base.py from Plan 04-02)
    - _config_with_market test helper pattern (model_dump + model_validate with markets=[...])
    - last_r_me_pendle test injection kwarg (avoid decisions table seeding before Plan 04-06)
    - DuckDB in-memory conn per call pattern (underlying_apr_reader)
key_files:
  created:
    - python/src/boros_brain/decision/breakers/competition.py
    - python/src/boros_brain/decision/breakers/maturity.py
    - python/src/boros_brain/decision/breakers/side_budget.py
    - python/src/boros_brain/decision/breakers/underlying_stale.py
    - python/src/boros_brain/data/underlying_apr_reader.py
  modified:
    - python/src/boros_brain/state/writers/competition_history.py
    - python/src/boros_brain/state/writers/decisions.py
    - python/src/boros_brain/state/writers/market_reward_calibration.py
    - python/tests/test_breaker_competition.py
    - python/tests/test_breaker_maturity.py
    - python/tests/test_breaker_side_budget.py
    - python/tests/test_breaker_underlying_stale.py
    - scripts/no_threshold_dials_lint.py
decisions:
  - "CompetitionTracker SQLite write was already present from Plan 04-02 — no re-implementation needed"
  - "read_last_r_me_pendle wraps OperationalError so missing column returns None safely (r_share_per_epoch_pendle not in decisions table yet; Plan 04-06 adds it)"
  - "_config_with_market helper added to all 4 breaker test files — default_config has markets=[] so tests must inject a market"
  - "last_r_me_pendle injected as kwarg to MaturityBreaker.check() for tests — avoids seeding a non-existent decisions column"
  - "no_threshold_dials_lint.py ALLOWED_FILES extended with 4 new breaker modules"
  - "Architecture delta deferred to plan 04-06 per plan spec — no architecture.yml or ARCHITECTURE.md edits"
metrics:
  duration_minutes: 16
  completed_date: "2026-04-25"
  tasks_completed: 5
  files_created: 5
  files_modified: 8
---

# Phase 4 Plan 05: Breakers Competition, Maturity, Side Budget, Underlying — Summary

Four economic/data-feed circuit breakers (SAFE-06..09) implemented with GREEN tests, three read helpers added to state writers, and 5 wiki pages filed with A2/A7 supersedences.

## One-liner

SAFE-06..09 breakers (competition collapse, maturity migration, side-budget drift, underlying-feed stale) with 20 GREEN tests, DuckDB underlying_apr reader, and 5 wiki pages filed.

## What Was Built

### 4 Breaker Modules

| Breaker | Module | Trigger | Kill Command | Tests |
|---------|--------|---------|--------------|-------|
| CompetitionBreaker (SAFE-06) | `decision/breakers/competition.py` | Q_total drop > 50% over 1 epoch | `PAUSE_AND_ALERT` | 4 |
| MaturityBreaker (SAFE-07) | `decision/breakers/maturity.py` | remaining_pendle < migration_cost | `ROLL_POSITION` | 3 |
| SideBudgetBreaker (SAFE-08) | `decision/breakers/side_budget.py` | per-side split drift > 30% | `HALVE_POSITION_AND_ALERT` | 4 |
| UnderlyingStaleBreaker (SAFE-09) | `decision/breakers/underlying_stale.py` | feed age > 2× expected cadence | `HALT_AND_ALERT` | 4 |

### 3 Read Helpers Added to State Writers

| Helper | Module | Used By |
|--------|--------|---------|
| `read_competition_history_since(sqlite_path, market_id, since_ts)` | `state/writers/competition_history.py` | CompetitionBreaker |
| `read_last_r_me_pendle(sqlite_path, market_id, side)` | `state/writers/decisions.py` | MaturityBreaker |
| `read_market_reward_calibration_history(sqlite_path, market_id, limit=10)` | `state/writers/market_reward_calibration.py` | SideBudgetBreaker |

### 1 New Data Reader

`python/src/boros_brain/data/underlying_apr_reader.py` — `read_underlying_apr_max_ts(parquet_root, exchange, symbol)` using in-memory DuckDB connection (~1ms per call) to query `MAX(snapshot_ts)` from Hive-partitioned parquet.

### CompetitionTracker SQLite Write

Already present from Plan 04-02 — `insert_competition_row` call and `self.conn.commit()` were already in `competition_tracker.py`. Verified via `test_competition_tracker.py` (5/5 passing).

## Test Coverage by Requirement

| Requirement | Test File | Tests | Status |
|-------------|-----------|-------|--------|
| SAFE-06 | test_breaker_competition.py | 4 | GREEN |
| SAFE-07 | test_breaker_maturity.py | 3 | GREEN |
| SAFE-08 | test_breaker_side_budget.py | 4 | GREEN |
| SAFE-09 | test_breaker_underlying_stale.py | 4 | GREEN |
| REWARD-02 (existing) | test_competition_tracker.py | 5 | GREEN |
| **Total** | | **20** | **GREEN** |

## First-Day Guard (Pitfall #3) — SAFE-06 and SAFE-08

Both CompetitionBreaker and SideBudgetBreaker explicitly check `len(rows) < 2` before computing epoch-lag comparisons:
- SAFE-06: `reason='insufficient_history'` if fewer than 2 competition_history rows
- SAFE-08: `reason='insufficient_calibration_history'` if fewer than 2 calibration rows

Tests cover this edge case for both breakers.

## Wiki Write-back

5 new wiki pages filed in LLM Wiki (separate commit eccfdb3):

| Page | Status | Content |
|------|--------|---------|
| `breaker-competition-collapse.md` | Current | SAFE-06 spec, Pitfall #3 guard |
| `breaker-maturity-migration.md` | Current | SAFE-07 spec, ROLL_POSITION semantics, operator workflow |
| `breaker-side-budget-rebalance.md` | Current | SAFE-08 spec, A2 absorbed |
| `breaker-underlying-feed-stale.md` | Current | SAFE-09 spec, A7 absorbed |
| `underlying-apr-cadence-by-exchange.md` | Current | binance=28800s, okx=3600s, hyperliquid=60s |

Plus:
- `circuit-breakers-v05.md`: SAFE-06..09 rows updated from TBD to Current with correct kill_command_kinds and wiki links
- `live-e-liq-polling-data-11.md`: Status updated with A2 supersedence by [[breaker-side-budget-rebalance]], Supersedence Log section added

## Architecture Delta — Deferred to Plan 04-06

Per plan spec, this plan deliberately does NOT touch `docs/architecture.yml` or `docs/ARCHITECTURE.md`. The architecture nodes/edges for:
- `decision.breakers.competition`
- `decision.breakers.maturity`
- `decision.breakers.side_budget`
- `decision.breakers.underlying_stale`
- `data.underlying_apr_reader`
- `competition_tracker -> competition_history WRITES edge`

...are registered atomically in Plan 04-06's final architecture delta task to avoid parallel-execution merge conflicts with Wave-2 sibling plans 04-03 and 04-04.

## Task Commits

| Task | Description | Commit |
|------|-------------|--------|
| 1 | SAFE-06 CompetitionBreaker + read_competition_history_since | f94d32f |
| 2 | SAFE-07 MaturityBreaker + read_last_r_me_pendle | 0efe1cc |
| 3 | SAFE-08 SideBudgetBreaker + read_market_reward_calibration_history | ed8c596 |
| 4 | SAFE-09 UnderlyingStaleBreaker + underlying_apr_reader | 51c7dd4 |
| 5 | Wiki write-back + no_threshold_dials_lint ALLOWED_FILES | 50240e8 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Relative import path in competition.py**
- **Found during:** Task 1 verification
- **Issue:** `from ..base import Breaker` pointed to `decision.base` (non-existent); breaker files are siblings in `decision/breakers/`, so the import should be `.base`
- **Fix:** Changed to `from .base import Breaker, BreakerSignal`
- **Files modified:** `python/src/boros_brain/decision/breakers/competition.py`
- **Commit:** f94d32f

**2. [Rule 2 - Missing critical functionality] default_config has markets=[] — all 4 breaker test files needed _config_with_market helper**
- **Found during:** Task 1 execution (first test run)
- **Issue:** `default_config` fixture loads `strategy/v0.5-default.yaml` which has `markets: []`. Every breaker calls `config.markets[0]` → IndexError.
- **Fix:** Added `_config_with_market(base, ...)` helper to each test file that injects a `MarketCalibration` dict via `model_dump + model_validate`
- **Files modified:** All 4 test files
- **Commits:** f94d32f, 0efe1cc, ed8c596, 51c7dd4

**3. [Rule 2 - Missing critical functionality] no_threshold_dials_lint.py ALLOWED_FILES needed 4 new breaker files**
- **Found during:** Task 5 verification (lint run after all tasks)
- **Issue:** `no_threshold_dials_lint.py` flagged `competition.py` and `side_budget.py` for using `cfg.drop_threshold` / `cfg.drift_threshold`; these files legitimately consume BotConfig breaker thresholds but were not in ALLOWED_FILES
- **Fix:** Added all 4 new breaker modules to ALLOWED_FILES
- **Files modified:** `scripts/no_threshold_dials_lint.py`
- **Commit:** 50240e8

**4. [Rule 3 - Blocking] MaturityBreaker test used kwarg not in Breaker ABC check() signature**
- **Found during:** Task 2 implementation
- **Issue:** Scaffolded test passed `last_r_me_pendle=0.001` to `breaker.check()` but Breaker ABC only defines `(sqlite_path, w3, parquet_root, config, current_chain_ts)`. `decisions` table has no `r_share_per_epoch_pendle` column (added by Plan 04-06).
- **Fix:** Added `last_r_me_pendle: float | None = None` optional kwarg to `MaturityBreaker.check()` as a test-injection override; production callers omit it and the breaker reads from SQLite.
- **Files modified:** `python/src/boros_brain/decision/breakers/maturity.py`, `python/tests/test_breaker_maturity.py`
- **Commit:** 0efe1cc

## Known Stubs

None. All breakers are fully wired. The `read_last_r_me_pendle` function returns None until Plan 04-06's decision engine loop populates `decisions.r_share_per_epoch_pendle` — this is documented as `reason='no_decision_history_yet'` (not a stub; it is the correct pre-history behavior).

## Threat Flags

No new network endpoints or auth paths introduced. All reads are from local SQLite and local parquet. The competition_history write path was already in Plan 04-02's scope (T-04-05-05 mitigated via existing OWNER_MAP lint).

## Self-Check: PASSED

Files confirmed present:
- python/src/boros_brain/decision/breakers/competition.py: EXISTS
- python/src/boros_brain/decision/breakers/maturity.py: EXISTS
- python/src/boros_brain/decision/breakers/side_budget.py: EXISTS
- python/src/boros_brain/decision/breakers/underlying_stale.py: EXISTS
- python/src/boros_brain/data/underlying_apr_reader.py: EXISTS
- Wiki: breaker-competition-collapse.md, breaker-maturity-migration.md, breaker-side-budget-rebalance.md, breaker-underlying-feed-stale.md, underlying-apr-cadence-by-exchange.md: ALL EXIST

Commits confirmed:
- f94d32f, 0efe1cc, ed8c596, 51c7dd4, 50240e8: all in git log
- LLM Wiki repo: eccfdb3
