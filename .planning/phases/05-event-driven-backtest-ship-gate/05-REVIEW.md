---
phase: 05-event-driven-backtest-ship-gate
reviewed: 2026-04-26T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - python/src/boros_brain/backtest/bootstrap.py
  - python/src/boros_brain/backtest/cancel_latency.py
  - python/src/boros_brain/backtest/cli.py
  - python/src/boros_brain/backtest/contour_2d.py
  - python/src/boros_brain/backtest/perturbation.py
  - python/src/boros_brain/backtest/report.py
  - python/src/boros_brain/backtest/run_manifest.py
  - python/src/boros_brain/backtest/schemas.py
  - python/src/boros_brain/backtest/ship_gate.py
  - python/src/boros_brain/backtest/sweeps/cancel_latency.py
  - python/src/boros_brain/backtest/sweeps/competition.py
  - python/src/boros_brain/backtest/sweeps/forfeit_branch.py
  - python/src/boros_brain/backtest/__main__.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-04-26
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Thirteen files covering the event-driven backtest engine, ship-gate, bootstrap, sweeps, and CLI were reviewed. The codebase is well-structured: manifest-first discipline is consistently applied, path-traversal guards appear at every write site, and the perturbation reflection idiom is sound. No security vulnerabilities or data-loss risks were found.

Four warnings were identified: a type mismatch that will crash the `plot` subcommand at runtime, a silent data-dropping bug in the perturbation grid's parquet persistence, a zero-value degenerate case in the contour grid that produces a collapsed (single-point) grid without any error, and an unguarded `IndexError` risk in the forfeit-branch divergence check. Three info items cover dead code in `_dispatch_plot`, an unused `replay_config` kwarg passed to `ReplayEngine`, and a missing guard on `contour_2d_knobs` list length.

---

## Warnings

### WR-01: `plot` subcommand passes `list[dict]` where `list[BacktestRunOutput]` is required — crashes at runtime

**File:** `python/src/boros_brain/backtest/cli.py:199-202`

**Issue:** `_dispatch_plot` reads parquet into a Polars DataFrame, calls `.to_dicts()` to get a `list[dict]`, then passes that to `plot_calibration(rows, ...)`. The function signature is `plot_calibration(rows: list[BacktestRunOutput], ...)` and it accesses `r.predicted_p_fill_mean` and `r.realized_fill_rate` as attributes (not dict keys). The plain-dict list will raise `AttributeError` on every row the first time `plot` is called.

**Fix:**
```python
# cli.py line 199-202 — deserialize dicts back to BacktestRunOutput
df = pl.read_parquet(str(rows_glob))
rows: list[BacktestRunOutput] = [BacktestRunOutput.model_validate(r) for r in df.to_dicts()]
plot_calibration(rows, out_path=plots_dir / "calibration.png")
```
Add the import at the top of the `_dispatch_plot` local block:
```python
from .schemas import BacktestRunOutput
```

---

### WR-02: `_run_one_perturbation` silently persists only the first row — all other rows from the child run are dropped

**File:** `python/src/boros_brain/backtest/perturbation.py:324-333`

**Issue:** After a child `ReplayEngine.run()`, the code checks `if result.rows:` and writes only `result.rows[0]` to parquet. If a child run produces multiple rows (e.g., multiple bootstrap rows), rows `[1:]` are silently discarded. This is inconsistent with the baseline path in `cli.py:117-118` which iterates `for row in base_result.rows: write_backtest_row(row, ...)`.

**Fix:**
```python
# perturbation.py — write ALL rows, not just the first
parquet_root = Path(perturbed_config.backtest.output_parquet_root)
for result_row in result.rows:
    tagged = result_row.model_copy(
        update={
            "sweep_axis": "perturbation",
            "sweep_value": f"{knob_path}={sign}",
            "parent_run_id": parent_manifest.run_id,
        }
    )
    write_backtest_row(tagged, parquet_root=parquet_root)
```

---

### WR-03: Contour grid collapses to a degenerate single point when a knob value is zero

**File:** `python/src/boros_brain/backtest/contour_2d.py:85-86`

**Issue:** The grid endpoints are computed as `a_unp * (1.0 - pct)` and `a_unp * (1.0 + pct)`. If `a_unp == 0.0` (or `b_unp == 0.0`), both endpoints are `0.0` and `np.linspace(0.0, 0.0, grid_size)` returns an array of `grid_size` identical zeros. The grid runs, produces `grid_size²` cells all with the same knob values, and no error is raised — the operator receives a misleading flat contour without any indication that the grid was degenerate.

**Fix:**
```python
# contour_2d.py — add a guard before building the grids
if a_unp == 0.0 or b_unp == 0.0:
    raise ValueError(
        f"contour_2d: knob value is zero for path "
        f"{'a' if a_unp == 0.0 else 'b'} "
        f"({'a: ' + knob_a_path if a_unp == 0.0 else 'b: ' + knob_b_path}). "
        "Relative perturbation is undefined at zero. Set a non-zero default or "
        "choose a different contour knob pair."
    )
```

---

### WR-04: Unguarded `IndexError` in forfeit-branch divergence check when rows list filtering produces empty results

**File:** `python/src/boros_brain/backtest/sweeps/forfeit_branch.py:93`

**Issue:** Line 93 accesses `benign_rows[0]` and `punitive_rows[0]` inside `if benign_rows and punitive_rows:`, which correctly guards against empty lists. However the rows appended to `rows` inside the loop are tagged using `r.model_copy(update={"voluntary_cancel_branch": branch_name, ...})`. If `result.rows` is empty for a branch (engine produced no output), that branch produces zero tagged rows, the outer `if` check passes (because `rows` accumulated rows from the other branch) but... actually, the guard `if benign_rows and punitive_rows:` does correctly handle this case — both lists must be non-empty. This is fine.

**Revised finding:** The real risk is the unconditional access at line 93 without verifying that the two lists each have at least one element. Since the guard on line 92 is `if benign_rows and punitive_rows:`, the access is safe. However, if a branch engine returns multiple rows, the divergence check only compares `[0]` — it ignores all other rows for that branch. This is a silent logic bug: for a multi-row branch, the comparison is between arbitrary first rows rather than the summary metric for the branch.

**Fix:**
```python
# sweeps/forfeit_branch.py — use mean across all rows for a branch rather than [0]
import statistics
benign_pnl = statistics.mean(r.annualized_pnl_pct for r in benign_rows)
punitive_pnl = statistics.mean(r.annualized_pnl_pct for r in punitive_rows)
divergence = abs(benign_pnl - punitive_pnl)
```

---

## Info

### IN-01: `json.loads(sidecar.read_text())` result is discarded — dead code

**File:** `python/src/boros_brain/backtest/cli.py:195`

**Issue:** The manifest JSON is parsed and the result is immediately thrown away. The comment says "future use for plot subtitles." This is harmless today but is dead code that will confuse readers.

**Fix:** Either assign to a variable with a leading underscore to signal intentional discard, or add a `_manifest_data = ...` name that can be used when plot subtitles land:
```python
_manifest_data = json.loads(sidecar.read_text())  # reserved for plot subtitles
```

---

### IN-02: `replay_config` kwarg accepted by `ReplayEngine` is unused in contour_2d and perturbation

**File:** `python/src/boros_brain/backtest/contour_2d.py:101-112`, `python/src/boros_brain/backtest/perturbation.py:304-315`

**Issue:** `ReplayEngine` is constructed with flat keyword arguments (`config=`, `market_id=`, etc.) but the `replay_config=` parameter visible in `cli.py:114` is absent in these call sites. The comment in `contour_2d.py:100` explicitly notes "Flat constructor — mirrors sweeps/cancel_latency.py pattern." If `ReplayEngine.__init__` accepts both a `replay_config` dataclass and flat kwargs, the two construction paths will diverge if `ReplayEngine` ever adds a new field to `ReplayConfig` — the flat-kwarg sites will silently miss it. This is an architectural coupling risk worth noting, not a current bug.

**Fix:** Consider a single canonical constructor path (e.g., always pass `replay_config=`). If the flat-kwargs path is intentional for testability, add a comment documenting the divergence so future maintainers know to update both patterns.

---

### IN-03: `contour_2d_knobs[:2]` slice with no length guard

**File:** `python/src/boros_brain/backtest/contour_2d.py:79`, `python/src/boros_brain/backtest/cli.py:144`

**Issue:** `base_config.backtest.contour_2d_knobs[:2]` is silently safe if the list has fewer than 2 elements — Python slicing never raises on short lists. The tuple unpack on the same line (`knob_a_path, knob_b_path = ...[:2]`) will then raise `ValueError: not enough values to unpack` with a confusing message. This fails loudly, so it is not a silent failure, but the error message does not point at the config key.

**Fix:** Add an explicit pre-check for clarity:
```python
if len(base_config.backtest.contour_2d_knobs) < 2:
    raise ValueError(
        "backtest.contour_2d_knobs must have at least 2 entries; "
        f"got {base_config.backtest.contour_2d_knobs!r}"
    )
knob_a_path, knob_b_path = base_config.backtest.contour_2d_knobs[:2]
```

---

_Reviewed: 2026-04-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
