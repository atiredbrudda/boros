---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
fixed_at: 2026-04-24T10:05:35Z
review_path: .planning/phases/01-foundation-infrastructure-spine-data-pipeline-economics-gate/01-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-24T10:05:35Z
**Source review:** `.planning/phases/01-foundation-infrastructure-spine-data-pipeline-economics-gate/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 10
- Fixed: 10
- Skipped: 0

---

## Fixed Issues

### CR-01: `ingest_order_book_combined` called with wrong positional arguments in ingester CLI

**Files modified:** `python/src/boros_brain/data/ingester/cli.py`
**Commit:** `64ef807`
**Applied fix:** Replaced the 4-positional-argument call `ingest_order_book_combined(args.src, args.market_id, args.tick_size, out_root)` with the correct keyword-argument form `ingest_order_book_combined(args.src, market_id=args.market_id, tick_size=args.tick_size, out_root=out_root)`. The function signature uses a `*` keyword-only barrier after `raw_ndjson_path`; the old call was passing `market_id` as `raw_ndjson_path` and raising `TypeError` on the 3rd and 4th positional args.

---

### CR-02: `rescreen.py` ingest stage passes `--dest` but ingester CLI only accepts `--out`

**Files modified:** `python/src/boros_brain/screener/rescreen.py`
**Commit:** `805ded3`
**Applied fix:** Changed `--dest` to `--out` in the subprocess argument list (the ingester CLI argument is named `--out`, not `--dest`). Also corrected the module path from `boros_brain.data.ingester` to `boros_brain.data.ingester.cli` — the package `__init__.py` has no `__main__.py` entry point, so `python -m boros_brain.data.ingester` would fail with "No module named boros_brain.data.ingester.__main__". The CLI entry point lives at `boros_brain.data.ingester.cli` as documented in the module's own docstring.

---

### CR-03: `conn.commit()` called on an autocommit connection in `reward_budget_history.py`

**Files modified:** `python/src/boros_brain/state/writers/reward_budget_history.py`
**Commit:** `912ebe9`
**Applied fix:** Removed `conn.commit()` from `insert_reward_budget_row`. The writer now only executes the INSERT and leaves transaction lifecycle to the caller, per the `db.py` docstring contract. Added an explanatory comment documenting why the call was removed (ProgrammingError in Python 3.12+ autocommit mode, premature-commit risk on non-autocommit connections).

---

### WR-01: Scale calibration formula divide-by-zero when `clo_lower_thresh == 10000.0`

**Files modified:** `python/src/boros_brain/screener/scale_calibration.py`
**Commit:** `7cafc6a`
**Applied fix:** Extracted both denominators (`denom1 = p1.clo_lower_thresh - 10000.0`, `denom2 = p2.clo_lower_thresh - 10000.0`) before division, and added an explicit guard that raises `InsufficientCalibrationData` if either denominator is zero. This reuses the existing exception type (already caught non-fatally by `apply_screener_filters`) so the behaviour is: if a market has `clo_lower_thresh == 10000.0`, SCALE calibration is skipped with a log message rather than producing `inf` or crashing.

---

### WR-02: `r_apr_potential` uses unexplained magic divisor `100.0`

**Files modified:** `python/src/boros_brain/screener/filter.py`
**Commit:** `ef55515`
**Applied fix:** Introduced named constant `COLLATERAL_PHASE1_PROXY = 100.0` with a detailed comment explaining the unit inconsistency (PENDLE vs USD) and a TODO for Phase-3 replacement with `config.screener.required_collateral_pendle`. Also imported `EPOCHS_PER_YEAR` from `.economics_gate` to replace the bare `52` literal, eliminating the duplication. Formula now reads `float(budget_row[0]) * EPOCHS_PER_YEAR / COLLATERAL_PHASE1_PROXY` — semantically identical but self-documenting.

---

### WR-03: Duplicate `model_config` assignment in `SyncStatus` — second silently overwrites first

**Files modified:** `python/src/boros_brain/data/poller/schemas.py`
**Commit:** `3bbce47`
**Applied fix:** Removed the first (incomplete) `model_config = ConfigDict(extra="allow")` assignment on line 28. The class now has a single `model_config = ConfigDict(extra="allow", populate_by_name=True)` directly below the docstring. Net runtime behaviour is unchanged; the fix eliminates the dead assignment that could mislead a future editor adding fields between the two lines.

---

### WR-04: `MarketsPoller.tick()` creates a new `AsyncWeb3 + AsyncHTTPProvider` per market per tick

**Files modified:** `python/src/boros_brain/data/poller/markets_poller.py`
**Commit:** `8a32a37`
**Applied fix:** Added `w3: object | None = None` parameter to `MarketsPoller.__init__`, stored as `self._w3`. In `tick()`, the lazy-create path now uses `self._w3` and raises `RuntimeError` (with clear guidance) if `_w3 is None` when a market without a pre-wired `FIndexReader` is encountered — preventing the silent session leak. Updated `run_markets_poller` to create a single `AsyncWeb3` via `make_arbitrum_rpc(config)` before the polling loop and pass it as `w3=w3` to the constructor. The import of `make_arbitrum_rpc` is moved inside `run_markets_poller` to avoid any circular-import risk at module level.

---

### IN-01: `now_cached()` return annotation says `int` but can return `None` on cold-cache timeout

**Files modified:** `python/src/boros_brain/data/chain_time.py`
**Commit:** `401f44e`
**Applied fix:** Added a `self._value is None` check inside the `except TimeoutError` block. If the cache is cold (no prior value) and the RPC times out, `RuntimeError` is raised with an actionable message. If the cache has a prior value, the existing `log.warning(..., stale=True)` path runs as before. The `# type: ignore[return-value]` suppression at the `return` line is now accurate — `self._value` is guaranteed non-None at that point.

---

### IN-02: `screener/filter.py` order-book SQL queries column `size` which does not exist in `order_book_combined` parquet

**Files modified:** `python/src/boros_brain/screener/filter.py`
**Commit:** `4f95e62`
**Applied fix:** Changed `SELECT ... size FROM order_book_combined` to `SELECT ... sz_combined_float AS size FROM order_book_combined`. The `order_book_combined` ingester (`order_book.py`) renames the column via `_parse_wei_size(df, "sz_combined", "sz_combined_wei", "sz_combined_float")` and drops the original; the parquet schema has `sz_combined_float`, not `size`. Using `AS size` preserves the downstream DataFrame column name expected by callers.

---

### IN-03: `screener/filter.py` market_trades SQL queries column `size` which does not exist after ingester renames it

**Files modified:** `python/src/boros_brain/screener/filter.py`
**Commit:** `4f95e62` *(same commit as IN-02 — both changes are in `filter.py`)*
**Applied fix:** Changed `SELECT ... size ... FROM market_trades` to `SELECT ... size_float AS size ... FROM market_trades`. The `market_trades` ingester drops the raw `size` column via `df.drop("size")` and replaces it with `size_float` and `size_wei`. Using `size_float AS size` preserves the column name `size` that downstream metric functions reference.

---

## Skipped Issues

None — all 10 findings were fixed.

---

_Fixed: 2026-04-24T10:05:35Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
