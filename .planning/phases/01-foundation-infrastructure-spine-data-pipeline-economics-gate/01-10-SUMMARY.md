---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
plan: "10"
subsystem: data-pipeline
tags: [polars, sqlite, asyncio, web3, amm-conservation, reward-budget, e-liq-poller, tdd]

# Dependency graph
requires:
  - phase: 01-06
    provides: NDJSON ingester skeleton with order_book raw/combined ingest stubs
  - phase: 01-07
    provides: BotConfig schema with DataConfig (e_liq_poll_interval_s, boros_rest_base)
  - phase: 01-08
    provides: SQLite WAL spine, schemas.sql with reward_budget_history table, Alembic setup
  - phase: 01-09
    provides: BorosRestClient.get_markets(), chain_time cache, rest_client.py

provides:
  - AMMConservationError exception class + assert_amm_conservation() wired into order_book.py before parquet write
  - ELiqPoller class (DATA-11): async poller writing one reward_budget_history row per market per cycle, no cross-poll cache
  - reward_budget_history writer module (single-writer discipline enforced)
  - Alembic migration 0002 adding data_source TEXT CHECK ('polled'|'synthetic_current') column
  - probe_historical_budget.py A6 spike script (--dry-run CI mode + live mode)
  - Architecture diagram nodes: assert_amm_conservation, e_liq_poller, probe_historical_budget

affects:
  - 01-11 (DATA-09 economics kill-switch reads reward_budget_history polled_at_utc DESC LIMIT 1)
  - 01-12 (R_apr computation consumes long_budget/short_budget from reward_budget_history)
  - Phase 2 fill model (AMM conservation check gates combined-book parquet that queue tracker uses)
  - Phase 3 reward-share model (E_liq_per_epoch live polling via ELiqPoller)
  - Phase 5 backtest (data_source='synthetic_current' enum needed for pre-pipeline reward rows)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DATA-05 AMM conservation: assert_amm_conservation(raw_df, combined_df) runs BEFORE parquet write, propagates to process exit — no try/except in caller (PITFALLS §B3)"
    - "DATA-11 no-cache invariant: every run_one_cycle() writes a fresh row; downstream reads polled_at_utc DESC LIMIT 1 (PITFALLS §A2 / ARCHITECTURE.md §9 Anti-pattern 4)"
    - "T-01-10-03 backoff: _get_with_backoff() with delays [0.5, 1, 2, 4, 8s]; on 5 failures log ERROR + publish poller.e_liq.degraded ZMQ event, continue loop (dead poller < dead brain)"
    - "B6 pitfall guard: data_source Python ValueError before SQL round-trip + SQL CHECK constraint — both layers reject invalid values"
    - "A6 spike pattern: one-shot script with --dry-run CI mode + live mode; verdict written to var/reports/ as JSON with feasible/blockers/time_spent fields"

key-files:
  created:
    - python/src/boros_brain/data/ingester/exceptions.py
    - python/src/boros_brain/data/poller/e_liq_poller.py
    - python/src/boros_brain/state/writers/reward_budget_history.py
    - python/src/boros_brain/state/migrations/versions/0002_reward_budget_history.py
    - python/tests/test_amm_conservation.py
    - python/tests/test_e_liq_poller.py
    - python/tests/fixtures/amm_conservation_violating_snapshot.ndjson
    - python/tests/fixtures/amm_conservation_valid_snapshot.ndjson
    - python/tests/test_probe_historical_budget_smoke.py
    - scripts/probe_historical_budget.py
  modified:
    - python/src/boros_brain/data/ingester/order_book.py
    - python/src/boros_brain/state/schemas.sql
    - docs/architecture.yml
    - docs/ARCHITECTURE.md

key-decisions:
  - "assert_amm_conservation uses polars full outer join + fill_null(0.0): a tick missing from combined is treated as combined_size=0 (more conservative than skipping)"
  - "ELiqPoller._fail_count increments per retry attempt inside _get_with_backoff, not per call to run_one_cycle — so fail_count >= 5 triggers degraded event after one exhausted retry cycle"
  - "probe_historical_budget.py exits 0 whether feasible or infeasible — infeasible is an expected outcome per A6, not an error; callers read the verdict JSON"
  - "data_source ValueError raised in Python writer before SQL round-trip — gives cleaner stack trace than relying solely on SQLite IntegrityError (B6 guard, two-layer enforcement)"

patterns-established:
  - "Loud-fail ingest assertions: conservation/validation checks run before any parquet write and propagate uncaught to process exit for non-zero exit code"
  - "Single-writer module per SQLite table: reward_budget_history.py is the sole INSERT path; scripts/sqlite_writer_lint.py mechanically enforces this"
  - "One-shot spike scripts: --dry-run flag for CI smoke tests; verdict written to var/reports/ as JSON; operator runs full spike manually"

requirements-completed: [DATA-05, DATA-11, PROTO-05]

# Metrics
duration: unknown
completed: "2026-04-24"
---

# Phase 01 Plan 10: AMM Conservation Assertion + Live E_liq Poller + A6 Historical Budget Spike Summary

**AMM conservation assert_amm_conservation() wired into order_book.py combined ingest (fail-loud, PITFALLS §B3); ELiqPoller writing live E_liq_per_epoch + long/short split per cycle to reward_budget_history with data_source enum; A6 spike script in --dry-run CI mode with full live mode for operator execution**

## Performance

- **Duration:** unknown (commits recovered post-execution)
- **Completed:** 2026-04-24
- **Tasks:** 3 (Task 1: DATA-05 AMM conservation TDD, Task 2: DATA-11 ELiqPoller TDD, Task 3: A6 spike)
- **Files modified:** 14

## Accomplishments

- AMM conservation assertion wired before parquet write in `ingest_order_book_combined()`: raises `AMMConservationError` on any tick where `combined_size - raw_book_size < 0`, propagates uncaught to process exit for non-zero exit code (PITFALLS §B3 prevention).
- `ELiqPoller` live polls `GET /markets` every `e_liq_poll_interval_s` (default 5s), writes one `reward_budget_history` row per market per cycle with no cross-poll caching; exponential backoff [0.5, 1, 2, 4, 8s] on failures; `poller.e_liq.degraded` ZMQ event after 5 consecutive failures (T-01-10-03 / PITFALLS §A2 prevention).
- `reward_budget_history` writer module enforces single-writer discipline at both Python (ValueError) and SQL (CHECK constraint) layers; `data_source` enum `'polled'|'synthetic_current'` supports Phase 5 backtest filtering (PITFALLS §B6 prevention).
- Alembic migration `0002` adds `data_source TEXT NOT NULL CHECK (data_source IN ('polled','synthetic_current')) DEFAULT 'polled'` column.
- `probe_historical_budget.py` A6 spike script: `--dry-run` mode for CI smoke tests (writes stub infeasible verdict); live mode probes distributor contract events (`BudgetSet`, `EmissionUpdated`, `EpochBudgetPosted`, etc.) for historical E_liq reconstruction; verdict written to `var/reports/a6_historical_budget_verdict.json`.
- Architecture diagram updated in same commit as each source change (PROTO-02): three new nodes added (`assert_amm_conservation`, `e_liq_poller`, `probe_historical_budget`).

## Task Commits

TDD tasks have RED + GREEN commits per TDD protocol:

1. **Task 1 RED: DATA-05 AMM conservation failing tests** - `f59290c` (test)
2. **Task 1 GREEN: DATA-05 AMM conservation assertion + writer/schema migration** - `dcf8aad` (feat)
3. **Task 2 RED: DATA-11 ELiqPoller failing tests** - `3c5e442` (test)
4. **Task 2 GREEN: DATA-11 ELiqPoller** - `426160c` (feat)
5. **Task 3: A6 historical-budget spike script + smoke test** - `fda85d4` (feat)

## Files Created/Modified

- `python/src/boros_brain/data/ingester/exceptions.py` — `AMMConservationError` exception class with PITFALLS §B3 docstring
- `python/src/boros_brain/data/ingester/order_book.py` — `assert_amm_conservation()` function added; wired into `ingest_order_book_combined()` before parquet write
- `python/src/boros_brain/data/poller/e_liq_poller.py` — `ELiqPoller` class with `run_one_cycle()`, `_get_with_backoff()`, `loop()`
- `python/src/boros_brain/state/writers/reward_budget_history.py` — `insert_reward_budget_row()` single-writer module with B6 two-layer validation
- `python/src/boros_brain/state/migrations/versions/0002_reward_budget_history.py` — Alembic migration adding `data_source` column
- `python/src/boros_brain/state/schemas.sql` — updated with `data_source` column + CHECK constraint
- `python/tests/test_amm_conservation.py` — 4 TDD tests (violating fixture raises, valid completes, subprocess non-zero exit, error message content)
- `python/tests/test_e_liq_poller.py` — 5 TDD tests (insert_reward_budget_row, data_source constraint, no-cache 2-row invariant, backoff-on-503, schema PRAGMA)
- `python/tests/fixtures/amm_conservation_violating_snapshot.ndjson` — test fixture with deliberate combined < raw tick
- `python/tests/fixtures/amm_conservation_valid_snapshot.ndjson` — test fixture with all valid ticks
- `python/tests/test_probe_historical_budget_smoke.py` — 4 smoke tests for spike script
- `scripts/probe_historical_budget.py` — A6 spike with `--dry-run` CI mode + live RPC mode
- `docs/architecture.yml` — three new nodes (assert_amm_conservation, e_liq_poller, probe_historical_budget)
- `docs/ARCHITECTURE.md` — Mermaid diagram updated with same nodes

## Decisions Made

- `assert_amm_conservation` uses a full outer join + `fill_null(0.0)` on both sides: a tick present in `raw` but absent from `combined` counts as `combined_size=0`, which is always a violation (conservative choice favoring loud failure over silent skip).
- `ELiqPoller._fail_count` increments per retry attempt inside `_get_with_backoff`, not per call to `run_one_cycle`. This means `fail_count >= 5` fires after a single exhausted-retry cycle (all 5 backoff windows expired), which is the tightest possible signal that the REST endpoint is consistently unavailable.
- `probe_historical_budget.py` exits 0 whether reconstruction is feasible or infeasible — infeasible is the expected outcome per A6 assumption; callers read `verdict["feasible"]` from the JSON.
- `data_source` validation is two-layer: Python `ValueError` before SQL round-trip + SQL `CHECK` constraint. Both layers reject invalid values; the Python layer gives a cleaner traceback for operator debugging.

## Deviations from Plan

None — plan executed exactly as written. The full outer join approach in `assert_amm_conservation` (filling nulls with 0.0) is consistent with the plan's formula; it is a clarifying implementation choice, not a deviation.

## A6 Spike Verdict

The spike script was written and CI smoke-tested in `--dry-run` mode. The **live spike has not been run** — it requires `RPC_URL_ARBITRUM` + `BOROS_DISTRIBUTOR_ADDRESS` + `configs/distributor_abi.json` to be populated by the operator as a one-shot manual step.

**Expected outcome per 01-RESEARCH.md Assumption A6:** infeasible. If infeasible, `reward_budget_history` remains forward-only from pipeline go-live. Phase 5 backtest rows from pre-pipeline data MUST use `data_source='synthetic_current'` (PITFALLS §B6).

The `data_source` enum in `reward_budget_history` already accommodates both outcomes — no schema change required once the verdict is confirmed.

## Issues Encountered

None.

## User Setup Required

To run the live A6 spike (one-shot operator step, not CI):

```bash
export RPC_URL_ARBITRUM=<your-arbitrum-rpc-url>
export BOROS_DISTRIBUTOR_ADDRESS=<distributor-contract-address>
# Provide configs/distributor_abi.json (fetch from Arbiscan)
python scripts/probe_historical_budget.py
cat var/reports/a6_historical_budget_verdict.json
```

## Next Phase Readiness

- `reward_budget_history` table is write-ready with full `data_source` enum and single-writer enforcement — 01-11 (DATA-09 economics kill-switch) can poll it immediately via `SELECT ... ORDER BY polled_at_utc DESC LIMIT 1`.
- AMM conservation assertion is active in `ingest_order_book_combined()` — Phase 2 fill model's queue tracker and AMM consumption model depend on conservation-validated combined parquet.
- `ELiqPoller` is wired and testable; it will be instantiated in the main brain loop in a later plan.
- A6 spike verdict (live) should be filed as a wiki page before Phase 5 backtest design.

---
*Phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate*
*Completed: 2026-04-24*

## Self-Check: PASSED

Files confirmed present:
- `python/src/boros_brain/data/ingester/exceptions.py` — FOUND
- `python/src/boros_brain/data/poller/e_liq_poller.py` — FOUND
- `python/src/boros_brain/state/writers/reward_budget_history.py` — FOUND
- `scripts/probe_historical_budget.py` — FOUND

Commits confirmed:
- `f59290c` (test RED Task 1) — FOUND
- `dcf8aad` (feat GREEN Task 1) — FOUND
- `3c5e442` (test RED Task 2) — FOUND
- `426160c` (feat GREEN Task 2) — FOUND
- `fda85d4` (feat Task 3) — FOUND
