---
status: fixed_with_followups
trigger: "Critical Blocker: Screener Cannot Run Against Real Data — DATA-08 screener returns 0 passing markets on every call, producing a false-positive project HALT"
created: 2026-04-27
updated: 2026-04-27
---

## Symptoms

- **Expected:** DATA-08 screener passes at least some markets through filters 1–6
- **Actual:** 0 markets pass every screener run → project HALT (false positive)
- **Errors:** No runtime error — silent wrong output (all markets filtered out)
- **Timeline:** Never worked (new code, Wave 1 completed but Wave 2 cannot start)
- **Reproduction:** Run the screener against the ingested parquet data

## Current Focus

hypothesis: "Two independent bugs cause 0 markets to pass: (1) market_id format mismatch between parquet index and screener query, and (2) maturity_ts always 0 because config.markets=[] in v0.5-default.yaml"
test: "Apply both fixes and verify screener returns ≥1 passing market on real data"
expecting: "At least one market passes all 6 filters after fixes"
next_action: "Both pre-diagnosed bugs fixed; investigation surfaced 3 additional independent blockers (see Resolution → Followups)"
reasoning_checkpoint: "Pre-diagnosed bugs verified fixed by direct screener output inspection; surfaced new findings rather than scope-creep into them"

## Root Cause

### Bug 1 — market_id format mismatch (filter.py)

- **Parquet indexed as:** `market_id=109-HYPERLIQUID-BTC-29MAY2026` (numeric-prefix archive format)
- **Screener queried with:** `WHERE market_id = 'HYPERLIQUID-BTC-29MAY2026'` (no prefix)
- **Refined during fix:** the asymmetry is *per-table*, not global —
  - **Parquet tables** (`market_trades`, `order_book_combined`) → archive-prefixed (`112-…`)
  - **SQLite tables** (`clo_history`, `reward_budget_history`) → canonical (un-prefixed)
- **Effect (pre-fix):** Zero trades returned for every market → all markets fail filters 1–4

### Bug 2 — maturity_ts always 0 (filter.py:154, Filter 6 — TTM)

- **Code:** `maturity_ts = next((m.maturity_ts for m in config.markets if m.market_id == mid), 0)`
- **Problem:** `config.markets = []` in v0.5-default.yaml → maturity_ts defaults to 0 → TTM ≈ −20,000 days → all markets fail 30-day TTM filter

## Evidence

- timestamp: 2026-04-27T00:00:00Z
  observation: "User pre-diagnosed both bugs from code inspection before debug session started"
  source: "user analysis + filter.py:154 + v0.5-default.yaml + parquet market_id inspection"

- timestamp: 2026-04-27T01:40:00Z
  observation: "Per-table format probe: market_trades / order_book_combined return rows ONLY for prefixed IDs; clo_history returns rows ONLY for un-prefixed IDs; reward_budget_history is empty under both forms."
  source: "uv --project python run python -c '… COUNT(*) FROM <table> WHERE market_id = ? …'"

- timestamp: 2026-04-27T01:43:00Z
  observation: "After fix: BINANCE-ETHUSDT-29MAY2026 → cv=4.99, reversal_count=143, clo_lower/upper=9300/9500, ttm=31.97d. BTCUSDT-26JUN2026 → ttm=59.97d (passes Filter 6). Both Bug 1 and Bug 2 demonstrably resolved on real data."
  source: "var/reports/screener_metrics.json after live run"

- timestamp: 2026-04-27T01:44:00Z
  observation: "reward_budget_history live SQLite schema uses chain_ts (BIGINT) — not snapshot_ts as the screener originally hardcoded. Fixed in same patch via _reward_budget_ts_column() introspection (whitelist: chain_ts | snapshot_ts)."
  source: "DESCRIBE reward_budget_history → cols include chain_ts, polled_at_utc; no snapshot_ts"

## Eliminated

- Hypothesis "shim could break existing test fixtures" — eliminated. All 34 screener-related tests still pass (`tests/test_screener_filter.py` + 4 sibling test files).

## Resolution

root_cause: "Bug 1: market_id prefix mismatch (refined per-table — parquet=prefixed, sqlite=canonical). Bug 2: maturity_ts always 0 due to empty config.markets."

fix: "filter.py — added _parquet_market_id() + _canonical_market_id() per-table resolvers consulting var/fetcher/market_id_mapping.json (no re-ingest); added _derive_maturity_ts_from_name() parsing the trailing DDMMMYYYY token as fallback when config.markets is empty (config still wins when present); added _reward_budget_ts_column() schema-tolerant ORDER BY (chain_ts on live SQLite, snapshot_ts on test fixtures)."

verification: "All 34 screener tests pass. Live screener run on 3 markets shows: trades retrieved (cv non-null, reversal_count > 0), clo_history reached (non-zero clo_lower/upper), TTM positive (~32d / ~60d via name parsing). BINANCE-BTCUSDT-26JUN2026 reaches Filter 6 PASS (only Filter 4 zero_depth_at_clo blocks it now). Bugs 1 and 2 are demonstrably fixed."

files_changed: "python/src/boros_brain/screener/filter.py (single file, no schema migrations, no re-ingest)"

## Followups (DISCOVERED during fix verification — outside original scope)

These are independent blockers preventing the shortlist from filling. They are NOT regressions from this fix — they were already present, just masked by the pre-diagnosed bugs. Each warrants its own debug session.

### Followup A — `compute_realized_vol` produces NaN on real Boros rates

- **Symptom:** every market fails `realized_vol_invalid`.
- **Root cause:** `metrics.py::compute_realized_vol` computes `(rates / rates.shift(1)).log()`. Real Boros rates oscillate around zero (range observed: -0.013 to +0.011, with 8 zeros and 608/360 negative/positive split for ETHUSDT-29MAY). Negative-ratio log returns NaN; division by zero produces inf. `std()` over a vector with NaN/inf returns NaN → function returns None.
- **Test fixtures hide this:** synthetic rates start at 9400 and never cross zero.
- **Fix direction:** rework realized-vol to operate on **rate differences** (`rates.diff().std()`) or on log-magnitude with sign tracking — talk to the strategy author before picking. Document the chosen primitive in `[[realized-vol-on-boros-rates]]`.

### Followup B — `order_book_combined` parquet has all-NULL data columns

- **Symptom:** every market fails `zero_depth_at_clo`.
- **Root cause:** `SELECT snapshot_ts, tick, sz_combined_float FROM order_book_combined WHERE market_id = '112-BINANCE-ETHUSDT-29MAY2026'` → 271 rows, ALL data columns are NULL. Only the partition key (`market_id`) is populated.
- **Provenance:** Wave-1 (`05_1_bulk_ingest.sh`) order_book_combined ingestion silently produced empty-payload parquet files.
- **Fix direction:** investigate the order_book_combined ingester path; the AMM-conservation gate clearly didn't catch this empty-data case (AMM check requires sums, sums of NULL = 0 = trivially conserved).

### Followup C — `reward_budget_history` is empty in production SQLite

- **Symptom:** `r_apr_potential = None` for every market → economics gate has no input even after DATA-08 passes a market.
- **Root cause:** Wave-1 ingest didn't populate `reward_budget_history`. The markets-poller writes to this table but apparently hasn't run against the historical window.
- **Fix direction:** decide whether r_apr_potential should fall back to `reward_budget_history` parquet (if it exists), or whether the markets-poller needs to be replayed over the Wave-1 window. (Schema column-name issue independently fixed in this patch.)
