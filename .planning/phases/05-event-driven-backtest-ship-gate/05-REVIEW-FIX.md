---
phase: 05-event-driven-backtest-ship-gate
fix_scope: critical_warning
findings_in_scope: 4
fixed: 4
skipped: 0
iteration: 1
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-04-26T00:00:00Z
**Source review:** .planning/phases/05-event-driven-backtest-ship-gate/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4
- Fixed: 4
- Skipped: 0

## Fixed Issues

### WR-01: `plot` subcommand passes `list[dict]` where `list[BacktestRunOutput]` is required

**Files modified:** `python/src/boros_brain/backtest/cli.py`
**Commit:** 70df182
**Applied fix:** Added `from .schemas import BacktestRunOutput` import inside `_dispatch_plot` and replaced `rows = df.to_dicts()` with `rows: list[BacktestRunOutput] = [BacktestRunOutput.model_validate(r) for r in df.to_dicts()]`. This ensures `plot_calibration` receives properly typed model instances whose attributes can be accessed rather than plain dicts.

---

### WR-02: `_run_one_perturbation` silently persists only the first row

**Files modified:** `python/src/boros_brain/backtest/perturbation.py`
**Commit:** 30b10c4
**Applied fix:** Replaced the `if result.rows: first = result.rows[0]; tagged = first.model_copy(...)` block with a `for result_row in result.rows:` loop that tags and persists every row. All bootstrap rows from a child run are now written to parquet, consistent with the baseline path in `cli.py`.

---

### WR-03: Contour grid collapses to a degenerate single point when a knob value is zero

**Files modified:** `python/src/boros_brain/backtest/contour_2d.py`
**Commit:** 6146ce4
**Applied fix:** Added a guard immediately after resolving `a_unp` and `b_unp` that raises `ValueError` when either value is `0.0`, with a message naming the offending knob path. This prevents `np.linspace(0.0, 0.0, grid_size)` from silently producing a degenerate all-zero grid.

---

### WR-04: Only compares first rows of each branch instead of mean across all rows

**Files modified:** `python/src/boros_brain/backtest/sweeps/forfeit_branch.py`
**Commit:** f1bef2f
**Applied fix:** Added `import statistics` at the top of the module and replaced the single-index divergence calculation (`benign_rows[0].annualized_pnl_pct - punitive_rows[0].annualized_pnl_pct`) with `statistics.mean()` over all rows in each branch list. The divergence is now computed from the true per-branch mean rather than an arbitrary first row.

---

_Fixed: 2026-04-26T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
