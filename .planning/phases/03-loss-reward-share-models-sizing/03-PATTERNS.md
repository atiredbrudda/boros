---
phase: 3
slug: loss-reward-share-models-sizing
kind: pattern-map
created: 2026-04-24
upstream: [03-RESEARCH.md, 03-VALIDATION.md]
downstream: 03-PLAN-*.md
---

# Phase 3 — Pattern Map

**Mapped:** 2026-04-24
**Files analyzed:** 34 new + 9 modified source / test / doc / config artifacts (from RESEARCH §Module / File Layout lines 769–816)
**Analogs found:** 34 / 34 (Phase 1 + Phase 2 scaffold is exhaustive — the `fill_model/` package is the load-bearing structural precedent for the whole `loss_model/` + `reward_model/` + `sizer/` triple)

Every new Phase 3 module has a direct structural precedent:
- `loss_model/*` mirrors `fill_model/*` (config + schemas + fit + artifact + refit_loop + cli) almost 1-for-1.
- `reward_model/*` splits into a formula module (analog: `screener/economics_gate.py`) and a polling loop (analog: `data/poller/e_liq_poller.py` + `data/poller/markets_poller.py`).
- `sizer/*` is pure-function numerics (analog: `screener/filter.py` + `screener/economics_gate.py::compute_r_apr_on_collateral_pendle`).
- New SQLite tables + Alembic migrations mirror `reward_budget_history` (migration 0002) + `fill_model_fits` (migration 0003) verbatim.

---

## File Classification

### Created files

| New file | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `python/src/boros_brain/loss_model/__init__.py` | package-marker | n/a | `python/src/boros_brain/fill_model/__init__.py` | exact |
| `python/src/boros_brain/loss_model/config.py` (`LossModelConfig`, `FeesConfig`) | config-schema | static | `python/src/boros_brain/fill_model/config.py` (`FillModelConfig`) | exact |
| `python/src/boros_brain/loss_model/schemas.py` (`LossGridArtifact`, `ExpectedLossInput/Output`, exceptions) | pydantic-schema | static | `python/src/boros_brain/fill_model/schemas.py` (`FitArtifact`, `PredictInput/Output`) | exact |
| `python/src/boros_brain/loss_model/replay.py` (`replay_historical_fills`) | service / transform | batch, DuckDB read → in-memory per-fill list | `python/src/boros_brain/fill_model/features.py` (`build_features_table`) + `screener/filter.py::apply_screener_filters` | role-match (DuckDB join of parquet + SQLite, per-row reduction) |
| `python/src/boros_brain/loss_model/fit.py` (`fit_loss_grid`) | service / aggregation | batch (cell aggregation) | `python/src/boros_brain/fill_model/fit.py` (`fit_market_side`) + `screener/scale_calibration.py` | role-match (numerics-in-batch → persisted artifact) |
| `python/src/boros_brain/loss_model/expected_loss.py` (`expected_loss`) | service / sync-query | request-response (sync) | `python/src/boros_brain/fill_model/predict.py` (`predict`) | exact (same contract shape — sync sub-10ms, named exceptions, staleness policy) |
| `python/src/boros_brain/loss_model/artifact.py` (`write_loss_grid_artifact`) | storage-writer-adapter | write (parquet + SQLite dual-write) | `python/src/boros_brain/fill_model/artifact.py` (`write_fit_artifact`) | exact |
| `python/src/boros_brain/loss_model/refit_loop.py` (`refit_once`, `run_loss_model_refit_loop`) | long-running async task | event-driven cadence loop | `python/src/boros_brain/fill_model/refit_loop.py` (`run_fill_model_refit_loop`) | exact |
| `python/src/boros_brain/loss_model/ou_parametric.py` (`OUBasisLossModel` Protocol, `fit_ou_basis`) | scaffold / Protocol | static | `python/src/boros_brain/fill_model/schemas.py` (Protocol pattern — `runtime_checkable Protocol`) + `fill_model/predict.py` (interface signature parallel) | role-match (no pre-existing scaffold-only NotImplementedError module — greenfield) |
| `python/src/boros_brain/loss_model/cli.py` + `__main__.py` | CLI entrypoint | request-response | `python/src/boros_brain/fill_model/cli.py` + `__main__.py` | exact |
| `python/src/boros_brain/reward_model/__init__.py` | package-marker | n/a | `python/src/boros_brain/fill_model/__init__.py` | exact |
| `python/src/boros_brain/reward_model/config.py` (`RewardShareModelConfig`) | config-schema | static | `python/src/boros_brain/fill_model/config.py` | exact |
| `python/src/boros_brain/reward_model/schemas.py` (`RewardCurveInput/Output`, `CompetitionSnapshot`, `RegimeLabel`) | pydantic-schema | static | `python/src/boros_brain/fill_model/schemas.py` | exact |
| `python/src/boros_brain/reward_model/competition_tracker.py` (`CompetitionTracker`, `run_competition_tracker_loop`) | long-running async + REST poller | event-driven (5s cadence REST + 1 Hz parquet read) | `python/src/boros_brain/data/poller/e_liq_poller.py` (`ELiqPoller`) + `data/poller/markets_poller.py` (`MarketsPoller`) | exact |
| `python/src/boros_brain/reward_model/r_capped.py` (`r_capped_curve`) | service / closed-form formula | request-response (pure sync) | `python/src/boros_brain/screener/economics_gate.py::compute_r_apr_on_collateral_pendle` | exact (same numerator structure + PENDLE-unit discipline + sub_cap/cap_binding/market_saturated regime) |
| `python/src/boros_brain/reward_model/q_cap.py` (`compute_q_cap`) | service / closed-form formula | request-response (pure sync) | `python/src/boros_brain/screener/economics_gate.py::compute_r_apr_on_collateral_pendle` | exact |
| `python/src/boros_brain/reward_model/cli.py` + `__main__.py` | CLI entrypoint | request-response | `python/src/boros_brain/fill_model/cli.py` + `__main__.py` | exact |
| `python/src/boros_brain/sizer/__init__.py` | package-marker | n/a | `python/src/boros_brain/fill_model/__init__.py` | exact |
| `python/src/boros_brain/sizer/config.py` (`SizerConfig`) | config-schema | static | `python/src/boros_brain/fill_model/config.py` | exact |
| `python/src/boros_brain/sizer/schemas.py` (`SizerInput/Output`) | pydantic-schema | static | `python/src/boros_brain/fill_model/schemas.py` | exact |
| `python/src/boros_brain/sizer/optimizer.py` (`q_me_target`) | service / sync query + 1-D optimization | request-response (sync) | `python/src/boros_brain/fill_model/predict.py` (`predict`) + `screener/filter.py::apply_screener_filters` (multi-source orchestration) | role-match (sync aggregator that calls `fill_model.predict` + `loss_model.expected_loss` + `reward_model.r_capped`) |
| `python/src/boros_brain/sizer/cli.py` + `__main__.py` | CLI entrypoint | request-response | `python/src/boros_brain/fill_model/cli.py` | exact |
| `python/src/boros_brain/pricing/__init__.py` | package-marker | n/a | `python/src/boros_brain/fill_model/__init__.py` | exact |
| `python/src/boros_brain/pricing/config.py` (`PricingConfig`) | config-schema | static | `python/src/boros_brain/fill_model/config.py` + `config/schema.py::DataConfig` | exact |
| `python/src/boros_brain/state/writers/loss_grid_artifacts.py` | state-writer (single-writer) | write | `python/src/boros_brain/state/writers/fill_model_fits.py` | exact |
| `python/src/boros_brain/state/writers/competition_history.py` | state-writer (single-writer) | write | `python/src/boros_brain/state/writers/reward_budget_history.py` + `state/writers/fill_model_fits.py` | exact |
| `python/src/boros_brain/state/schemas.sql` (append `loss_grid_artifacts`, `competition_history` DDL) | schema DDL | n/a | existing `fill_model_fits` / `reward_budget_history` DDL in same file | exact |
| `python/src/boros_brain/state/migrations/versions/0004_loss_grid_artifacts.py` | Alembic migration | n/a | `python/src/boros_brain/state/migrations/versions/0003_fill_model_fits.py` | exact |
| `python/src/boros_brain/state/migrations/versions/0005_competition_history.py` | Alembic migration | n/a | `python/src/boros_brain/state/migrations/versions/0002_reward_budget_history.py` + `0003_fill_model_fits.py` | exact |
| `python/tests/test_loss_model_replay.py` | pytest unit | n/a | `python/tests/test_fill_model_features.py` | exact |
| `python/tests/test_loss_model_fit_and_expected_loss.py` | pytest unit | n/a | `python/tests/test_fill_model_fit_basic.py` + `test_fill_model_predict_contract.py` | exact |
| `python/tests/test_loss_model_ou_scaffold.py` | pytest unit | n/a | `python/tests/test_fill_model_predict_contract.py` (NotImplementedError-shape test) | exact |
| `python/tests/test_reward_curve.py` | pytest unit + property | n/a | `python/tests/test_economics_kill_switch.py` + `test_screener_metrics.py` | exact (pure numerics tests for closed-form) |
| `python/tests/test_competition_tracker.py` | pytest unit + mocked REST | n/a | `python/tests/test_e_liq_poller.py` | exact |
| `python/tests/test_sizer.py` | pytest unit + property | n/a | `python/tests/test_economics_kill_switch.py` + `test_fill_model_predict_contract.py` | exact |

### Modified files

| Modified file | Role | Change | Analog Pattern |
|---|---|---|---|
| `python/src/boros_brain/config/schema.py` | config-schema-modify | Add `loss_model`, `reward_share_model`, `sizer`, `pricing` sub-models + `MarketRewardCalibration` + extend `MarketCalibration` with `reward_calibration` field | Self — `fill_model: FillModelConfig` attachment pattern at line 136 |
| `python/src/boros_brain/main.py` | process-entrypoint-modify | Spawn `run_loss_model_refit_loop` + `run_competition_tracker_loop` tasks at boot; extend `--dry-run` guard | Self — `refit_task = asyncio.create_task(run_fill_model_refit_loop(cfg, manifest.run_id))` at line 142 |
| `docs/architecture.yml` | machine-yml | Add ~24 node rows + ~30 edge rows (per RESEARCH §Architecture Manifest Delta) | Self — existing `brain.fill_model.*` node/edge rows |
| `docs/ARCHITECTURE.md` | human-markdown + Mermaid | Add Phase 3 Mermaid subgraph | Self — existing `brain.fill_model.*` subgraph |
| `scripts/no_time_time_lint.py` | lint-hook-modify | One-line extend of `_BANNED_DIRS` to include `loss_model/`, `reward_model/`, `sizer/` | Self — existing `fill_model/` entry |
| `strategy/v0.5-default.yaml` | operator-config | Add Phase 3 knob defaults + per-market `market_reward_calibration` block | Self — existing `fill_model` / `screener` YAML blocks |
| `python/tests/test_manifest_contains_all_knobs.py` | pytest modify | Auto-coverage via reflection (no test edit strictly required); add one spot-check per new sub-model for defensiveness | Self — `test_fill_model_leaves_surfaced` at lines 118–134 |
| `python/tests/test_sqlite_single_writer.py` | pytest modify | Extend for `loss_grid_artifacts`, `competition_history` tables | Self |
| Wiki pages under `LLM Wiki/workspaces/boros/wiki/` | markdown + frontmatter | 7 new + 2 supersedences per Protocol 1 | Self — existing workspace seeded 2026-04-23 |

---

## Pattern Assignments

Every new file below cites concrete line ranges from its analog. The planner should quote these ranges verbatim in the `<read_first>` field of each plan's actions so the executor has the exact context.

### `python/src/boros_brain/loss_model/__init__.py` — package marker

**Analog:** `python/src/boros_brain/fill_model/__init__.py` (1-line file, empty).

**Pattern:** empty file (or single-line module docstring). No imports, no public re-exports. Matches the `fill_model/__init__.py` convention (`-shorter than the provided offset` — the file is 1 line).

Same applies verbatim to `reward_model/__init__.py`, `sizer/__init__.py`, `pricing/__init__.py`.

---

### `python/src/boros_brain/loss_model/config.py` — `LossModelConfig` + `FeesConfig` Pydantic sub-models

**Role:** Pydantic `StrictBase` sub-models that slot into `BotConfig.loss_model` and surface automatically in RUN_MANIFEST via reflection (`test_manifest_contains_all_knobs.py::_collect_leaf_paths`).

**Data flow:** static config → reflection by `manifest.writer.build_run_manifest` → every `expected_loss()`/`fit_loss_grid()`/`refit_loop` consumer reads the field from a frozen `BotConfig` instance.

**Analog:** `python/src/boros_brain/fill_model/config.py` (`FillModelConfig`) — exact precedent for an 11-knob StrictBase sub-model with `@field_validator`, ranged `Field(..., ge=..., le=...)`, and `Literal` enum knobs.

**Imports pattern** (`fill_model/config.py` lines 10–16):
```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import ALLOWED_COVARIATES, DEFAULT_COVARIATE_WHITELIST
```

**Local StrictBase re-declaration pattern** (`fill_model/config.py` lines 19–25) — mandatory to avoid circular imports with `config/schema.py`:
```python
class StrictBase(BaseModel):
    """Strict frozen base. Identical contract to BotConfig sub-models.

    Re-declared here to avoid circular imports with brain.config.schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Ranged-Field pattern** (`fill_model/config.py` lines 36–43):
```python
window_days: int = Field(14, ge=7, le=30)
"""Number of days of trade history used to build the feature table for each fit."""

bin_duration_s: float = Field(60.0, ge=30.0, le=300.0)
"""Width of each time bin in seconds. Trade counts per bin are the Poisson response."""

refit_cadence_s: float = Field(900.0, ge=60.0, le=3600.0)
"""How often (seconds) the refit loop re-runs fit_market_side and updates the cached artifact."""
```

**Literal-enum + validator pattern** (`fill_model/config.py` lines 50–54 + 79–89):
```python
queue_tracker_bias_mode: Literal["pessimistic", "optimistic", "realized"] = "pessimistic"

@field_validator("covariate_whitelist")
@classmethod
def _whitelist_subset(cls, v: list[str]) -> list[str]:
    bad = [x for x in v if x not in ALLOWED_COVARIATES]
    if bad:
        raise ValueError(
            f"covariate_whitelist contains non-allowed entries: {bad}. "
            f"Allowed: {sorted(ALLOWED_COVARIATES)}"
        )
    return v
```

**Nested sub-model pattern** — unique to Phase 3; the closest in-repo is how `BotConfig.fill_model: FillModelConfig` attaches at `config/schema.py` line 136. Apply recursively: `LossModelConfig.fees: FeesConfig = Field(default_factory=FeesConfig)  # type: ignore`:
```python
class FeesConfig(StrictBase):
    taker_fee_rate: float = Field(5e-4, ge=0.0, le=0.01)
    # ... 7 more fee knobs per RESEARCH §BotConfig Knob Delta lines 1012–1026

class LossModelConfig(StrictBase):
    depth_bucket_edges: list[float] = Field(default_factory=lambda: [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, float('inf')])
    tau_bucket_edges: list[float] = Field(default_factory=lambda: [0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, float('inf')])
    # ... 9 more knobs per RESEARCH §BotConfig Knob Delta lines 1028–1048
    fees: FeesConfig = Field(default_factory=FeesConfig)  # type: ignore
```

**Deltas vs analog:**
- Two classes in one file (`FeesConfig` + `LossModelConfig`), with `FeesConfig` nested inside `LossModelConfig` via `default_factory`.
- `list[float]` knobs for `depth_bucket_edges` / `tau_bucket_edges` (each a leaf path in the manifest reflection — same pattern as `fill_model.covariate_whitelist: list[str]`).
- `aggregation_metric: Literal["mean", "p50", "p95"] = "mean"` — same pattern as `queue_tracker_bias_mode`.
- Default `window_days=90` (vs fill_model's 14) — loss events are rarer than trades.

**Gotchas:**
- `# type: ignore` on `Field(default_factory=FeesConfig)` — mypy pattern from `config/schema.py` line 131.
- Float-infinity literal edges: `float('inf')` is JSON-serialisable under Pydantic `model_dump(mode='json')` as `"Infinity"` (string). Confirm the round-trip test `test_config_round_trip.py` still passes — may need to represent edges as a finite sentinel (e.g. 10000.0) to keep YAML parseable.

**Same pattern applies verbatim to:** `reward_model/config.py` (5 knobs), `sizer/config.py` (6 knobs), `pricing/config.py` (4 knobs) — each its own StrictBase sub-model.

---

### `python/src/boros_brain/loss_model/schemas.py` — Pydantic + dataclass shapes for loss model

**Role:** Wire-contract shapes for `fit_loss_grid()` outputs + `expected_loss()` I/O + named exceptions. Single home for all `loss_model` shape declarations so architecture.yml has a single `brain.loss_model.schemas` node.

**Data flow:** static schema; `LossGridArtifact` is written to SQLite + parquet; `ExpectedLossInput`/`ExpectedLossOutput` are the sync function boundary.

**Analog:** `python/src/boros_brain/fill_model/schemas.py` — three-concepts-in-one-file pattern (dataclass results + Pydantic models + exception classes) is the exact precedent.

**Dataclass result pattern** (`fill_model/schemas.py` lines 14–27) — for `LossGridArtifact`'s per-cell aggregation container if any:
```python
@dataclass(frozen=True)
class ReplayResult:
    """Result from QueueTracker.replay_window — tri-track queue estimates + diagnostics."""

    market_id: str
    side: Literal["long", "short"]
    window_start_ts: int
    window_end_ts: int
    pessimistic_queue_at_anchor: dict[int, dict[int, float]] = field(default_factory=dict)
    # ...
    event_index_coverage: Literal["full", "degraded"] = "full"
```

**StrictBase re-declaration** (`fill_model/schemas.py` lines 62–71) — same pattern as `fill_model/config.py` (avoid circular imports):
```python
from pydantic import BaseModel, ConfigDict  # noqa: E402


class StrictBase(BaseModel):
    """Local strict base for fill_model Pydantic models (avoids circular import
    with config.schema). Matches manifest/schema.py pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Artifact Pydantic pattern** (`fill_model/schemas.py` lines 74–98) — `LossGridArtifact` mirrors this:
```python
class FitArtifact(StrictBase):
    run_id: str
    fit_window_start_ts: int
    fit_window_end_ts: int
    market_id: str
    side: Literal["long", "short"]
    covariate_whitelist: list[str]
    beta: list[float]                                       # length = 1 + len(covariate_whitelist)
    beta_stderr: list[float]
    log_likelihood: float
    deviance: float
    aic: float
    n_observations: int
    converged: bool
    fit_status: Literal["ok", "degraded", "stale"]
    gof_ks_pval: float | None = None
    gof_lr_vs_null: float | None = None
    event_index_coverage: Literal["full", "degraded"] = "full"
    created_at: int
```

**Input/Output Pydantic pattern** (`fill_model/schemas.py` lines 101–117):
```python
class PredictInput(StrictBase):
    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    queue_ahead_wei: int
    current_features: dict[str, float]                      # keyed by covariate_whitelist names
    time_to_epoch_end_s: float
    current_chain_ts: int                                    # Phase 4 supplies from chain_time.now_cached()


class PredictOutput(StrictBase):
    p_fill_this_epoch: float
    lambda_per_second: float
    fit_run_id: str
    fit_age_s: float
    fit_status: Literal["ok", "degraded", "stale"]
```

**Named exception pattern** (`fill_model/schemas.py` lines 119–136) — `LossModelNoFreshGridError` + `LossModelSparseCellWarning` follow this shape:
```python
class FillModelStaleFeatureError(RuntimeError):
    """Raised by predict() when any current_features value is NaN or missing.
    ...
    Never silently substitute exp(β₀) — PITFALLS §NaN-covariate silent-fallback
    is the canonical fuck-up here."""

    def __init__(self, missing_features: list[str]):
        self.missing_features = missing_features
        super().__init__(f"stale/missing features: {missing_features}")


class FillModelNoFreshFitError(RuntimeError):
    """Raised by predict() when no fit exists OR all fits older than fit_max_staleness_s."""
```

**Deltas vs analog:**
- `LossGridArtifact` exact fields per RESEARCH §LOSS-01 (lines 297–298, 321–324): `run_id`, `market_id`, `side`, `window_start_ts`, `window_end_ts`, `fit_status`, `depth_bucket_edges: list[float]`, `tau_bucket_edges: list[float]`, `cells: list[LossGridCell]` (each with `depth_bucket_idx`, `tau_bucket_idx`, `n_samples`, `mean`, `p50`, `p95`, `std`), `event_index_coverage`, `created_at`.
- `ExpectedLossInput` / `ExpectedLossOutput` per RESEARCH §LOSS-02 (lines 336–364).
- `LossModelNoFreshGridError(RuntimeError)` — exact parallel to `FillModelNoFreshFitError`.
- `LossModelSparseCellWarning` — a **warning**, not an exception (structlog emits; no raise). Implement as a module-level `log.warning("loss_model.sparse_cell_fallback", ...)` pattern, **not** a Python `Warning` subclass.

**Same pattern applies to:** `reward_model/schemas.py` (`RewardCurveInput`, `RewardCurveOutput`, `CompetitionSnapshot`, `RegimeLabel` Literal), `sizer/schemas.py` (`SizerInput`, `SizerOutput`).

**Gotchas:**
- `public_functions: []` in the `brain.loss_model.schemas` architecture.yml node: classes only, no top-level functions (matches the lint rule — `scripts/architecture_lint.py` only picks up `FunctionDef`/`AsyncFunctionDef`).
- Keep exceptions in `schemas.py` and re-export from `expected_loss.py` — matches the `fill_model.predict` re-export pattern at `fill_model/predict.py` lines 32–38.

---

### `python/src/boros_brain/loss_model/replay.py` — historical-fill replayer

**Role:** Joint DuckDB batch job over Phase 1 parquet outputs + `state.clo_history`. Produces one `PerFillPnL` row per historical fill on the candidate market per RESEARCH §LOSS-01 (lines 263–275).

**Data flow:** reads `parquet.market_trades`, `parquet.order_book_raw`, `parquet.order_book_combined`, `parquet.underlying_apr`, `parquet.settlement`, `parquet.market_data`, `state.clo_history` via `brain.duckdb_layer.setup.open_analytical_conn`; returns in-memory `list[PerFillPnL]` (not persisted here — `fit.py` does the aggregation).

**Analog:** `python/src/boros_brain/fill_model/features.py` — the closest existing DuckDB multi-parquet join → polars-reduction pipeline.

**Imports + DuckDB-open pattern** (`fill_model/features.py` lines 18–29):
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
import structlog

from ..config.schema import BotConfig
from ..duckdb_layer.setup import open_analytical_conn

log = structlog.get_logger(__name__)
```

**Multi-CTE DuckDB join pattern** (`fill_model/features.py` lines 62–145) — the whole `_FEATURE_SQL` query is the canonical shape for Phase 3 replay: CTEs joined by `LEFT JOIN ... USING`, parameterised with `:market_id`, `:window_start`, `:window_end` placeholders.

**Parameterised execution pattern** (`fill_model/features.py` lines 179–191):
```python
conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")
try:
    df = conn.execute(
        _FEATURE_SQL,
        {
            "market_id": market_id,
            "window_start": window_start_ts,
            "window_end": window_end_ts,
            "bin_duration_s": bin_s,
            "bin_duration_s_int": bin_s_int,
        },
    ).pl()
finally:
    conn.close()
```

**eventIndex-ordered sort pattern** (`screener/metrics.py` lines 23–60) — mandatory for Phase 3 replay because fills are matched 1-to-1 via `eventIndex`:
```python
df = trades.sort(["blockTimestamp", "eventIndex"])

null_count = df["eventIndex"].is_null().sum()
if null_count > 0:
    log.warning(
        "screener.eventindex_gap",
        market_id=market_id,
        null_rows=int(null_count),
    )
    return None
```

**Deltas vs analog:**
- Output is `list[PerFillPnL]` (in-memory dataclass list), NOT parquet. `fit.py` takes the list, aggregates into cells, persists the aggregation via `artifact.py`.
- SQL logic per RESEARCH §LOSS-01 step-by-step (lines 265–275): for each row in `parquet.market_trades` filtered to `(market_id, window)`, LEFT JOIN to nearest `clo_history` snapshot ≤ `blockTimestamp`, LEFT JOIN to nearest `market_data` markApr, LEFT JOIN to nearest `underlying_apr` funding row, LEFT JOIN to NEXT opposite-side trade within ≤ 60s for close price.
- Fee computation per RESEARCH §LOSS-01 step 5: `P&L = size × (close_rate - fill_rate) × τ_effective - taker_fee × size × τ × rate - settlement_fee_amortized - gas_proxy`. Knobs come from `config.loss_model.fees.*`.
- `close_latency_s` flag per RESEARCH §LOSS-01 edge case — if no opposite-side trade within 60s, use next available + set flag.

**Gotchas:**
- `open_analytical_conn` attaches SQLite READ-ONLY (`duckdb_layer/setup.py` lines 50–68). `replay.py` MUST NOT try to write through DuckDB; results are returned in-memory only.
- `close_latency_budget_s` default 60.0 lives on `LossModelConfig` (RESEARCH §BotConfig Knob Delta line 1046). Use `:close_latency_budget_s` as SQL placeholder.
- Defensive against zero-fill markets (Phase 1 screener would have filtered them, but check): return empty `list[PerFillPnL]` without raising. `fit.py` handles the degrade path.

---

### `python/src/boros_brain/loss_model/fit.py` — `fit_loss_grid` aggregation + persistence

**Role:** Takes `list[PerFillPnL]` from `replay.py`, bins into `(depth_bucket, tau_bucket)` cells, computes per-cell `mean / p50 / p95 / std / n_samples`, emits `LossGridArtifact`, persists via `artifact.py`.

**Data flow:** calls `replay.py::replay_historical_fills`; constructs `LossGridArtifact`; calls `state.writers.loss_grid_artifacts.insert_loss_grid_artifact`.

**Analog:** `python/src/boros_brain/fill_model/fit.py` (`fit_market_side`) — exact precedent for the "numerics-in-batch + persisted artifact + health-gate degraded-path" shape.

**Imports pattern** (`fill_model/fit.py` lines 10–26):
```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import polars as pl
import statsmodels.api as sm
import structlog

from ..config.schema import BotConfig
from .artifact import write_fit_artifact
from .schemas import FitArtifact

log = structlog.get_logger(__name__)

__all__ = ["fit_market_side"]
```

**Health-gate + degraded-artifact pattern** (`fill_model/fit.py` lines 31–48 + 83–111):
```python
def _passes_health_gate(
    results: sm.GLMResultsWrapper,
    config: BotConfig,
) -> tuple[bool, str]:
    """Return (passes, reason). reason='ok' iff passes."""
    if not bool(results.converged):
        return False, "not_converged"
    # ...
    return True, "ok"

# Degraded-artifact emission instead of raising (see RESEARCH §Common Pitfalls #3):
if pdf.empty:
    artifact = FitArtifact(
        run_id=run_id,
        fit_window_start_ts=0,
        fit_window_end_ts=0,
        market_id=market_id,
        side=side,
        # ... all fields defaulted or sentinelled
        fit_status="degraded",
        created_at=0,  # sentinel — stamped by artifact.write_fit_artifact
    )
    log.warning("fill_model.fit_degraded", market_id=market_id, side=side, reason="no_data")
    if persist:
        write_fit_artifact(artifact, sqlite_path=sqlite_path)
    return artifact
```

**Sentinel-created_at pattern** (`fill_model/fit.py` lines 101, 150, 177; `fill_model/artifact.py` lines 36–38):
- `fit.py` lives under the `no_time_time_lint.py`-banned dirs (brain/fill_model/), so it CANNOT call `datetime.now(UTC).timestamp()`.
- Instead: set `created_at=0` as sentinel; `artifact.write_fit_artifact` does the stamp:
  ```python
  if artifact.created_at == 0:
      artifact = artifact.model_copy(update={"created_at": int(datetime.now(UTC).timestamp())})
  ```
- Phase 3: Per RESEARCH §Modified in Phase 3 line 812, the lint will be extended to include `loss_model/`, `reward_model/`, `sizer/`. The same sentinel pattern must be applied in `loss_model/fit.py` and `reward_model/competition_tracker.py`.

**Persistence-with-persist-flag pattern** (`fill_model/fit.py` lines 60, 109, 152, 201):
```python
def fit_market_side(
    ...
    *,
    persist: bool = True,
) -> FitArtifact:
    # ...
    if persist:
        write_fit_artifact(artifact, sqlite_path=sqlite_path)
    return artifact
```

**Deltas vs analog:**
- No statsmodels/GLM — cell aggregation is `polars.DataFrame.group_by(["depth_bucket_idx", "tau_bucket_idx"]).agg([...])`.
- Bucket assignment: use `config.loss_model.depth_bucket_edges` / `tau_bucket_edges` with `polars.cut()` (idiomatic polars bucketing).
- `fit_status = "degraded"` when any cell has `n_samples < config.loss_model.min_samples_per_cell` globally — NOT per-cell (the degradation is a grid-wide flag; per-cell sparsity is handled in `expected_loss.py` at query time).
- `event_index_coverage` carries through from `replay.py` output.

**Gotchas:**
- `_passes_health_gate` logic (fit.py lines 31–48) translates to: "n_observations / n_cells >= config.loss_model.min_samples_per_cell × n_cells" — i.e. enough samples to populate at least some cells.
- Keep `fit_loss_grid` pure of wall-clock calls — same sentinel discipline as `fill_model/fit.py`.
- The in-memory artifact uses frozen Pydantic; if refactoring `fit_status` mid-stream, use `model_copy(update=...)` (matches `artifact.py` line 38 pattern).

---

### `python/src/boros_brain/loss_model/expected_loss.py` — sync `expected_loss()` contract

**Role:** The Phase-4-locked sync entry point. Takes `ExpectedLossInput`, returns `ExpectedLossOutput`, or raises `LossModelNoFreshGridError`. Called by `sizer.optimizer` + Phase 4 DecisionEngine at 1 Hz per in-flight order.

**Data flow:** reads `state.loss_grid_artifacts` (via `state.writers.loss_grid_artifacts.get_latest_loss_grid`); pure-sync (chain_time passed in via `current_chain_ts: int`).

**Analog:** `python/src/boros_brain/fill_model/predict.py` (`predict`) — exact contract precedent: sync, named exceptions, staleness policy, sub-10ms budget.

**Imports + module docstring pattern** (`fill_model/predict.py` lines 1–12 + 14–30):
```python
"""FILL-05 sync predict() contract. Phase 4 DecisionEngine calls this at 1 Hz.

Contract:
    - SYNC (not async). p95 < 10ms budget.
    - NaN covariate → FillModelStaleFeatureError (NEVER silent exp(β₀) fallback).
    - Fit older than fit_max_staleness_s → FillModelNoFreshFitError.
    - Monotone-decreasing in depth_from_mark_ticks (via explicit depth penalty).
    - Monotone-decreasing in queue_ahead_wei (via queue penalty).

Design-locked. Any change to this signature is a Phase-4 breaking change.
"""

from __future__ import annotations

import math
from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..state.writers.fill_model_fits import get_latest_fit
from .schemas import (
    FillModelNoFreshFitError,
    FillModelStaleFeatureError,
    PredictInput,
    PredictOutput,
)

log = structlog.get_logger(__name__)

__all__ = [
    "predict",
    "PredictInput",
    "PredictOutput",
    "FillModelStaleFeatureError",
    "FillModelNoFreshFitError",
]
```

**Named-exception + re-export** (`fill_model/predict.py` lines 32–38) — required so callers can `from boros_brain.loss_model.expected_loss import LossModelNoFreshGridError`.

**Staleness 3-tier policy pattern** (`fill_model/predict.py` lines 90–128):
```python
fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)
if fit_age_s < 0:
    log.warning("fill_model.predict_future_dated_fit", ...)
    fit_age_s = 0.0
if fit_age_s > config.fill_model.fit_max_staleness_s:
    log.warning("fill_model.no_fresh_fit", ..., fit_age_s=fit_age_s, ...)
    raise FillModelNoFreshFitError(
        f"fit too stale: age={fit_age_s}s > max={config.fill_model.fit_max_staleness_s}s"
    )

final_status: str = fit.fit_status
if fit_age_s > config.fill_model.fit_warn_staleness_s and final_status == "ok":
    final_status = "stale"
    log.warning("fill_model.predict_stale_fit_warning", ...)
```

**No-silent-fallback discipline** (`fill_model/predict.py` lines 62–77) — Phase 3 parallel: any missing cell → `fallback_mode='coarse_bound'` + explicit warning log, NEVER silently return 0:
```python
missing = [
    name
    for name in whitelist
    if name not in req.current_features
    or not isinstance(req.current_features[name], int | float)
    or math.isnan(float(req.current_features[name]))
]
if missing:
    log.warning(
        "fill_model.predict_nan_covariate",
        market_id=req.market_id,
        side=req.side,
        missing_features=missing,
    )
    raise FillModelStaleFeatureError(missing_features=missing)
```

**Deltas vs analog:**
- Sparse-cell fallback algorithm per RESEARCH §LOSS-02 lines 366–370:
  1. Look up cell for `(depth, τ)`.
  2. If `n_samples >= config.loss_model.min_samples_per_cell` → `fallback_mode='exact'`.
  3. Else k-NN with `config.loss_model.knn_k` neighbors within `config.loss_model.knn_max_distance` → `fallback_mode='nearest_neighbor'`.
  4. Else `config.screener.fill_loss_coarse_bound × notional_proxy` → `fallback_mode='coarse_bound'` + warn.
- No NaN-covariate concept (inputs are all scalars); instead clamp `depth_from_mark_ticks < 0` to bucket 0 per RESEARCH §LOSS-02 edge case.
- `time_to_maturity_s < 0` → raise explicitly (Phase 4 SAFE-07 breaker territory).
- `fit_max_staleness_s` default is 86400s (24h) per `LossModelConfig` — LONGER than fill_model's 3600s because loss grids refit on slower cadence.

**Gotchas:**
- Keep `expected_loss()` SYNC. `current_chain_ts: int` passed in via `ExpectedLossInput` — same pattern as `PredictInput` at `fill_model/schemas.py` line 108.
- The `coarse_bound` fallback MUST be logged at `warning` level with full context per PITFALL §NaN-covariate silent fallback discipline — see `fill_model/predict.py` line 71 pattern.

---

### `python/src/boros_brain/loss_model/artifact.py` — `LossGridArtifact` SQLite + parquet dual-write

**Role:** Atomic dual-write: (a) parquet sidecar at `data/parquet/loss_grid_artifacts/market_id={m}/side={s}/window_end_ts={ts}/artifact.parquet` with full per-cell aggregation, (b) SQLite row into `state.loss_grid_artifacts` via single-writer.

**Data flow:** writes `parquet.loss_grid_artifacts` (new Hive-partitioned storage node), writes `state.loss_grid_artifacts` (new SQLite table).

**Analog:** `python/src/boros_brain/fill_model/artifact.py` (`write_fit_artifact`) — EXACT precedent. Mirror line-for-line.

**Full pattern to mirror** (`fill_model/artifact.py` lines 1–63 — the entire file):
```python
"""FitArtifact atomic dual-write: parquet sidecar + SQLite row.

Ordering: parquet first (orphan-tolerant), SQLite second.
If SQLite insert fails, the parquet is still readable.
If the parquet write fails, no SQLite row pollutes the latest-fit lookup.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import structlog

from ..state.writers.fill_model_fits import insert_fit_artifact
from .schemas import FitArtifact

log = structlog.get_logger(__name__)

__all__ = ["write_fit_artifact"]


def write_fit_artifact(
    artifact: FitArtifact,
    *,
    sqlite_path: Path,
    parquet_root: Path = Path("data/parquet/fill_model_artifacts"),
) -> Path:
    """Write FitArtifact to parquet sidecar + SQLite. Returns parquet path.

    If artifact.created_at == 0 (sentinel set by fit.py to keep wall-clock calls
    out of the banned fill_model/ dirs), stamp it here before writing.
    datetime.now(UTC).timestamp() is NOT matched by no_time_time_lint.py regex.
    """
    # Stamp created_at if not yet set (sentinel pattern — keeps fit.py lint-clean)
    if artifact.created_at == 0:
        artifact = artifact.model_copy(update={"created_at": int(datetime.now(UTC).timestamp())})

    out_dir = (
        parquet_root
        / f"market_id={artifact.market_id}"
        / f"side={artifact.side}"
        / f"window_end_ts={artifact.fit_window_end_ts}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "artifact.parquet"

    # Parquet sidecar: one-row frame with the full β vector serialized as list columns
    frame = pl.DataFrame([artifact.model_dump(mode="json")])
    frame.write_parquet(out_path)

    # SQLite row via single-writer module (parquet-first ordering per design)
    insert_fit_artifact(sqlite_path, artifact)

    log.info(
        "fill_model.fit_artifact_written",
        market_id=artifact.market_id,
        side=artifact.side,
        parquet=str(out_path),
        fit_status=artifact.fit_status,
    )
    return out_path
```

**Deltas vs analog:**
- Rename: `write_loss_grid_artifact`.
- Import: `from .schemas import LossGridArtifact`, `from ..state.writers.loss_grid_artifacts import insert_loss_grid_artifact`.
- Default `parquet_root`: `Path("data/parquet/loss_grid_artifacts")`.
- Because `LossGridArtifact` contains a nested list of cell dicts, the parquet sidecar is **multi-row** (one row per cell) with the top-level artifact metadata repeated — convert via `pl.DataFrame(artifact.cells.model_dump() for ...)` or flatten first. Alternatively keep single-row with `cells` as struct column (polars supports this).

**Gotchas:**
- The parquet-first / SQLite-second ordering is load-bearing (comment in `fill_model/artifact.py` line 3–4). Do NOT swap.
- `datetime.now(UTC).timestamp()` is the approved escape hatch for wall-clock in the banned dirs — `no_time_time_lint.py` regex only matches `time.time()`, not `datetime.now`. Phase 3: confirm the lint extension (line 812 of RESEARCH) preserves this exemption.

---

### `python/src/boros_brain/loss_model/refit_loop.py` — 15-min async cadence loop

**Role:** Long-running `asyncio.create_task` loop that calls `fit_loss_grid` every `config.loss_model.refit_cadence_s` seconds (default 900s). Initial fit is synchronous at boot.

**Data flow:** event-driven cadence; calls `replay.py::replay_historical_fills` → `fit.py::fit_loss_grid` → `artifact.py::write_loss_grid_artifact`.

**Analog:** `python/src/boros_brain/fill_model/refit_loop.py` — EXACT precedent (mirror line-for-line).

**Full pattern** (`fill_model/refit_loop.py` lines 1–85 — entire file):
```python
"""FILL-06: 15-min-cadence rolling refit loop.

Spawned from brain.main.run() alongside the existing heartbeat + ingest tasks.
Initial fit is synchronous (boot-block ~30s); subsequent fits are async-driven
at `config.fill_model.refit_cadence_s` (default 900s).

Per-loop errors are caught and logged; the loop continues. Mirrors
data/poller/markets_poller.run_markets_poller.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import polars as pl
import structlog

from ..config.schema import BotConfig
from ..data import chain_time
from .features import build_features_table
from .fit import fit_market_side

log = structlog.get_logger(__name__)

__all__ = ["refit_once", "run_fill_model_refit_loop"]


async def refit_once(config: BotConfig, run_id: str) -> None:
    """One refit across all (market_id, side) in config.markets."""
    if not config.markets:
        log.info("fill_model.refit_skipped_no_markets", run_id=run_id)
        return

    now_s = await chain_time.now_cached()
    window_end_ts = now_s
    window_start_ts = window_end_ts - int(config.fill_model.window_days * 86400)

    for mkt in config.markets:
        for side in ("long", "short"):
            try:
                fs = build_features_table(...)
                df = pl.read_parquet(fs.path)
                fit_market_side(...)
            except Exception as exc:  # noqa: BLE001
                log.exception(
                    "fill_model.refit_failed",
                    run_id=run_id,
                    market_id=mkt.market_id,
                    side=side,
                    err=str(exc),
                )


async def run_fill_model_refit_loop(config: BotConfig, run_id: str) -> None:
    """Long-running task. Pattern = markets_poller.run_markets_poller."""
    log.info("fill_model.refit_loop_started", run_id=run_id, cadence_s=config.fill_model.refit_cadence_s)
    while True:
        try:
            await refit_once(config, run_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("fill_model.refit_failed", run_id=run_id, err=str(exc))
        await asyncio.sleep(config.fill_model.refit_cadence_s)
```

**Chain-time async usage** (`fill_model/refit_loop.py` lines 41–43) — MANDATORY per INFRA-14: any time comparison inside `loss_model/` uses `await chain_time.now_cached()`, never `time.time()` / `datetime.now()`:
```python
now_s = await chain_time.now_cached()
window_end_ts = now_s
window_start_ts = window_end_ts - int(config.fill_model.window_days * 86400)
```

**Deltas vs analog:**
- Replace `build_features_table` + `fit_market_side` call sequence with `replay_historical_fills` + `fit_loss_grid`.
- `window_days` default 90 (vs fill_model's 14).
- `refit_cadence_s` default 900.0 (same as fill_model — matches RESEARCH §BotConfig Knob Delta line 1042).

**Gotchas:**
- Spawn-from-main pattern: `main.py` line 141 (`await refit_once(cfg, manifest.run_id)`) + line 142 (`refit_task = asyncio.create_task(run_fill_model_refit_loop(cfg, manifest.run_id))`). Phase 3: add two more `asyncio.create_task` calls for `run_loss_model_refit_loop` and `run_competition_tracker_loop`. Cancel-on-shutdown per main.py line 146–148.

---

### `python/src/boros_brain/loss_model/ou_parametric.py` — LOSS-03 scaffold (`NotImplementedError`)

**Role:** v1.0 drop-in point. Defines `OUBasisLossModel` Protocol matching the `expected_loss()` signature + `fit_ou_basis(*args, **kwargs) -> None` that raises `NotImplementedError("LOSS-03 scaffold — v1.0 drop-in point. See [[ou-on-basis-loss-scaffold]]").`

**Data flow:** static; no runtime calls in v0.5.

**Analog (closest):** `python/src/boros_brain/data/poller/e_liq_poller.py` lines 36–44 — `@runtime_checkable Protocol` pattern for `_RestClient` / `_EventPub`:
```python
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class _RestClient(Protocol):
    async def get_markets(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class _EventPub(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...
```

**Deltas vs analog:**
- Verbatim code from RESEARCH §LOSS-03 lines 392–423 — paste as canonical.
- Protocol signature must **match `expected_loss.expected_loss()` exactly** so Phase 4 can swap backends via config. Test `test_loss_model_ou_scaffold.py::test_ou_scaffold_protocol_surface` uses `inspect.signature` to enforce this (RESEARCH §LOSS-03 lines 427–441).

**Gotchas:**
- Do NOT add any partial implementation. The LOSS-03 contract is "scaffold only" — partial implementation creates two truth sources for `E[loss|fill]` that will diverge (RESEARCH §LOSS-03 lines 404–405).
- `public_functions: [fit_ou_basis]` in architecture.yml — Protocol classes are not functions and don't appear in the yml (same rule as `@dataclass` — see 02-PATTERNS.md line 251 note).

---

### `python/src/boros_brain/loss_model/cli.py` + `__main__.py` — CLI entrypoint

**Role:** CLI dispatcher: `fit` / `expected-loss` / `force-degrade` subcommands. Emits `RUN_MANIFEST` FIRST via `manifest/writer.py` (PROTO-01).

**Analog:** `python/src/boros_brain/fill_model/cli.py` — EXACT precedent (mirror line-for-line). Also `screener/cli.py` for the two-command argparse shape.

**MANIFEST-FIRST boot pattern** (`fill_model/cli.py` lines 66–91):
```python
def main(argv: list[str] | None = None) -> int:
    """Fill model CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    from ..config.loader import load_config
    from ..logging.structlog_setup import configure_logging
    from ..manifest.writer import build_run_manifest, write_manifest

    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        print(f"ConfigError: {exc}", file=sys.stderr)
        return 2

    # MANIFEST-FIRST (PROTO-01)
    manifest = build_run_manifest(config)
    configure_logging(
        run_id=manifest.run_id,
        tier="fill_model",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(manifest, logs_dir=config.infra.logs_dir, sqlite_path=config.infra.sqlite_path)
    log = structlog.get_logger("fill_model.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump())
    log.info("fill_model.cli_started", subcommand=args.cmd)
```

**Exit-code contract pattern** (`fill_model/cli.py` lines 8–14):
```
Exit codes:
    0  -- success
    1  -- FillModelNoFreshFitError (no fit persisted; predict subcommand)
    2  -- ConfigError (bad or missing config YAML)
```
Mirror for `loss_model/cli.py`: `1 -- LossModelNoFreshGridError`, `2 -- ConfigError`.

**Subparser pattern** (`fill_model/cli.py` lines 32–63):
```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.fill_model",
        description="Fill model CLI (FILL-01/05/06)",
    )
    p.add_argument("--config", default="strategy/v0.5-default.yaml", help="Path to strategy YAML")
    sub = p.add_subparsers(dest="cmd", required=True)

    fit_p = sub.add_parser("fit", help="Run a single synchronous refit across config.markets")
    # ...
```

**`__main__.py` pattern** (`fill_model/__main__.py` lines 1–6, whole file):
```python
"""Enables ``python -m boros_brain.fill_model``."""
from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

**Deltas vs analog:**
- Subcommands per RESEARCH §Module layout line 784: `fit`, `expected-loss`, `force-degrade`.
- `tier='loss_model'` in `configure_logging` call.
- For `reward_model/cli.py`: subcommands `curve`, `competition-snapshot`. `tier='reward_model'`.
- For `sizer/cli.py`: subcommand `target`. `tier='sizer'`.

**Gotchas:**
- Subcommand names use hyphens (`expected-loss`, `competition-snapshot`, `force-degrade`) — argparse converts to underscore attrs automatically.

---

### `python/src/boros_brain/reward_model/r_capped.py` — closed-form reward-share formula

**Role:** Pure sync function `r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput` implementing the capped pro-rata reward-share formula verbatim from RESEARCH §REWARD-01 lines 452–470 + `boros_consolidated_plan.md` §4 step 4.

**Data flow:** pure — no I/O. Called by `sizer.optimizer.q_me_target` (sync).

**Analog:** `python/src/boros_brain/screener/economics_gate.py::compute_r_apr_on_collateral_pendle` — EXACT structural precedent (same formula shape, PENDLE-unit discipline, divide-by-zero guard, frozen PROJECT.md constants).

**Imports + constants pattern** (`screener/economics_gate.py` lines 18–35):
```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ..config.loader import load_config, load_raw_yaml
from .kill_report import write_kill_report

log = structlog.get_logger(__name__)

# PROJECT.md L63 -- weekly epochs (Fri 00:00 UTC -> Thu 23:59 UTC). Locked constant.
EPOCHS_PER_YEAR = 52
```

**Formula-module pattern** (`screener/economics_gate.py` lines 108–131) — the exact closed-form shape:
```python
def compute_r_apr_on_collateral_pendle(
    *,
    e_liq_per_epoch: float,
    side_split: float,
    q_me: float,
    sigma_others: float,
    t_frac: float,
    required_collateral_pendle: float,
) -> float:
    """Returns R_apr_on_collateral as a decimal-fraction APR in PENDLE-units.

    Formula verbatim from 01-RESEARCH.md §Pattern 10:
        R_share_per_epoch_pendle = e_liq * side_split * (q_me * t_frac) / (sigma_others + q_me * t_frac)
        R_apr_pendle = R_share_per_epoch_pendle * EPOCHS_PER_YEAR / required_collateral_pendle
    """
    denominator = sigma_others + q_me * t_frac
    if denominator == 0.0:
        return 0.0
    r_share_per_epoch_pendle = e_liq_per_epoch * side_split * (q_me * t_frac) / denominator
    r_apr_pendle = r_share_per_epoch_pendle * EPOCHS_PER_YEAR / required_collateral_pendle
    return r_apr_pendle
```

**Deltas vs analog:**
- Phase 3's `r_capped_curve` computes the RAW share (NOT the APR) + regime classification + cap comparison:
  ```python
  def r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput:
      # r_uncapped
      denom = req.sigma_others_pendle + req.q_me_pendle * req.t_frac
      if denom == 0.0 or req.q_me_pendle == 0.0:
          r_uncapped = 0.0
      else:
          r_uncapped = req.e_liq_per_epoch_pendle * req.side_split * (req.q_me_pendle * req.t_frac) / denom

      # cap_budget
      if req.pendle_price_usd <= 0.0:
          raise ValueError("pendle_price_usd must be > 0")
      cap_budget = 10.0 * req.collateral_usd * (req.epoch_days / 365.0) / req.pendle_price_usd

      # regime
      if r_uncapped >= cap_budget:
          regime = "cap_binding"
      elif req.sigma_others_pendle == 0.0 and req.q_me_pendle > 0.0:
          regime = "market_saturated"
      else:
          regime = "sub_cap"

      r_capped = min(r_uncapped, cap_budget)
      return RewardCurveOutput(r_uncapped_pendle=r_uncapped, r_capped_pendle=r_capped, cap_budget_pendle=cap_budget, regime=regime)
  ```
- Inputs are a frozen Pydantic `RewardCurveInput` (not kwargs) — mirrors `PredictInput` (fill_model/schemas.py line 101) pattern.
- `EPOCHS_PER_YEAR` is defined at `screener/economics_gate.py` line 35 — REUSE by import rather than redeclaring. Same for any new constants (hardcode `CAP_APR_MULTIPLE = 10.0` but expose via `RewardShareModelConfig.cap_apr_multiple` per RESEARCH line 1058).
- `e_liq_per_epoch_pendle < 0` → `ValueError` (protocol always non-negative — RESEARCH §REWARD-01 line 516).

**Gotchas:**
- PENDLE-unit discipline per `screener/economics_gate.py` lines 9–14: ALL reward-share math is in PENDLE-units, not USD. The only USD knob is `config.pricing.pendle_price_usd` (used to compute `cap_budget_per_epoch_pendle` from `collateral_usd`).
- Edge cases per RESEARCH §REWARD-01 lines 512–516: `Σ_others == 0`, `Q_me == 0`, `pendle_price_usd == 0`, `e_liq_per_epoch < 0`.

**Same pattern applies to:** `reward_model/q_cap.py` (`compute_q_cap`) — same imports, same closed-form shape, keyword-only signature per RESEARCH §REWARD-04 lines 676–685. Formula per RESEARCH §REWARD-04 lines 660–671:
```python
def compute_q_cap(
    *,
    sigma_others_pendle: float,
    e_liq_per_epoch_pendle: float,
    side_split: float,
    t_frac: float,
    collateral_usd: float,
    pendle_price_usd: float,
    epoch_days: float,
) -> float:
    cap_budget = 10.0 * collateral_usd * (epoch_days / 365.0) / pendle_price_usd
    numerator = sigma_others_pendle * cap_budget
    denominator = e_liq_per_epoch_pendle * side_split * t_frac - cap_budget * t_frac
    if denominator <= 0.0:
        return math.inf  # cap never binds
    return numerator / denominator
```

---

### `python/src/boros_brain/reward_model/competition_tracker.py` — 5s REST poll + 1 Hz parquet read

**Role:** `CompetitionTracker` class + `run_competition_tracker_loop` async task. Polls `POST /open-api/v2/accounts/all-limit-orders` for `Q_me`; reads `parquet.order_book_combined` aggregated over `[clo_lower, clo_upper]` for `Σ_others`; subtracts AMM share via `fill_model.amm_consumption.compute_amm_share_timeseries`; writes `CompetitionSnapshot` row per cycle via `state.writers.competition_history.insert_competition_row`.

**Data flow:** REST + parquet → `state.competition_history`. 5s REST cadence + 1 Hz parquet read. Degraded-mode when REST fails 5× consecutive.

**Analog:** `python/src/boros_brain/data/poller/e_liq_poller.py` (`ELiqPoller`) — EXACT structural precedent for class + `run_one_cycle()` + `loop()` + `_get_with_backoff` + degraded-event pattern. Also `data/poller/markets_poller.py::run_markets_poller` for the async spawning function.

**Class structure pattern** (`data/poller/e_liq_poller.py` lines 46–81):
```python
class ELiqPoller:
    """DATA-11: polls GET /markets every e_liq_poll_interval_s and writes one
    reward_budget_history row per market per cycle. NO CACHE per PITFALLS §A2.
    """

    def __init__(
        self,
        config: Any,
        conn: sqlite3.Connection,
        rest: Any,
        run_id: str,
        event_pub: Any,
    ) -> None:
        self.interval: float = config.data.e_liq_poll_interval_s
        self.markets: list[str] = [m.market_id for m in config.markets]
        self.conn = conn
        self.rest = rest
        self.run_id = run_id
        self.event_pub = event_pub
        self._fail_count: int = 0
```

**run_one_cycle + degraded-event pattern** (`data/poller/e_liq_poller.py` lines 81–127):
```python
async def run_one_cycle(self) -> None:
    try:
        markets = await self._get_with_backoff()
    except Exception as exc:
        log.error("e_liq_poller.fetch_failed", error=str(exc), fail_count=self._fail_count)
        if self._fail_count >= 5:
            await self.event_pub.publish(
                "poller.e_liq.degraded",
                {"fail_count": self._fail_count},
            )
        return

    self._fail_count = 0
    chain_ts = await get_chain_time_cached()
    # ... writes rows ...
```

**Backoff retry pattern** (`data/poller/e_liq_poller.py` lines 128–146):
```python
_BACKOFF_DELAYS = [0.5, 1.0, 2.0, 4.0, 8.0]

async def _get_with_backoff(self) -> list[dict[str, Any]]:
    last_exc: BaseException | None = None
    for delay in _BACKOFF_DELAYS:
        try:
            result = await self.rest.get_markets()
            return result
        except Exception as exc:
            last_exc = exc
            self._fail_count += 1
            await asyncio.sleep(delay)
    raise last_exc
```

**Loop-forever pattern** (`data/poller/e_liq_poller.py` lines 148–152):
```python
async def loop(self) -> None:
    """Continuous polling loop — runs until cancelled."""
    while True:
        await self.run_one_cycle()
        await asyncio.sleep(self.interval)
```

**AMM-share subtraction (EXACT reuse) pattern** — Phase 2 already built this:
```python
from ..fill_model.amm_consumption import compute_amm_share_timeseries
# Σ_others = SUM(raw_book in range) - Q_me
# AMM share is NOT in Σ_others because AMMs don't compete for LO Liquidity Rewards.
```
See `fill_model/amm_consumption.py` lines 35–86 for the full `compute_amm_share_timeseries` signature.

**Parquet + DuckDB read pattern** — use `brain.duckdb_layer.setup.open_analytical_conn` per `screener/cli.py` line 39:
```python
from ..duckdb_layer.setup import open_analytical_conn
conn = open_analytical_conn(config.infra.sqlite_path, "data/parquet/")
```

**Single-writer writer pattern** — from `state/writers/reward_budget_history.py`:
```python
from ..state.writers.competition_history import insert_competition_row
# ...
insert_competition_row(self.conn, snapshot=snapshot)
```

**Deltas vs analog:**
- Two cadences in one class: REST poll at 5s (`config.reward_share_model.competition_poll_interval_s`), parquet aggregation at 1 Hz for sub-second freshness of `Σ_others`. Implement as two coroutines inside the class OR one cycle that does both on every REST tick (simpler — the parquet read is cheap).
- Degraded event name: `competition_tracker.rest_degraded` (NOT `poller.e_liq.degraded`).
- Fallback mode per RESEARCH §REWARD-02 line 560: `data_source='fallback_parquet_only'` — estimate `Q_me` from SQLite `open_orders` (Phase 1 writer).
- `_BACKOFF_DELAYS` same `[0.5, 1.0, 2.0, 4.0, 8.0]` (matches `e_liq_poller.py` line 33).
- `_fail_count` threshold: `config.reward_share_model.fallback_to_parquet_after_rest_fails_n` (default 5, RESEARCH line 1060) — replaces the hardcoded `>= 5` at `e_liq_poller.py` line 96.

**Gotchas:**
- POST /open-api/v2/accounts/all-limit-orders needs `{userAddress, accountId}` body (verified in RESEARCH §REWARD-02 lines 547–555). The existing `make_boros_rest_client` at `data/rest_client.py` returns an `httpx.AsyncClient` that can POST; extend the pattern — do NOT create a new client.
- `now_cached()` call: `await get_chain_time_cached()` from `data.chain_time` — matches `e_liq_poller.py` line 104 pattern.
- `competition_tracker.py` will live under the expanded lint-banned dir list (RESEARCH §Modified line 812). Same sentinel-created_at discipline as `fill_model/fit.py` for any persisted timestamps.

---

### `python/src/boros_brain/sizer/optimizer.py` — `q_me_target` sync aggregator

**Role:** Pure sync function `q_me_target(req: SizerInput, *, sqlite_path, config) -> SizerOutput`. Calls `fill_model.predict`, `loss_model.expected_loss`, `reward_model.r_capped_curve`, `reward_model.compute_q_cap`; runs 1-D bracketed optimization over `Q_me ∈ [Q_min, Q_max]`. At $100 collateral returns `Q_min` deterministically per RESEARCH §REWARD-03 line 597.

**Data flow:** sync fan-out — reads all three model layers via their public sync contracts; returns `SizerOutput`.

**Analog:** `python/src/boros_brain/screener/filter.py::apply_screener_filters` (multi-source aggregator returning a result dataclass) + `python/src/boros_brain/fill_model/predict.py::predict` (sync contract shape).

**Imports pattern** (`fill_model/predict.py` lines 14–30 + `screener/filter.py` lines 18–38):
```python
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import scipy.optimize  # new dependency per REWARD-03 algorithm step 5
import structlog

from ..config.schema import BotConfig
from ..fill_model.predict import PredictInput, predict
from ..loss_model.expected_loss import ExpectedLossInput, LossModelNoFreshGridError, expected_loss
from ..reward_model.q_cap import compute_q_cap
from ..reward_model.r_capped import r_capped_curve
from ..reward_model.schemas import RewardCurveInput
from .schemas import SizerInput, SizerOutput

log = structlog.get_logger(__name__)

__all__ = ["q_me_target"]
```

**Multi-source orchestration pattern** (`screener/filter.py` lines 74–244 — the whole `apply_screener_filters` function):
The key structural moves:
1. Fetch inputs from multiple upstream sources (DuckDB queries + Pydantic config).
2. Compute derived values with named exception propagation.
3. Return a frozen result dataclass.

**1-D bracketed optimization** — no in-repo analog; use `scipy.optimize.minimize_scalar` per RESEARCH §REWARD-03 step 5 (line 644):
```python
# Step 1-2: collapse Q interval at $100 collateral
q_min = config.sizer.q_min_pendle
q_max = (req.collateral_usd * config.sizer.q_max_safety_margin) / config.sizer.notional_per_yu_usd

# Step 3: Q_cap
q_cap = compute_q_cap(
    sigma_others_pendle=req.sigma_others_pendle,
    e_liq_per_epoch_pendle=req.e_liq_per_epoch_pendle,
    side_split=req.side_split,
    t_frac=req.t_frac,
    collateral_usd=req.collateral_usd,
    pendle_price_usd=req.pendle_price_usd,
    epoch_days=7.0,
)

# Step 4: market-saturated shortcut
if q_cap < q_min:
    return SizerOutput(q_me_target_pendle=q_min, regime="market_saturated", ...)

# Step 5: grid search + scipy polish
upper = min(q_max, q_cap)
q_grid = np.logspace(np.log10(q_min), np.log10(upper), config.sizer.optimizer_grid_points)
objectives = np.array([_ev_objective(q, req, sqlite_path, config) for q in q_grid])
q0 = q_grid[np.argmax(objectives)]
res = scipy.optimize.minimize_scalar(
    lambda q: -_ev_objective(q, req, sqlite_path, config),
    bounds=(q_min, upper),
    method="bounded",
)
return SizerOutput(q_me_target_pendle=res.x, ...)
```

**Sync-predict call pattern** (`fill_model/predict.py` lines 53–158 — the entire function):
```python
pred = predict(
    PredictInput(
        market_id=req.market_id,
        side=req.side,
        depth_from_mark_ticks=req.depth_from_mark_ticks,
        queue_ahead_wei=req.queue_ahead_wei,
        current_features=req.current_features,
        time_to_epoch_end_s=req.time_to_epoch_end_s,
        current_chain_ts=req.current_chain_ts,
    ),
    sqlite_path=sqlite_path,
    config=config,
)
```

**Exception-propagation pattern** (`fill_model/predict.py` lines 77–88):
- `FillModelStaleFeatureError` / `FillModelNoFreshFitError` propagate upward (Phase 4 DecisionEngine suppresses PLACE commands).
- `LossModelNoFreshGridError` likewise propagates (RESEARCH §REWARD-03 lines 649–650).

**Deltas vs analog:**
- NEW dependency: `scipy` (already in CLAUDE.md stack list and must be added to `pyproject.toml` if not already — confirmed via Phase 2's calibration.py path).
- `InsufficientCollateralError` new named exception per RESEARCH §REWARD-03 line 648 — raise when `Q_min > Q_max`.
- `config.sizer.optimizer_method: Literal["grid_only", "grid_plus_scipy", "scipy_only"]` — dispatch on this flag.
- At $100 collateral, `Q_max ≈ Q_min` (collateral-constrained), so the optimizer shortcut returns `Q_min` trivially. Test this deterministically per RESEARCH §REWARD-03 line 597 / Success Criterion #3.

**Gotchas:**
- `time_to_epoch_end_s` comes in via `SizerInput` — caller (Phase 4 DecisionEngine) supplies. No wall-clock / chain_time call inside `optimizer.py`.
- `sizer/optimizer.py` is under the banned dirs (RESEARCH §Modified line 812) — no `time.time()`, no `datetime.now()`. All timestamps come in via `SizerInput.current_chain_ts`.
- Cross-package imports are OK (`from ..fill_model.predict import ...`). Phase 2 locked the `fill_model.predict` signature (CLAUDE.md + RESEARCH §Phase Dependencies line 1252) — do NOT change it.

---

### `python/src/boros_brain/state/writers/loss_grid_artifacts.py` — single-writer for `state.loss_grid_artifacts`

**Role:** `insert_loss_grid_artifact(sqlite_path, artifact)` + `get_latest_loss_grid(sqlite_path, market_id, side)`. Single-writer discipline per INFRA-03.

**Data flow:** writes `state.loss_grid_artifacts`; read by `expected_loss.py` and `sizer.optimizer`.

**Analog:** `python/src/boros_brain/state/writers/fill_model_fits.py` — EXACT precedent (mirror line-for-line).

**Full file pattern to mirror** (`state/writers/fill_model_fits.py` lines 1–119 — entire file):
```python
"""Single writer for the `fill_model_fits` table (brain-owned).

PROTO-02 single-writer discipline. Only `brain.fill_model.artifact.write_fit_artifact`
imports insert_fit_artifact. `brain.fill_model.predict.predict` imports `get_latest_fit`
(read, not write — lint doesn't care).

Any `INSERT INTO fill_model_fits` / `UPDATE fill_model_fits` / `DELETE FROM fill_model_fits`
outside this module triggers scripts/sqlite_writer_lint.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import structlog

from boros_brain.state.db import open_connection

from ...fill_model.schemas import FitArtifact

log = structlog.get_logger(__name__)

__all__ = ["insert_fit_artifact", "get_latest_fit"]


def insert_fit_artifact(sqlite_path: Path, artifact: FitArtifact) -> None:
    """Insert one fit artifact. Self-contained — manages its own connection."""
    with open_connection(sqlite_path) as conn:
        conn.execute(
            """
            INSERT INTO fill_model_fits (
                run_id, fit_window_start_ts, ..., created_at
            ) VALUES (?, ?, ..., ?)
            ON CONFLICT(market_id, side, fit_window_end_ts) DO UPDATE SET
                run_id = excluded.run_id, ...
            """,
            (artifact.run_id, artifact.fit_window_start_ts, ...),
        )
    log.info(
        "fill_model.fit_artifact_persisted",
        market_id=artifact.market_id,
        side=artifact.side,
        fit_window_end_ts=artifact.fit_window_end_ts,
        fit_status=artifact.fit_status,
        n_observations=artifact.n_observations,
    )


def get_latest_fit(sqlite_path: Path, market_id: str, side: str) -> FitArtifact | None:
    """Return the most-recent-by-fit_window_end_ts artifact for (market_id, side)."""
    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            """SELECT run_id, fit_window_start_ts, ..., created_at
               FROM fill_model_fits
               WHERE market_id = ? AND side = ?
               ORDER BY fit_window_end_ts DESC LIMIT 1""",
            (market_id, side),
        ).fetchone()
    if row is None:
        return None
    return FitArtifact(run_id=row[0], fit_window_start_ts=row[1], ...)
```

**UPSERT pattern** — `ON CONFLICT(market_id, side, fit_window_end_ts) DO UPDATE SET ...` (fill_model_fits lines 37–52): supports idempotent re-writes of the same `(market_id, side, window_end_ts)` artifact without duplicates.

**JSON-serialize list columns** (fill_model_fits lines 60–61):
```python
json.dumps(artifact.covariate_whitelist),  # list[str] -> TEXT
json.dumps(artifact.beta),                  # list[float] -> TEXT
```

**Deltas vs analog:**
- Table name: `loss_grid_artifacts`.
- PK: `(market_id, side, window_end_ts)`.
- List columns (`depth_bucket_edges`, `tau_bucket_edges`, `cells`) serialized as JSON TEXT.
- `get_latest_loss_grid` single-row SELECT by `(market_id, side)` ORDER BY `window_end_ts DESC LIMIT 1`.

---

### `python/src/boros_brain/state/writers/competition_history.py` — single-writer for `state.competition_history`

**Role:** `insert_competition_row(conn, snapshot)` + `get_latest_competition(sqlite_path, market_id)`. Uses B6-style `data_source` CHECK constraint.

**Analog:** `python/src/boros_brain/state/writers/reward_budget_history.py` — EXACT precedent for the B6 pattern (wall-clock ISO8601 `polled_at_utc`, `data_source` CHECK constraint, caller-owns-transaction discipline).

**Full file pattern to mirror** (`state/writers/reward_budget_history.py` lines 1–72):
```python
"""Single writer for the `reward_budget_history` table (brain-owned).

PROTO-02 single-writer discipline. DATA-11 polled E_liq writes here only.

**B6 pitfall guard:** `data_source` must be 'polled' (forward-only live poll)
or 'synthetic_current' (historical backfill reconstructed from current budget).
The DB CHECK constraint enforces this at the SQL layer; this writer also rejects
invalid values at the Python layer so callers get a clean error before the SQL
round-trip.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal

DataSource = Literal["polled", "synthetic_current"]
_ALLOWED: frozenset[str] = frozenset({"polled", "synthetic_current"})


def insert_reward_budget_row(
    conn: sqlite3.Connection,
    *,
    market_id: str,
    e_liq_per_epoch: float,
    # ...
    run_id: str,
    data_source: DataSource = "polled",
) -> None:
    if data_source not in _ALLOWED:
        raise ValueError(f"data_source={data_source!r} not in {sorted(_ALLOWED)} (B6 pitfall guard)")
    conn.execute(
        "INSERT INTO reward_budget_history "
        "(polled_at_utc, chain_ts, market_id, e_liq_per_epoch, long_budget, short_budget, run_id, data_source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(UTC).isoformat(),
            chain_ts,
            market_id,
            # ...
            data_source,
        ),
    )
    # Do NOT call conn.commit() here — caller owns transaction lifecycle (db.py contract).
```

**Deltas vs analog:**
- `DataSource = Literal["live", "fallback_parquet_only"]` per RESEARCH §REWARD-02 line 538 (DIFFERENT values than reward_budget_history's `["polled", "synthetic_current"]`).
- No `e_liq_per_epoch` / budget columns; instead `q_me_pendle`, `sigma_others_pendle`.
- For the `MarketRewardCalibration` operator-manual flow (RESEARCH lines 1086–1100, table `reward_budget_history` sidecar): when the daily re-screen writes a row derived from the dApp UI calibration, use `data_source='operator'` — **this requires extending the existing `reward_budget_history` CHECK constraint** in a new migration (0002's constraint is `('polled','synthetic_current')`). The RESEARCH §Modified in Phase 3 list (lines 806–816) does NOT include a `reward_budget_history` schema change, so re-read RESEARCH §MarketRewardCalibration flow before locking — my read of lines 1085–1100 + 800 suggests `market_reward_calibration` lives in `BotConfig.markets[].reward_calibration`, NOT in the `reward_budget_history` table. No migration needed for operator values; they live in the config YAML.

**Gotchas:**
- Caller-owns-transaction contract per line 68: do NOT `conn.commit()` inside the insert helper. This matches `reward_budget_history.py` CR-03 fix note.
- The two-function split (`insert_*_snapshot(conn, ...)` low-level + `insert_*_history(sqlite_path, ...)` self-contained) from `state/writers/clo_history.py` lines 30–91 is the optional richer pattern if both patterns are needed. For Phase 3, pick the single-pattern approach from `reward_budget_history.py` (simpler — CompetitionTracker already holds its own connection).

---

### `python/src/boros_brain/state/migrations/versions/0004_loss_grid_artifacts.py` — Alembic migration

**Role:** Create `state.loss_grid_artifacts` table + index. Idempotent — detects if `schemas.sql` was already updated.

**Analog:** `python/src/boros_brain/state/migrations/versions/0003_fill_model_fits.py` — EXACT precedent (mirror line-for-line).

**Full file pattern to mirror** (`state/migrations/versions/0003_fill_model_fits.py` lines 1–83 — entire file):
```python
"""Add fill_model_fits table + index.

Revision ID: 0003_fill_model_fits
Revises: 0002
Create Date: 2026-04-24

Idempotency: schemas.sql (executed by 0001) already includes fill_model_fits DDL
using CREATE TABLE IF NOT EXISTS, so on a fresh database the table is created by
0001. This migration detects that case via inspection and only creates the table
and index if they don't already exist — matching the same pattern used by 0002
for the reward_budget_history idempotency.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0003_fill_model_fits"
down_revision = "0002"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table in inspector.get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    indexes = [ix["name"] for ix in inspector.get_indexes(table)]
    return index_name in indexes


def upgrade() -> None:
    if not _has_table("fill_model_fits"):
        op.create_table(
            "fill_model_fits",
            sa.Column("run_id", sa.Text(), nullable=False),
            # ... per-column declarations ...
            sa.CheckConstraint("side IN ('long','short')", name="ck_fill_model_fits_side"),
            sa.CheckConstraint("fit_status IN ('ok','degraded','stale')", name="ck_fill_model_fits_status"),
            sa.PrimaryKeyConstraint("market_id", "side", "fit_window_end_ts"),
        )

    if not _has_index("fill_model_fits", "ix_fill_model_fits_market_side_end"):
        op.create_index(
            "ix_fill_model_fits_market_side_end",
            "fill_model_fits",
            ["market_id", "side", sa.text("fit_window_end_ts DESC")],
        )


def downgrade() -> None:
    if _has_index("fill_model_fits", "ix_fill_model_fits_market_side_end"):
        op.drop_index("ix_fill_model_fits_market_side_end", table_name="fill_model_fits")
    if _has_table("fill_model_fits"):
        op.drop_table("fill_model_fits")
```

**CRITICAL: schemas.sql round-trip** (`state/schemas.sql` lines 160–204 — the full `fill_model_fits` DDL stanza) — DDL lives in `schemas.sql` FIRST, migration second. Every new table in Phase 3 requires:
1. Append table DDL (`CREATE TABLE IF NOT EXISTS ...` with CHECK constraints) to `schemas.sql`.
2. Author the Alembic migration (this file) that creates the table idempotently via `_has_table` gate.

**Deltas for `0004_loss_grid_artifacts.py`:**
- `revision = "0004_loss_grid_artifacts"`, `down_revision = "0003_fill_model_fits"`.
- Table name `loss_grid_artifacts`.
- Columns per RESEARCH §storage nodes line 944–947: `market_id`, `side`, `window_end_ts`, `window_start_ts`, `run_id`, `fit_status`, `depth_bucket_edges` (JSON TEXT), `tau_bucket_edges` (JSON TEXT), `cells_json` (JSON TEXT), `event_index_coverage`, `created_at`.
- PK: `(market_id, side, window_end_ts)`.
- Index: `(market_id, side, window_end_ts DESC)`.

**Deltas for `0005_competition_history.py`:**
- `revision = "0005_competition_history"`, `down_revision = "0004_loss_grid_artifacts"`.
- Table DDL per RESEARCH §REWARD-02 lines 567–578:
  ```sql
  CREATE TABLE competition_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      polled_at_utc TEXT NOT NULL,
      chain_ts INTEGER,
      market_id TEXT NOT NULL,
      q_me_pendle REAL NOT NULL,
      sigma_others_pendle REAL NOT NULL,
      data_source TEXT NOT NULL CHECK(data_source IN ('live','fallback_parquet_only')),
      run_id TEXT NOT NULL
  );
  CREATE INDEX ix_competition_market_polled ON competition_history (market_id, polled_at_utc DESC);
  ```
- B6-style CHECK constraint on `data_source` per `reward_budget_history` lines 153 pattern.

**Gotchas:**
- Both migrations must append to `schemas.sql` in the same commit (PROTO-02 discipline — CLAUDE.md L13).
- Use `sa.text("window_end_ts DESC")` for descending index columns (matches 0003_fill_model_fits.py line 74).

---

### `python/src/boros_brain/config/schema.py` — add Phase 3 sub-model fields

**Role:** Extend top-level `BotConfig` with four new sub-models + extend `MarketCalibration` with `reward_calibration` field + add new `MarketRewardCalibration` sub-model.

**Analog:** self — the existing `fill_model: FillModelConfig = Field(default_factory=FillModelConfig)` attachment at line 136 is the exact pattern.

**Existing BotConfig attachment pattern** (`config/schema.py` lines 117–137):
```python
class BotConfig(StrictBase):
    """Top-level config. One instance per run; frozen after load."""

    mode: Literal["live", "paper", "backtest", "ingest", "screen"]
    strategy_version: str
    # ... top-level fields ...

    strategy: StrategyConfig = Field(default_factory=StrategyConfig)  # type: ignore
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)  # type: ignore
    data: DataConfig
    infra: InfraConfig = Field(default_factory=InfraConfig)  # type: ignore
    screener: ScreenerConfig = Field(default_factory=ScreenerConfig)  # type: ignore
    fill_model: FillModelConfig = Field(default_factory=FillModelConfig)  # type: ignore
    markets: list[MarketCalibration] = Field(default_factory=list, max_length=1)
```

**MarketCalibration extension pattern** (`config/schema.py` lines 105–114 — the existing class to modify):
```python
class MarketCalibration(StrictBase):
    """Per-market calibration (OU params + CLO bands + oracle addr + maturity)."""

    market_id: str
    scale: float
    s: float
    clo_lower_thresh: float
    clo_upper_thresh: float
    fIndex_oracle_address: str
    maturity_ts: int
```

**Deltas:**
- 4 new imports at top:
  ```python
  from ..loss_model.config import LossModelConfig
  from ..reward_model.config import RewardShareModelConfig
  from ..sizer.config import SizerConfig
  from ..pricing.config import PricingConfig
  ```
- 4 new attachments per RESEARCH lines 1115–1118:
  ```python
  loss_model: LossModelConfig = Field(default_factory=LossModelConfig)        # type: ignore
  reward_share_model: RewardShareModelConfig = Field(default_factory=RewardShareModelConfig)   # type: ignore
  sizer: SizerConfig = Field(default_factory=SizerConfig)                     # type: ignore
  pricing: PricingConfig = Field(default_factory=PricingConfig)               # type: ignore
  ```
- Add `class MarketRewardCalibration(StrictBase)` per RESEARCH lines 1086–1100 (new class, placed near `MarketCalibration`).
- Extend `MarketCalibration` with `reward_calibration: MarketRewardCalibration | None = None` (line 1110 of RESEARCH).

**Gotchas:**
- Check for circular imports: `loss_model/config.py` cannot import from `config/schema.py` (nor can the other three). They use local `StrictBase` re-declarations — see `fill_model/config.py` lines 19–25 pattern.
- `test_manifest_contains_all_knobs.py::_collect_leaf_paths` at lines 53–76 auto-reflects — no test edit needed. Add defensive spot-checks in the same test file mirroring `test_fill_model_leaves_surfaced` at lines 118–134 to catch accidental schema drift.

---

### `python/src/boros_brain/main.py` — spawn Phase 3 async tasks at boot

**Role:** Modify `run()` to spawn `run_loss_model_refit_loop` + `run_competition_tracker_loop` alongside the existing `run_fill_model_refit_loop`.

**Analog:** self — existing Phase 2 wiring at lines 140–142 + lines 146–149.

**Existing refit spawn pattern** (`main.py` lines 137–143):
```python
# Phase 2 Plan 02-04: synchronous initial fit (blocks ~30s on a warm market;
# required so predict() has an artifact before the 1 Hz decision loop starts).
# Skipped automatically in dry-run mode (the `return` above short-circuits).
from .fill_model.refit_loop import refit_once, run_fill_model_refit_loop
await refit_once(cfg, manifest.run_id)
refit_task = asyncio.create_task(run_fill_model_refit_loop(cfg, manifest.run_id))
```

**Existing cancel-on-shutdown pattern** (`main.py` lines 146–149):
```python
for t in (send_task, monitor_task, ingest_task, refit_task):
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
```

**Deltas:**
- Add after line 142:
  ```python
  from .loss_model.refit_loop import refit_once as loss_refit_once, run_loss_model_refit_loop
  from .reward_model.competition_tracker import run_competition_tracker_loop
  await loss_refit_once(cfg, manifest.run_id)  # sync initial loss-grid fit
  loss_refit_task = asyncio.create_task(run_loss_model_refit_loop(cfg, manifest.run_id))
  comp_task = asyncio.create_task(run_competition_tracker_loop(cfg, manifest.run_id))
  ```
- Extend the tuple in the shutdown block to include `loss_refit_task, comp_task`.
- Extend the `--dry-run` guard (line 109) if needed so these tasks are not created in dry-run (they are after the `dry_run return`, so already fine).

**Gotchas:**
- `loss_refit_once` is a rename to avoid shadowing the existing `refit_once` from `fill_model.refit_loop`. Or use module prefix: `from . import loss_model; await loss_model.refit_loop.refit_once(cfg, ...)`.
- The `main.py` file is NOT under the `no_time_time_lint.py` ban list — but the modules it imports are. Keep wall-clock calls out of the Phase 3 modules' bodies.

---

### `python/tests/test_loss_model_fit_and_expected_loss.py` — LOSS-01 + LOSS-02 tests

**Role:** Unit + property tests for `fit_loss_grid` (health gate, sparse-data degraded path) + `expected_loss` (staleness, sparse-cell fallback).

**Analog:** `python/tests/test_fill_model_fit_basic.py` (lines 1–124) + `test_fill_model_predict_contract.py` (referenced by 02-PATTERNS.md line 47).

**Test fixture config + migrations pattern** (`test_fill_model_fit_basic.py` lines 13–45):
```python
from boros_brain.config.schema import BotConfig, DataConfig
from boros_brain.fill_model.fit import fit_market_side
from boros_brain.fill_model.schemas import FitArtifact


def _tiny_config() -> BotConfig:
    return BotConfig(
        mode="backtest",
        strategy_version="test",
        market_id=MARKET_ID,
        side="long",
        root_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        data=DataConfig(rpc_url_arbitrum="https://example.com"),
    )


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config

    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
```

**Degraded-path assertion pattern** (`test_fill_model_fit_basic.py` lines 83–114):
```python
def test_fit_degrades_on_sparse(tmp_path: Path) -> None:
    """T-02-M-02 — 10-row input → fit_status='degraded' + no crash."""
    # ... small synthetic df ...

    db = tmp_path / "state.sqlite"
    _apply_migrations(db)

    config = _tiny_config()
    artifact = fit_market_side(...)
    assert artifact.fit_status == "degraded"
    assert len(artifact.beta) == 1 + len(artifact.covariate_whitelist)
```

**Deltas:**
- `test_loss_grid_health_gate_passes` — synthetic per-fill list with ≥ `min_samples_per_cell × n_cells` samples → `fit_status='ok'`, cells populated.
- `test_loss_grid_health_gate_degrades_on_sparse` — under-sampled input → `fit_status='degraded'`.
- `test_expected_loss_returns_exact_mode_for_populated_cell` — direct lookup.
- `test_expected_loss_returns_nearest_neighbor_for_sparse_cell` — assert `fallback_mode='nearest_neighbor'` + warning log.
- `test_expected_loss_returns_coarse_bound_for_all_sparse` — assert `fallback_mode='coarse_bound'` + the `fill_loss_coarse_bound` value.
- `test_expected_loss_raises_on_stale_grid` — assert `LossModelNoFreshGridError` when `fit_age_s > fit_max_staleness_s`.

**Gotchas:**
- Migrations must include `0004_loss_grid_artifacts` + `0005_competition_history` (the `alembic upgrade head` call picks them up automatically).
- Caplog for assertions on the `loss_model.sparse_cell_fallback` structlog event — use `pytest.LogCaptureFixture` + `structlog.testing` per the existing `test_e_liq_poller.py` pattern.

---

### `python/tests/test_reward_curve.py` — REWARD-01 + REWARD-04 numerics

**Role:** Unit + property tests for `r_capped_curve` + `compute_q_cap`.

**Analog:** `python/tests/test_economics_kill_switch.py` (closed-form formula tests) + `test_screener_metrics.py` (pure-numerics pattern).

**Pattern highlights:**
- At $100 collateral, assert `regime == 'sub_cap'` across realistic `Q_total_in_range` values for the candidate market (RESEARCH §REWARD-01 line 518).
- At $5000 collateral, assert `regime == 'cap_binding'` + `Q_cap < Q_max` for the ETHUSDT-29MAY2026 anchor (RESEARCH §REWARD-04 test matrix line 693).
- Property test: for any `Q_me > 0` and `Σ_others > 0`, `r_capped_curve(...).r_capped_pendle <= cap_budget_pendle`.
- Property test: `Σ_others == 0` → `regime == 'market_saturated'`.
- Edge cases: `pendle_price_usd == 0` raises `ValueError`; `e_liq_per_epoch_pendle < 0` raises `ValueError`.

---

### `python/tests/test_competition_tracker.py` — REWARD-02 polling + degraded mode

**Role:** Unit tests for CompetitionTracker REST poll + parquet read + fallback path.

**Analog:** `python/tests/test_e_liq_poller.py` (lines 1–100+) — exact test structure (stubs, migrations helper, mocked REST, degraded-event assertion).

**Stub pattern** (`test_e_liq_poller.py` lines 72–79):
```python
class StubEventPub:
    """Records published events instead of connecting to ZMQ."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    async def publish(self, topic: str, payload: dict) -> None:
        self.published.append((topic, payload))
```

**Config-stub pattern** (`test_e_liq_poller.py` lines 82–90):
```python
def _make_config(market_id: str = "ETHUSDT-29MAY2026", interval: float = 5.0) -> Any:
    cfg = MagicMock()
    cfg.data.e_liq_poll_interval_s = interval
    cfg.data.boros_rest_base = "https://api.boros.finance/open-api/v1"
    market = MagicMock()
    market.market_id = market_id
    cfg.markets = [market]
    return cfg
```

**Migrations helper** (`test_e_liq_poller.py` lines 50–66): reuse verbatim.

**Deltas:**
- `test_competition_tracker_writes_one_row_per_cycle` — no cross-poll dedup (parallel to test_e_liq_poller's `test_e_liq_poller_no_cache_writes_two_rows`).
- `test_competition_tracker_fallback_to_parquet_only_after_n_rest_failures` — mock REST to 503; assert `data_source='fallback_parquet_only'` on the persisted row after N failures (where N = `config.reward_share_model.fallback_to_parquet_after_rest_fails_n`).
- `test_competition_tracker_amm_share_subtracted` — build a `parquet.order_book_combined` fixture with a known AMM delta; assert `Σ_others` excludes that delta.
- `test_competition_history_data_source_check_constraint` — parallel to `test_e_liq_poller.py::test_data_source_check_constraint_rejects_invalid`.

---

### `python/tests/test_sizer.py` — REWARD-03 optimizer + $100-collateral determinism

**Role:** Unit tests for `q_me_target`.

**Analog:** `test_economics_kill_switch.py` (closed-form + CLI) + `test_fill_model_predict_contract.py` (sync contract test shape).

**Deltas:**
- `test_sizer_returns_q_min_at_100_collateral` — assert `q_me_target(...).q_me_target_pendle == config.sizer.q_min_pendle` for the ETHUSDT anchor (Success Criterion #3 per RESEARCH line 653).
- `test_sizer_scale_up_to_5000_collateral_enters_cap_binding` — assert `regime == 'cap_binding'` + `q_me_target_pendle < q_cap_pendle` (Success Criterion #3 scale-up branch).
- `test_sizer_propagates_fill_model_errors` — mock `fill_model.predict` to raise `FillModelStaleFeatureError`; assert `q_me_target` propagates it (no silent swallow).
- `test_sizer_propagates_loss_model_errors` — parallel for `LossModelNoFreshGridError`.
- `test_sizer_raises_insufficient_collateral` — assert `InsufficientCollateralError` when `Q_min > Q_max`.

---

## Shared Patterns

Every plan consuming Phase 3 files must apply these cross-cutting patterns. Cite these sections in each plan's `<read_first>`.

### MANIFEST-FIRST CLI boot (PROTO-01)

**Source:** `python/src/boros_brain/fill_model/cli.py` lines 66–91.

**Apply to:** `loss_model/cli.py`, `reward_model/cli.py`, `sizer/cli.py`.

**The load-bearing first 3 log events** per plan:
1. Load `BotConfig` via `load_config`.
2. `build_run_manifest(config)` + `configure_logging(run_id=manifest.run_id, tier='<name>', logs_dir=...)` + `write_manifest(...)`.
3. `log.info("RUN_MANIFEST", **manifest.model_dump())` as the FIRST structured log record.

**Exit code discipline:** `2` for ConfigError (operator mistake), `1` for domain exceptions (`LossModelNoFreshGridError`, `FillModelNoFreshFitError`, etc.), `0` for success.

---

### Single-writer SQLite discipline (PROTO-02)

**Source:** `python/src/boros_brain/state/writers/fill_model_fits.py` + `reward_budget_history.py`. Lint: `scripts/sqlite_writer_lint.py`.

**Apply to:** `state/writers/loss_grid_artifacts.py`, `state/writers/competition_history.py`.

**Contract:**
- Every SQLite table has ONE Python module in `state/writers/` that owns all `INSERT`/`UPDATE`/`DELETE`. Lint fails on any raw DML elsewhere.
- The writer module is self-contained — opens its own `open_connection(sqlite_path)` OR takes a caller-owned `conn: sqlite3.Connection` (two-function split per `state/writers/clo_history.py` lines 30–91).
- Callers OWN the transaction lifecycle (no `conn.commit()` inside the writer — see `reward_budget_history.py` line 68 CR-03 note).
- Reads are unrestricted — `get_latest_*` functions in the same module are fine (see `fill_model_fits.py::get_latest_fit` lines 85–119).

---

### Dual-write artifact (parquet-first, SQLite-second)

**Source:** `python/src/boros_brain/fill_model/artifact.py` lines 22–63.

**Apply to:** `loss_model/artifact.py`.

**Contract:** Parquet sidecar written first (orphan-tolerant), SQLite row second. Crash between them leaves parquet readable + no poisoned SQLite row.

---

### Sentinel-created_at escape hatch for banned dirs

**Source:** `fill_model/fit.py` line 101 (sentinel=0) + `fill_model/artifact.py` lines 36–38 (stamp in artifact writer).

**Apply to:** `loss_model/fit.py`, `loss_model/artifact.py`, `reward_model/competition_tracker.py`.

**Why:** `scripts/no_time_time_lint.py` bans `time.time()` in `brain/{decision,data,screener,fill_model}/` — Phase 3 extends to `loss_model/, reward_model/, sizer/`. Use `created_at=0` sentinel in the core modules; the artifact writer at the directory edge uses `datetime.now(UTC).timestamp()` (regex doesn't match).

---

### Chain-time async (INFRA-14)

**Source:** `python/src/boros_brain/data/chain_time.py` lines 204–208 + `fill_model/refit_loop.py` line 41.

**Apply to:** `loss_model/refit_loop.py`, `reward_model/competition_tracker.py`.

**Contract:** `from ..data import chain_time; now_s = await chain_time.now_cached()` — NEVER `time.time()` / `datetime.now()`.

---

### Pydantic StrictBase (PROTO-04)

**Source:** `python/src/boros_brain/config/schema.py` lines 22–30 (top-level `StrictBase`) + `fill_model/config.py` lines 19–25 (local re-declare for circular-import avoidance).

**Apply to:** ALL new Pydantic classes in `loss_model/`, `reward_model/`, `sizer/`, `pricing/`.

**Contract:** `model_config = ConfigDict(extra="forbid", frozen=True)`. `frozen=True` forces `.model_copy(update={...})` for mutation; `extra="forbid"` catches typos in YAML.

---

### RUN_MANIFEST reflection auto-coverage

**Source:** `python/tests/test_manifest_contains_all_knobs.py` lines 53–76 (`_collect_leaf_paths` + `_walk_dict_paths` reflection walker).

**Apply to:** NO changes required — adding `loss_model: LossModelConfig = Field(default_factory=LossModelConfig)` to `BotConfig` auto-registers every sub-model leaf. Add spot-check tests mirroring `test_fill_model_leaves_surfaced` (lines 118–134) for defensiveness only.

---

### Architecture.yml node + edge discipline (PROTO-02)

**Source:** `docs/architecture.yml` (every existing `brain.*` module node) — re-read before any change.

**Contract (CLAUDE.md L13):** Every commit that touches `python/` source also updates `docs/architecture.yml` + `docs/ARCHITECTURE.md`. The pre-commit hook `scripts/architecture_lint.py` fails on drift. For Phase 3, RESEARCH §Architecture Manifest Delta (lines 818–1006) enumerates all new nodes and edges — do not deviate.

---

### Spawn-from-main pattern (`asyncio.create_task`)

**Source:** `python/src/boros_brain/main.py` lines 141–142 + 146–149.

**Apply to:** Phase 3 adds `loss_refit_task` + `comp_task`.

**Contract:**
- Sync initial fit awaits (boot-block for fresh artifact).
- Long-running loop via `asyncio.create_task(...)` — do NOT `await` the loop itself.
- Cancel-on-shutdown: `task.cancel()` + `with contextlib.suppress(asyncio.CancelledError): await task`.

---

### Structured logging with `run_id` context

**Source:** `python/src/boros_brain/logging/structlog_setup.py` + every existing module's `log = structlog.get_logger(__name__)` + `log.info("event_name", **kwargs)` calls.

**Apply to:** All Phase 3 modules. Every log event name uses `dot_namespace`: `loss_model.fit_completed`, `loss_model.sparse_cell_fallback`, `reward_model.competition_tracker.rest_degraded`, `sizer.q_me_target_computed`, etc.

**Contract:** `run_id` is auto-included via structlog contextvars (installed by `configure_logging`). Never emit a bare `print()` — all diagnostics go through `log`.

---

### PENDLE-unit discipline

**Source:** `python/src/boros_brain/screener/economics_gate.py` lines 9–14 + lines 108–131.

**Apply to:** ALL reward-share math in `reward_model/` + `sizer/`. USD appears ONLY as `config.pricing.pendle_price_usd` and `config.sizer.collateral_usd` — converted to PENDLE at the point of use.

---

## No Analog Found

One Phase 3 file has NO exact in-repo structural precedent; planner should treat as greenfield (but still follow Shared Patterns).

| File | Role | Data Flow | Reason | Guidance |
|---|---|---|---|---|
| `python/src/boros_brain/loss_model/ou_parametric.py` | scaffold / Protocol | static | No pre-existing "NotImplementedError scaffold" module exists. Closest is the `@runtime_checkable Protocol` pattern at `data/poller/e_liq_poller.py` lines 36–44. | Use verbatim code from RESEARCH §LOSS-03 lines 392–423. Protocol signature must match `expected_loss.expected_loss()` — contract test at RESEARCH lines 432–441 enforces via `inspect.signature`. |

The `sizer/optimizer.py` 1-D bracketed optimization has no in-repo analog either (this would be the first `scipy.optimize.minimize_scalar` call in the codebase), but it's covered above as a "role-match" to `screener/filter.py::apply_screener_filters` (multi-source orchestration shape) + new `scipy` math per RESEARCH §REWARD-03 step 5.

---

## Metadata

**Analog search scope:**
- `python/src/boros_brain/` — full Python source tree
- `python/tests/` — full test suite
- `python/src/boros_brain/state/migrations/versions/` — all 3 existing migrations
- `.planning/phases/02-fill-model-nhpp-v0-5/02-PATTERNS.md` — Phase 2 pattern map for cross-check
- `.planning/phases/01-foundation-infrastructure-spine-data-pipeline-economics-gate/` — Phase 1 plans for migration pattern + B6 tag
- `docs/samples/markets-response.json` (referenced by RESEARCH §E_liq Source Resolution line 702)
- `docs/architecture.yml` — existing node/edge rows
- `LLM Wiki/workspaces/boros/` — page index (via RESEARCH citations)

**Files scanned:** 48 Python source files + 46 test files + 3 migrations + 2 planning MDs + 1 schemas.sql + 1 architecture.yml.

**Pattern extraction date:** 2026-04-24

**Key insight:** The `fill_model/` package IS the Phase 3 pattern library. Every new `loss_model/` file has a 1-for-1 structural analog. The `reward_model/` splits cleanly into formula modules (analog: `screener/economics_gate.py`) + a polling loop (analog: `data/poller/e_liq_poller.py`). The `sizer/` is a sync aggregator (analog: `screener/filter.py::apply_screener_filters` + `fill_model/predict.py::predict`). No greenfield except `ou_parametric.py` (scaffold-only Protocol) and the `scipy.optimize.minimize_scalar` call inside `sizer/optimizer.py`.
