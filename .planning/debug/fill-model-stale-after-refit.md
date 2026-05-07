---
status: resolved
trigger: "Backtest crashes with FillModelNoFreshFitError: fit too stale: age=3610.0s > max=3600.0s — refit cadence is 900s so fit should never be >900s stale, yet 0 fill_model_refit_failed events in structured log"
created: 2026-05-07
updated: 2026-05-07
---

## Symptoms

- **Expected:** refit cadence = 900s; fit age should never exceed 900s at predict time
- **Actual:** crash at chain_ts ~T+3610 with `FillModelNoFreshFitError: fit too stale: age=3610.0s > max=3600.0s`
- **Error:** `FillModelNoFreshFitError: fit too stale: age=3610.0s > max=3600.0s`
- **Observation:** 0 `fill_model_refit_failed` events in structured log — refits are running (no failure events) but either writing fits with wrong `fit_window_end_ts` OR the fit written at T0 is not being replaced by later refits
- **Timeline:** surfaced as 6th pre-flight bug during Phase 05.5 Plan 03 Task 2 execution
- **Reproduction:** run the backtest replay; crashes at the predict() call after T+3610

## Suspect (from prior session)

`_maybe_refit_fill_model` at chain_ts T+900/T+1800 writes a fit but with a `fit_window_end_ts` that doesn't match what the SQL `ORDER BY fit_window_end_ts DESC LIMIT 1` query returns at T+3610 — so `get_latest_fit` either returns the T0 artifact (age=3610s) or nothing.

## Current Focus

hypothesis: CONFIRMED — successful-fit path in fit.py sets fit_window_end_ts = pdf["bin_start"].max(), which is the last real trade bin in the historical parquet and does NOT advance between refit cadence ticks during backtest replay (no new trades are appended to parquet during replay). Every refit upserts onto the same fit_window_end_ts key (ON CONFLICT(market_id, side, fit_window_end_ts) DO UPDATE), leaving exactly one DB row stuck at the T0 value.
next_action: DONE — fix applied in fit.py

## Evidence

- timestamp: 2026-05-07T00:00:00Z
  finding: >
    fit.py successful-fit path (lines 174-175 pre-fix): fit_window_end_ts =
    int(pdf["bin_start"].max()) — bin_start is the 60-second bin floor of
    blockTimestamp from historical market_trades parquet. During backtest replay,
    no new rows are written to parquet, so bin_start.max() is the same constant
    value at T0, T+900, T+1800, etc.

- timestamp: 2026-05-07T00:01:00Z
  finding: >
    insert_fit_artifact uses ON CONFLICT(market_id, side, fit_window_end_ts) DO UPDATE.
    With a constant fit_window_end_ts across all refits, every T+900/T+1800 refit
    simply updates the single existing row rather than inserting a new one. The row's
    fit_window_end_ts never advances.

- timestamp: 2026-05-07T00:02:00Z
  finding: >
    get_latest_fit with current_chain_ts=T+3610 runs:
      AND fit_window_end_ts <= T+3610
      ORDER BY fit_window_end_ts DESC LIMIT 1
    Returns the single stale row with fit_window_end_ts = bin_start.max() from T0.
    fit_age_s = (T+3610) - bin_start.max(). With bin_start.max() near the
    replay start, fit_age_s ≈ 3610, which exceeds fit_max_staleness_s=3600.

- timestamp: 2026-05-07T00:03:00Z
  finding: >
    The degraded (empty-data) path already had the correct fix: it uses
    window_end_ts when provided by the caller. The successful-fit path and the
    fit-exception degraded path were missing the same fix.

- timestamp: 2026-05-07T00:04:00Z
  finding: >
    refit_loop.refit_once() passes current_chain_ts as window_end_ts to
    fit_market_side(). At T+900 this is T_start+900, at T+1800 it is T_start+1800.
    With the fix applied, each cadence tick writes a new row with a distinct
    fit_window_end_ts, so get_latest_fit returns an artifact whose age is bounded
    to refit_cadence_s (900s) << fit_max_staleness_s (3600s).

## Eliminated

- fill_model_refit_failed events: not fired because refits ARE succeeding without exception — the bug is in what value is stored as fit_window_end_ts, not in whether the refit runs
- get_latest_fit SQL: query is correct; the anti-look-ahead filter (fit_window_end_ts <= current_chain_ts) is not the cause — the cause is that all refits upsert onto the same key

## Resolution

root_cause: >
  fit_market_side() in python/src/boros_brain/fill_model/fit.py stored
  fit_window_end_ts = pdf["bin_start"].max() for successful fits. During backtest
  replay, bin_start.max() is a constant (the last real trade bin in the historical
  parquet — no new trades are appended during replay). Every refit cadence tick
  upserted onto the same (market_id, side, fit_window_end_ts) conflict key, leaving
  a single DB row. At T+3610, predict() saw this row with an age of 3610s >
  fit_max_staleness_s=3600s and raised FillModelNoFreshFitError.

fix: >
  In fit.py, all three artifact-construction paths (successful fit, fit-exception
  degraded, empty-data degraded) now use window_end_ts when provided by the caller,
  falling back to bin_start.max()/0 only when window_end_ts is None. The refit loop
  passes current_chain_ts as window_end_ts, so each cadence tick creates a new row
  with a fresh fit_window_end_ts, keeping fit_age_s <= refit_cadence_s (900s).
  File changed: python/src/boros_brain/fill_model/fit.py
