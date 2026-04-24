---
plan: 02-04
phase: 02-fill-model-nhpp-v0-5
status: complete
completed: 2026-04-24
tasks_total: 3
tasks_complete: 3
requirements: [FILL-01, FILL-05, FILL-06]
self_check: PASSED
---

# Plan 02-04 Summary — Fill Model Capstone (Calibration + Refit + CLI)

## What was built

Closed the Phase 2 loop with calibration GoF, rolling refit loop, CLI entry point, and operator report.

### Task 1 — calibration.py + refit_loop.py + un-skip calibration_gof tests

**calibration.py** — Rosenblatt time-change GoF:
- `gof_rosenblatt(event_times_s, lambda_fn)` → `GofResult(ks_stat, ks_pval, n_gaps)` via `scipy.stats.kstest` against Exp(1) on integrated-compensator inter-arrival gaps
- `bootstrap_gof_threshold(event_times_s, lambda_fn, n_bootstrap=100)` → 5th-percentile KS stat from in-sample resamples (replaces intuition-set threshold; PITFALL #8)
- `run_calibration(config, market_id, side, run_id)` → `CalibrationReport` with per-decile (predicted, realized) pairs on 20% hold-out; `fill_model.fit_degraded` emitted when GoF threshold crossed
- Regime-shift fixture triggers degradation warning (T-02-C-03 passes)

**refit_loop.py** — 15-min async cadence:
- `refit_once(config, run_id)` — async coroutine using `await chain_time.now_cached()` (INFRA-14 compliant); awaited from main.py at boot to guarantee artifact before 1 Hz loop
- `run_fill_model_refit_loop(config, run_id)` — long-running asyncio task; catches + logs per-iteration exceptions (loop never dies)

3 calibration_gof wave-0 stubs promoted from SKIPPED → PASSING.

### Task 2 — cli.py + __main__.py + report.py + main.py wiring

**cli.py / __main__.py** — `python -m boros_brain.fill_model` entry point:
- Subcommands: `fit`, `predict`, `calibration-report`, `force-degrade`
- MANIFEST-FIRST boot (PROTO-01): `build_run_manifest` + `write_manifest` before any other log line; `tier='fill_model'`
- `force-degrade`: forces `fit_status='degraded'` on synthetic run → emits `fill_model.fit_degraded` → smoke test for Success Criterion #4

**report.py** — `write_fill_model_report(config, run_id, output_path)`: reads latest fit rows from `fill_model_fits` via `get_latest_fit`, writes JSON + Markdown summary

**main.py** — `brain.main.run()` extended:
- `await refit_once(cfg, run_id)` at boot (synchronous first fit before loop starts)
- `asyncio.create_task(run_fill_model_refit_loop(cfg, run_id))` alongside existing tasks
- Shutdown: `refit_task.cancel()` + `contextlib.suppress(CancelledError)`
- `--dry-run` guard: returns early before `refit_once` to keep dry-run fast

### Task 3 — architecture.yml + ARCHITECTURE.md + wiki pages

- `docs/architecture.yml` extended: 4 new module nodes (`brain.fill_model.calibration`, `.refit_loop`, `.report`, `.cli`) + 13 new edges; architecture lint exits 0
- `docs/ARCHITECTURE.md` Mermaid subgraph updated to Plans 02-01/02/03/04; Plan 02-04 description added; wiki references extended
- LLM Wiki pages filed:
  - `[[fill-model-goodness-of-fit-rosenblatt-time-change]]` — KS/bootstrap method, degradation signal
  - `[[rolling-14-day-refit-cadence-and-staleness]]` — boot-time fit, 15-min cadence, staleness policy

## Test results

All 3 previously-skipped wave-0 calibration_gof tests now pass:
- `test_calibration_on_holdout` — run_calibration returns CalibrationReport with n_deciles=10
- `test_refit_loop_writes_artifact` — refit_once writes a fit artifact to state DB
- `test_degraded_warning_on_regime_shift` — regime-shift fixture triggers fill_model.fit_degraded

Pre-existing failure in `test_screener_filter.py::test_all_six_filters_applied` (DuckDB column name mismatch in test fixture, Phase 1 issue) unchanged and unrelated to Phase 2.

## Key files created/modified

| File | Action | Notes |
|------|--------|-------|
| `python/src/boros_brain/fill_model/calibration.py` | created | GoF + decile calibration (FILL-06) |
| `python/src/boros_brain/fill_model/refit_loop.py` | created | async refit cadence task |
| `python/src/boros_brain/fill_model/report.py` | created | JSON+MD report writer |
| `python/src/boros_brain/fill_model/cli.py` | created | argparse CLI, MANIFEST-FIRST |
| `python/src/boros_brain/fill_model/__main__.py` | created | `python -m boros_brain.fill_model` |
| `python/src/boros_brain/main.py` | modified | boot refit_once + create_task |
| `python/tests/test_fill_model_calibration_gof.py` | modified | 3 stubs → passing |
| `python/docs/fill_model/.gitkeep` | created | calibration-report PNG target dir |
| `docs/architecture.yml` | modified | 4 nodes + 13 edges |
| `docs/ARCHITECTURE.md` | modified | subgraph + text extended |

## Deviations

None. All must_haves satisfied per plan spec.

## Self-Check

- [x] gof_rosenblatt returns ks_stat + ks_pval + n_gaps via scipy KS against Exp(1)
- [x] bootstrap_gof_threshold returns 5th-percentile LR-vs-null from 100 resamples
- [x] run_calibration produces CalibrationReport with per-decile pairs on 20% hold-out
- [x] run_fill_model_refit_loop is a long-running asyncio task with exception catch+continue
- [x] refit_once is async, uses await chain_time.now_cached(), awaited before create_task
- [x] CLI emits RUN_MANIFEST as first log record (PROTO-01), tier='fill_model'
- [x] force-degrade forces fit_status='degraded', emits fill_model.fit_degraded
- [x] fill_model.fit_degraded fires on gof threshold crossing; regime-shift fixture triggers it
- [x] brain/main.py spawns refit_task; shutdown cancels with suppress(CancelledError)
- [x] Full FILL-06 test suite (3 tests) passes — not skipped
