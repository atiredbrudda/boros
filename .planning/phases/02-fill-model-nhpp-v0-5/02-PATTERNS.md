---
phase: 2
slug: fill-model-nhpp-v0-5
kind: pattern-map
created: 2026-04-24
upstream: [02-RESEARCH.md, 02-VALIDATION.md]
downstream: 02-PLAN-*.md
---

# Phase 2 — Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 24 new / modified source + test + fixture + protocol artifacts
**Analogs found:** 24 / 24 (Phase 1 scaffold is in-place and exhaustive; no NO_ANALOG entries)

The Boros Phase 1 scaffold is load-bearing: every new Phase 2 module has a direct structural precedent in `python/src/boros_brain/`. This map assigns the closest analog per target file, quotes the specific 5–30-line pattern fragment the new file must mirror, and lists the deltas + non-obvious gotchas the planner must honor.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `python/src/boros_brain/fill_model/__init__.py` | package-marker | n/a | `python/src/boros_brain/screener/__init__.py` | exact |
| `python/src/boros_brain/fill_model/config.py` (new `FillModelConfig` sub-model) | config-schema | static | `python/src/boros_brain/config/schema.py` (`ScreenerConfig`) | exact |
| `python/src/boros_brain/fill_model/constants.py` | constants | static | `python/src/boros_brain/data/ingester/schemas.py` (constants-only module) | exact |
| `python/src/boros_brain/fill_model/schemas.py` (`FitArtifact`, `PredictInput`, `PredictOutput`) | pydantic-schema | static | `python/src/boros_brain/manifest/schema.py` + `python/src/boros_brain/data/poller/schemas.py` | exact |
| `python/src/boros_brain/fill_model/features.py` | service / transform | batch, DuckDB read → parquet write | `python/src/boros_brain/screener/metrics.py` + `python/src/boros_brain/duckdb_layer/setup.py` | role-match (pure transform) |
| `python/src/boros_brain/fill_model/queue_tracker.py` | service / event-replay | event-driven batch | `python/src/boros_brain/data/ingester/order_book.py` (`assert_amm_conservation`) + `screener/metrics.py` (eventIndex-ordered replay) | role-match (tape-replay + identity assertion) |
| `python/src/boros_brain/fill_model/amm_consumption.py` | service / invariant-check | batch | `python/src/boros_brain/data/ingester/order_book.py` (`assert_amm_conservation`) | exact (runtime analogue of DATA-05 ingest check) |
| `python/src/boros_brain/fill_model/fit.py` | service / model-fit | batch (statsmodels GLM) | `python/src/boros_brain/screener/scale_calibration.py` + `screener/filter.py` (batch computation → dataclass result) | role-match (numerics-in-batch → persisted artifact) |
| `python/src/boros_brain/fill_model/predict.py` | service / sync-query | request-response (sync) | `python/src/boros_brain/data/chain_time.py` (`now_cached()` sync contract) + `screener/filter.py` result-shape | role-match (sync entry point + error-raising contract) |
| `python/src/boros_brain/fill_model/artifact.py` (FitArtifact persistence + parquet sidecar) | storage-writer-adapter | write | `python/src/boros_brain/manifest/writer.py` (sidecar+SQLite atomic writer) | exact |
| `python/src/boros_brain/fill_model/refit_loop.py` | long-running async task | event-driven (cadence loop) | `python/src/boros_brain/data/poller/markets_poller.py` (`run_markets_poller`) + `e_liq_poller.py` | exact |
| `python/src/boros_brain/fill_model/calibration.py` | service / stats | batch | `python/src/boros_brain/screener/scale_calibration.py` (stats-in-module pattern) + `screener/metrics.py` | role-match (no pre-existing Rosenblatt/KS analog — reuse `screener/metrics.py` stylistic contract) |
| `python/src/boros_brain/fill_model/report.py` | service / report-writer | batch (writes JSON + PNG artifact) | `python/src/boros_brain/screener/report.py` + `screener/kill_report.py` | exact |
| `python/src/boros_brain/fill_model/cli.py` | CLI entrypoint | request-response | `python/src/boros_brain/screener/cli.py` | exact |
| `python/src/boros_brain/state/writers/fill_model_fits.py` | state-writer (single-writer discipline) | write | `python/src/boros_brain/state/writers/clo_history.py` | exact |
| `python/src/boros_brain/state/schemas.sql` (append `fill_model_fits` table) | schema DDL | n/a | existing `clo_history` / `run_manifests` DDL in same file | exact |
| `python/src/boros_brain/state/migrations/versions/XXXX_fill_model_fits.py` | Alembic migration | n/a | `python/src/boros_brain/state/migrations/versions/*0001_initial_8_tables*` | exact |
| `python/src/boros_brain/config/schema.py` (add `fill_model: FillModelConfig`) | config-schema-modify | static | self (top-level `BotConfig` class already has `screener:`, `strategy:`) | exact |
| `python/src/boros_brain/main.py` (wire refit_loop) | process-entrypoint-modify | async-task supervision | self (`main.run()` already spawns `send_task`, `monitor_task`, `ingest_task`) | exact |
| `python/tests/test_fill_model_features.py` | pytest unit/property | n/a | `python/tests/test_screener_metrics.py` | exact |
| `python/tests/test_fill_model_queue_tracker.py` | pytest unit/property | n/a | `python/tests/test_amm_conservation.py` + `test_findex_reader.py` | exact |
| `python/tests/test_fill_model_amm_consumption.py` | pytest unit/property | n/a | `python/tests/test_amm_conservation.py` | exact |
| `python/tests/test_fill_model_fit_basic.py` | pytest unit | n/a | `python/tests/test_screener_scale_calibration.py` | exact |
| `python/tests/test_fill_model_predict_contract.py` | pytest unit/property | n/a | `python/tests/test_manifest_contains_all_knobs.py` (contract tests) + `test_screener_metrics.py` | exact |
| `python/tests/test_fill_model_calibration_gof.py` | pytest integration | n/a | `python/tests/test_daily_rescreen.py` (end-to-end integration style) | exact |
| `python/tests/test_manifest_contains_all_knobs.py` (extend w/ fill_model assertion) | pytest modify | n/a | self | exact (no change needed — test already reflection-walks every `FillModelConfig` leaf automatically) |
| `python/tests/test_architecture_lint.py` (new stub) | pytest lint | n/a | hook `scripts/architecture_lint.py` | role-match (no existing subprocess-wrapper test; template available from `test_cli.py` subprocess pattern) |
| `python/tests/fixtures/fill_model_tiny_tape.ndjson` | fixture | NDJSON | `python/tests/fixtures/sample_market_trades.ndjson` | exact |
| `python/tests/fixtures/fill_model_synthetic_poisson.parquet` | fixture | parquet | no existing `.parquet` fixture → generate from polars `write_parquet()` in a conftest fixture or a one-shot `scripts/` generator | role-match (pattern: write fixture generator as a test helper) |
| `python/tests/fixtures/fill_model_regime_shift.parquet` | fixture | parquet | same as above | role-match |
| `docs/architecture.yml` (modify — add ~25 node rows + ~30 edge rows) | machine-yml | n/a | self | exact |
| `docs/ARCHITECTURE.md` (modify — add Mermaid subsystem) | human-markdown + Mermaid | n/a | self | exact |
| `scripts/no_time_time_lint.py` (one-line extend to include `fill_model/`) | lint-hook-modify | n/a | self | exact |

---

## Pattern Assignments

### `python/src/boros_brain/fill_model/config.py` — `FillModelConfig` Pydantic sub-model

**Role:** 11-knob Pydantic `StrictBase` sub-model that slots into `BotConfig.fill_model` so every knob auto-surfaces in RUN_MANIFEST via reflection.

**Data flow:** static config → reflection by `manifest.writer.build_run_manifest` → every `predict()`/`fit()`/`refit_loop` consumer reads the field from a frozen `BotConfig` instance.

**Analog:** `python/src/boros_brain/config/schema.py` (`ScreenerConfig` and `StrategyConfig` classes — same extra=forbid / frozen=True contract, same Field-with-range pattern).

**Imports pattern** (config/schema.py lines 13–17):
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
```

**StrictBase contract** (config/schema.py lines 20–28) — every new sub-model MUST inherit from `StrictBase`:
```python
class StrictBase(BaseModel):
    """Base for every BotConfig sub-model.

    `extra='forbid'` turns unknown YAML keys into a loud ValidationError.
    `frozen=True` prevents runtime mutation of a loaded BotConfig — knobs are
    authored in YAML, loaded once, and then read-only for the lifetime of the run.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Sub-model pattern** (config/schema.py lines 92–101, `ScreenerConfig` — closest analog):
```python
class ScreenerConfig(StrictBase):
    """Market-screener knobs — window lengths and thresholds for the economics gate."""

    min_time_to_maturity_days: int = 30
    trades_window_days: int = 60
    realized_vol_window_days: int = 14
    reversal_count_window_days: int = 3
    alt_yield: float = Field(0.05, ge=0.0, le=1.0)
    fill_loss_coarse_bound: float = Field(0.02, ge=0.0, le=1.0)
```

**BotConfig attach-point pattern** (config/schema.py lines 115–134):
```python
class BotConfig(StrictBase):
    """Top-level config. One instance per run; frozen after load."""
    ...
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)  # type: ignore
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)  # type: ignore
    ...
    screener: ScreenerConfig = Field(default_factory=ScreenerConfig)  # type: ignore
    markets: list[MarketCalibration] = Field(default_factory=list, max_length=1)
```

**Deltas vs analog:**
- Expose 11 knobs per RESEARCH §Logging + RUN_MANIFEST Additions (window_days=14, bin_duration_s=60.0, refit_cadence_s=900.0, covariate_whitelist=list[str] default 5-entry list, queue_tracker_bias_mode=Literal, gof_ks_pval_threshold=0.0, gof_lr_ratio_threshold=None (populated post-bootstrap), fit_warn_staleness_s=1800.0, fit_max_staleness_s=3600.0, bracket_width_warn_multiplier=0.5, min_events_per_param_ratio=10).
- `covariate_whitelist: list[str]` is not a scalar — add a `@field_validator` to check each entry is in a module-level `ALLOWED_COVARIATES` set (defined in `constants.py`) so the "non-whitelisted covariate → ConfigError" test (T-02-F-01) passes.
- `queue_tracker_bias_mode: Literal["pessimistic", "optimistic", "realized"] = "pessimistic"` — Literal, not plain str, to get Pydantic validation for free.
- Where the research says "SHOULD live at `fill_model/config.py`" but RESEARCH §3 Recommended Project Structure says `constants.py`: put the Pydantic sub-model in `config.py`; put the `ALLOWED_COVARIATES: frozenset[str] = frozenset({"basis_spread", "imbalance", "sin_settlement", "cos_settlement", "ewma_vol"})` + `DEFAULT_BIN_DURATION_S = 60.0` constants in `constants.py`. Two files, not one. Mirrors the split between `config/schema.py` and screener-level constants.

**Gotchas:**
- Adding `FillModelConfig` to `BotConfig.fill_model` auto-registers every leaf in `test_manifest_contains_all_knobs.py` via `_collect_leaf_paths` reflection — no test edit needed. If the planner adds a knob that is a `list[BaseModel]` (none planned), the reflection walker special-cases lists-of-models (lines 67–74 of the test) but treats them as a single leaf path; do not nest a `BaseModel` inside `covariate_whitelist`.
- `Field(default_factory=FillModelConfig)` on the `BotConfig` attachment line needs the `# type: ignore` comment per the plugin-vs-no-plugin mypy dance (see analog line 129: `strategy: StrategyConfig = Field(default_factory=StrategyConfig)  # type: ignore`).
- `gof_lr_ratio_threshold: float | None = None` — Pydantic v2 accepts this; the default is `None` until bootstrap-calibrated from the first fit, documented inline per RESEARCH §8.

---

### `python/src/boros_brain/fill_model/constants.py` — covariate whitelist + defaults

**Role:** Module-level constants, no functions (public_functions=[] in architecture.yml).

**Analog:** `python/src/boros_brain/data/ingester/schemas.py` — constants-only module (per architecture.yml line entry: `public_functions: []   # Schema constants only — MARKET_TRADES_SCHEMA etc.`).

**Pattern to mirror:** single file, module-level UPPERCASE constants, type-annotated, docstring-only (no helper functions → no `public_functions` to declare in architecture.yml).

**Deltas:** ~5 constants (`ALLOWED_COVARIATES`, `DEFAULT_BIN_DURATION_S`, `DEFAULT_WINDOW_DAYS`, `DEFAULT_REFIT_CADENCE_S`, `DEFAULT_COVARIATE_WHITELIST`). The `FillModelConfig` imports `ALLOWED_COVARIATES` for its validator.

**Gotchas:** `public_functions: []` in the `brain.fill_model.constants` architecture.yml node entry — no top-level `def` statements, or the lint fires.

---

### `python/src/boros_brain/fill_model/schemas.py` — `FitArtifact`, `PredictInput`, `PredictOutput` Pydantic models

**Role:** Wire-contract Pydantic models for `fit()` outputs and `predict()` I/O. Consumed by `state/writers/fill_model_fits.py` (to persist), by `predict.py` (to validate inputs), and by Phase 4 DecisionEngine (to consume outputs).

**Data flow:** static schema; `FitArtifact` is written to SQLite + parquet; `PredictInput`/`PredictOutput` are the sync function boundary.

**Analog:** `python/src/boros_brain/manifest/schema.py` (frozen+extra=forbid Pydantic model with `dict[str, Any]` for the nested config field).

**Imports + StrictBase pattern** (manifest/schema.py lines 13–23):
```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Concrete model pattern** (manifest/schema.py lines 26–39):
```python
class RunManifest(StrictBase):
    run_id: str
    parent_run_id: str | None = None
    started_at: str
    mode: str
    strategy_version: str
    git_sha: str
    git_dirty: bool
    market_id: str
    side: str
    wallet_address_hash: str
    config: dict[str, Any]
    chain_time_drift_at_start_seconds: float | None = None
    agent_wallet_gas_balance_at_start: float | None = None
```

**Deltas:**
- Three classes in one file (not one).
- `FitArtifact` fields per RESEARCH §Code Examples #2 + §Feature Engineering's `state.fill_model_fits` column list: `run_id: str`, `fit_window_start_ts: int`, `fit_window_end_ts: int`, `market_id: str`, `side: Literal["long","short"]`, `covariate_whitelist: list[str]`, `beta: list[float]`, `beta_stderr: list[float]`, `log_likelihood: float`, `deviance: float`, `aic: float`, `n_observations: int`, `converged: bool`, `fit_status: Literal["ok","degraded","stale"]`, `gof_ks_pval: float | None = None`, `gof_lr_vs_null: float | None = None`, `created_at: int`.
- `PredictInput` per RESEARCH §Code Examples #3: `market_id`, `side`, `depth_from_mark_ticks`, `queue_ahead_wei`, `current_features: dict[str,float]`, `time_to_epoch_end_s`.
- `PredictOutput` per same §: `p_fill_this_epoch`, `lambda_per_second`, `fit_run_id`, `fit_age_s`, `fit_status`.
- Also declare exception classes: `class FillModelStaleFeatureError(RuntimeError): ...` and `class FillModelNoFreshFitError(RuntimeError): ...` (per RESEARCH §Code Examples #3 & §Decision-Engine Interface).

**Gotchas:**
- Put the exception classes in `schemas.py` (alongside the Pydantic models), not a separate `exceptions.py` — matches the ingester pattern where exceptions live in a dedicated sibling but also the screener pattern where `economics_gate.py` inlines `ProjectHalt`/`ConfigError`. For Phase 2, the DecisionEngine in Phase 4 imports both from `fill_model.predict` (via re-export) — having them in `schemas.py` and re-exported from `predict` is cleaner.
- `public_functions: []` in the `brain.fill_model.schemas` architecture.yml node: classes only, no top-level functions. (This is load-bearing — the lint in `scripts/architecture_lint.py` lines 76–79 only picks up `FunctionDef`/`AsyncFunctionDef`, not classes.)

---

### `python/src/boros_brain/fill_model/features.py` — DuckDB-joined binned feature table writer

**Role:** Execute the DuckDB SQL from RESEARCH §Code Examples #1 to produce the per-(market, side, bin) feature table; write it to `data/parquet/fill_features/`.

**Data flow:** reads `parquet.market_trades`, `parquet.order_book_raw`, `parquet.order_book_combined`, `parquet.underlying_apr`, `state.clo_history` via `brain.duckdb_layer.setup.open_analytical_conn`; writes `parquet.fill_features` (new Hive-partitioned storage node).

**Analog:** `python/src/boros_brain/screener/metrics.py` (pure-transform module that reads parquet via DuckDB, computes per-market metrics, returns polars DataFrames / scalars).

**Imports pattern** (screener/metrics.py lines 13–20):
```python
from __future__ import annotations

import math

import polars as pl
import structlog

log = structlog.get_logger(__name__)
```

**DuckDB + polars read pattern** (duckdb_layer/setup.py lines 111–135 + screener/cli.py lines 35–40):
```python
from ..duckdb_layer.setup import open_analytical_conn
...
conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")
results = conn.execute(SQL, {"market_id": market_id, ...}).pl()   # polars DataFrame
```

**Event-ordered sort pattern** (screener/metrics.py lines 41–60) — `eventIndex` is load-bearing:
```python
# Sort by blockTimestamp then eventIndex (canonical ordering for this project)
df = trades.sort(["blockTimestamp", "eventIndex"])

# T-01-11-01: reject markets with any null eventIndex
null_count = df["eventIndex"].is_null().sum()
if null_count > 0:
    log.warning(
        "screener.eventindex_gap",
        market_id=market_id,
        null_rows=int(null_count),
    )
    return None
```

**Deltas:**
- Translate the RESEARCH §Code Examples #1 SQL verbatim into a single parameterised DuckDB execute (with `:market_id`, `:window_start`, `:window_end` params).
- Output schema per RESEARCH §Feature Engineering: columns `market_id, side, bin_start, trade_count, basis_spread, imbalance, sin_settlement, cos_settlement, ewma_vol, bin_duration_s`.
- Write to Hive-partitioned parquet `data/parquet/fill_features/market_id=.../side=.../window_end_ts=.../features.parquet` via `polars.DataFrame.write_parquet` (pattern from `data/ingester/base.py::write_partitioned_parquet`).
- Left-closed EWMA: the SQL uses `ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING` — this excludes the current bin, implementing the "no look-ahead" invariant. Do NOT change to `CURRENT ROW` (kills T-02-F-02).
- Public functions per RESEARCH §Protocol 2: `build_features_table`, `FeatureSet` (class).

**Gotchas:**
- `open_analytical_conn` attaches SQLite **read-only** (setup.py lines 50–68) — features.py MUST NOT try to write through the DuckDB connection; it writes parquet via polars directly.
- `FeatureSet` being a class means `architecture.yml` declares `public_functions: [build_features_table]` only — the class itself is not a top-level function and the lint won't see it. Per the existing ingester pattern (line 195 architecture.yml: `# IngesterSchemaViolation + IngestResult are classes`), declare the class in a comment next to `public_functions`.
- The feature table emits `bin_duration_s = 60.0` as a column (the `exposure` in `statsmodels.GLM(exposure=...)`) — do NOT accept null / zero bins; filter them at SQL level with `WHERE bin_duration_s > 0`.

---

### `python/src/boros_brain/fill_model/queue_tracker.py` — tri-track replay + drift diagnostic

**Role:** Replay NDJSON tape with pessimistic / realized / optimistic accounting; per-hour reconciliation against `order_book_raw` snapshots; emit `drift_signed_mean`, `drift_magnitude_mean`, `drift_std`; compute `bracket_width_warn` log event.

**Data flow:** reads `parquet.market_trades` (tape), `parquet.order_book_raw` (hourly anchors), `parquet.order_book_combined` (for AMM subtraction via `amm_consumption`).

**Analog:** `python/src/boros_brain/data/ingester/order_book.py` (eventIndex-aware replay + invariant assertion) + `python/src/boros_brain/screener/metrics.py` (eventIndex-ordered polars sort pattern, §7 above).

**Eventindex-ordered replay pattern** (screener/metrics.py lines 23–60, shown above) — queue_tracker must also:
1. Sort by `(blockTimestamp, eventIndex)`.
2. Reject or down-weight rows with `null eventIndex` (graceful degrade per RESEARCH §Assumption A3).

**Invariant-check pattern to mirror for tri-track bracket** (ingester/order_book.py lines 48–80 — `assert_amm_conservation`):
```python
def assert_amm_conservation(raw: pl.DataFrame, combined: pl.DataFrame) -> None:
    """DATA-05: for each tick delta in an hourly snapshot, combined_size(delta) >= raw_book_size(delta).

    Formula: combined_size(delta) - raw_book_size(delta) >= 0 per tick.
    Violation => raise AMMConservationError.

    PITFALLS §B3: negative AMM share poisons every fill-probability model downstream.
    This MUST NOT be caught and skipped — let it propagate to a non-zero process exit.
    ...
    """
    ...
    joined = raw_sel.join(combined_sel, on=["snapshot_ts", "tick"], how="full", coalesce=True)
    joined = joined.with_columns(
        pl.col("size_combined").fill_null(0.0),
        pl.col("size").fill_null(0.0),
    )
    neg = joined.filter(pl.col("size_combined") - pl.col("size") < 0)
```

**Drift-diagnostic output pattern** (RESEARCH §Pattern 2 — canonical — already in research; mirror the **structlog shape** from screener/metrics.py):
```python
log.warning(
    "fill_model.queue_drift_reconciliation",
    market_id=market_id,
    side=side,
    drift_signed_mean=float(drifts.mean()),
    drift_magnitude_mean=float(np.abs(drifts).mean()),
    drift_std=float(drifts.std(ddof=1)),
    n_ticks_compared=len(ticks),
)
```

**Deltas:**
- New: three parallel replay functions (`_replay_pessimistic`, `_replay_realized`, `_replay_optimistic`) returning per-tick queue sizes at each hourly anchor.
- New: `compute_drift_diagnostic(replay_queue, snapshot_queue) -> dict` — canonical signature from RESEARCH §Pattern 2 code block.
- `QueueTracker` class holds the three-track state machine; `compute_drift_diagnostic` is a free function. Public functions per RESEARCH §Protocol 2: `QueueTracker`, `compute_drift_diagnostic` — the class shows up in a yml comment, the function as `public_functions: [compute_drift_diagnostic]`.
- `bracket_width_warn` log per RESEARCH §8 log events table — fire when `pessimistic − optimistic > bracket_width_warn_multiplier × hourly_mean_queue`.
- **Do NOT raise** on drift bias — drift IS the diagnostic (widening bracket is information, not failure). Contrast with `assert_amm_conservation`: amm_consumption.py DOES raise because it's an identity violation.

**Gotchas:**
- `eventIndex` coverage — RESEARCH Assumption A3: if the confirmed shortlist market has `eventIndex` universally, we're fine; if a later-added market lacks it, queue_tracker collapses to `blockTimestamp` ties and **must** log `fill_model.eventindex_coverage_degraded` + mark the fit artifact's `eventIndex_coverage = "degraded"`. Do not silently collapse.
- Phase 1's `assert_amm_conservation` raises at INGEST time; Phase 2's queue_tracker runs a separate **runtime** AMM identity check via `amm_consumption.py::assert_epoch_conservation` (NOT the ingest one) — different phases, different fail modes. Don't conflate.

---

### `python/src/boros_brain/fill_model/amm_consumption.py` — amm_share + runtime conservation identity

**Role:** Compute `amm_share(δ, t) = combined(δ, t) − raw(δ, t)` time series per epoch; assert per-epoch identity `book_ahead_of_us(t_end) = book_ahead_of_us(t_start) − taker_consumption_ahead − amm_consumption + net_placements_ahead`.

**Data flow:** reads `parquet.order_book_raw`, `parquet.order_book_combined`; called by `queue_tracker.py` (identity check per epoch).

**Analog (exact):** `python/src/boros_brain/data/ingester/order_book.py::assert_amm_conservation`. Phase 2 implements the **runtime** analogue — structurally identical, different domain (per-epoch instead of per-snapshot).

**Full pattern to mirror** (ingester/order_book.py lines 48–90, reproduced above in §QueueTracker). Note:
- Raises a named exception (`AMMConservationError`), not a plain `ValueError`.
- Propagates to process exit (`"MUST NOT be caught and skipped"` — docstring line 55).
- Includes offending rows in the error message (tested in `tests/test_amm_conservation.py::test_amm_conservation_error_message_includes_offending_rows`).

**Deltas:**
- Create `class AMMConsumptionIdentityError(RuntimeError)` parallel to `AMMConservationError` — distinct name because it's a different invariant (runtime per-epoch identity, not ingest-time snapshot monotonicity).
- Public functions per RESEARCH §Protocol 2: `compute_amm_share_timeseries`, `assert_epoch_conservation`.
- `amm_share` non-negativity (T-02-A-01) — property-level assertion at every `(δ, t)`: `amm_share = max(combined − raw, 0.0)` should never be negative **by definition**; raising is the correct response to a negative.
- Log `fill_model.amm_conservation_violation` (structlog error level per RESEARCH §8) before raising — gives the operator a grep-able event tied to `run_id`.

**Gotchas:**
- Two separate AMM invariants now exist in the codebase: (a) Phase 1 ingest-time `assert_amm_conservation` (per-snapshot `combined ≥ raw`) and (b) Phase 2 runtime `assert_epoch_conservation` (per-epoch flow identity). Docs/wiki + architecture.yml edges MUST distinguish — use different node IDs and different exception class names.
- Phase 1's `brain.data.ingester.exceptions.AMMConservationError` is NOT reused — Phase 2 defines its own in `brain.fill_model.amm_consumption` (or re-exported from `schemas.py`). Reusing would lie in the architecture graph.
- Declare `brain.fill_model.amm_consumption calls brain.data.ingester.exceptions` edge in architecture.yml only if you actually import from there; RESEARCH §Protocol 2 says this edge exists, but cleaner to keep them separate.

---

### `python/src/boros_brain/fill_model/fit.py` — statsmodels.GLM Poisson log-linear fit

**Role:** Fit `log λ = β₀ + β·x` via `statsmodels.GLM(Poisson, log, exposure)` per `(market_id, side)`; return a `FitArtifact` Pydantic object.

**Data flow:** reads `parquet.fill_features` (output of `features.py`); calls `state.writers.fill_model_fits.insert_fit_artifact` to persist.

**Analog (best-match):** `python/src/boros_brain/screener/scale_calibration.py` (batch numerical computation with `polars` + returns a typed result object).

**Imports + log pattern (shared across screener+fit numerics):**
```python
from __future__ import annotations

import polars as pl
import structlog

log = structlog.get_logger(__name__)
```

**Full fit recipe** — verbatim from RESEARCH §Code Examples #2 (lines 484–540 of 02-RESEARCH.md). The planner should copy that code example into `fit.py` as the canonical implementation; the structural analog for how it integrates with the rest of the system is `screener/scale_calibration.py`.

**Result-object → artifact-writer call pattern** (inferred from screener/filter.py + state/writers/clo_history.py):
```python
# scale_calibration / filter return @dataclass results; Phase 2 returns a Pydantic FitArtifact.
# Writer module is single-writer-per-table (see CLAUDE.md):
from ..state.writers.fill_model_fits import insert_fit_artifact
...
artifact = FitArtifact(run_id=run_id, ..., fit_status="ok")
insert_fit_artifact(sqlite_path=sqlite_path, artifact=artifact)
```

**Deltas:**
- New dependency: `statsmodels>=0.14.6` (RESEARCH §Wave 0 Gaps — add to `python/pyproject.toml`).
- `statsmodels.GLM(endog=counts, exog=sm.add_constant(features), family=sm.families.Poisson(link=sm.families.links.Log()), exposure=bin_duration_s).fit(method="IRLS", maxiter=100)` — exact call signature.
- **Fit-health gate** (per RESEARCH §Pitfall 3): if `not results.converged` OR `n_observations / n_params < min_events_per_param_ratio` OR any `|β| / bse > 10× bse`, mark `fit_status="degraded"`. Fall back to intercept-only GLM rather than refusing (Phase 4 decision engine has its own breakers).
- Public functions per RESEARCH §Protocol 2: `fit_market_side`, `FitArtifact` — noting that `FitArtifact` is a Pydantic class in `schemas.py`, so architecture.yml declares `public_functions: [fit_market_side]` with the class in a comment.

**Gotchas:**
- **`statsmodels` isn't in `pyproject.toml` yet** — Plan 02-01 must add it before Plan 02-03 (fit) can even import. Same wave-ordering for `tick==0.8.0.1` (simulator, not critical path). RESEARCH §Wave 0 Gaps calls this out.
- `add_constant` prepends the β₀ column — the `FitArtifact.beta` list therefore has length `1 + n_features`. Tests that assert `len(beta) == 1 + len(covariate_whitelist)` catch accidental drops of the intercept.
- Left-closed EWMA is enforced by the SQL in `features.py`, NOT here. `fit.py` consumes the feature table as-is; if tests find look-ahead, fix the SQL, not the fit.
- `FitArtifact` is IMMUTABLE (frozen Pydantic). Once constructed, you cannot patch `fit_status` — if degrading, construct a new artifact.

---

### `python/src/boros_brain/fill_model/predict.py` — sync predict contract

**Role:** The Phase-4-locked sync entry point. Takes a `PredictInput`, returns a `PredictOutput`, or raises `FillModelStaleFeatureError` / `FillModelNoFreshFitError`. Called by DecisionEngine at 1 Hz per in-flight order.

**Data flow:** reads `state.fill_model_fits` (via a thin DuckDB read or direct SQLite `SELECT ... ORDER BY fit_window_end_ts DESC LIMIT 1`); calls `brain.data.chain_time.now_cached()` for `fit_age_s`.

**Analog:** `python/src/boros_brain/data/chain_time.py` (sync `now_cached()` + named exception raises + strict validation contract) + `python/src/boros_brain/screener/filter.py` (result-object output).

**Sync entry-point + named-exception contract** (chain_time.py lines 1–74):
```python
"""INFRA-14 — Chain-time cache + drift monitor.

Every chain-relevant time comparison in brain/{decision,data,screener}/ MUST use
``now_cached()`` instead of ``time.time()``.  The ``no_time_time_lint.py``
pre-commit hook (and ``test_no_time_time_in_hotpath.py``) enforce this ban at
commit time — any ``time.time()`` call outside this file in those directories
causes the hook to fail with a line reference.
...
Startup invariant
-----------------
``ChainTimeCache.startup_check()`` (called by ``main.py`` at boot):
  - Fetches the latest block timestamp directly.
  - Raises ``ChainTimeDriftHalt`` if |wall_time - chain_time| > chain_drift_warn_s.
    ...
"""
...
class ChainTimeDriftHalt(RuntimeError):
    """Raised by ``startup_check()`` when initial drift exceeds the warn threshold.
    ...
    """
```

**Deltas:**
- Full signature given in RESEARCH §Code Examples #3 (lines 548–591 of 02-RESEARCH.md) — paste as canonical.
- Public functions per RESEARCH §Protocol 2: `predict`, `PredictInput`, `PredictOutput` (the Pydantic classes are declared in `schemas.py` and re-exported from `predict.py`; architecture.yml declares `public_functions: [predict]` with a note).
- **NaN-covariate rule** (PITFALLS §6, RESEARCH §Anti-Patterns) — any NaN in `req.current_features` raises `FillModelStaleFeatureError(missing_features=[...])` BEFORE multiplying by β. Log `fill_model.predict_nan_covariate` at warn level first.
- **Staleness rule** — `fit_age_s = now_cached() - fit_window_end_ts`; if `> fit_max_staleness_s` raise `FillModelNoFreshFitError`; if `> fit_warn_staleness_s` set `fit_status="stale"` and log warn.
- **Monotonicity contract** — test-only invariant (T-02-P-03, T-02-P-04) enforced by hypothesis property tests, not runtime assertion.

**Gotchas:**
- **`predict()` MUST be sync**, not `async`. RESEARCH §Decision-Engine Interface row "Sync / async: Sync": making it async adds event-loop overhead without benefit for the <10ms p95 budget. Plan 02-03 must name the function `def predict(...)` not `async def predict(...)`.
- `now_cached()` is `async` in Phase 1 — see `data/poller/markets_poller.py` line 123: `snapshot_ts = await now_cached()`. That collides with sync `predict()`. The correct fix: for the `fit_age_s` computation in `predict()`, read the cache value **synchronously** via a new `chain_time.now_cached_sync()` helper (returns the last-cached value without awaiting a refresh) OR pass `current_chain_ts: int` into `PredictInput` and let Phase 4's DecisionEngine pass the cached value in. RESEARCH §Decision-Engine Interface implies the latter is acceptable ("fit_age_s in the return payload is diagnostic only"). Recommend: add `current_chain_ts: int` to `PredictInput` — keeps `predict()` pure-sync with no hidden IO.
- The `no_time_time_lint.py` hook currently bans `time.time()` in `brain/{decision,data,screener}/`. RESEARCH §Protocol 2 lint extension: extend to include `brain/fill_model/` so the same ban applies. One-line patch in `scripts/no_time_time_lint.py` (pattern: see its `_BANNED_DIRS` tuple or equivalent).
- Phase 2 `predict.py` MUST NOT import from Phase 4's DecisionEngine (no circular dep; Phase 4 doesn't exist yet).

---

### `python/src/boros_brain/fill_model/artifact.py` — FitArtifact SQLite + parquet sidecar writer

**Role:** Orchestrate atomic dual-write: (a) `INSERT INTO fill_model_fits` row, (b) sidecar parquet with full covariate-coefficient-with-CI dump. Single public wrapper around `state/writers/fill_model_fits.py`.

**Data flow:** writes `state.fill_model_fits` (SQLite) + writes `data/parquet/fill_model_artifacts/market_id=.../side=.../window_end_ts=.../artifact.parquet`.

**Analog (exact):** `python/src/boros_brain/manifest/writer.py::write_manifest` — atomic sidecar-JSON + SQLite-row writer.

**Atomic dual-write pattern** (manifest/writer.py lines 86–126):
```python
def write_manifest(
    manifest: RunManifest,
    *,
    logs_dir: Path | str,
    sqlite_path: Path | str,
) -> Path:
    """Emit sidecar JSON AND insert into the `run_manifests` SQLite table.
    ...
    """
    logs_dir = Path(logs_dir)
    sqlite_path = Path(sqlite_path)

    date_dir = logs_dir / datetime.now(UTC).strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    sidecar_path = date_dir / f"{manifest.run_id}.manifest.json"
    sidecar_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2))

    with open_connection(sqlite_path) as conn:
        insert_run_manifest(conn, run_id=manifest.run_id, ...)
        conn.commit()

    return sidecar_path
```

**Deltas:**
- Sidecar format is **parquet** (not JSON) — use `polars.DataFrame(...).write_parquet(sidecar_path)`.
- Ordering: write parquet first, SQLite row second (same as manifest writer's JSON-first ordering). If SQLite insert fails, the parquet is orphaned but readable; if we did it the other way, a crashed write leaves an unparsable SQLite row pointing at nothing.
- Delegate the SQL to `state/writers/fill_model_fits.insert_fit_artifact` (single-writer discipline — see next section).

**Gotchas:**
- `artifact.py` MUST NOT execute raw `INSERT INTO fill_model_fits` — that would violate the single-writer-per-table lint (`scripts/sqlite_writer_lint.py`). Delegate to the writer module.
- The "atomic" contract is best-effort (SQLite WAL autocommit + parquet fsync). A crash between the two writes will leave one of them inconsistent. For v0.5 this is acceptable — the `refit_loop` will regenerate on next cycle (per RESEARCH §Pitfall 7: bot-restart safe because `predict` loads the most-recent-by-window-end row).

---

### `python/src/boros_brain/fill_model/refit_loop.py` — 15-min cadence asyncio task

**Role:** Long-running `asyncio.create_task` loop that calls `fit_market_side` every `config.fill_model.refit_cadence_s` seconds (default 900s). Spawned once from `main.py` alongside the existing `send_task`/`monitor_task`/`ingest_task`.

**Data flow:** event-driven cadence; calls `features.py::build_features_table`, `fit.py::fit_market_side`, `artifact.py::write_fit_artifact` in sequence.

**Analog (exact):** `python/src/boros_brain/data/poller/markets_poller.py::run_markets_poller` (long-running async cadence loop) + `data/poller/e_liq_poller.py` (async loop with failure-count logic).

**Long-running async task pattern** (markets_poller.py lines 195–208):
```python
async def run_markets_poller(config: BotConfig, run_id: str) -> None:
    """Long-running asyncio task — call from brain main.py.

    Loops forever at config.data.markets_poll_interval_s cadence.
    Exceptions from tick() are caught and logged; the loop continues.
    """
    async with make_boros_rest_client(config) as http:
        poller = MarketsPoller(config, http, run_id)
        while True:
            try:
                await poller.tick()
            except Exception as exc:
                log.exception("markets_poller.tick_failed", run_id=run_id, err=str(exc))
            await asyncio.sleep(config.data.markets_poll_interval_s)
```

**Deltas:**
- Name: `run_fill_model_refit_loop(config: BotConfig, run_id: str) -> None`.
- Loop body: one refit across all `(market_id, side)` combinations in `config.markets` (v0.5 caps at 1 market × 2 sides = 2 fits per refit).
- **Initial fit at startup is synchronous** (per RESEARCH §Fit cadence line 639): "Initial fit at bot startup (synchronous; boot blocks until fit completes — ~30s)." Implement as a `refit_once(config, run_id)` free function called from `main.py` **before** spawning the async loop; the loop then starts its `asyncio.sleep(refit_cadence_s)` cycle.
- Per-loop failure handling: `log.exception("fill_model.refit_failed", run_id=run_id, err=str(exc))` then continue; DO NOT crash the brain (mirrors markets_poller's `except Exception` block line 205–207).
- Public functions per RESEARCH §Protocol 2: `run_fill_model_refit_loop`, `refit_once`.

**Gotchas:**
- The refit loop is the **only writer** of `state.fill_model_fits`. If another module (e.g. `cli.py --force-refit`) also writes, the single-writer lint (`scripts/sqlite_writer_lint.py`) will fire — CLI must delegate to `refit_loop.refit_once` OR the writer itself (`state/writers/fill_model_fits.insert_fit_artifact`), never write directly.
- `main.py` must spawn this with `asyncio.create_task(...)` NOT `await` — blocking in main would halt the brain. The existing pattern at main.py lines 126–135 (`send_task = asyncio.create_task(heartbeat.send_loop())`) is the exact shape to mirror.
- Cancel on shutdown: add `task.cancel()` + `with contextlib.suppress(asyncio.CancelledError): await task` to the brain shutdown block (main.py lines 139–142). Forgetting this produces "Task was destroyed but it is pending!" warnings.

---

### `python/src/boros_brain/fill_model/calibration.py` — Rosenblatt-KS GoF + bootstrap threshold + hold-out calibration plot

**Role:** Compute goodness-of-fit statistics (Rosenblatt time-change + KS against Exp(1)); bootstrap a per-fit threshold; produce the calibration-plot dataset (predicted vs realized decile).

**Data flow:** reads `parquet.market_trades`, `state.fill_model_fits` (via DuckDB); writes `parquet.fill_predictions` (backtest only).

**Analog:** `python/src/boros_brain/screener/scale_calibration.py` (per-market statistics computation, NO existing Rosenblatt/KS pattern exists — use `screener/metrics.py` stylistic conventions for the imports/log shape; the stats math is canonical from RESEARCH §Code Examples #4).

**Canonical code** from RESEARCH §Code Examples #4 (lines 593–613 of 02-RESEARCH.md):
```python
from scipy import stats
import numpy as np

def gof_rosenblatt(
    event_times_s: np.ndarray,
    lambda_fn,
) -> dict[str, float]:
    """Null hypothesis: λ is the true intensity. Rejected ⟹ fit is bad."""
    compensator = np.array([_integrate_lambda(lambda_fn, event_times_s[0], t) for t in event_times_s])
    gaps = np.diff(compensator)
    ks_stat, ks_pval = stats.kstest(gaps, "expon", args=(0, 1))
    return {"ks_stat": float(ks_stat), "ks_pval": float(ks_pval), "n_gaps": len(gaps)}
```

**Deltas:**
- Three functions per RESEARCH §Protocol 2 architecture.yml declaration: `gof_rosenblatt`, `bootstrap_gof_threshold`, `run_calibration`.
- `bootstrap_gof_threshold`: fit on 14 days, compute GoF on 100 bootstrap resamples, return 5th percentile of LR as threshold. Populate `fill_model.gof_lr_ratio_threshold` knob on first-fit completion (write a migration log event, not a config mutation — the knob default is `None` until the bootstrap publishes).
- `run_calibration`: deciles of `predicted p_fill` vs realized fill frequency on hold-out (last 20% of fit window per RESEARCH §Nyquist).
- New dependency: `scipy` already pinned in the CLAUDE.md stack list (not yet in `pyproject.toml` — Plan 02-04 adds).

**Gotchas:**
- **No existing statistics/GoF analog in the codebase.** `screener/scale_calibration.py` is the nearest neighbour but does a different computation (SCALE parameter calibration via two (clo, fIndex) snapshots). The planner should treat `calibration.py` as a greenfield module with Phase 1 style (structlog, type hints, frozen Pydantic result if applicable) but new math.
- `bootstrap_gof_threshold` is the **only** knob-calibration pathway for `gof_ks_pval_threshold` / `gof_lr_ratio_threshold`. Intuition-set thresholds are a PITFALL (RESEARCH §Common Pitfalls #8). Defend the bootstrap path in code review — never let a human-picked threshold into the config YAML.
- Calibration plot is a **manifest artifact** (per 02-VALIDATION.md line 91) — `python/docs/fill_model/calibration-<date>.png`. Use `matplotlib` (not yet in `pyproject.toml`) only when `run_calibration(..., emit_plot=True)` — keep matplotlib an optional import guarded by `try: import matplotlib.pyplot as plt; except ImportError: ...` so it doesn't block the headless refit_loop.

---

### `python/src/boros_brain/fill_model/report.py` — periodic calibration report rollup + plot generator

**Role:** Aggregate calibration output across runs/markets into a single operator-facing JSON + Markdown + optional PNG; surface `fit_status=degraded` in the rollup.

**Analog:** `python/src/boros_brain/screener/report.py::write_screener_metrics_report` + `screener/kill_report.py`.

**Full pattern** (screener/report.py lines 18–46):
```python
def write_screener_metrics_report(
    results: list[MarketScreeningResult],
    out: str | Path,
) -> None:
    ...
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    shortlist = sorted(
        [r for r in results if r.filter_pass],
        key=lambda r: r.r_apr_potential or 0.0,
        reverse=True,
    )[:_SHORTLIST_MAX]

    payload = {
        "results": [asdict(r) for r in results],
        "shortlist": [r.market_id for r in shortlist],
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
```

**Deltas:**
- Read from `state.fill_model_fits` for the rollup (not the in-memory result list — rollup runs across multiple fit cycles).
- Output shape: `var/reports/fill_model_report.json` + human-facing `python/docs/fill_model/calibration-<date>.md` (per 02-VALIDATION.md §Manual-Only Verifications).
- Surface `fit_status == "degraded"` rows at the top with the reason.

---

### `python/src/boros_brain/fill_model/cli.py` — `python -m boros_brain.fill_model` entrypoint

**Role:** CLI dispatcher: `fit` / `predict` / `backtest` / `report` / `force-degrade` subcommands. Emits `RUN_MANIFEST` FIRST via `manifest/writer.py` (PROTO-01).

**Analog (exact):** `python/src/boros_brain/screener/cli.py`.

**MANIFEST-FIRST CLI boot pattern** (screener/cli.py lines 49–122):
```python
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.screener",
        description="...",
    )
    p.add_argument("--run", action="store_true", ...)
    p.add_argument("--config", default="strategy/v0.5-default.yaml", ...)
    args = p.parse_args(argv)
    ...
    from ..config.loader import load_config
    from ..logging.structlog_setup import configure_logging
    from ..manifest.writer import build_run_manifest, write_manifest

    config = load_config(args.config)

    # PROTO-01: RUN_MANIFEST emitted FIRST -- build manifest before configure_logging
    # so we have a run_id to pass as the log-file stem.
    manifest = build_run_manifest(config)
    configure_logging(
        run_id=manifest.run_id,
        tier="screener",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(manifest, logs_dir=config.infra.logs_dir, sqlite_path=config.infra.sqlite_path)
```

**Deltas:**
- Tier name in `configure_logging`: `"fill_model"` (not `"brain"` — CLI tier is separate so logs go to `logs/YYYY-MM-DD/<run_id>.fill_model.log.jsonl`).
- Subcommands: `fit --market <id> --side <long|short>`, `predict --market --side --depth`, `calibration-report`, `force-degrade` (per 02-VALIDATION.md manual-only check: `uv run python -m boros_brain.fill_model.refit --force-degrade`).
- Exit code 2 on `ConfigError`, 1 on `FillModelNoFreshFitError`, 0 on success (mirrors `screener/cli.py` lines 131–140).

**Gotchas:**
- Adding a `__main__.py` file alongside `cli.py` enables `python -m boros_brain.fill_model` (mirrors `screener/__main__.py`). Don't forget — architecture.yml declares `brain.fill_model.cli` but the CLI runs via `__main__.py`. Add the file or use `python -m boros_brain.fill_model.cli` invocation instead.

---

### `python/src/boros_brain/state/writers/fill_model_fits.py` — single-table writer

**Role:** The ONLY module that writes to `state.fill_model_fits`. Two public functions: `insert_fit_artifact(sqlite_path, artifact)` (self-contained) and `get_latest_fit(sqlite_path, market_id, side)` (read, returns `FitArtifact | None`).

**Analog (exact):** `python/src/boros_brain/state/writers/clo_history.py`.

**Full writer pattern** (state/writers/clo_history.py lines 1–92 — all of it):
```python
"""Single writer for the `clo_history` table (brain-owned).

PROTO-02 single-writer discipline. Only markets_poller imports this module;
other readers go through DuckDB.
...
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

from boros_brain.state.db import open_connection

log = structlog.get_logger(__name__)


def insert_clo_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_ts: int,
    market_id: str,
    ...
) -> None:
    """Insert one CLO + fIndex snapshot (low-level — caller owns the connection)."""
    conn.execute(
        "INSERT INTO clo_history ..."
    )


def insert_clo_history(
    sqlite_path: Path | str,
    *,
    market_id: str,
    ...
) -> None:
    """Append one row to clo_history. Self-contained — manages its own connection.
    ...
    """
    with open_connection(sqlite_path) as conn:
        conn.execute("INSERT INTO clo_history ...", (...))
    log.info("clo_history.appended", market_id=market_id, ...)
```

**Deltas:**
- Two functions: `insert_fit_artifact(sqlite_path, artifact: FitArtifact)` and `get_latest_fit(sqlite_path, market_id: str, side: str) -> FitArtifact | None`.
- `covariate_whitelist`, `beta`, `beta_stderr` are `list` columns — store as JSON strings (`json.dumps(artifact.beta)`) in TEXT columns. Matches `run_manifests.config_json` pattern (schemas.sql line 96).
- Primary key: `(market_id, side, fit_window_end_ts)` per RESEARCH §Phase 2 writes table.

**Gotchas:**
- **Single-writer lint.** `scripts/sqlite_writer_lint.py` (not re-read in this pass but referenced in CLAUDE.md Engineering Protocol 2) will fire if `INSERT INTO fill_model_fits` appears in any module other than this one. `refit_loop.py`, `artifact.py`, and `cli.py` must all route through `insert_fit_artifact` — no exceptions.
- Writer registry in `state/schemas.sql` top-of-file ownership comment — add new line: `--   brain (Python state/writers/<table>.py): decisions, queue_positions, run_manifests, epoch_rewards, clo_history, reward_budget_history, fill_model_fits` (append `fill_model_fits`).
- `get_latest_fit` is a READ. The single-writer lint only cares about writes. But per CLAUDE.md, non-writers should go through `duckdb_layer` for reads — for Phase 2, the hot-path `predict()` reads the latest fit 1 Hz, so direct SQLite read (with attach-read-only semantics) is faster and acceptable. Document the deviation inline: "predict() reads SQLite directly to avoid DuckDB attach overhead on the 1 Hz hot path".

---

### `python/src/boros_brain/state/schemas.sql` + Alembic migration — new `fill_model_fits` table

**Role:** Canonical DDL for `fill_model_fits` (appended to `schemas.sql`) + Alembic migration replaying it.

**Analog (exact):** existing `clo_history` / `run_manifests` blocks inside the same file.

**Pattern** (state/schemas.sql lines 113–126, `clo_history`):
```sql
-- ---------------------------------------------------------------------------
-- clo_history  (brain-owned) — DATA-06 /markets poll + fIndex for SCALE calib
-- ---------------------------------------------------------------------------
-- f_index_raw: decoded floatingIndex_raw from the fIndexOracle bytes26 payload,
-- polled at the same cadence as CLO by the /markets poller in plan 01-09. ...
CREATE TABLE IF NOT EXISTS clo_history (
    snapshot_ts       INTEGER NOT NULL,
    market_id         TEXT NOT NULL,
    clo_lower_thresh  REAL NOT NULL,
    clo_upper_thresh  REAL NOT NULL,
    f_index_raw       INTEGER,
    PRIMARY KEY(snapshot_ts, market_id)
);
```

**Deltas:**
- Add `fill_model_fits` block with columns per RESEARCH §Phase 2 writes table: `run_id TEXT NOT NULL`, `fit_window_start_ts INTEGER NOT NULL`, `fit_window_end_ts INTEGER NOT NULL`, `market_id TEXT NOT NULL`, `side TEXT NOT NULL CHECK(side IN ('long','short'))`, `covariate_whitelist TEXT NOT NULL` (JSON), `beta TEXT NOT NULL` (JSON), `beta_stderr TEXT NOT NULL` (JSON), `log_likelihood REAL NOT NULL`, `deviance REAL NOT NULL`, `aic REAL NOT NULL`, `n_observations INTEGER NOT NULL`, `converged INTEGER NOT NULL CHECK(converged IN (0,1))`, `fit_status TEXT NOT NULL CHECK(fit_status IN ('ok','degraded','stale'))`, `gof_ks_pval REAL`, `gof_lr_vs_null REAL`, `created_at INTEGER NOT NULL`, `PRIMARY KEY(market_id, side, fit_window_end_ts)`.
- Add index `CREATE INDEX IF NOT EXISTS ix_fill_model_fits_market_side_end ON fill_model_fits(market_id, side, fit_window_end_ts DESC);` — supports the `get_latest_fit` query's `ORDER BY ... DESC LIMIT 1`.
- Alembic migration under `python/src/boros_brain/state/migrations/versions/XXXX_fill_model_fits.py` — rev_id auto-generated via `alembic revision -m "add_fill_model_fits"`.
- Update the top-of-file ownership comment to include `fill_model_fits` under brain ownership.

**Gotchas:**
- **`PRAGMA foreign_keys = ON` is required** for any FK references (schemas.sql line 16). If you reference `run_id` as a FK to `run_manifests(run_id)`, ensure the Alembic env.py and the `open_connection` helper both set the pragma. `run_id` as FK is **nice-to-have**, not required — the existing tables (clo_history, etc.) don't FK on `run_id` either; keep `fill_model_fits.run_id` a plain `TEXT NOT NULL` for now to minimize cross-table invariants.
- The DDL goes into `schemas.sql` (the SSoT per top-of-file comment lines 3–5) AND a new Alembic migration — both in the same commit. The migration is the replay; the SSoT is the canonical. Drift between them breaks `test_sqlite_migrations.py`.

---

### `python/src/boros_brain/config/schema.py` — modify to add `fill_model: FillModelConfig` field

**Role:** One-line modification to attach `FillModelConfig` into `BotConfig`.

**Analog (exact):** self, line 133: `screener: ScreenerConfig = Field(default_factory=ScreenerConfig)  # type: ignore`.

**Exact delta:**
```python
# In python/src/boros_brain/config/schema.py, add import + field:
from .fill_model_config import FillModelConfig   # or wherever config.py lives

class BotConfig(StrictBase):
    ...
    screener: ScreenerConfig = Field(default_factory=ScreenerConfig)  # type: ignore
    fill_model: FillModelConfig = Field(default_factory=FillModelConfig)  # type: ignore   # NEW
    markets: list[MarketCalibration] = Field(default_factory=list, max_length=1)
```

**Gotchas:**
- Circular-import risk: `fill_model/config.py` might try to import from `boros_brain.config.schema` (e.g., for `StrictBase`). Solution: **do not re-use `StrictBase` by import**; redeclare an identical `StrictBase` inside `fill_model/config.py` (it's 9 lines — see manifest/schema.py which does exactly this, lines 20–23). Matches the existing pattern in the manifest module.
- YAML strategy files (`strategy/v0.5-default.yaml`) get a new top-level `fill_model:` block. Adding the field with `default_factory=FillModelConfig` means YAMLs **without** the block still validate (defaults fill in). No YAML migration strictly required for v0.5 — but the operator-facing `strategy/v0.5-default.yaml` should get an explicit `fill_model:` block for documentation.

---

### `python/src/boros_brain/main.py` — modify to spawn refit_loop

**Role:** Wire the synchronous initial fit + async refit loop into brain boot, mirroring the existing heartbeat task pattern.

**Analog (exact):** self, `main.py` lines 126–142 (the `send_task`/`monitor_task`/`ingest_task` block).

**Exact pattern to mirror** (main.py lines 126–142):
```python
# Spawn heartbeat send + monitor + peer-ingest as background tasks.
send_task = asyncio.create_task(heartbeat.send_loop())
monitor_task = asyncio.create_task(heartbeat.monitor_loop())

async def _peer_heartbeat_ingest() -> None:
    while not stop.is_set():
        ...

ingest_task = asyncio.create_task(_peer_heartbeat_ingest())

await stop.wait()
heartbeat.stop()
for t in (send_task, monitor_task, ingest_task):
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
```

**Deltas:**
- Before `asyncio.create_task(...)` lines, insert a synchronous initial fit:
  ```python
  # Phase 2: initial fit synchronous (blocks boot ~30s; required so predict()
  # has an artifact before the 1 Hz decision loop starts).
  from .fill_model.refit_loop import refit_once, run_fill_model_refit_loop
  await refit_once(cfg, manifest.run_id)
  ```
- Spawn the refit task:
  ```python
  refit_task = asyncio.create_task(run_fill_model_refit_loop(cfg, manifest.run_id))
  ```
- Add `refit_task` to the shutdown cancel loop: `for t in (send_task, monitor_task, ingest_task, refit_task): t.cancel(); ...`.

**Gotchas:**
- `refit_once` in the boot path BLOCKS `run()` for ~30s (per RESEARCH §Fit cadence). Acceptable for paper/live mode; make it optional / skipped in `--dry-run` (line 109 `if dry_run:` branch short-circuits before reaching refit). Confirm the `dry_run` branch exits BEFORE the new `refit_once` call — otherwise `test_tracer_bullet.py` (dry-run smoke) will take 30s instead of <1s.
- Architecture-graph update: add edge `brain.main calls brain.fill_model.refit_loop` (both `refit_once` and `run_fill_model_refit_loop` are `public_functions`).

---

### Test files — analog pattern for each

All Phase 2 tests follow the existing `python/tests/test_*.py` conventions: imports of the target module, shared `FIXTURES = Path(__file__).parent / "fixtures"` constant, pytest functions named `test_<target>_<behavior>`, hypothesis used for property tests (T-02-Q-01, T-02-A-01, T-02-P-03, T-02-P-04), `wave0_scaffold` marker for TDD red-phase stubs.

#### `python/tests/test_fill_model_features.py`

**Analog (exact):** `python/tests/test_screener_metrics.py`.

**Pattern** (test_screener_metrics.py lines 1–48):
```python
"""Tests for DATA-08 screener metrics (plan 01-11, Task 1).

TDD RED phase: all tests import from boros_brain.screener.metrics,
which does not yet exist — these must FAIL before implementation.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import structlog.testing

from boros_brain.screener.metrics import (
    compute_days_to_maturity,
    ...
)

FIXTURES = Path(__file__).parent / "fixtures"
MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _load_trades() -> pl.DataFrame:
    rows = [
        json.loads(line)
        for line in (FIXTURES / "screener_sample_trades.ndjson").read_text().splitlines()
        if line.strip()
    ]
    return pl.DataFrame(rows)
```

**Deltas:** import from `boros_brain.fill_model.features`; load `fill_model_tiny_tape.ndjson` / `fill_model_synthetic_poisson.parquet` fixtures. Include explicit `test_ewma_no_lookahead` (T-02-F-02) and `test_covariate_whitelist` (T-02-F-01).

#### `python/tests/test_fill_model_amm_consumption.py`

**Analog (exact):** `python/tests/test_amm_conservation.py` — SAME invariant-check test style (positive + negative cases + error message includes offending rows).

**Deltas:** swap `AMMConservationError` → `AMMConsumptionIdentityError`; swap ingest-time fixtures for synthetic per-epoch fixtures; include `test_amm_share_non_negative` (property via hypothesis — T-02-A-01) and `test_epoch_conservation` (T-02-A-02).

#### `python/tests/test_fill_model_queue_tracker.py`

**Analog:** `test_amm_conservation.py` + `test_findex_reader.py` (tape-replay style).

**Tests required** (from 02-VALIDATION.md): `test_bracket_invariant` (property), `test_replay_on_fixture`, `test_drift_bias_detected`, `test_bracket_width_warn`.

#### `python/tests/test_fill_model_fit_basic.py`

**Analog:** `python/tests/test_screener_scale_calibration.py` (numerical convergence tests with synthetic data).

**Tests required:** `test_fit_converges_on_synthetic_poisson` (T-02-M-01), `test_fit_degrades_on_sparse` (T-02-M-02), `test_covariate_whitelist` (T-02-F-01).

#### `python/tests/test_fill_model_predict_contract.py`

**Analog:** `test_manifest_contains_all_knobs.py` (contract-enforcement style) + hypothesis for monotonicity (T-02-P-03/04).

**Tests required:** `test_predict_in_unit_interval` (T-02-P-01), `test_predict_raises_on_nan` (T-02-P-02), `test_predict_monotone_in_depth` (T-02-P-03 — hypothesis), `test_predict_monotone_in_queue` (T-02-P-04 — hypothesis).

#### `python/tests/test_fill_model_calibration_gof.py`

**Analog:** `python/tests/test_daily_rescreen.py` (end-to-end integration style — writes + reads artifacts + subprocess invocation).

**Tests required:** `test_calibration_on_holdout` (T-02-C-01), `test_refit_loop_writes_artifact` (T-02-C-02), `test_degraded_warning_on_regime_shift` (T-02-C-03 — uses `fill_model_regime_shift.parquet`).

#### `python/tests/test_architecture_lint.py`

**Analog:** NO existing subprocess-wrapper test for `architecture_lint.py` (the hook runs in pre-commit but has no pytest wrapper). Stylistic analog: `python/tests/test_cli.py` (subprocess invocation of a Python module + exit-code assertion).

**Pattern to write from (inferred):**
```python
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

def test_architecture_lint_clean() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/architecture_lint.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"drift:\n{result.stderr}"
```

#### `python/tests/test_manifest_contains_all_knobs.py` — modify check

**No actual code change required.** The existing test at line 90–99 walks every `BotConfig` leaf via reflection; adding `fill_model: FillModelConfig` to `BotConfig` causes all 11 new leaves to auto-register as expected leaves. Run the test post-Plan-02-01 to confirm green.

---

### Fixture files

**`python/tests/fixtures/fill_model_tiny_tape.ndjson`** — 100-trade synthetic tape for queue replay.

**Analog:** `python/tests/fixtures/sample_market_trades.ndjson`.

**Exact shape** (sample_market_trades.ndjson line 1):
```json
{"eventIndex":363716829000015,"blockTimestamp":1754021093,"datetime":"2025-08-01T04:04:53.000Z","rate":0.07332,"side":"short","size":"5000000000000000","txHash":"0x2578aa"}
```

**Deltas:** 100 lines, hand-constructed so queue-ahead-at-each-tick is computable by hand (per T-02-Q-02 "matches hand-computed expectation on tiny tape fixture"). Include ties on `blockTimestamp` with distinct `eventIndex` values (to exercise ordering). Include one row with `eventIndex=null` for the degraded-mode path.

**`python/tests/fixtures/fill_model_synthetic_poisson.parquet`** — known-β Poisson realization for fit regression.

**Analog:** none (no existing .parquet fixtures in `tests/fixtures/`). Pattern: write a generator helper in `tests/fixtures/_generate_fill_model_fixtures.py` that uses `numpy.random` + `polars.DataFrame(...).write_parquet(...)` with a fixed seed. Commit both the generator and the output parquet. (Analogous to how `amm_conservation_valid_*.ndjson` were hand-authored — but parquet can't be hand-authored, so the generator IS the source of truth.)

**Deltas:**
- Schema: `market_id, side, bin_start, trade_count, basis_spread, imbalance, sin_settlement, cos_settlement, ewma_vol, bin_duration_s` (matches features.py output).
- `trade_count` drawn from `Poisson(exp(β₀ + β·x))` with hard-coded β so `test_fit_converges_on_synthetic_poisson` can assert `|β_hat - β_true| < 3·SE`.

**`python/tests/fixtures/fill_model_regime_shift.parquet`** — regime-change fixture for GoF degradation.

**Same generator pattern.** Two regimes stitched together: first 70% of bins use β₁, last 30% use β₂ with different slope. GoF KS on the whole window rejects the single-regime fit → `test_degraded_warning_on_regime_shift` passes.

**Gotchas:**
- Parquet fixtures are binary and slightly annoying in git diffs. The generator script is the real SSoT; the .parquet is an artifact. Include a `test_fixture_regenerate` gate that compares the live file to `_generate_fill_model_fixtures.py`'s output hash (optional but prevents silent parquet rot).

---

### `docs/architecture.yml` — add ~25 nodes + ~30 edges

**Role:** Machine-readable architecture manifest; the lint `scripts/architecture_lint.py` diffs this against the code tree and fails commits with drift.

**Analog (exact):** self, especially:
- Module block (lines 588–593): `brain.screener.metrics` — shows module / process / path / public_functions.
- Config knob block (lines 372–398): `config.screener.*` knobs — one node per leaf with `pydantic_path` + `default`.
- Storage block (lines 563–590): `parquet.market_trades` with Hive-partition note.
- Edges block (lines 677+): edges with `from`/`to`/`type`/`notes`.

**Exact node-block pattern** (architecture.yml lines 588–593):
```yaml
  - id: brain.screener.metrics
    type: module
    process: brain
    path: python/src/boros_brain/screener/metrics.py
    public_functions: [compute_inter_arrival_cv, compute_realized_vol, compute_reversal_count, compute_depth_at_clo_edge, compute_outside_range_wall_ratio, compute_days_to_maturity]
```

**Exact config-knob pattern** (architecture.yml lines 392–395):
```yaml
  - id: config.screener.alt_yield
    type: config_knob
    pydantic_path: BotConfig.screener.alt_yield
    default: 0.05
```

**Exact storage pattern** (architecture.yml lines 563–566):
```yaml
  - id: parquet.market_trades
    type: storage
    path: data/parquet/market_trades/**/*.parquet
    notes: "Hive-partitioned: market_id / year_month. Written by ingest_market_trades."
```

**Exact edge pattern** (architecture.yml lines 1260–1264, screener.metrics → parquet.market_trades):
```yaml
  - from: brain.screener.metrics
    to: parquet.market_trades
    type: reads
    notes: "compute_inter_arrival_cv / compute_realized_vol / compute_reversal_count read market_trades via DuckDB"
```

**Deltas:** full list in RESEARCH §Protocol 2 Architecture.yml deltas (lines 826–872 of 02-RESEARCH.md). Summary:
- ~12 new module nodes under `brain.fill_model.*` + `brain.state.writers.fill_model_fits`.
- 3 new storage nodes: `state.fill_model_fits`, `parquet.fill_features`, `parquet.fill_predictions`.
- 11 new config_knob nodes: `config.fill_model.window_days`, ..., `config.fill_model.min_events_per_param_ratio`.
- ~25+ edges covering every `reads`/`writes`/`calls`/`emits-event`/`depends-on-config` per RESEARCH §Protocol 2 bullet list.

**Gotchas:**
- `public_functions` must match EXACTLY what `architecture_lint.py::extract_python_inventory` finds — any top-level `def` (not starting with `_`, not in a test file). If you write a helper function and forget to declare it, lint fails. If you declare a function that doesn't exist, lint fails. (See `scripts/architecture_lint.py` lines 76–79.)
- Classes are NOT picked up (lint only checks `FunctionDef`/`AsyncFunctionDef`). Declare classes in a trailing `# ...` comment: `public_functions: [build_features_table]   # FeatureSet is a class`.
- Every node must point at a real path on disk (lint checks `Path(n["path"]).exists()`). The `parquet.*` nodes use glob patterns (e.g. `data/parquet/market_trades/**/*.parquet`); the lint check in lines 141–147 uses `Path(p).exists()` which returns False for a glob. Confirm by re-reading `architecture_lint.py::compare` — actually the check is `if p and not Path(p).exists()`, which fails for unresolved globs. The existing `parquet.market_trades` node passes today... because `data/parquet/market_trades/**/*.parquet` evaluates to `Path(...).exists() == False` → would be a violation. **Verify by running the lint today against the current tree**; if it passes, the glob is tolerated somehow (likely because parquet files DO exist under Phase 1 ingest). For new `parquet.fill_features` and `parquet.fill_predictions` nodes that won't exist until code runs, the lint might fire at commit time. Safe fallback: write a zero-byte `.gitkeep` into `data/parquet/fill_features/` so the directory exists, and/or follow the Phase 1 pattern where the directory gets created on first ingest.

---

### `docs/ARCHITECTURE.md` — Mermaid diagram update (human-facing)

**Role:** Visual topology diagram kept in lock-step with `architecture.yml`. Operator + reviewer read this first.

**Analog (exact):** self, `docs/ARCHITECTURE.md`. (Not re-read in this pass — 560+ lines — but the Mermaid block structure is the canonical pattern.)

**Pattern:** `mermaid` code fence with `graph TD` / `graph LR`, node shapes matching node types (rectangles for modules, cylinders for storage, parallelograms for external), arrow labels matching edge types.

**Deltas:**
- Add subgraph `subgraph fill_model` containing all 12 `brain.fill_model.*` modules.
- Add cylinders for `state.fill_model_fits`, `parquet.fill_features`, `parquet.fill_predictions`.
- Add arrows for every edge declared in `architecture.yml`.

**Gotchas:**
- Two diagrams, one yaml. Updating only `architecture.yml` would pass the lint but leave the human doc stale. CLAUDE.md Engineering Protocol 2: "update both the Mermaid diagram and `architecture.yml`... in the same commit."
- Mermaid rendering on GitHub caps at ~500 nodes before it truncates; Phase 2 adds ~15 nodes to a diagram that's already substantial. Consider a separate `subgraph` rendered standalone if the main diagram becomes unreadable.

---

### `scripts/no_time_time_lint.py` — one-line extension

**Role:** Pre-commit hook banning `time.time()` in `brain/{decision,data,screener}/`. Extend to include `brain/fill_model/`.

**Analog (exact):** self, current `_BANNED_DIRS` tuple (inferred from chain_time.py docstring lines 1–6).

**Deltas:** one-line tuple addition. Per RESEARCH §Protocol 2: "Lint extension: `scripts/no_time_time_lint.py` currently bans `time.time()` in `brain/{decision,data,screener}/`. Extend to add `brain/fill_model/` to the banned list in the same plan that lands the module tree (one-line patch)."

---

## Shared Patterns

### Structlog `run_id`-bound logging (apply to EVERY new module)

**Source:** `python/src/boros_brain/logging/structlog_setup.py` lines 84–91.

```python
# Reset contextvars so test isolation is clean, then bind the active run.
clear_contextvars()
bind_contextvars(run_id=run_id, tier=tier, pid=os.getpid())
```

**Every module imports and uses:**
```python
import structlog
log = structlog.get_logger(__name__)

# In code:
log.info(
    "fill_model.fit_completed",
    market_id=market_id,
    side=side,
    fit_window_end_ts=fit_window_end_ts,
    n_observations=n_observations,
    converged=converged,
    gof_ks_pval=gof_ks_pval,
    fit_status=fit_status,
)
```

**Apply to:** ALL new `fill_model/` modules. Log event keys must match RESEARCH §New log events table (fill_model.fit_completed, fill_model.fit_degraded, fill_model.predict_nan_covariate, fill_model.no_fresh_fit, fill_model.queue_drift_reconciliation, fill_model.bracket_width_warn, fill_model.amm_conservation_violation).

**Non-obvious:** `run_id` is auto-attached via `contextvars` — DO NOT pass `run_id=...` as a log kwarg (redundant + error-prone). It's bound once at brain boot / CLI boot and inherited by every `asyncio.create_task` (per structlog_setup.py module docstring lines 3–8).

---

### Pydantic StrictBase (extra=forbid + frozen) on every DTO

**Source:** `python/src/boros_brain/config/schema.py` lines 20–28; `python/src/boros_brain/manifest/schema.py` lines 20–23.

```python
class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Apply to:** `FillModelConfig`, `FitArtifact`, `PredictInput`, `PredictOutput` — every Phase 2 Pydantic model.

**Why load-bearing:** RUN_MANIFEST reflection in `manifest/writer.py::build_run_manifest` walks `BotConfig.model_dump(mode='json')`; `frozen=True` guarantees no knob mutates mid-run; `extra='forbid'` guarantees YAML typos fail loud. Violating this breaks PROTO-04 (RUN_MANIFEST invariant).

---

### Single-writer-per-table for SQLite

**Source:** `scripts/sqlite_writer_lint.py` (not re-read — documented in CLAUDE.md + schemas.sql top-of-file comment lines 7–11).

**Contract:** exactly one module writes to each SQLite table. The writer modules live in `python/src/boros_brain/state/writers/<table>.py`. All other code that needs to mutate the table imports and calls these functions.

**Apply to:** `state.fill_model_fits` writer is `state/writers/fill_model_fits.py` (new). `refit_loop.py`, `artifact.py`, and `cli.py` MUST all delegate to `insert_fit_artifact` — no inline `INSERT`.

**Non-obvious:** The lint regex in `scripts/sqlite_writer_lint.py` looks for `INSERT INTO <table>` / `UPDATE <table>` / `DELETE FROM <table>` outside the owning module. Writing `conn.execute("INSERT INTO fill_model_fits (...)")` anywhere except `state/writers/fill_model_fits.py` fails the lint.

---

### `eventIndex`-ordered replay (not blockTimestamp)

**Source:** `python/src/boros_brain/screener/metrics.py` lines 23–60 + CLAUDE.md Strategy non-negotiables bullet.

**Contract:** any code that replays `market_trades` MUST sort by `(blockTimestamp, eventIndex)` AND reject (or gracefully degrade on) rows where `eventIndex IS NULL`.

**Apply to:** `queue_tracker.py` (primary consumer), `amm_consumption.py` (secondary — reads epoch-boundary trades), `features.py` (the SQL in features.py already uses `ORDER BY bin_start`, but bin-building must respect intra-block eventIndex for tie-breaking).

**Non-obvious:** Phase 1's `screener/metrics.py` uses a pseudo-continuous time trick: `t_continuous = blockTimestamp + eventIndex * 1e-6`. Reuse this pattern in Phase 2 rather than reinventing — it preserves strict intra-block ordering without clamping sub-second intervals to zero.

---

### Manifest-first boot invariant (CLI + main.py)

**Source:** `python/src/boros_brain/main.py` lines 65–78 + `python/src/boros_brain/screener/cli.py` lines 108–122.

**Contract:** `RUN_MANIFEST` is emitted as the FIRST structured log record of any process/CLI invocation. Pattern: `build_run_manifest()` → `write_manifest()` (writes sidecar JSON + SQLite row) → `configure_logging(first_manifest_line=manifest.model_dump(mode='json'))` (emits manifest as log line 1).

**Apply to:** `fill_model/cli.py`. Phase 2's `refit_loop.py` inherits the main.py manifest (no new manifest per refit — unless a knob changes mid-run, which would require a mid-run `parent_run_id` chain per PROTO-03; not in Phase 2 scope).

---

### Chain-time via `now_cached()`, NEVER `time.time()`

**Source:** `python/src/boros_brain/data/chain_time.py` module docstring lines 1–11.

**Contract:** `time.time()` is banned in `brain/{decision,data,screener}/` by `scripts/no_time_time_lint.py` pre-commit hook. Phase 2 adds `brain/fill_model/` to the ban list.

**Apply to:** EVERY new `fill_model/` module that needs a wall-clock reference. Use `await now_cached()` (async) or pass `current_chain_ts: int` as a parameter (sync).

**Non-obvious:** `predict()` is sync but `now_cached()` is async. Resolution: pass the chain timestamp into `PredictInput.time_to_epoch_end_s` (already the case per RESEARCH §Code Examples #3) and compute `fit_age_s` as `(time_to_epoch_end_s_ref - fit_window_end_ts)` OR add a `current_chain_ts: int` field to `PredictInput`. The decision engine (Phase 4) has the async context and supplies it.

---

### Long-running async task pattern (spawn + cancel)

**Source:** `python/src/boros_brain/data/poller/markets_poller.py::run_markets_poller` lines 195–208 + `main.py` lines 126–142.

**Contract:** any long-running loop is an `async def run_<name>(config, run_id)` that `while True: try: await tick(); except Exception: log.exception(...); await asyncio.sleep(cadence)`. Spawned from `main.py` via `asyncio.create_task(...)`. Cancelled at shutdown with `t.cancel()` + `contextlib.suppress(asyncio.CancelledError)`.

**Apply to:** `refit_loop.py::run_fill_model_refit_loop`.

---

## No Analog Found

None. Every Phase 2 target has a direct or role-match analog in the Phase 1 scaffold. The two "weakest" matches are:

1. **`calibration.py` Rosenblatt/KS GoF math** — no pre-existing stats module uses `scipy.stats.kstest` or bootstrap-thresholding. The **stylistic** analog (structlog imports, type hints, polars usage) is `screener/metrics.py` + `screener/scale_calibration.py`; the **math** is canonical in RESEARCH §Code Examples #4. Planner should treat calibration.py as new math layered onto Phase 1 stylistic conventions.

2. **`.parquet` test fixtures** — no existing parquet fixtures in `python/tests/fixtures/`. Pattern: ship a generator Python helper as the SSoT, commit the generated `.parquet` as a binary artifact. Generator lives at `python/tests/fixtures/_generate_fill_model_fixtures.py`; fixed seed; deterministic.

Both are low-risk greenfield additions, not patterns-without-precedent.

---

## Metadata

**Analog search scope:** `python/src/boros_brain/` (all subpackages), `python/tests/`, `docs/architecture.yml`, `docs/ARCHITECTURE.md`, `scripts/`, `python/src/boros_brain/state/schemas.sql`, `python/pyproject.toml`.

**Files scanned (partial list):** 22 scaffold files (main, config.schema, config.loader, manifest.writer, manifest.schema, logging.structlog_setup, duckdb_layer.setup, state.db, state.schemas.sql, state.writers.clo_history, state.writers.run_manifests, data.poller.markets_poller, data.poller.e_liq_poller, data.chain_time, data.ingester.order_book, screener.metrics, screener.cli, screener.report, screener.rescreen, scripts.architecture_lint, test_screener_metrics, test_amm_conservation, test_manifest_contains_all_knobs, conftest).

**Pattern extraction date:** 2026-04-24.

**Planner's next move:** consume this map + 02-RESEARCH.md §Planner Hand-Off + 02-VALIDATION.md to produce 4 PLAN-02-0X.md files (per RESEARCH §Planner Hand-Off #10 decomposition recommendation). Every plan action MUST cite the analog path:line from this PATTERNS.md so the executor copies the right pattern.
