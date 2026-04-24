---
phase: 03-loss-reward-share-models-sizing
plan: 01
subsystem: loss_model
tags: [loss_model, empirical_grid, ou_scaffold, alembic, duckdb, pendle_units]
requires:
  - phase: 01
    plan: 02
    provides: [state.fill_model_fits writer pattern, sqlite_writer_lint discipline]
  - phase: 01
    plan: 03
    provides: [structlog tier + run_id contextvars, ZMQ event bus]
  - phase: 02
    plan: 03
    provides: [fill_model.fit_artifact pattern, fill_model.predict sync contract]
provides:
  modules:
    - brain.loss_model.config (LossModelConfig + FeesConfig)
    - brain.loss_model.schemas (LossGridArtifact, LossGridCell, ExpectedLossInput/Output, LossModelNoFreshGridError, PerFillPnL)
    - brain.loss_model.replay (replay_historical_fills, build_per_fill_pnl_from_frame)
    - brain.loss_model.fit (fit_loss_grid, build_loss_grid_artifact_from_fills)
    - brain.loss_model.expected_loss (expected_loss SYNC sub-10ms contract)
    - brain.loss_model.artifact (write_loss_grid_artifact dual-write)
    - brain.loss_model.refit_loop (refit_once, run_loss_model_refit_loop)
    - brain.loss_model.ou_parametric (LOSS-03 scaffold + Protocol)
    - brain.loss_model.cli (fit | expected-loss | force-degrade subcommands)
    - brain.state.writers.loss_grid_artifacts (insert_loss_grid_artifact + get_latest_loss_grid)
  schema:
    - state.loss_grid_artifacts (Alembic 0004; PK (market_id, side, window_end_ts))
  contracts:
    - LossGridArtifact (Phase-4 LOCKED dual-write shape)
    - ExpectedLossInput / ExpectedLossOutput (Phase-4 LOCKED sync signature)
    - LossModelNoFreshGridError (raised on stale or missing grid)
    - OUBasisLossModel Protocol (v1.0 drop-in interface)
affects:
  - python/tests/test_sqlite_migrations.py (table-set assertion updated for loss_grid_artifacts)
tech_stack:
  patterns:
    - fill_model fit + predict + artifact + refit_loop + cli pattern (mirrored)
    - sentinel created_at = 0 + datetime.now(UTC) stamp at write-edge
    - parquet-FIRST / SQLite-SECOND dual-write (orphan-tolerant)
    - DuckDB CTE join with no-look-ahead invariant baked into SQL
    - test-injection seam (fills_frame / fills) bypassing DuckDB for unit tests
key_files:
  created:
    - python/src/boros_brain/loss_model/__init__.py
    - python/src/boros_brain/loss_model/__main__.py
    - python/src/boros_brain/loss_model/config.py
    - python/src/boros_brain/loss_model/schemas.py
    - python/src/boros_brain/loss_model/replay.py
    - python/src/boros_brain/loss_model/fit.py
    - python/src/boros_brain/loss_model/expected_loss.py
    - python/src/boros_brain/loss_model/artifact.py
    - python/src/boros_brain/loss_model/refit_loop.py
    - python/src/boros_brain/loss_model/ou_parametric.py
    - python/src/boros_brain/loss_model/cli.py
    - python/src/boros_brain/state/writers/loss_grid_artifacts.py
    - python/src/boros_brain/state/migrations/versions/0004_loss_grid_artifacts.py
    - python/tests/test_loss_model_ou_scaffold.py
    - python/tests/test_loss_model_artifact.py
    - python/tests/test_loss_model_replay.py
    - python/tests/test_loss_model_fit_and_expected_loss.py
    - python/tests/fixtures/_generate_loss_grid_fixtures.py
    - python/tests/fixtures/loss_grid_synthetic_fills.parquet
    - LLM Wiki/workspaces/boros/wiki/empirical-loss-grid-v05.md
    - LLM Wiki/workspaces/boros/wiki/ou-on-basis-loss-scaffold.md
    - LLM Wiki/workspaces/boros/wiki/fee-cost-term-in-expected-loss.md
  modified:
    - python/src/boros_brain/state/schemas.sql (append loss_grid_artifacts DDL + index)
    - python/tests/test_sqlite_migrations.py (table-set expectation updated)
decisions:
  - "Bucket-edge sentinel 10000.0 (not float('inf')) — Pydantic JSON dump emits 'Infinity' which YAML cannot re-parse"
  - "fee_entrance + fee_gas scaled by 1/pendle_price_usd; pendle_price_usd=1.0 placeholder until Plan 03-04 wires PricingConfig"
  - "BotConfig.loss_model attachment deferred to Plan 03-02 — _get_loss_model_config(config) helper falls back to default LossModelConfig() so Plan 03-01 lands independently"
  - "Architecture.yml + Mermaid delta deferred to Plan 03-04 (atomic Phase-3 architecture commit) per plan spec; architecture_lint will fail in this wave until 03-04 lands"
  - "v0.5 OU scaffold raises NotImplementedError — partial implementation would create two truth sources for E[loss|fill] that diverge"
metrics:
  duration_min: 70
  tasks_completed: 3
  files_created: 19
  files_modified: 2
  total_lines: 2535
  tests_added: 20  # 19 pass + 1 skipped (Phase-5 placeholder)
  completed: "2026-04-24"
---

# Phase 3 Plan 01: LossModel (Empirical Grid + OU Scaffold) Summary

Empirical (depth, tau)-grid `E[loss|fill]` over historical fills with sparse-cell
k-NN fallback to `coarse_bound`, plus a v1.0 OU-on-basis Protocol scaffold —
LOSS-01/02/03 in 11 modules, 1 Alembic migration, and 4 test files.

## Core Deliverables

### 1. `LossModelConfig` + `FeesConfig` (PROTO-04 SSoT)

`brain.loss_model.config` exports both as `StrictBase` Pydantic sub-models with
`extra='forbid'` + `frozen=True`. Knob counts:

- **`LossModelConfig`**: 12 (`depth_bucket_edges`, `tau_bucket_edges_days`,
  `min_samples_per_cell`, `knn_k`, `knn_max_distance`, `aggregation_metric`,
  `window_days`, `refit_cadence_s`, `fit_warn_staleness_s`, `fit_max_staleness_s`,
  `close_latency_budget_s`, `fees`).
- **`FeesConfig`**: 8 (`taker_fee_rate`, `settlement_fee_rate`,
  `settlement_period_s`, `market_entrance_fee_usd`, `gas_place_gwei`,
  `gas_cancel_gwei`, `gas_close_gwei`, `gas_price_gwei`).

Bucket-edge terminal sentinel is `10000.0` (not infinity) per PATTERNS §config.py
gotcha — Pydantic JSON-dump emits `"Infinity"` which YAML cannot re-parse. The
1.0 PENDLE notional proxy keeps Phase-3-Plan-01 independent of `config.pricing`
(lands in Plan 03-02).

### 2. Schemas (Phase-4 LOCKED contracts)

`brain.loss_model.schemas` defines:

- `PerFillPnL` (frozen dataclass) — one row of empirical post-fill P&L under
  immediate-close. Fields cover all four fee terms.
- `LossGridCell` (StrictBase) — per-cell aggregation: `n_samples`,
  `mean_pendle`, `std_pendle`, `p5_pendle`, `p50_pendle`, `p95_pendle`.
- `LossGridArtifact` (StrictBase) — full artifact shape (PK: `market_id`,
  `side`, `window_end_ts`). `event_index_coverage='full'|'degraded'`. Default
  `created_at = 0` (sentinel; stamped at write-edge).
- `ExpectedLossInput` / `ExpectedLossOutput` — sync sub-10ms call shape.
- `LossModelNoFreshGridError(RuntimeError)` — raised by `expected_loss()` on
  no-grid or grid-too-stale.

### 3. `replay_historical_fills` (LOSS-01)

DuckDB multi-CTE join over Phase-1 parquet (`market_trades`) with the **no
look-ahead** invariant baked into SQL:

    close.blockTimestamp >= fill.blockTimestamp
    AND (close.blockTimestamp > fill.blockTimestamp
         OR close.eventIndex > fill.eventIndex)

T-03-05 mitigation. `build_per_fill_pnl_from_frame` is the test-injection seam
— accepts a polars DataFrame matching the SQL output schema. **A6 fee
absorption**: `pnl_pendle = gross - taker - settlement - entrance_amortized -
gas_proxy` for long; negated for short. `pendle_price_usd: float = 1.0`
default with a TODO marker for Plan 03-04 to thread the real value.

Fills with no forward-matchable close inside `close_latency_budget_s` are
**skipped** (with `loss_model.replay_close_missing` warn log) rather than
emitted with a fabricated close — preserves data integrity over coverage.

### 4. `fit_loss_grid` + `build_loss_grid_artifact_from_fills` (LOSS-01)

Bins per-fill PnL into the configured grid via a custom `_bucket_idx()` (no
polars `.cut()` to keep determinism on edge values). Aggregates cells via
polars `group_by([depth_bucket_idx, tau_bucket_idx]).agg(...)`. `fit_status`:

- `'ok'` — every populated cell has `n_samples >= min_samples_per_cell`.
- `'degraded'` — fills empty OR `len(fills) < min_samples_per_cell × 0.5`, OR
  any populated cell falls below the threshold.

`event_index_coverage` flips to `'degraded'` if any fill in the input list has
`fill_event_index is None`.

### 5. `expected_loss()` (LOSS-02 sync sub-10ms contract)

Three-tier fallback chain — every miss emits a structured warn log
(`loss_model.sparse_cell_fallback`):

| Mode | Trigger | Output value |
|------|---------|--------------|
| `exact` | target cell has `n_samples >= min_samples_per_cell` | cell aggregation_metric (mean / p50 / p95) |
| `nearest_neighbor` | top-`knn_k` neighbors within `knn_max_distance` sum to `>= min_samples_per_cell` | n_samples-weighted mean of neighbor metrics |
| `coarse_bound` | no neighbor satisfies | `screener.fill_loss_coarse_bound × 1.0` PENDLE |

T-03-03 mitigation: `n_samples == 0` cells never reach a divide step — the
coarse_bound branch is the safety net. T-03-04 mitigation: every fallback
carries `market_id`, `side`, `depth`, `tau_days`, `n_samples` in the structured
warn so the operator can audit grid sparsity. `LossModelNoFreshGridError` on
stale or absent grid; `ValueError` on negative `time_to_maturity_s` (Phase 4
SAFE-07 already breaks earlier — this is belt-and-braces).

### 6. `write_loss_grid_artifact` (parquet + SQLite dual-write)

Parquet FIRST, SQLite SECOND (orphan-tolerant). Sentinel `created_at = 0`
stamped via `datetime.now(UTC)` at the write edge — keeps `fit.py` /
`replay.py` / `expected_loss.py` lint-clean for the upcoming
`no_time_time_lint` extension. **T-03-01 path-traversal mitigation**:
`Path.resolve()` + `is_relative_to(parquet_root.resolve())` check before any
`mkdir`. Operator-typed `market_id` containing `..` segments raises
`ValueError("path traversal blocked")`.

### 7. `refit_loop` + CLI

`refit_once(config, run_id)` and `run_loss_model_refit_loop(config, run_id)`
mirror `fill_model.refit_loop`. Window end-ts comes from
`await chain_time.now_cached()` per INFRA-14.

CLI surface: `python -m boros_brain.loss_model {fit | expected-loss | force-degrade}`.
PROTO-01 MANIFEST-FIRST boot — `RUN_MANIFEST` written as the FIRST log record.
Exit codes: 0 success, 1 `LossModelNoFreshGridError`, 2 `ConfigError`. Tier:
`'loss_model'` (joins the existing structlog tier set).

### 8. `OUBasisLossModel` Protocol + `fit_ou_basis` scaffold (LOSS-03)

`brain.loss_model.ou_parametric.fit_ou_basis(...)` raises
`NotImplementedError("LOSS-03 scaffold — v1.0 drop-in point. See [[ou-on-basis-loss-scaffold]]")`.
The Protocol locks `expected_loss(self, req, *, sqlite_path, config)` so
Phase 4 can swap empirical→OU via config without code changes anywhere.
`test_ou_scaffold_protocol_matches_empirical_expected_loss` uses
`inspect.signature` to enforce signature-equality with the empirical backend.

### 9. Single-writer + Alembic 0004

`brain.state.writers.loss_grid_artifacts.insert_loss_grid_artifact` is the
**only** write path for `loss_grid_artifacts` (`scripts/sqlite_writer_lint.py`
will catch any drift on commit). UPSERT on `(market_id, side, window_end_ts)`
PK — second insert mutates the row in place rather than duplicating.

Alembic migration `0004_loss_grid_artifacts` is idempotent
(`_has_table` / `_has_index` gates) and applies cleanly on a fresh DB.
Verified by `test_sqlite_migrations.py::test_all_8_tables_exist_after_migration`
(table-set expectation updated).

## Interfaces Published for Plan 03-02 / 03-03 Consumption

```python
# Phase-4 LOCKED contracts — Plan 03-02 attaches BotConfig.loss_model;
# Plan 03-03 Sizer + Phase 4 DecisionEngine call expected_loss() at 1 Hz.

class ExpectedLossInput(StrictBase):
    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    time_to_maturity_s: int
    current_chain_ts: int  # caller threads chain_time.now_cached()

class ExpectedLossOutput(StrictBase):
    expected_loss_pendle: float
    cell_n_samples: int
    cell_p50_pendle: float
    cell_p95_pendle: float
    fallback_mode: Literal["exact", "nearest_neighbor", "coarse_bound"]
    grid_artifact_run_id: str
    grid_age_s: float
    fit_status: Literal["ok", "degraded", "stale"]

def expected_loss(
    req: ExpectedLossInput, *, sqlite_path: Path, config: BotConfig
) -> ExpectedLossOutput: ...

class LossModelNoFreshGridError(RuntimeError): ...
```

`FeesConfig` knob list (Plan 03-02 attaches via `LossModelConfig.fees`):
`taker_fee_rate=5e-4, settlement_fee_rate=1e-3, settlement_period_s=28800,
market_entrance_fee_usd=1.0, gas_place_gwei=200000, gas_cancel_gwei=100000,
gas_close_gwei=300000, gas_price_gwei=0.1`.

## Test Results

- **Plan tests added**: 20 (19 PASS + 1 SKIP placeholder for Phase-5 backtest
  integration).
- **Migrations test**: 8/8 PASS (table-set updated to include
  `loss_grid_artifacts`).
- **Plan-relevant suite**: `tests/test_loss_model_*.py` + `tests/test_sqlite_migrations.py`
  → 27 PASS + 1 SKIP.

| File | Tests |
|------|-------|
| `test_loss_model_ou_scaffold.py` | 3 (1 skip — pending Task 2's expected_loss.py — automatically lifts) |
| `test_loss_model_artifact.py` | 4 (dual-write, sentinel-stamp, T-03-01 path-traversal, UPSERT idempotency) |
| `test_loss_model_replay.py` | 4 (3 PASS + 1 SKIP for Phase-5 integration) |
| `test_loss_model_fit_and_expected_loss.py` | 9 (fit ok/degraded + expected_loss exact/nn/coarse/stale/no-artifact/neg-tau/pendle-units) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] BotConfig.loss_model not yet attached**

- **Found during:** Task 2 (replay test ran into `'BotConfig' object has no attribute 'loss_model'`).
- **Cause:** Plan 03-02 attaches `loss_model` to `BotConfig`; Plan 03-01 lands first.
- **Fix:** Added `_get_loss_model_config(config)` helper in `replay.py`,
  `fit.py`, `expected_loss.py`, `refit_loop.py` that returns
  `getattr(config, "loss_model", None) or LossModelConfig()`. Keeps Plan 03-01
  independent; once Plan 03-02 attaches the field, the helper transparently
  returns the operator-supplied config. Test fixture switches to a default
  `LossModelConfig()` for assertions until 03-02 lands.
- **Files modified:** `loss_model/replay.py`, `loss_model/fit.py`,
  `loss_model/expected_loss.py`, `loss_model/refit_loop.py`,
  `tests/test_loss_model_replay.py`.
- **Commit:** 9164e64

**2. [Rule 1 - Bug] `test_all_8_tables_exist_after_migration` brittle assertion**

- **Found during:** Task 2 verification.
- **Cause:** Test asserts an exact table set; Alembic 0004 adds `loss_grid_artifacts`.
- **Fix:** Updated `expected` set to include `loss_grid_artifacts`. Comment
  notes Plan 03-01 adds table 10. Same pattern Plan 02-03 used to add
  `fill_model_fits` as table 9.
- **Files modified:** `tests/test_sqlite_migrations.py`.
- **Commit:** 9164e64

**3. [Rule 1 - Test polish] `float('inf')` in config.py docstrings tripped the literal grep acceptance criterion**

- **Found during:** Task 1 self-check.
- **Cause:** Two docstring lines literally contained `float('inf')` (in
  warnings against using it). Plan acceptance criterion is `grep -c "float('inf')" config.py == 0`.
- **Fix:** Rephrased docstrings to use "an infinity literal" — same warning
  intent, no `float('inf')` substring. Now 0 hits.
- **Files modified:** `loss_model/config.py`.
- **Commit:** 697d8cf (squashed into Task 1 since it landed before commit).

**4. [Rule 1 - Test polish] `time.time()` in `fit.py` docstring tripped the acceptance grep**

- **Found during:** Task 2 self-check.
- **Cause:** A line in the module docstring literally read "NO time.time() /
  datetime.now() in this module" — same regex as the lint pattern.
- **Fix:** Rephrased to "NO wall-clock calls in this module." Lint regex no
  longer matches. Now 0 hits across `loss_model/`.
- **Files modified:** `loss_model/fit.py`.
- **Commit:** 9164e64

## Auth Gates

None. The plan is pure offline batch + sync query; no network endpoints, no
secrets, no operator-only steps.

## Known Stubs / Open TODOs

These are explicitly deferred to Plan 03-04 per the plan's `<deferred>` block —
they are NOT bugs:

| TODO | File | Plan that closes it |
|------|------|---------------------|
| `pendle_price_usd: float = 1.0` argument | `loss_model/replay.py:replay_historical_fills` | Plan 03-04 (`config.pricing` wiring) |
| BotConfig.loss_model attachment | `config/schema.py` | Plan 03-02 (Phase-3 schema delta) |
| Mermaid + `architecture.yml` nodes for loss_model package | `docs/architecture.yml` | Plan 03-04 (atomic Phase-3 architecture commit) |
| Supersedence Status flip on `[[fill-loss-coarse-bound-v05]]` | LLM Wiki | Plan 03-04 |
| Supersedence Status flip on `[[economics-kill-switch-v05]]` | LLM Wiki | Plan 03-04 |
| `no_time_time_lint.py` extension to include `loss_model/` | `scripts/no_time_time_lint.py` | Plan 03-04 |
| OU empirical implementation | `loss_model/ou_parametric.py:fit_ou_basis` | v1.0 (DEFERRED) |

## Deferred / Out-of-Scope Test Failures

Three pre-existing failures observed in the worktree at execution start — NOT
caused by Plan 03-01 work:

- `tests/test_screener_filter.py::test_all_six_filters_applied` — `_duckdb.BinderException: size_float not found`
- `tests/test_screener_filter.py::test_shortlist_capped_at_four` — same root cause
- `tests/test_screener_filter.py::test_r_apr_potential_ranking` — same root cause

Verified pre-existing by stash-test on the base commit. Routed to deferred-items
(architecture.yml lint also pre-existing once you exclude the loss_model nodes
that Plan 03-04 will add atomically — but the architecture-lint test does
genuinely fail in this wave because of new loss_model modules; this is the
plan's intended drift state and Plan 03-04 closes it).

## TDD Gate Compliance

Plan-level type is `execute` (not `tdd`), but each task's `tdd="true"` was
honored: tests were written alongside implementation (test files committed in
the same task commits as their target modules). Pattern matches `fill_model`
predecessor plans. Per-task commit hashes:

- Task 1 (697d8cf): scaffold + OU + 0004 migration + scaffold tests.
- Task 2 (9164e64): full pipeline + 3 test files + brittle-test fix.
- Task 3 (no in-repo commit; wiki pages live at
  `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/`
  per CLAUDE.md Engineering Protocol 1).

## Self-Check: PASSED

**Files created (in-repo):**
- `python/src/boros_brain/loss_model/__init__.py` — FOUND
- `python/src/boros_brain/loss_model/config.py` — FOUND
- `python/src/boros_brain/loss_model/schemas.py` — FOUND
- `python/src/boros_brain/loss_model/replay.py` — FOUND
- `python/src/boros_brain/loss_model/fit.py` — FOUND
- `python/src/boros_brain/loss_model/expected_loss.py` — FOUND
- `python/src/boros_brain/loss_model/artifact.py` — FOUND
- `python/src/boros_brain/loss_model/refit_loop.py` — FOUND
- `python/src/boros_brain/loss_model/ou_parametric.py` — FOUND
- `python/src/boros_brain/loss_model/cli.py` — FOUND
- `python/src/boros_brain/loss_model/__main__.py` — FOUND
- `python/src/boros_brain/state/writers/loss_grid_artifacts.py` — FOUND
- `python/src/boros_brain/state/migrations/versions/0004_loss_grid_artifacts.py` — FOUND
- `python/tests/test_loss_model_ou_scaffold.py` — FOUND
- `python/tests/test_loss_model_artifact.py` — FOUND
- `python/tests/test_loss_model_replay.py` — FOUND
- `python/tests/test_loss_model_fit_and_expected_loss.py` — FOUND
- `python/tests/fixtures/_generate_loss_grid_fixtures.py` — FOUND
- `python/tests/fixtures/loss_grid_synthetic_fills.parquet` — FOUND

**Files created (LLM Wiki, external):**
- `LLM Wiki/.../empirical-loss-grid-v05.md` — FOUND
- `LLM Wiki/.../ou-on-basis-loss-scaffold.md` — FOUND
- `LLM Wiki/.../fee-cost-term-in-expected-loss.md` — FOUND

**Commits:**
- 697d8cf — FOUND
- 9164e64 — FOUND
