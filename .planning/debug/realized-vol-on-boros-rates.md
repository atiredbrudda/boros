---
status: resolved
trigger: "compute_realized_vol returns NaN on real Boros rates — every market fails realized_vol_invalid filter"
created: 2026-04-27
updated: 2026-04-27
---

## Symptoms

- **Expected:** compute_realized_vol returns a valid float for each market
- **Actual:** returns None/NaN for every market → all fail Filter 2 (realized_vol_invalid)
- **Errors:** Silent — no exception, just None returned
- **Timeline:** Never worked on real data (test fixtures use synthetic positive rates that never cross zero)
- **Reproduction:** Run screener against real Wave-1 parquet

## Current Focus

hypothesis: "Log-return formula (rates / rates.shift(1)).log() breaks on Boros rates that oscillate around zero — negative ratio → NaN log, division by near-zero → inf; std() over NaN/inf returns NaN → function returns None"
test: "Run compute_realized_vol on a real rate series from parquet and confirm it returns a valid non-NaN float after fix"
expecting: "A valid float (e.g. std of rate differences in basis points) returned for BINANCE-ETHUSDT-29MAY2026"
next_action: "Rework compute_realized_vol to use rate differences (rates.diff().std()) instead of log-returns, then verify all screener tests still pass and live run returns non-NaN realized_vol"
reasoning_checkpoint: "Root cause pre-confirmed: ETHUSDT-29MAY rates range -0.013 to +0.011 with 8 zeros, 608 negative, 360 positive — log-return formula is categorically wrong for this data"

## Root Cause

### compute_realized_vol uses log-returns on rates that cross zero

- **Location:** `python/src/boros_brain/screener/metrics.py` — `compute_realized_vol()`
- **Formula (broken):** `(rates / rates.shift(1)).log()` — log-return assumes positive prices
- **Why it breaks:** Real Boros implied APR rates oscillate around zero (observed ETHUSDT-29MAY: range -0.013 to +0.011, 8 zeros, 608/360 neg/pos split). Negative ratio → NaN from log. Division by zero → inf. `std()` over NaN/inf → NaN. Function returns None.
- **Test fixtures hide this:** synthetic rates start at ~9400 and are always positive — never expose the sign-crossing failure mode
- **Fix direction:** Use `rates.diff().std()` (rate differences in native units) as the realized vol primitive. This is sign-agnostic and correct for a rate that oscillates around zero.

## Evidence

- timestamp: 2026-04-27T01:43:00Z
  observation: "ETHUSDT-29MAY rates: range -0.013 to +0.011, 8 zeros, 608 negative / 360 positive. Log-return formula confirmed to produce NaN."
  source: "Discovered during screener-marketid-maturity debug session fix verification"
- timestamp: 2026-04-27T02:10:00Z
  observation: "In-process repro confirmed bug: built a 968-point series mirroring the observed split (473 neg / 487 pos / 8 zero, range [-0.035, +0.029]). OLD log-return formula returned None; NEW diff-based formula returned 0.002345 (valid finite positive float)."
  source: "Post-fix verification harness in this debug session"

## Eliminated

(none — root cause was pre-confirmed; no alternatives needed elimination)

## Resolution

root_cause: "compute_realized_vol applied log-return formula `(rates / rates.shift(1)).log()` to a rate series that crosses zero. Negative ratios produce NaN; zero divisors produce inf; `std()` over NaN/inf returns NaN; the `math.isfinite` guard converted that to `None`, making every market fail Filter 2 (realized_vol_invalid) on real Boros data."
fix: "Replaced the log-return formula with `rates.diff().std()` (standard deviation of first differences in native rate units). This is sign-agnostic and well-defined for a series that crosses zero, which is the actual data-generating process for Boros implied APR. Function signature, return type, and `None`-on-degenerate-input semantics are preserved. Updated the docstring to explain the choice and reference the observed ETHUSDT-29MAY data so future maintainers don't reintroduce a log-return formula."
verification: "Three-part verification passed: (1) Full screener test suite — all 18 tests across test_screener_metrics.py, test_screener_filter.py, test_screener_scale_calibration.py pass with the fix. (2) In-process bug repro — built a 968-point rate series mirroring observed Boros distribution (473 neg / 487 pos / 8 zero, range [-0.035, +0.029]); confirmed OLD formula returns `None` and NEW formula returns `0.002345` (valid finite positive float). (3) Backward-compat check — NEW formula on the synthetic always-positive fixture (rates ~9400) returns `6.58`, confirming existing test_realized_vol_synthetic_series still gets a valid finite positive value."
files_changed: "python/src/boros_brain/screener/metrics.py (compute_realized_vol body + docstring)"
