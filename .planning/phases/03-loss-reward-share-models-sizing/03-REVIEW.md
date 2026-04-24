---
phase: 03-loss-reward-share-models-sizing
reviewed: 2026-04-24T00:00:00Z
depth: standard
files_reviewed: 53
files_reviewed_list:
  - python/src/boros_brain/loss_model/__init__.py
  - python/src/boros_brain/loss_model/__main__.py
  - python/src/boros_brain/loss_model/artifact.py
  - python/src/boros_brain/loss_model/cli.py
  - python/src/boros_brain/loss_model/config.py
  - python/src/boros_brain/loss_model/expected_loss.py
  - python/src/boros_brain/loss_model/fit.py
  - python/src/boros_brain/loss_model/ou_parametric.py
  - python/src/boros_brain/loss_model/refit_loop.py
  - python/src/boros_brain/loss_model/replay.py
  - python/src/boros_brain/loss_model/schemas.py
  - python/src/boros_brain/pricing/__init__.py
  - python/src/boros_brain/pricing/config.py
  - python/src/boros_brain/reward_model/__init__.py
  - python/src/boros_brain/reward_model/__main__.py
  - python/src/boros_brain/reward_model/calibrate.py
  - python/src/boros_brain/reward_model/cli.py
  - python/src/boros_brain/reward_model/competition_tracker.py
  - python/src/boros_brain/reward_model/config.py
  - python/src/boros_brain/reward_model/q_cap.py
  - python/src/boros_brain/reward_model/r_capped.py
  - python/src/boros_brain/reward_model/schemas.py
  - python/src/boros_brain/sizer/__init__.py
  - python/src/boros_brain/sizer/__main__.py
  - python/src/boros_brain/sizer/cli.py
  - python/src/boros_brain/sizer/config.py
  - python/src/boros_brain/sizer/optimizer.py
  - python/src/boros_brain/sizer/schemas.py
  - python/src/boros_brain/config/schema.py
  - python/src/boros_brain/main.py
  - python/src/boros_brain/state/migrations/versions/0004_loss_grid_artifacts.py
  - python/src/boros_brain/state/migrations/versions/0005_competition_history.py
  - python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py
  - python/src/boros_brain/state/schemas.sql
  - python/src/boros_brain/state/writers/competition_history.py
  - python/src/boros_brain/state/writers/loss_grid_artifacts.py
  - python/src/boros_brain/state/writers/market_reward_calibration.py
  - python/tests/fixtures/_generate_loss_grid_fixtures.py
  - python/tests/test_competition_tracker.py
  - python/tests/test_loss_model_artifact.py
  - python/tests/test_loss_model_fit_and_expected_loss.py
  - python/tests/test_loss_model_ou_scaffold.py
  - python/tests/test_loss_model_replay.py
  - python/tests/test_manifest_contains_all_knobs.py
  - python/tests/test_market_reward_calibration.py
  - python/tests/test_reward_curve.py
  - python/tests/test_sizer.py
  - python/tests/test_sqlite_migrations.py
  - python/tests/test_sqlite_single_writer.py
  - scripts/no_time_time_lint.py
  - strategy/v0.5-default.yaml
  - docs/architecture.yml
  - docs/ARCHITECTURE.md
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-04-24T00:00:00Z
**Depth:** standard
**Files Reviewed:** 53
**Status:** issues_found

## Summary

Phase 3 delivers the loss model (LOSS-01/02/03), reward share model (REWARD-01/02/04), sizing optimizer (REWARD-03), and all Phase-3 SQLite tables/migrations. The code is well-structured and follows the engineering protocols from CLAUDE.md. The architecture diagram and `architecture.yml` are updated. MANIFEST-FIRST, single-writer discipline, and Pydantic validation layering are all present and correct.

Four warnings and three info items were found. None are blockers to the phase passing its acceptance criteria, but the warnings should be addressed before Phase 4 wiring because two of them affect correctness of the fail-count tracking during CompetitionTracker degraded-mode, one produces a silent incorrect P&L sign for short-side fills under certain conditions, and one leaves a context-manager leak in main.py that will cause the SQLite connection to stay open forever when the process does not exit cleanly.

---

## Warnings

### WR-01: CompetitionTracker fail-count increments once per retry, not once per REST cycle

**File:** `python/src/boros_brain/reward_model/competition_tracker.py:148-152`

**Issue:** `_get_q_me_with_backoff` increments `self._fail_count` inside the retry loop — once per `delay` in `_BACKOFF_DELAYS` (5 entries). A single REST-failing cycle therefore increments `_fail_count` by 5, not 1. The degraded-mode threshold is `fallback_to_parquet_after_rest_fails_n = 5`, which means after one failed cycle `_fail_count` reaches 5 and `rest_degraded` is emitted immediately. If the intent is "5 *consecutive cycles* of failure", the increment should be outside the retry loop (in `run_one_cycle`'s `except` branch). If the intent is "5 total retry attempts", the current code is fine but the config-knob docstring ("5 consecutive REST failures") is misleading and the test `test_fallback_on_rest_fail` passes because it also triggers 5 backoff slots in one cycle.

**Fix:** Move the `_fail_count` increment to the outer `except` block in `run_one_cycle`, so one failed cycle = one increment:

```python
# In run_one_cycle's except branch:
except Exception as exc:  # noqa: BLE001
    self._fail_count += 1          # one increment per failed cycle
    log.error(...)
    if self._fail_count >= self.fail_threshold and not self._degraded_emitted:
        ...
    q_me = self._estimate_q_me_from_open_orders(market_id)
    data_source = "fallback_parquet_only"

# Remove the self._fail_count += 1 line from _get_q_me_with_backoff
```

---

### WR-02: CompetitionTracker `_fail_count` is not reset per-market — a failure on market A blocks recovery detection on market B

**File:** `python/src/boros_brain/reward_model/competition_tracker.py:85-130`

**Issue:** `run_one_cycle` iterates over all markets. `self._fail_count` and `self._degraded_emitted` are single scalars shared across all markets. If the REST call for market A succeeds but the call for market B fails (or vice versa), the success branch of market A sets `self._fail_count = 0` and `self._degraded_emitted = False`, which clears the failure state accumulated for market B. Conversely, a persistent failure on market B could suppress the degraded event for market A. In v0.5 `config.markets` is capped at length 1 so this does not cause a live bug, but the code is subtly wrong for multi-market use and the fix is cheap now while the class is small.

**Fix:** Use a `dict[str, int]` keyed by `market_id` for fail counts and a `dict[str, bool]` for `_degraded_emitted`:

```python
self._fail_count: dict[str, int] = {}
self._degraded_emitted: dict[str, bool] = {}

# In run_one_cycle, replace scalar reads with:
self._fail_count.get(market_id, 0)
self._degraded_emitted.get(market_id, False)
```

---

### WR-03: Short-side P&L sign in `build_per_fill_pnl_from_frame` double-negates when `close_rate < fill_rate`

**File:** `python/src/boros_brain/loss_model/replay.py:249-254`

**Issue:** The gross P&L formula for short is:

```python
gross = fill_size_float * (float(close_rate) - fill_rate) * (tau_days / 365.0)
if side == "short":
    gross = -gross
```

For a short fill that closes profitably (the APR moved down so `close_rate < fill_rate`), `(close_rate - fill_rate)` is negative; negating again produces a *positive* gross, which is correct. However the test fixture at `test_fees_term_included` only exercises the long side (`side="long"`) and none of the test fixtures verify the short-side sign directly. The formula matches `boros_consolidated_plan.md §4` intent, but the naming is confusing: "Long P&L = size × (close - fill) × tau/365" implicitly assumes close > fill is profitable for longs. For shorts, close < fill is profitable but the code negates `(close - fill)` which equals `(fill - close) > 0` — this is correct. The risk is that a reviewer or future maintainer misreads the formula and "fixes" the sign. The comment in the code says "Short P&L is the negation" without explaining why, which is the actual bug risk.

The immediate correctness concern: the test fixture only places `close_rate=0.11 > fill_rate=0.10` for a long. The short-side path is untested with an actual close that is more favorable than fill (close < fill for a short). If someone refactors the sign logic the regression would be silent.

**Fix:** Add a short-side test case to `test_loss_model_replay.py::test_fees_term_included` (or a new test) that verifies `pnl_pendle` is positive when `close_rate < fill_rate` on the short side:

```python
# Short profitable: fill_rate=0.12, close_rate=0.10 → gross = 1.0*(0.10-0.12)*(30/365) → negated = positive
injected_short = pl.DataFrame({
    "market_id": [MARKET_ID], "side": ["short"],
    "fill_event_index": [2], "fill_block_ts": [block_ts],
    "fill_rate": [0.12], "fill_size_float": [1.0],
    "close_rate": [0.10], "close_block_ts": [block_ts + 30],
    "close_event_index": [3], "tau_days": [30.0],
    "depth_from_mark_ticks": [0],
})
rows_short = build_per_fill_pnl_from_frame(injected_short, config=config, market_id=MARKET_ID)
assert rows_short[0].pnl_pendle > 0  # net of fees; profitable close
```

---

### WR-04: `comp_conn` in `main.py` opened as a context-manager but `__enter__` result stored — connection leaks on exception before `comp_conn.close()`

**File:** `python/src/boros_brain/main.py:178`

**Issue:**

```python
comp_conn = open_connection(Path(cfg.infra.sqlite_path)).__enter__()
```

`open_connection` is a context manager. Calling `__enter__()` directly returns the inner `sqlite3.Connection`, but it never arranges `__exit__()` to be called on the context manager itself. If an exception occurs between line 178 and the `comp_conn.close()` call in the finally-equivalent block at line 209, the underlying context manager's `__exit__` is never invoked. In practice `contextlib.suppress(Exception)` around `comp_conn.close()` at line 209 does close the raw connection, but the context manager wrapper is orphaned — this is fragile if `open_connection.__exit__` does any additional cleanup beyond the raw `close()`.

More concretely: if an exception propagates out of `await stop.wait()` (e.g., an unhandled error in the `stop.wait()` machinery) or from the task-cancellation loop before reaching line 209, the `comp_conn.close()` block is bypassed entirely because it is not in a `finally` block.

**Fix:** Use the context manager properly inside a `try/finally`, or restructure to use `async with` (not applicable here), or at minimum move the cleanup into an unconditional `finally`:

```python
# Option A: use try/finally explicitly
comp_conn_cm = open_connection(Path(cfg.infra.sqlite_path))
comp_conn = comp_conn_cm.__enter__()
try:
    ...
    await stop.wait()
    ...
finally:
    comp_conn_cm.__exit__(None, None, None)

# Option B (simpler): just call sqlite3.connect directly since the context
# manager is already bypassed — make the bypass explicit:
import sqlite3 as _sqlite3
comp_conn = _sqlite3.connect(str(cfg.infra.sqlite_path))
# ... use comp_conn ...
# In shutdown block (inside a finally):
with contextlib.suppress(Exception):
    comp_conn.close()
```

---

## Info

### IN-01: `_get_loss_model_config` is copy-pasted into three modules

**File:** `python/src/boros_brain/loss_model/fit.py:34-37`, `python/src/boros_brain/loss_model/replay.py:38-42`, `python/src/boros_brain/loss_model/refit_loop.py:29-31`

**Issue:** The same three-line helper is duplicated:

```python
def _get_loss_model_config(config: BotConfig) -> LossModelConfig:
    return getattr(config, "loss_model", None) or LossModelConfig()
```

The docstring in each copy says "Plan-03-01-independent fallback until 03-02 wires BotConfig.loss_model", but Plan 03-02 has now wired `BotConfig.loss_model` directly. The `getattr` fallback is no longer needed; `config.loss_model` is always present. The three copies can be replaced by a single direct attribute access.

**Fix:** Remove the helper from all three modules and access `config.loss_model` directly. If the fallback pattern is genuinely needed for test seams, consolidate it into one place (e.g., a `_utils.py` in `loss_model/`).

---

### IN-02: `expected_loss.py` duplicates `_bucket_idx` from `fit.py` with identical logic

**File:** `python/src/boros_brain/loss_model/expected_loss.py:50-61`

**Issue:** `_bucket_idx` in `expected_loss.py` is word-for-word identical to the function in `fit.py`. The comment says "duplicated here to keep loss_model sync-path free of cross-module imports for the 1 Hz hot path." This is a valid performance argument — a module import at call time can add overhead. However, given that Python module imports are cached after the first import, and that both modules are already imported by the time `expected_loss` is called in normal operation, the cross-import concern does not actually apply. The duplication creates a maintenance risk: if the bucketing convention changes (e.g., half-open vs. closed boundaries), the fix must be applied in two places.

**Fix:** Import `_bucket_idx` from `fit.py` into `expected_loss.py`. If the hot-path import concern is real, measure it; otherwise eliminate the duplication. Alternatively, move `_bucket_idx` to `schemas.py` or a `_utils.py` that both modules import.

---

### IN-03: `r_capped.py` imports `EPOCHS_PER_YEAR` with a `# noqa: F401` comment acknowledging it is unused

**File:** `python/src/boros_brain/reward_model/r_capped.py:19`

**Issue:**

```python
from ..screener.economics_gate import EPOCHS_PER_YEAR  # noqa: F401
```

The comment says "reused pattern (may inform docs); our formula uses epoch_days directly." The constant is not used anywhere in the file. The `# noqa: F401` suppresses the unused-import lint warning. An unused import in a module that is called at 1 Hz adds no runtime cost (it's one additional attribute in `sys.modules`), but it is a dead import that confuses readers and violates the codebase's convention of keeping files clean.

**Fix:** Remove the import. If the intent is to document the relationship between `epoch_days` and `EPOCHS_PER_YEAR`, add a comment in the formula section instead.

---

_Reviewed: 2026-04-24T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
