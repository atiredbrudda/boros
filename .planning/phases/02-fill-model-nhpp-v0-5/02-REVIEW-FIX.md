---
phase: 02-fill-model-nhpp-v0-5
fixed_at: 2026-04-24T00:00:00Z
review_path: .planning/phases/02-fill-model-nhpp-v0-5/02-REVIEW.md
fix_scope: critical_warning
findings_in_scope: 5
fixed: 5
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-04-24T00:00:00Z
**Source review:** `.planning/phases/02-fill-model-nhpp-v0-5/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 5
- Skipped: 0

All five Warning findings were fixed and committed atomically. Each commit passed all pre-commit hooks (architecture lint, ruff, ruff-format, mypy, single-writer lint, private-key check, INFRA-14 time.time lint). Two pre-existing lint errors in `report.py` (UP038 `isinstance` tuple syntax, missing `dict` type parameters) were surfaced by the hook run on the WR-04 commit and fixed in that same commit.

---

## Fixed

### WR-01: Rosenblatt compensator uses midpoint rule

**Files modified:** `python/src/boros_brain/fill_model/calibration.py`
**Commit:** `4fc4ae1`
**Applied fix:**
- Added `import bisect` and `from collections.abc import Callable`.
- Added `_integrate_step(t_prev, t_curr, sorted_bins, bin_lambda)` helper that splits the integration interval at bin boundaries, correctly accumulating each bin's constant rate over its segment rather than sampling a single midpoint.
- Changed `gof_rosenblatt` signature to accept optional `sorted_bins` and `bin_lambda` keyword arguments and a typed `lambda_fn: Callable[[float], float]` parameter.
- When `sorted_bins` and `bin_lambda` are both provided, the loop calls `_integrate_step` for each inter-arrival gap; otherwise falls back to the midpoint approximation for non-step-function callers.
- Updated the call site in `run_calibration` to pass `sorted_bins=sorted_bins, bin_lambda=bin_lambda`.
- Also fixed a pre-existing SIM108 ruff warning (ternary expression for `current_ts`) surfaced by the hook.

### WR-02: Negative `fit_age_s` not detected

**Files modified:** `python/src/boros_brain/fill_model/predict.py`
**Commit:** `bd0d9e3`
**Applied fix:**
- After computing `fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)`, added an `if fit_age_s < 0` guard that logs `fill_model.predict_future_dated_fit` (with `market_id`, `side`, `fit_window_end_ts`, `current_chain_ts`, `fit_age_s`) and resets `fit_age_s = 0.0`.
- Added explanatory comment noting the cause (clock drift or bootstrap artifact with future window end) and why treating as age=0 is the correct response rather than raising.
- Also fixed a pre-existing UP038 ruff warning (`isinstance(x, (int, float))` → `isinstance(x, int | float)`) surfaced by the hook.

### WR-03: DuckDB connection not closed on exception

**Files modified:** `python/src/boros_brain/fill_model/features.py`
**Commit:** `c549cb6`
**Applied fix:**
- Wrapped `conn.execute(...).pl()` in `try/finally: conn.close()` so the DuckDB connection is always released even when the query raises (missing parquet file, schema mismatch, etc.), preventing a leaked read lock on the parquet directory.

### WR-04: `predict` subcommand uses `datetime.now(UTC)` for `current_chain_ts`

**Files modified:** `python/src/boros_brain/fill_model/cli.py`, `python/src/boros_brain/fill_model/report.py`
**Commit:** `a09fb90`
**Applied fix:**
- Added a four-line inline comment above `current_chain_ts=int(datetime.now(UTC).timestamp())` in the `predict` subcommand body explaining that `chain_time` is not initialised in the CLI (no RPC), wall-clock is an approximation acceptable for operator diagnostics only, and noting the INFRA-14 acknowledged deviation.
- Expanded the `predict` subparser `help=` string to surface the wall-clock staleness caveat to operators using `--help`.
- Fixed pre-existing mypy errors in `report.py` (`-> dict` → `-> dict[str, object]`, `list[dict]` → `list[dict[str, object]]`) and pre-existing ruff UP038 errors (`isinstance(x, (int, float))` → `isinstance(x, int | float)`) that were surfaced by the hook run on this commit.

### WR-05: Queue tracker parquet paths hardcoded — silent failure when missing

**Files modified:** `python/src/boros_brain/fill_model/queue_tracker.py`
**Commit:** `6063b92`
**Applied fix:**
- Added `from pathlib import Path` import.
- In `_load_trades`: before calling `pl.scan_parquet`, checks `Path("data/parquet/market_trades").exists()`. If absent, logs `fill_model.queue_tracker_parquet_missing` at ERROR level (with `path`, `market_id`, `side`) and returns `(pl.DataFrame(), "degraded")` so the caller sees a degraded coverage signal rather than a silent empty result.
- In `_load_raw_snapshots`: same guard for `Path("data/parquet/order_book_raw")`, returning `pl.DataFrame()` on missing directory with the same structured error log.

---

_Fixed: 2026-04-24T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
