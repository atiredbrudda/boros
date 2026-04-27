---
status: resolved
trigger: "reward_budget_history SQLite table is empty — r_apr_potential=None for every market, economics gate has no input"
created: 2026-04-27
updated: 2026-04-27
---

## Symptoms

- **Expected:** reward_budget_history contains reward budget entries so screener can compute r_apr_potential
- **Actual:** Table is empty → r_apr_potential = None for every market → economics gate cannot rank markets
- **Errors:** Silent — no error, just None values
- **Timeline:** Never populated (Wave-1 ingest only writes parquet; ELiqPoller (DATA-11) is architecturally dead per LOCKED D-01)
- **Reproduction:** SELECT COUNT(*) FROM reward_budget_history → 0

## Current Focus

hypothesis: "RESOLVED — root cause was correct (table empty) but the proposed fix options A/B/C in the dispatch context were all infeasible. Investigated each, found the actual unblock path, applied it."
test: "After backfill, screener returns non-None r_apr_potential for ≥1 market"
expecting: "All 5 in-scope markets show r_apr_potential=141.96"
next_action: "DONE — see Resolution"
reasoning_checkpoint: "DONE"

## Root Cause

### Wave-1 ingest never populated SQLite spine; LOCKED D-01 broke the live-poll path

The pre-diagnosis labeled the writer as "markets-poller" but the actual writer for
`reward_budget_history` is `brain.data.poller.e_liq_poller.ELiqPoller` (DATA-11).
The architecturally significant fact is:

1. **Wave-1 ingest only writes parquet.** `scripts/05_1_bulk_ingest.sh` enumerates
   `data/ndjson/{market-trades, order-book, settlement, underlying-apr}/` and dispatches
   per-market ingester subprocesses that write to `data/parquet/`. It never touches the
   SQLite spine — so `reward_budget_history`, `clo_history`, `market_reward_calibration`
   are all empty after Wave-1.

2. **`ELiqPoller` is architecturally dead.** Per LOCKED D-01 (2026-04-24,
   [[e-liq-per-epoch-source-decision]]), the live `GET /markets` endpoint does NOT carry
   `liquidityRewardPerEpoch / longBudget / shortBudget` fields. Phase-1 UAT and the
   Phase-3 probe both confirmed this. The Pendle SDK's "Incentives API" endpoints all
   return 404. Operator-manual calibration into the NEW `state.market_reward_calibration`
   table is the v0.5 source of truth; ELiqPoller writing to `reward_budget_history` is a
   defunct code path that no production component invokes.

3. **The screener reads the OLD table.** `brain.screener.filter` still queries
   `reward_budget_history` for `r_apr_potential` ranking — it has not been migrated to
   read from `market_reward_calibration`. That migration is implicit-deferred work.

4. **No reward_budget parquet exists.** The Boros archive at
   `historical-data.boros.finance` exposes market_trades, order_book, settlement, and
   underlying_apr — NOT reward budgets. Per
   [[historical-reward-budget-reconstruction-infeasible]], on-chain reconstruction from
   distributor events is also infeasible.

The three fix options proposed by the dispatching context (A: ingest reward_budget
parquet; B: replay markets-poller; C: parquet fallback in screener) all assume an
external data source that doesn't exist. The actual unblock is a deliberate
**operator-supplied synthetic backfill** — the schema CHECK constraint already reserves
the `data_source='synthetic_current'` lineage marker for exactly this case (PITFALLS §B6).

## Evidence

- timestamp: 2026-04-27T01:44:00Z
  observation: "reward_budget_history SQLite table confirmed empty (0 rows). chain_ts column present. schema-drift (snapshot_ts vs chain_ts) independently fixed."
  source: "Discovered during screener-marketid-maturity debug session fix verification"

- timestamp: 2026-04-27T02:00:00Z
  observation: "No reward_budget parquet anywhere — neither data/parquet/ nor data/ndjson/ nor var/fetcher/ contain anything related. Wave-1 fetcher manifest covers market-trades, market-data, order-book, underlying-apr, settlement only. Option A is dead."
  source: "find / grep across data/ tree"

- timestamp: 2026-04-27T02:05:00Z
  observation: "Pre-diagnosis named wrong poller. The actual writer is ELiqPoller (DATA-11), not markets-poller. ELiqPoller calls insert_reward_budget_row from m['liquidityRewardPerEpoch'] etc. — fields confirmed ABSENT from live API per LOCKED D-01 ([[e-liq-per-epoch-source-decision]]). Option B is architecturally dead."
  source: "Read python/src/boros_brain/data/poller/e_liq_poller.py + wiki page"

- timestamp: 2026-04-27T02:10:00Z
  observation: "Two SQLite databases exist with diverged alembic versions. state/state.sqlite (project root) is at 0002 — has reward_budget_history with chain_ts column but missing 0006/0007 tables. python/state/state.sqlite is at 0007_phase4_tables — has all tables. Screener resolves config.infra.sqlite_path='state/state.sqlite' relative to cwd, which means project-root invocation hits the legacy DB. Backfilled BOTH for safety."
  source: "sqlite3 .tables comparisons + alembic_version queries"

- timestamp: 2026-04-27T02:13:00Z
  observation: "Verified screener returns r_apr_potential=141.96 for all 5 in-scope markets after backfill. Filter still fails on zero_depth_at_clo (separate Wave-2 concern about order_book_combined data gaps), but that's not this debug session's scope."
  source: "var/reports/screener_metrics.json after end-to-end run"

## Eliminated

- **Option A** (ingest reward_budget parquet): No reward_budget parquet exists. The Boros archive does not expose this data; on-chain distributor events do not carry it either ([[historical-reward-budget-reconstruction-infeasible]]).
- **Option B** (replay markets-poller): The pre-diagnosis named markets-poller, but markets-poller writes `clo_history`, not `reward_budget_history`. The actual writer is `ELiqPoller` (DATA-11). ELiqPoller is architecturally dead — its assumed `/markets` fields don't exist on the live API per LOCKED D-01.
- **Option C** (parquet fallback in screener): There is no reward_budget parquet to fall back to.

## Resolution

root_cause: "Wave-1 bulk_ingest only writes parquet (market_trades, order_book, settlement, underlying_apr); SQLite spine including reward_budget_history was never populated. The original writer (ELiqPoller / DATA-11) is architecturally dead per LOCKED D-01 because GET /markets does not expose the required reward fields. The screener still queries reward_budget_history (not yet migrated to market_reward_calibration), so an empty table → r_apr_potential=None for every market."
fix: "Wrote scripts/backfill_reward_budget_history.py — a one-shot operator script that calls the existing single-writer brain.state.writers.reward_budget_history.insert_reward_budget_row with data_source='synthetic_current' (the lineage marker the schema CHECK constraint reserves for this case per PITFALLS §B6). Uses operator-anchor values per [[market-reward-calibration-operator-workflow]] (e_liq_per_epoch_pendle=273.0, long/short splits 0.14/0.86). Discovers markets from data/parquet/market_trades/ partitions, strips the leading numeric archive prefix to get the canonical SQLite-keyed market_id. Idempotent (skips markets that already have a synthetic_current row). Backfilled BOTH state.sqlite locations (project-root and python/state/) since cwd-relative path resolution hits different DBs depending on invocation. PROTO-02 single-writer discipline preserved (insert_reward_budget_row remains the only INSERT for this table). Filed wiki page [[reward-budget-history-synthetic-backfill]] and updated docs/architecture.yml + docs/ARCHITECTURE.md per Engineering Protocol 2 — both lints exit 0."
verification: "End-to-end: (1) sqlite3 state/state.sqlite 'SELECT COUNT(*) FROM reward_budget_history' → 25 rows / 25 markets / data_source=synthetic_current. (2) Screener invocation `uv run --project python python -m boros_brain.screener --run --config strategy/v0.5-default.yaml --markets ...` produces var/reports/screener_metrics.json with r_apr_potential=141.96 (= 273.0 * 52 epochs/yr / 100 USD collateral proxy) for all 5 in-scope markets. (3) Existing screener tests still pass: pytest tests/test_screener_filter.py tests/test_screener_metrics.py tests/test_e_liq_poller.py tests/test_backtest_reward_budget_lineage_filter.py → 22 passed. (4) Full pytest suite: 418 passed, 1 pre-existing failure unrelated to this fix (test_amm_conservation, caused by other untracked changes in python/src/boros_brain/data/ingester/order_book.py). (5) python3 scripts/architecture_lint.py → exit 0."
files_changed: "scripts/backfill_reward_budget_history.py (NEW); docs/architecture.yml (added scripts.backfill_reward_budget_history node + 2 edges); docs/ARCHITECTURE.md (Mermaid diagram updated with backfill_rb node + 2 edges); /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/reward-budget-history-synthetic-backfill.md (NEW); /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md (added new page link in Phase 5.1 section + A-Z table); state/state.sqlite (25 synthetic_current rows added); python/state/state.sqlite (25 synthetic_current rows added)."
