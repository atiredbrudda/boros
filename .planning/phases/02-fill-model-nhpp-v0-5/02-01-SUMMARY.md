---
phase: 02-fill-model-nhpp-v0-5
plan: "01"
subsystem: fill_model
tags: [fill_model, features, config, pydantic, wave-0-scaffold, statsmodels-addition, nhpp]
dependency_graph:
  requires:
    - 01-foundation-infrastructure-spine-data-pipeline-economics-gate
  provides:
    - FillModelConfig (11-knob Pydantic sub-model)
    - build_features_table (DuckDB feature pipeline)
    - Wave-0 test stubs + fixtures for plans 02-02/03/04
  affects:
    - BotConfig (fill_model field attached)
    - scripts/no_time_time_lint.py (fill_model/ added to PROTECTED_DIRS)
    - docs/architecture.yml (15 new nodes + 12 new edges)
    - RUN_MANIFEST (fill_model.* knobs auto-surface via reflection)
tech_stack:
  added:
    - statsmodels>=0.14.6 (Poisson GLM NHPP fit, Phase 2 critical path)
    - tick==0.8.0.1 (wheel built successfully on macOS arm64; role: simulation + v1.0 Hawkes)
  patterns:
    - Local StrictBase re-declaration (avoids circular import with brain.config.schema)
    - DuckDB ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING left-closed EWMA (T-02-F-02)
    - default_rng(42) deterministic fixture generator as SSoT
key_files:
  created:
    - python/src/boros_brain/fill_model/__init__.py
    - python/src/boros_brain/fill_model/constants.py
    - python/src/boros_brain/fill_model/config.py
    - python/src/boros_brain/fill_model/features.py
    - python/tests/test_fill_model_features.py
    - python/tests/test_fill_model_queue_tracker.py
    - python/tests/test_fill_model_amm_consumption.py
    - python/tests/test_fill_model_fit_basic.py
    - python/tests/test_fill_model_predict_contract.py
    - python/tests/test_fill_model_calibration_gof.py
    - python/tests/test_architecture_lint.py
    - python/tests/fixtures/_generate_fill_model_fixtures.py
    - python/tests/fixtures/fill_model_tiny_tape.ndjson
    - python/tests/fixtures/fill_model_synthetic_poisson.parquet
    - python/tests/fixtures/fill_model_regime_shift.parquet
    - strategy/v0.5-default.yaml
    - data/parquet/fill_features/.gitkeep
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/fill-model-library-decision-tick-vs-statsmodels.md
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/covariate-selection-v05.md
  modified:
    - python/pyproject.toml (statsmodels + tick added)
    - python/uv.lock
    - python/src/boros_brain/config/schema.py (fill_model: FillModelConfig field)
    - scripts/no_time_time_lint.py (fill_model/ added to PROTECTED_DIRS)
    - docs/architecture.yml (15 new nodes + 12 new edges)
    - docs/ARCHITECTURE.md (Phase 2 fill_model subgraph + paragraph)
    - python/tests/test_manifest_contains_all_knobs.py (test_fill_model_leaves_surfaced added)
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/python-stack-v05.md (statsmodels row + tick reframe)
decisions:
  - "statsmodels GLM(Poisson, log) on critical path for NHPP covariate fit — tick does not expose covariate-driven NHPP learner (only simulator + Hawkes learners)"
  - "tick stays in stack as simulator (calibration Monte Carlo) + v1.0 Hawkes overlay staging"
  - "tick==0.8.0.1 wheel built successfully on macOS arm64 — no fallback to 0.7.x needed"
  - "FillModelConfig with 11 knobs is frozen+extra=forbid; covariate_whitelist validated against ALLOWED_COVARIATES frozenset (5 entries)"
  - "EWMA window ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING (left-closed, no look-ahead) enforced by T-02-F-02"
  - "default_rng(42) generator script is SSoT for parquet fixtures; committed parquet files are artifacts"
metrics:
  duration: ~45 min
  completed_date: "2026-04-24"
  tasks: 3
  files: 20
---

# Phase 02 Plan 01: Fill Model Scaffold + FillModelConfig + Wave-0 Tests Summary

**One-liner:** Fill model module tree with 11-knob FillModelConfig, DuckDB feature pipeline (left-closed EWMA), Wave-0 test stubs + deterministic fixtures, and statsmodels/tick dependency install.

## What Was Built

### Task 1: Dependencies + Module Scaffold + FillModelConfig

Installed `statsmodels>=0.14.6` and `tick==0.8.0.1` into the worktree's Python venv. `tick` wheel built cleanly on macOS arm64 — no fallback to `tick==0.7.x` was needed.

Created `python/src/boros_brain/fill_model/` package with 4 files:

- **`constants.py`** — `ALLOWED_COVARIATES: frozenset[str]` (5 entries) + 4 `DEFAULT_*` constants. Constants-only module (no functions).
- **`config.py`** — `FillModelConfig(StrictBase)` with exactly 11 knobs matching RESEARCH §8 Table. Local `StrictBase` re-declaration (avoids circular import with `brain.config.schema`). `@field_validator("covariate_whitelist")` rejects non-`ALLOWED_COVARIATES` entries with `"non-allowed entries"` message (T-02-F-01 / STRIDE T-02-01-01).
- **`features.py`** — `build_features_table(config, market_id, window_start_ts, window_end_ts)` → `FeatureSet`. DuckDB SQL joins `market_trades + order_book_combined + underlying_apr + clo_history` via `open_analytical_conn`. EWMA window is `ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING` — left-closed, no look-ahead (T-02-F-02).
- **`__init__.py`** — empty package marker.

`BotConfig.fill_model: FillModelConfig = Field(default_factory=FillModelConfig)` attached in `config/schema.py` (one-line addition after `screener:`).

`scripts/no_time_time_lint.py` extended: `"python/src/boros_brain/fill_model/"` added to `PROTECTED_DIRS`.

`strategy/v0.5-default.yaml` updated with explicit `fill_model:` block (all 11 defaults documented).

### Task 2: Wave-0 Test Files + Fixtures

6 test stub files created:

| File | Tests | Status |
|------|-------|--------|
| `test_fill_model_features.py` | `test_covariate_whitelist`, `test_ewma_no_lookahead` | IMPLEMENTED (no skip) |
| `test_fill_model_queue_tracker.py` | 4 stubs (T-02-Q-01..04) | SKIPPED (plan 02-02) |
| `test_fill_model_amm_consumption.py` | 2 stubs (T-02-A-01..02) | SKIPPED (plan 02-02) |
| `test_fill_model_fit_basic.py` | 2 stubs (T-02-M-01..02) | SKIPPED (plan 02-03) |
| `test_fill_model_predict_contract.py` | 4 stubs (T-02-P-01..04) | SKIPPED (plan 02-03) |
| `test_fill_model_calibration_gof.py` | 3 stubs (T-02-C-01..03) | SKIPPED (plan 02-04) |

Also created `test_architecture_lint.py` (T-02-L-01 — subprocess call to `architecture_lint.py`).

Extended `test_manifest_contains_all_knobs.py` with `test_fill_model_leaves_surfaced` (T-02-R-01 — asserts ≥11 `fill_model.*` leaves via reflection).

3 fixture artifacts:
- `fill_model_tiny_tape.ndjson` — 100 trades, 1 null `eventIndex`, 10 tied `blockTimestamp` pairs
- `fill_model_synthetic_poisson.parquet` — 2000 bins, `β_true=[-1.0, 0.5, -0.3, 0.1, 0.1, 0.2]`, seed=42
- `fill_model_regime_shift.parquet` — 2000 bins, regime change at bin 1400 (basis_spread sign flip), seed=42
- `_generate_fill_model_fixtures.py` — SSoT generator; `default_rng(42)` ensures determinism

Suite result: **13 passed, 15 skipped** (all 15 skips have `wave-0-scaffold` reason + plan reference).

### Task 3: Architecture + Wiki Pages

**`docs/architecture.yml`** additions:
- 3 module nodes: `brain.fill_model.{constants,config,features}`
- 1 storage node: `parquet.fill_features`
- 11 `config.fill_model.*` knob nodes
- 12 edges (reads, writes, calls, depends-on-config)

`data/parquet/fill_features/.gitkeep` created so the `architecture_lint.py` path check passes.

**`docs/ARCHITECTURE.md`**: Phase 2 fill_model subgraph added (Mermaid) + paragraph with EWMA invariant note.

**LLM Wiki pages filed:**

| Page | Status |
|------|--------|
| `fill-model-library-decision-tick-vs-statsmodels.md` | Current — v0.5 regime (NEW) |
| `covariate-selection-v05.md` | Current — v0.5 regime (NEW) |
| `python-stack-v05.md` | Current — v0.5 regime (AMENDED: statsmodels row + tick reframe) |

## Key Decisions Made

1. **statsmodels on critical path, tick reframed** — `statsmodels.GLM(Poisson, log, exposure=bin_duration_s)` is the v0.5 NHPP fit primitive. `tick` stays for simulation + v1.0 Hawkes staging but is not the FILL-01 fitter. Filed in `[[fill-model-library-decision-tick-vs-statsmodels]]`.

2. **`tick==0.8.0.1` wheel built on macOS arm64** — No fallback to `tick==0.7.x` needed. Both `statsmodels 0.14.6` and `tick 0.8.0.1` import cleanly (tick has cosmetic `SyntaxWarning` on import, no effect).

3. **ALLOWED_COVARIATES frozenset (5 entries)** — `basis_spread, imbalance, sin_settlement, cos_settlement, ewma_vol`. Dropped: CEX spot move (A7 feed risk), time-to-maturity (near-zero variation in 14d window), dRate/dt (VIF inflation). Filed in `[[covariate-selection-v05]]`.

4. **Left-closed EWMA window** — `ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING` in DuckDB SQL. This is the T-02-F-02 no-look-ahead invariant. Verified both via SQL string assertion in tests and documented in comments.

5. **default_rng(42) fixture generator as SSoT** — committed parquet files are reproducible artifacts; the generator script is the authoritative source.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Scope Boundary Discovery

**Pre-existing test failure: `test_screener_filter.py::test_all_six_filters_applied`**

- **Found during:** Task 2 (full suite run)
- **Issue:** Test fixture creates DuckDB table with `size VARCHAR` column, but `screener/filter.py` references `size_float AS size` (from Phase 1 fix commit `4f95e62`). Test fixture was not updated when the SQL column name was fixed.
- **Action:** Logged to `deferred-items.md`. NOT fixed — this is out-of-scope pre-existing failure in `screener/` code, not related to Plan 02-01 changes.

## Architecture Delta Summary

New nodes in `docs/architecture.yml`:
- `brain.fill_model.constants` (module, no public functions)
- `brain.fill_model.config` (module, no public functions — Pydantic class)
- `brain.fill_model.features` (module, `public_functions: [build_features_table]`)
- `parquet.fill_features` (storage, Hive-partitioned)
- 11× `config.fill_model.*` (config_knob)

New edges (12 total): features→{parquet.market_trades, parquet.order_book_combined, parquet.order_book_raw, parquet.underlying_apr, state.clo_history, parquet.fill_features, brain.duckdb_layer.setup, config.fill_model.bin_duration_s, config.fill_model.window_days, config.fill_model.covariate_whitelist}; config→constants; brain.config.schema→brain.fill_model.config.

## Wave-0 Downstream Unblock Map

| Downstream Plan | Unblocked by | Skip markers to remove |
|-----------------|-------------|----------------------|
| 02-02 (QueueTracker + AMMConsumption) | `fill_model.config`, `fill_model.features`, fixtures | `wave-0-scaffold: implemented in plan 02-02` (6 tests) |
| 02-03 (Fit + Predict) | `FillModelConfig`, `build_features_table`, synthetic_poisson.parquet | `wave-0-scaffold: implemented in plan 02-03` (6 tests) |
| 02-04 (Calibration + GoF + Refit Loop) | All above + regime_shift.parquet | `wave-0-scaffold: implemented in plan 02-04` (3 tests) |

## Self-Check: PASSED

All 18 key files exist. All 3 task commits (76d141a, 5d69c51, b813fbf) present in git log.
