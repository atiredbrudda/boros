---
status: resolved
trigger: "order_book_combined parquet has all-NULL data columns — every market fails zero_depth_at_clo filter"
created: 2026-04-27
updated: 2026-04-27
---

## Symptoms

- **Expected:** order_book_combined parquet contains valid snapshot_ts, tick, sz_combined_float data
- **Actual:** 271 rows for BINANCE-ETHUSDT-29MAY2026 partition but ALL data columns are NULL — only partition key (market_id) is populated
- **Errors:** No error at ingest time — silent empty-payload write
- **Timeline:** Never had valid data (Wave-1 ingest, 05_1_bulk_ingest.sh)
- **Reproduction:** SELECT snapshot_ts, tick, sz_combined_float FROM order_book_combined WHERE market_id = '112-BINANCE-ETHUSDT-29MAY2026' → all NULL

## Current Focus

hypothesis: "Wave-1 order_book_combined ingestion wrote parquet partitions with correct row count but empty/null payloads — the AMM-conservation gate didn't catch it because SUM(NULL) = 0 = trivially conserved"
test: "Identify the ingester code path for order_book_combined, find where data columns are dropped/nulled, fix and re-ingest"
expecting: "After fix + re-ingest: SELECT returns non-NULL tick and sz_combined_float values; screener zero_depth_at_clo filter passes for at least one market"
next_action: "Inspect the order_book_combined ingest path in 05_1_bulk_ingest.sh and the underlying Python ingester; find where payload is lost"
reasoning_checkpoint: "Root cause direction pre-confirmed: 271 rows exist (correct row count) but data is all NULL — this is an ingest payload mapping bug, not a schema or query bug"

## Root Cause

### Schema/ingester assumed flat per-tick rows; real archive NDJSON is nested per-snapshot arrays

- **Evidence:** `python/src/boros_brain/data/ingester/schemas.py` declared `ORDER_BOOK_COMBINED_SCHEMA = {snapshot_ts, tick, sz_combined}` (a flat per-tick row), but the real Boros historical-data archive ([[boros-historical-data-archive-layout]]) emits one NDJSON line per **hourly snapshot** with the shape `{timestamp, datetime, blockNumber, long: [{rate, size}], short: [{rate, size}]}`.
- When `pl.read_ndjson(path, schema=...)` is called with a schema declaring top-level fields that do not exist in the JSON, polars produces one row per JSON line with all-null values for the declared fields (no error). This explains the 271 rows × all-null pattern (271 NDJSON lines × 271 null-rows).
- **Same bug also affected `order_book_raw`** — the schema declared `{snapshot_ts, tick, t, sz}` but the archive emits `{blockNumber, blockTimestamp, dateTime, long: [{t, sz}], short: [{t, sz}], ammState}`. All 25 markets had all-null `order_book_raw` parquets too. (User's debug brief mentioned only `order_book_combined`; both shared the schema bug and required the joint fix because AMM conservation needs raw to be correct.)
- AMM-conservation gate did not catch this because (a) the previous per-tick join compared null vs null (trivially "conserved"), and (b) the bulk-ingest CLI never passed `raw_ndjson_path` to the combined ingester so the gate was never invoked at bulk ingest anyway.
- Test fixtures (`sample_order_book_*.ndjson`, `amm_conservation_*.ndjson`) used a synthetic flat shape that matched the broken schema, so the unit tests passed against a fictional NDJSON contract that did not match production.

## Evidence

- timestamp: 2026-04-27T01:43:00Z
  observation: "271 rows for 112-BINANCE-ETHUSDT-29MAY2026 with all NULL data columns confirmed via direct DuckDB query"
  source: "Discovered during screener-marketid-maturity debug session fix verification"
- timestamp: 2026-04-27T02:05:00Z
  observation: "All 25 markets have order_book_combined and order_book_raw parquets in `snapshot_ts=__HIVE_DEFAULT_PARTITION__` directories — this is polars' marker for null partition values, confirming the partition column itself was null at write time"
  source: "find /Users/macbookair/boros/data/parquet -path '*order_book*' -type d -name 'snapshot_ts=*'"
- timestamp: 2026-04-27T02:06:00Z
  observation: "Real archive NDJSON sample shows nested-array shape: `{timestamp, datetime, blockNumber, long:[{rate,size}], short:[{rate,size}]}` (combined) and `{blockNumber, blockTimestamp, dateTime, long:[{t,sz}], short:[{t,sz}], ammState}` (raw). LLM Wiki [[boros-historical-data-archive-layout]] §Schema (lines 149-159) confirms this is the documented contract."
  source: "head -3 data/ndjson/order-book/{market}/combined_0.01/*.ndjson"

## Eliminated

- **Not a partition-key bug** — partition writer is fine; it received null `snapshot_ts` because the schema mapped a nonexistent JSON field
- **Not a write-side bug** — `write_partitioned_parquet` correctly preserved the null payload it received
- **Not a query-time issue** — DuckDB and polars both correctly read what's actually in the parquet (which is nulls)

## Resolution

root_cause: "Wave-1 order-book ingester schemas (`ORDER_BOOK_RAW_SCHEMA`, `ORDER_BOOK_COMBINED_SCHEMA`) described a flat per-tick row shape (`{snapshot_ts, tick, sz/sz_combined}`) that did not exist in the real archive NDJSON. Real archive emits one nested per-snapshot row containing `long`/`short` arrays of per-tick liquidity entries. polars `read_ndjson` with a mismatched schema silently produces all-null rows. Test fixtures shared the broken shape so the unit tests passed against a fictional contract."
fix: "Replaced the schemas with the real nested per-snapshot shape (List<Struct> for long/short). Added an explode step in `_explode_raw` and `_explode_combined` to fan one snapshot row out to per-(snapshot_ts, side, tick) rows. Added a `side` column ('long'/'short'). Mapped combined `rate` → `tick = round(rate / tick_size)` for grid alignment. Combined `size` is already a Float64 (PT-YT contracts), no wei conversion. Raw `sz` retains the wei→float conversion. Replaced the per-tick AMM conservation join (which never worked because raw and combined are on different tick grids) with a per-snapshot total invariant `SUM(combined) >= SUM(raw)` (with 1% relative tolerance for upstream rounding). Re-ingested order_book_raw + order_book_combined for all 25 markets via `/tmp/reingest_order_book.sh` (62 jobs, 0 failures). Replaced all 6 broken test fixtures and updated 9 ingester+AMM tests."
verification: "DuckDB query `SELECT snapshot_ts, tick, sz_combined_float FROM order_book_combined WHERE market_id='112-BINANCE-ETHUSDT-29MAY2026'` now returns 1797 non-null rows (was 271 all-null). Across all 25 markets: order_book_combined has 240,043 rows (0 nulls), order_book_raw has 695,896 rows (0 nulls), 1,135 distinct snapshot_ts. Test suite: 25 ingester tests + 9 downstream tests (screener, duckdb, competition, amm-replay) all pass. AMM conservation gate verified to fire on synthetic violating fixture (subprocess exit code != 0, 'AMMConservationError' in stderr)."
files_changed: "python/src/boros_brain/data/ingester/schemas.py, python/src/boros_brain/data/ingester/order_book.py, python/tests/test_ingester_order_book.py, python/tests/test_amm_conservation.py, python/tests/fixtures/sample_order_book_raw.ndjson, python/tests/fixtures/sample_order_book_combined.ndjson, python/tests/fixtures/amm_conservation_valid_snapshot.ndjson, python/tests/fixtures/amm_conservation_valid_combined.ndjson, python/tests/fixtures/amm_conservation_violating_snapshot.ndjson, python/tests/fixtures/amm_conservation_violating_combined.ndjson, data/parquet/order_book_raw/** (replaced), data/parquet/order_book_combined/** (replaced), data/parquet.broken-backup-2026-04-27/** (broken parquets archived for forensics)"

## Followups (not in scope of this debug session)

1. **Wire the AMM-conservation gate into bulk ingest.** `scripts/05_1_bulk_ingest.sh` calls the CLI with `--kind order_book_combined` but never passes a `--raw-src` argument, so `assert_amm_conservation()` is skipped. The CLI itself does not even accept a `--raw-src` flag. This pre-existed the bug fixed here. File a follow-up to add `--raw-src` to the CLI and the bulk script so the gate actually runs in production.
2. **Tighten partition-write null guard.** `write_partitioned_parquet` should raise (not silently write) if any partition column contains nulls, since `__HIVE_DEFAULT_PARTITION__` directories are almost always a sign of upstream bugs in this project.
3. **Schema-vs-real contract test.** Add a "smoke" test that reads 1 line from each NDJSON kind in `data/ndjson/` and asserts all required output columns are non-null after ingest. Would have caught this Wave-1 bug instantly.
