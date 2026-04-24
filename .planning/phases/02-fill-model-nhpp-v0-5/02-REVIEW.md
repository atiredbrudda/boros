---
phase: 02-fill-model-nhpp-v0-5
reviewed: 2026-04-24T00:00:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - python/src/boros_brain/config/schema.py
  - python/src/boros_brain/fill_model/__init__.py
  - python/src/boros_brain/fill_model/__main__.py
  - python/src/boros_brain/fill_model/amm_consumption.py
  - python/src/boros_brain/fill_model/artifact.py
  - python/src/boros_brain/fill_model/calibration.py
  - python/src/boros_brain/fill_model/cli.py
  - python/src/boros_brain/fill_model/config.py
  - python/src/boros_brain/fill_model/constants.py
  - python/src/boros_brain/fill_model/features.py
  - python/src/boros_brain/fill_model/fit.py
  - python/src/boros_brain/fill_model/predict.py
  - python/src/boros_brain/fill_model/queue_tracker.py
  - python/src/boros_brain/fill_model/refit_loop.py
  - python/src/boros_brain/fill_model/report.py
  - python/src/boros_brain/fill_model/schemas.py
  - python/src/boros_brain/main.py
  - python/src/boros_brain/state/migrations/versions/0003_fill_model_fits.py
  - python/src/boros_brain/state/writers/fill_model_fits.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-24T00:00:00Z
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

This is the NHPP fill model implementation (statsmodels GLM Poisson, Rosenblatt GoF, queue tracker, calibration pipeline, and refit loop). The code is architecturally sound and the design intent is well-communicated through inline comments and wiki links. No critical issues were found.

Five warnings were identified: two are logic bugs that produce silently wrong results (the Rosenblatt compensator using midpoint evaluation rather than the correct inter-arrival integral, and a `fit_age_s` staleness check that can compute a negative age without detection), two are missing-error-handling gaps (DuckDB connection not closed on exception in `features.py`, and unchecked `run_id` field on the predict-subcommand `current_chain_ts` using wall-clock in the CLI), and one is a correctness concern with the queue tracker's hardcoded parquet paths. Four info items cover code style, a NaN check idiom, a non-standard import structure, and an unreachable branch.

---

## Warnings

### WR-01: Rosenblatt compensator uses midpoint rule — systematically biased for non-constant λ

**File:** `python/src/boros_brain/fill_model/calibration.py:70-77`

**Issue:** `gof_rosenblatt` integrates the compensator via a single-point midpoint evaluation per inter-arrival interval:

```python
mid = 0.5 * (t_prev + t_curr)
compensator.append(compensator[-1] + lambda_fn(mid) * (t_curr - t_prev))
```

The Rosenblatt time-change requires `∫_{t_{i-1}}^{t_i} λ(s) ds`. For the step-function λ used in `run_calibration`, the midpoint is exact only when the integration interval falls entirely within a single bin. When an inter-arrival gap straddles two bins, the midpoint picks one bin's rate and misses the contribution from the adjacent bin. In the test scenario where events span multiple bins (as they do in the holdout window), this produces systematically wrong compensator gaps and an artificially well-fitting (or artificially bad) KS result depending on which bin the midpoint happens to land in.

The comment acknowledges this ("v0.5 — scipy.integrate.quad is more accurate but 10-100× slower") but the documented trade-off understates the risk: for the step-function case, piecewise-exact integration is O(n_bins_crossed) per gap — not `quad` — and is not materially slower.

**Fix:** For step-function λ, integrate exactly by splitting at bin boundaries:

```python
def _integrate_step(t_prev: float, t_curr: float, sorted_bins: list[float], bin_lambda: dict[float, float]) -> float:
    """Exact integral of step-function λ from t_prev to t_curr."""
    total = 0.0
    # Find first bin containing t_prev
    lo = bisect.bisect_right(sorted_bins, t_prev) - 1
    lo = max(lo, 0)
    t = t_prev
    while t < t_curr:
        bin_end = sorted_bins[lo + 1] if lo + 1 < len(sorted_bins) else t_curr
        seg_end = min(bin_end, t_curr)
        lam = bin_lambda.get(sorted_bins[lo], 0.0)
        total += lam * (seg_end - t)
        t = seg_end
        lo += 1
    return total
```

Replace the midpoint body with a call to this helper inside `gof_rosenblatt` (passing `sorted_bins` and `bin_lambda` as parameters, or keeping the callable form for non-step cases by switching on type).

---

### WR-02: Negative `fit_age_s` not detected — staleness check silently passes for future-dated fits

**File:** `python/src/boros_brain/fill_model/predict.py:90-101`

**Issue:**

```python
fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)
if fit_age_s > config.fill_model.fit_max_staleness_s:
    raise FillModelNoFreshFitError(...)
```

If `fit.fit_window_end_ts` is greater than `req.current_chain_ts` (possible when chain time rolls back or a bootstrap artifact is persisted with a future window end — e.g., from a machine with a drifted clock), `fit_age_s` is negative. The staleness check `fit_age_s > fit_max_staleness_s` passes (negative < positive), the warn-staleness check also passes, and the fit is used without a warning. The fit may be from a future window and its covariates meaningless for the current moment.

**Fix:** Add a non-negativity guard immediately after computing `fit_age_s`:

```python
fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)
if fit_age_s < 0:
    log.warning(
        "fill_model.predict_future_dated_fit",
        market_id=req.market_id,
        side=req.side,
        fit_window_end_ts=fit.fit_window_end_ts,
        current_chain_ts=req.current_chain_ts,
        fit_age_s=fit_age_s,
    )
    # Treat as age=0 (fresh); do not raise — the operator warning is sufficient.
    fit_age_s = 0.0
```

---

### WR-03: DuckDB connection not closed on exception in `build_features_table`

**File:** `python/src/boros_brain/fill_model/features.py:179-190`

**Issue:**

```python
conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")

df = conn.execute(_FEATURE_SQL, {...}).pl()
```

`conn` is never closed on the happy path or on exception. `open_analytical_conn` returns a DuckDB connection object. DuckDB connections hold file locks on parquet glob patterns — if `conn.execute(...)` raises (e.g., a missing parquet file, a schema mismatch on the combined book), the connection is leaked, leaving a read lock on the parquet directory. On a re-run before GC collects the connection, a second `open_analytical_conn` call may fail to open the same parquet path.

**Fix:** Wrap in a context manager or explicit try/finally:

```python
conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")
try:
    df = conn.execute(_FEATURE_SQL, {...}).pl()
finally:
    conn.close()
```

Alternatively, if `open_analytical_conn` returns a context-manager-compatible object, use `with open_analytical_conn(...) as conn:`.

---

### WR-04: `predict` subcommand uses `datetime.now(UTC)` for `current_chain_ts` — violates INFRA-14

**File:** `python/src/boros_brain/fill_model/cli.py:105`

**Issue:**

```python
req = PredictInput(
    ...
    current_chain_ts=int(datetime.now(UTC).timestamp()),
)
```

CLAUDE.md INFRA-14 bans wall-clock time comparisons in `brain/data/`, `brain/decision/`, `brain/screener/`, and `brain/fill_model/`. The CLI is under `fill_model/`, so this usage is in-scope for the lint. The `no_time_time_lint.py` regex may or may not match `datetime.now(UTC).timestamp()` depending on its pattern (it likely targets `time.time()` specifically), but the semantic violation is the same: the CLI predict subcommand computes a staleness check based on wall clock, not chain time, so in a backtest or diverged-clock scenario the staleness guard gives wrong results.

Additionally, the `chain_time` module is not initialized in the CLI (`install_chain_time` is never called), so `chain_time.now_cached()` cannot be used as a drop-in. This is an acknowledged CLI limitation but the wall-clock usage should be documented explicitly.

**Fix:** Add a comment at that line that acknowledges the deviation and why it is acceptable for the CLI diagnostic path:

```python
# CLI-only: chain_time not initialized here (no RPC). Wall-clock is an
# approximation; staleness check may be wrong in clock-skew scenarios.
# This is acceptable for operator diagnostics — not used by the 1 Hz loop.
current_chain_ts=int(datetime.now(UTC).timestamp()),
```

Additionally, note in the `build_parser` help text for `predict` that staleness results are wall-clock-based.

---

### WR-05: Queue tracker parquet paths are hardcoded strings — break under non-default working directories

**File:** `python/src/boros_brain/fill_model/queue_tracker.py:88, 114`

**Issue:**

```python
trades = pl.scan_parquet("data/parquet/market_trades/**/*.parquet").filter(...)
...
return pl.scan_parquet("data/parquet/order_book_raw/**/*.parquet").filter(...)
```

Both paths are bare relative strings with no configuration binding. They assume the process working directory is the repo root. If `boros-brain` is launched from a different directory (e.g., via launchd with a different `WorkingDirectory`), or in tests that `chdir`, these globs resolve to the wrong location and fail silently (polars returns an empty DataFrame from a glob that matches zero files, rather than raising). The result would be `raw.is_empty()` and `QueueTracker.replay_window` returning an empty `ReplayResult` — which the downstream fit sees as zero events and produces a degraded fit with no error.

**Fix:** Route through `BotConfig` or a dedicated path config. At minimum, make the base directory configurable:

```python
# In __init__:
self._parquet_root = Path(config.infra.parquet_root)  # add to InfraConfig

# In _load_trades:
trades = pl.scan_parquet(str(self._parquet_root / "market_trades/**/*.parquet")).filter(...)
```

If adding a new knob is deferred, at minimum assert the path exists and log an error rather than returning empty:

```python
trade_glob = Path("data/parquet/market_trades")
if not trade_glob.exists():
    log.error("fill_model.queue_tracker_parquet_missing", path=str(trade_glob))
    return pl.DataFrame(), coverage
```

---

## Info

### IN-01: `gof_lr_ratio_threshold` config field is never checked in `calibration.py` or `predict.py`

**File:** `python/src/boros_brain/fill_model/config.py:60-63`

**Issue:** `FillModelConfig.gof_lr_ratio_threshold` is declared as a knob and described as "bootstrap-calibrated at first fit." However, neither `run_calibration` (which does compute `lr_vs_null`) nor `predict` uses this field in any branch. The LR ratio is computed and stored in the `CalibrationReport` and in `FitArtifact.gof_lr_vs_null`, but the threshold comparison that would trigger a "degraded" status based on LR is not implemented. Only the KS p-value threshold (`gof_ks_pval_threshold`) is actually checked (line 274 of `calibration.py`).

This is likely intentional for v0.5 (the field is documented as "None until the calibration run populates it"), but the fact that `bootstrap_gof_threshold` already computes the calibrated value and returns it (line 133 of `calibration.py`) with no caller persisting it back to config means the bootstrap runs but its output is discarded.

**Fix:** Either implement the threshold check in `run_calibration` alongside the existing KS check, or add a TODO comment at line 274 of `calibration.py` making the deferred nature explicit:

```python
# TODO (Phase 2 post-v0.5): add gof_lr_ratio_threshold check here, mirroring
# the KS check above. bootstrap_gof_threshold() already computes the value;
# it needs a caller that persists the result back into config or into state.
```

---

### IN-02: Idiomatic NaN check replaced by `x != x` comparison in `report.py`

**File:** `python/src/boros_brain/fill_model/report.py:78-79`

**Issue:**

```python
ll_str = f"{ll:.2f}" if isinstance(ll, (int, float)) and not (ll != ll) else "nan"
```

The `(ll != ll)` pattern is a C-era NaN check. In Python, `math.isnan(ll)` is clearer, handles the same cases, and is lint-compliant. The current pattern will also silently produce wrong output for `None` (which passes `isinstance` as `False`, routing to `"nan"` correctly by accident, but is confusing).

**Fix:**
```python
import math
ll_str = f"{ll:.2f}" if isinstance(ll, float) and not math.isnan(ll) else "nan"
```

---

### IN-03: `__init__.py` is empty — package has no public re-exports

**File:** `python/src/boros_brain/fill_model/__init__.py`

**Issue:** The fill_model package `__init__.py` is empty. The package currently exposes its API only via direct submodule imports. This is not a bug but means there is no single import surface for callers. Phase 4 (DecisionEngine) will import `predict`, `FillModelStaleFeatureError`, `FillModelNoFreshFitError` and `PredictInput`/`PredictOutput` from their respective submodule paths. If those paths ever restructure, all callers break.

**Fix:** Add minimal re-exports to `__init__.py` to establish a stable surface:

```python
from .predict import predict, PredictInput, PredictOutput
from .schemas import FillModelStaleFeatureError, FillModelNoFreshFitError, FitArtifact
```

This is low-urgency for v0.5 but should land before Phase 4 DecisionEngine is built.

---

### IN-04: `refit_loop.py` does not pass `event_index_coverage` from `QueueTracker` to `fit_market_side`

**File:** `python/src/boros_brain/fill_model/refit_loop.py:48-65`

**Issue:** `refit_once` calls `build_features_table` then `fit_market_side` with the default `event_index_coverage="full"`. The `QueueTracker` is not invoked in the refit loop (only in the queue feature path). If the queue tracker detects degraded coverage when called separately, that signal never propagates into the persisted `FitArtifact.event_index_coverage`. The `event_index_coverage` field in the stored artifact will always be `"full"` regardless of the actual coverage of the underlying data.

This is minor for v0.5 (queue tracker is a separate call path and the field is informational), but means the `event_index_coverage` column in `fill_model_fits` is unreliable as an audit signal.

**Fix:** Either: (a) have `build_features_table` return a coverage flag (derived from checking for null `eventIndex` in the trades parquet), or (b) document in the `refit_once` docstring that `event_index_coverage` in artifacts produced by this path is always `"full"` and should not be relied on until the queue-tracker path is integrated.

---

_Reviewed: 2026-04-24T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
