# Phase 05.4 — look-ahead bias at predict layer (fill_model + loss_model)

**Status:** Open. Diagnosis only — no fix landed.
**Filed:** 2026-05-06 by Claude after killing run `01KQYNPPE2CB46414WKHEGCZP5` at 21:22Z.
**Severity:** Blocks every binding ship-gate verdict on this codebase. The bug pre-dates Phase 05.4 and was not surfaced by the 05.4-03 fix because that fix only bound the *write* side of the look-ahead.

## TL;DR

`fill_model.predict.predict()` and `loss_model.expected_loss.expected_loss()` both retrieve the latest fit/grid artifact via `get_latest_fit` / `get_latest_loss_grid`, which order by `window_end_ts DESC LIMIT 1` with **no `current_chain_ts` bound**. When prior runs have persisted artifacts at later wall-clock times, the current backtest at earlier chain timestamps reads them, logs a `*_future_dated_*` warning, then **silently sets `*_age_s = 0.0`** and proceeds to use future-fitted parameters on past chain data. Result: every prediction during a backtest of historical data is contaminated by future information drawn from the persisted artifact tables. In the run we killed today, this produced 266,740 such reads on a single side and zero downstream fill activity, yielding `annualized_pnl_pct=0.0` on every cancel_latency child.

## Symptom

Sweep results from PID 49950 (run_id `01KQYNPPE2CB46414WKHEGCZP5`, killed 21:22Z 2026-05-06):

| sweep_axis      | L     | annualized_pnl_pct |
|-----------------|-------|--------------------|
| cancel_latency  | 0.5   | 0.0                |
| cancel_latency  | 1.0   | 0.0                |

Same shape as the prior PID 18460 / run_id `01KQTMW2VE7HF408T4V6XV5TDW`, which recorded a full 6/6 cancel_latency at 0.0% before being killed.

## Root cause

### File: `python/src/boros_brain/state/writers/fill_model_fits.py:86-98`

```python
def get_latest_fit(sqlite_path: Path, market_id: str, side: str) -> FitArtifact | None:
    """Return the most-recent-by-fit_window_end_ts artifact for (market_id, side)."""
    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            """SELECT ... FROM fill_model_fits
               WHERE market_id = ? AND side = ?
               ORDER BY fit_window_end_ts DESC LIMIT 1""",
            (market_id, side),
        ).fetchone()
```

No `current_chain_ts` parameter, no `WHERE fit_window_end_ts <= ?` filter.

### File: `python/src/boros_brain/state/writers/loss_grid_artifacts.py:73-84`

Identical shape:

```python
def get_latest_loss_grid(sqlite_path: Path, market_id: str, side: str) -> LossGridArtifact | None:
    ...
    """SELECT ... FROM loss_grid_artifacts
       WHERE market_id = ? AND side = ?
       ORDER BY window_end_ts DESC LIMIT 1"""
```

### File: `python/src/boros_brain/fill_model/predict.py:80-106`

```python
fit = get_latest_fit(sqlite_path, req.market_id, req.side)   # ← no chain_ts bound
...
fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)
if fit_age_s < 0:
    log.warning("fill_model.predict_future_dated_fit", ...)
    fit_age_s = 0.0                                          # ← silently treats future fit as fresh
```

The negative-age branch is documented as "possible if the chain clock rolled back or a bootstrap artifact was persisted with a future window end (e.g. drifted machine clock)". In a live deployment that is the right interpretation. **In a backtest replaying historical data, every prediction call satisfies that branch by construction**, because the persisted artifact tables accumulate fits across runs and the latest fit is generally from the most recent prior run, dated later than any historical replay timestamp.

### File: `python/src/boros_brain/loss_model/expected_loss.py:90-111`

Same shape: `get_latest_loss_grid` → `grid_age_s < 0` → log warning → `grid_age_s = 0.0` → proceed.

## Evidence — log signatures from `01KQYNPPE2CB46414WKHEGCZP5`

Distribution of events in the 350 MB log over ~8.5h wall-clock (2 cancel_latency children completed + 1 mid-flight when killed):

```
266740  loss_model.sparse_cell_fallback
266740  loss_model.future_dated_grid
266740  fill_model.predict_future_dated_fit
 16598  duckdb.empty_parquet_view_registered
 16590  fill_model.fit_completed         (n_observations 15-17, fit_status='degraded')
   896  backtest.sigma_others.using_earliest_snapshot_fallback
     8  fill_model.refit_failed          ("cannot write 'Object' datatype to" — secondary bug, see below)
     8  fill_model.features_empty
     4  backtest.replay.seeded_initial_order   ← seed IS placed correctly (Wave 4 fix is in)
     2  backtest.sweep.cancel_latency.row      ← both 0.0%
     1  backtest.row_written                   ← only baseline persisted before kill
     0  any fill, close, or pnl_realized event
```

Sample `predict_future_dated_fit`:

```json
{
  "market_id": "BINANCE-ETHUSDT-25SEP2026",
  "side": "long",
  "fit_window_end_ts": 1777194810,
  "current_chain_ts":  1774970568,
  "fit_age_s": -2224242.0
}
```

Translation: at simulated chain time `2026-03-27 22:42:48 UTC`, `predict()` returned a fit whose window ended at `2026-04-26 13:53:30 UTC` — **2.6M seconds (30 days) in the future**.

## Why prior fixes didn't catch this

Phase 05.4-03 commit `d954bc5` was titled *"Bug C — bound `fill_model.refit_once` window_end_ts by current_chain_ts"*. That fix bounds the *write* path: when the refit loop produces new artifacts during a backtest, those new artifacts are now stamped with `window_end_ts <= current_chain_ts`. But the *read* path (`get_latest_fit`) returns whichever artifact has the latest `window_end_ts` across all rows in the table, including rows persisted by previous runs with the unfixed write path or by subsequent live/calibration runs. So the table is permanently poisoned with future-dated rows, and the read path never filters them out.

The diagnostic narrative in the 05.4-03 plan focused on the simpler look-ahead direction (writes during a backtest leaking into the same backtest's later predictions), and the fix was scoped accordingly. The cross-run leak was not in scope.

## Persisted-artifact state on disk

`data/parquet/fill_model_artifacts/market_id=BINANCE-ETHUSDT-25SEP2026/side=long/`:
- 20 distinct `window_end_ts=...` partitions, latest near `1777194810` (2026-04-26).
- Spans cover a mix of post-fix (windowed correctly) and pre-fix (unbounded) writes.

`data/parquet/loss_grid_artifacts/market_id=BINANCE-ETHUSDT-25SEP2026/side=long/`:
- **Exactly one partition**: `window_end_ts=1777799610` (2026-05-03 18:13:30 UTC).
- Means **every** `expected_loss` call during the 26-day historical backtest replays chain timestamps `2026-03-27 → 2026-04-22`, all of which are before this single artifact, so 100% of calls hit `future_dated_grid`. That matches the observed 266,740 events.

The SQLite tables `fill_model_fits` and `loss_grid_artifacts` mirror these — `get_latest_*` reads from SQLite, the parquet tree is the artifact storage.

## Secondary finding — `refit_failed` write bug

Less severe but tracked here for completeness:

```
fill_model.refit_failed err="cannot write 'Object' datatype to "
  at python/src/boros_brain/fill_model/refit_loop.py:84
  caused by python/src/boros_brain/fill_model/features.py:296 -> df.write_parquet
```

When `build_features_table` produces an empty DataFrame (window precedes data start), polars `streaming` engine refuses to write because at least one column has `Object` dtype on the empty frame. Triggers 8 times per side at run start (covering the warm-up window before chain time enters the data range). The exception is caught and logged, so it does not abort the run, but it produces a misleading `refit_failed` ERROR-level event in the log. Fix is independent of the primary look-ahead bug and probably one line: cast `Object` columns or use a non-streaming engine for empty-frame writes.

## Proposed fix shape

### Required changes

1. **Add `current_chain_ts` to retrieval API** (both `fill_model_fits.py` and `loss_grid_artifacts.py`):
   ```python
   def get_latest_fit(sqlite_path, market_id, side, *, current_chain_ts: int | None = None)
   ```
   Default `None` preserves existing call signature for non-backtest callers (live brain). When provided, append `AND fit_window_end_ts <= ?` to the SQL.

2. **Wire `req.current_chain_ts` through `predict()` and `expected_loss()`** at the existing read sites. Both already have `current_chain_ts` on the input dataclass.

3. **Decide what `fit_age_s < 0` means after the fix:** with the chain-ts filter in place, the negative-age branch is unreachable from a correct backtest. Two options:
   - Keep the branch as a defensive log + raise (asserts it's now genuinely a clock-rollback).
   - Remove the branch entirely; let the `no_fresh_fit` path handle it via the `fit is None` check.
   The `predict.py` docstring says *"Design-locked. Any change to this signature is a Phase-4 breaking change."* — so this is a Phase 4 contract amendment, not a freebie.

4. **Same for `loss_model.expected_loss`** with the identical structure.

### TDD scaffolding (RED → GREEN, mirroring 05.4-03 commits `d954bc5` / `5417c93`)

- **RED test** (one per layer): persist two artifacts at `window_end_ts ∈ {T0+86400, T0+604800}` for the same `(market_id, side)`. Call `predict(req)` with `req.current_chain_ts = T0 + 100000`. Assert `fit.fit_window_end_ts == T0+86400` (the older one). Currently fails because the latest is returned.
- **Negative-control RED test**: assert no `predict_future_dated_fit` warning is emitted in normal backtest replay. Currently fails (266,740 emissions per run).
- **GREEN**: implement the chain-ts filter. Both tests pass.
- **Regression test**: live brain path (`current_chain_ts=None`) returns the absolute latest fit unchanged.

### Engineering Protocols ledger

- **Wiki (Protocol 1):** A page like `[[fill-model-predict-look-ahead-at-read-layer]]` is required, citing the current `predict.py:92-106` implementation as `Status: Historical` once fixed and adding a `Status: Current` page describing the `current_chain_ts`-bounded retrieval. Same for the loss model. There are existing related wiki pages (`fill-model-predict-contract`, `empirical-loss-grid-v05`, `known-issues-nan-covariate-silent-fallback-do-not`) that will need supersedence headers.
- **Architecture (Protocol 2):** `state.writers.fill_model_fits.get_latest_fit` and `state.writers.loss_grid_artifacts.get_latest_loss_grid` already declared in `architecture.yml`. Signature change is internal, no node/edge changes needed, but the docstring contract change should be reflected in `ARCHITECTURE.md` if any prose describes the read shape.
- **RUN_MANIFEST (Protocol 3):** No knobs added; manifest unaffected.

### Effort estimate

- 30 min: RED tests for both layers
- 30 min: SQL filter + signature plumbing
- 30 min: GREEN run + regression sweep of existing fill_model and loss_model tests
- 30 min: wiki pages (1 supersede + 1 current per layer = 4 pages)
- 30 min: re-run baseline backtest and confirm `predict_future_dated_fit` count drops to 0

Total: ~2.5 hours. The fix is small; the discipline overhead is most of the time.

## Why I did not land this fix in this session

1. **Design-locked surface.** `predict.py` carries an explicit warning that signature changes are Phase-4 breaking. Adding `current_chain_ts` to `get_latest_fit` propagates upward, and the right answer to "what does `fit_age_s < 0` mean after the fix" is a contract-shape decision that should belong to a phase plan, not a side-effect of an autonomous session.
2. **Ship-gate path.** This is the engine bug that has been masking ship-gate verdicts since at least Phase 05.1 Wave 4. Fixing it changes the verdict branch — it should land inside an explicit phase (whether 05.4-05 or 05.5) with goal-backward verification, not as a drive-by patch.
3. **Protocol obligations.** A code change of this kind without the wiki/architecture co-commits would violate the project's stated protocols. Doing the protocols half-correctly is worse than not doing the change.

## Adjacent open items in working tree

- **`python/src/boros_brain/backtest/perturbation.py`** has an uncommitted 34-line addition introducing `_PERTURBATION_WHITELIST` (11 EV-critical knobs) — a defensible scope reduction from 112 → 11 knobs that brings the perturbation grid from 225 → 23 children. Independently coherent, but missing test + wiki + architecture co-commits. Not committed in this session because the user has not yet decided whether the whitelist composition is the right one — best left for the next phase plan to either accept (commit + co-commit protocols) or revert.
- **`.planning/phases/05.1-ship-gate-execution-historical-data-fetch-ingest-screener-ec/05.1-04b-PLAN.md`** — untracked planning doc, untouched by this session.
- 11 untracked `var/*.log` diagnostic artifacts and one `var/fetcher/files.json.cache` — none load-bearing.

## Suggested next step

`/gsd-plan-phase 05.5` (or insert a `05.4-05` plan, depending on roadmap preference) scoped specifically to:

1. Apply the `current_chain_ts`-bounded retrieval fix at both layers.
2. Decide and document the Phase-4 contract amendment for `fit_age_s < 0` / `grid_age_s < 0`.
3. Re-run binding ship-gate against a clean artifact tree (or with `WHERE fit_window_end_ts <= current_chain_ts` in place; the latter is preferable because it makes the system robust to artifact pollution rather than depending on operational hygiene).
4. Optional: address the secondary `refit_failed` `Object`-dtype empty-frame write bug in the same plan since it's adjacent and trivial.

Once that lands, the perturbation whitelist scope reduction can be committed as part of the same plan, with its own RED test (assert `len(enumerate_perturbable_leaves(cfg))` matches the whitelist length).
