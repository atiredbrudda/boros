---
phase: "01"
plan: "01-07"
subsystem: "brain/data + brain/duckdb_layer"
tags: [infra, chain-time, rpc, duckdb, analytics, lint, pre-commit]
dependency_graph:
  requires: [01-01, 01-02, 01-03, 01-04, 01-05]
  provides: [chain-time-cache, rpc-client-factory, duckdb-analytical-layer, no-time-time-lint]
  affects: [01-08, 01-09]
tech_stack:
  added:
    - "web3.py AsyncWeb3 / AsyncHTTPProvider — Arbitrum RPC client"
    - "duckdb sqlite_scanner extension — read-only SQLite + parquet hybrid analytical layer"
  patterns:
    - "TTL cache via time.monotonic() (not time.time()) for cache staleness checks"
    - "Dependency-injection halt_callback pattern — ZMQ bus wired at main.py startup"
    - "sqlite_scanner CALL sqlite_attach() (not ATTACH … USE) to preserve default DDL catalog"
    - "TDD RED → GREEN per task; ruff + mypy + architecture_lint all green at commit"
key_files:
  created:
    - python/src/boros_brain/data/__init__.py
    - python/src/boros_brain/data/rpc_client.py
    - python/src/boros_brain/data/chain_time.py
    - python/src/boros_brain/duckdb_layer/__init__.py
    - python/src/boros_brain/duckdb_layer/setup.py
    - python/src/boros_brain/duckdb_layer/views.sql
    - scripts/no_time_time_lint.py
    - python/tests/test_chain_time_drift.py
    - python/tests/test_no_time_time_in_hotpath.py
    - python/tests/test_duckdb_layer.py
  modified:
    - .pre-commit-config.yaml
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
decisions:
  - "Drift thresholds kept at plan defaults: startup halt = chain_drift_warn_s (5s), runtime halt = chain_drift_halt_s (30s). The startup threshold is intentionally the same as warn_s — tighter than the runtime halt — because startup drift means NTP is badly off and refusing to start is correct."
  - "no_time_time_lint.py uses full-tree walk (not git diff --cached fallback) so tests can inject files without staging them and see the lint fire. Normal pre-commit run behaves the same — walks all .py files under PROTECTED_DIRS every time."
  - "sqlite_scanner: CALL sqlite_attach() chosen over ATTACH … (TYPE sqlite, READ_ONLY) + USE live because USE live makes CREATE VIEW fail (DuckDB rejects DDL in a read-only catalog). The CALL form mounts tables into the in-memory catalog."
  - "DuckDB stub views (SELECT NULL::VARCHAR AS _placeholder WHERE FALSE) registered for empty parquet subdirs — lets plan 01-08 boot without errors before any parquet data exists."
metrics:
  duration_minutes: 11
  completed_date: "2026-04-24"
  tasks_completed: 2
  files_changed: 13
---

# Phase 01 Plan 07: Chain-Time Cache + DuckDB Analytical Layer Summary

Chain-time drift monitor with 1s-TTL cache and pre-commit time.time() ban (INFRA-14), plus DuckDB read-only analytical layer over SQLite + Hive-partitioned parquet (INFRA-04).

## What Was Built

### Task 1 — Chain-time cache + drift monitor + lint (INFRA-14)

**`python/src/boros_brain/data/rpc_client.py`**
- `make_arbitrum_rpc(config)` — returns `AsyncWeb3(AsyncHTTPProvider(rpc_url_arbitrum))`. URL never logged (T-01-07-02).
- `get_latest_block_timestamp(w3)` — awaits `w3.eth.get_block("latest")["timestamp"]`. Callers wrap in `asyncio.wait_for`.

**`python/src/boros_brain/data/chain_time.py`**
- `ChainTimeCache` dataclass: TTL-cached chain timestamp. `now_cached()` uses `time.monotonic()` for cache staleness (not `time.time()` — see below), wraps the RPC call in `asyncio.wait_for(timeout=5.0)` per T-01-07-03. On timeout: WARN + return stale value, no halt.
- `startup_check()` — raises `ChainTimeDriftHalt` if `|time.time() - chain_ts| > chain_drift_warn_s` (5s default). Returns drift float for `chain_time_drift_at_start_seconds` RUN_MANIFEST field.
- `drift_monitor_tick()` — drift > 30s invokes `halt_callback("chain_time_drift", {...})`; drift > 5s logs WARNING.
- Module-level `install(cache)` + convenience `now_cached()` / `startup_check()` / `drift_monitor_tick()` delegates for hot-path modules to import directly.
- `halt_callback` defaults to log-only (`_default_halt_callback`); `main.py` will inject the real `CmdBus.send_kill` wrapper when the ZMQ bus is initialised.

**`scripts/no_time_time_lint.py`**
- Full-tree walk of `python/src/boros_brain/{decision,data,screener}/`.
- Allowed: `chain_time.py` itself (the only file that legitimately measures wall-clock vs chain-time). Test files are outside PROTECTED_DIRS and thus exempt.
- Wired as `no_time_time_hotpath` hook in `.pre-commit-config.yaml` at `stages: [pre-commit]`.

**Tests — 10 passing:**
- `test_startup_check_passes_on_small_drift` — 2s drift (< 5s) passes.
- `test_startup_check_halts_on_large_drift` — 10s drift raises `ChainTimeDriftHalt`.
- `test_now_cached_uses_ttl` — two calls within 0.5s share one RPC call.
- `test_now_cached_refreshes_past_ttl` — calls 1.2s apart trigger two RPC calls.
- `test_drift_monitor_warn_threshold` — 7s drift logs WARNING, no halt.
- `test_drift_monitor_halt_threshold` — 35s drift fires `halt_callback`.
- `test_chain_time_manifest_field_populated` — `startup_check()` returns `float`.
- `test_lint_passes_on_clean_tree` — clean source tree exits 0.
- `test_lint_fails_on_injected_time_time_in_data` — injected file causes exit 1.
- `test_lint_ignores_time_time_in_tests` — test files exempt from lint.

### Task 2 — DuckDB analytical layer (INFRA-04)

**`python/src/boros_brain/duckdb_layer/setup.py`**
- `attach_sqlite_readonly(con, sqlite_path)` — loads `sqlite_scanner` extension, calls `CALL sqlite_attach(path, overwrite=true)`. Tables visible directly (no schema prefix). Writes raise `duckdb.Error`.
- `register_parquet_views(con, parquet_root)` — for each of 6 subdirs: if `.parquet` files exist, registers the Hive-partitioned view from `views.sql`; otherwise registers a zero-row stub (`SELECT NULL::VARCHAR AS _placeholder WHERE FALSE`).
- `open_analytical_conn(sqlite_path, parquet_root)` — `:memory:` DuckDB connection, calls both helpers above.

**`python/src/boros_brain/duckdb_layer/views.sql`**
6 views: `market_trades`, `order_book_raw`, `order_book_combined`, `underlying_apr`, `market_data`, `settlement`. Each uses `read_parquet('…/**/*.parquet', hive_partitioning=true)`.

**Tests — 5 passing:**
- `test_attach_sqlite_readonly` — reads 1-row SQLite table; INSERT raises `duckdb.Error`.
- `test_parquet_views_graceful_on_empty_root` — empty root, no raise, returns `[]`.
- `test_parquet_views_with_sample_data` — Hive-partitioned parquet visible via view.
- `test_views_sql_file_contains_expected_views` — all 5 required views in `views.sql`.
- `test_duckdb_layer_not_imported_from_hotpath` — `bus/`, `decision/`, `manifest/` are all clean.

## Drift Thresholds

Startup halt threshold = `chain_drift_warn_s` (5s default). This matches the plan spec: startup is stricter than the runtime halt (30s). A 10s startup drift means NTP is badly off; refusing to start is the correct behaviour.

## DuckDB Read-Only Attach — Verification

`CALL sqlite_attach(path, overwrite=true)` opens the SQLite file with `SQLITE_OPEN_READONLY`. Attempting `INSERT INTO clo_history …` through the DuckDB connection raises `duckdb.CatalogException` (a subclass of `duckdb.Error`) — verified empirically in `test_attach_sqlite_readonly`.

The alternative `ATTACH … (TYPE sqlite, READ_ONLY) + USE live` approach was rejected because `USE live` switches the default catalog to the read-only attach, causing `CREATE OR REPLACE VIEW` to fail with `InvalidInputException: Cannot execute statement of type "CREATE" on database "live" which is attached in read-only mode`. The `CALL sqlite_attach` approach mounts tables into the in-memory catalog without this issue.

## Parquet View Stub Behaviour

When `parquet_root/market_trades/` is empty (pre-01-08), the view is:

```sql
CREATE OR REPLACE VIEW market_trades AS
SELECT NULL::VARCHAR AS _placeholder WHERE FALSE
```

`SELECT * FROM market_trades LIMIT 1` returns `[]` — no error. Once 01-08 writes the first parquet file, a fresh `open_analytical_conn` call registers the real view.

## no_time_time_lint Findings

No pre-existing `time.time()` calls found in `brain/{decision,data,screener}/` on the clean tree. The only hits in the data module are the two deliberate usages inside `chain_time.py` (measuring drift vs chain-time in `startup_check` and `drift_monitor_tick`), which are in the `ALLOWED_FILES` set.

## Wiki Pages Filed

- `[[Chain-time discipline]]` — documents the `time.time()` ban, drift thresholds, macOS sleep-wake pitfall (PITFALLS §C7), and the `now_cached()` / `startup_check()` / `drift_monitor_tick()` API.
- `[[DuckDB analytical layer]]` — documents the `sqlite_scanner` attach approach, Hive-partitioned parquet views, stub behaviour for empty roots, and the hot-path isolation invariant.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `stages: [commit]` deprecated pre-commit stage name**
- **Found during:** Task 1 commit (pre-commit warning)
- **Issue:** `stages: [commit]` is a deprecated stage alias; pre-commit emits a warning about future removal.
- **Fix:** Changed to `stages: [pre-commit]` in `.pre-commit-config.yaml`.
- **Files modified:** `.pre-commit-config.yaml`
- **Commit:** 16b4ece

**2. [Rule 1 - Bug] `AsyncWeb3` not imported in `chain_time.py`**
- **Found during:** Task 1 commit (ruff F821 + mypy `name-defined`)
- **Issue:** `chain_time.py` used `AsyncWeb3` as a type annotation in the `@dataclass` field but didn't import it — ruff F821 + mypy `name-defined` errors.
- **Fix:** Added `from web3 import AsyncWeb3` import.
- **Files modified:** `python/src/boros_brain/data/chain_time.py`
- **Commit:** 16b4ece

**3. [Rule 1 - Bug] `HaltCallback` dict param missing type args (mypy strict)**
- **Found during:** Task 1 commit (mypy `type-arg`)
- **Issue:** `Callable[[str, dict], Awaitable[None]]` — `dict` needs type args under `--strict`.
- **Fix:** Changed to `dict[str, Any]` with `from typing import Any` import.
- **Files modified:** `python/src/boros_brain/data/chain_time.py`
- **Commit:** 16b4ece

**4. [Rule 1 - Bug] `no_time_time_lint.py` injection test failed**
- **Found during:** Task 1 test run (GREEN phase)
- **Issue:** The lint used `git diff --cached` to discover files; when staged files existed (the new data module), the fallback to full-tree walk never triggered, so the injected test file was missed.
- **Fix:** Rewrote `_staged_files()` to always do a full-tree walk of `PROTECTED_DIRS` instead of conditional fallback. Behaviour is identical for pre-commit hooks (which don't care about staged vs on-disk) and is correct for direct test invocation.
- **Files modified:** `scripts/no_time_time_lint.py`
- **Commit:** 16b4ece

**5. [Rule 1 - Bug] DuckDB `USE live` broke `CREATE VIEW` in `register_parquet_views`**
- **Found during:** Task 2 test run (GREEN phase)
- **Issue:** `ATTACH … (TYPE sqlite, READ_ONLY) + USE live` switched the default catalog to the read-only attach. Subsequent `CREATE OR REPLACE VIEW` calls raised `InvalidInputException`.
- **Fix:** Switched to `CALL sqlite_attach(path, overwrite=true)` (older but functional API) which mounts tables into the in-memory catalog without changing the default catalog for DDL.
- **Files modified:** `python/src/boros_brain/duckdb_layer/setup.py`
- **Commit:** d21af81

**6. [Rule 1 - Bug] SQL comment lines included in split statements**
- **Found during:** Task 2 test run (GREEN phase, `test_parquet_views_with_sample_data`)
- **Issue:** `views.sql` split by `;` included fragments containing only `-- comment` lines, which DuckDB tried to parse as SQL and raised `ParserException`.
- **Fix:** Strip `--` comment lines before splitting the DDL string.
- **Files modified:** `python/src/boros_brain/duckdb_layer/setup.py`
- **Commit:** d21af81

## Self-Check: PASSED

All 10 created source files verified present on disk.
All 4 task commits (32a1e07, 16b4ece, 88e26be, d21af81) verified in git log.
15/15 tests pass: `uv run pytest tests/test_chain_time_drift.py tests/test_no_time_time_in_hotpath.py tests/test_duckdb_layer.py`.
