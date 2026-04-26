# Phase 4: Decision Engine + Predictive Circuit Breakers — Pattern Map

**Mapped:** 2026-04-25
**Files analyzed:** 28 net-new source files + 17 net-new test files + 2 net-new lint scripts + 1 alembic migration + 1 main.py edit + 1 architecture.yml/Mermaid edit
**Analogs found:** 28 / 28 source files (100% — Phase 4 is a wiring phase that mirrors Phase 2/3 grain exactly)
**Search scope:** `python/src/boros_brain/{fill_model,loss_model,reward_model,data,state,bus,manifest}/`, `python/tests/`, `scripts/`, `ts/src/boros_hands/bus/`

---

## File Classification

### Engine family (5 files)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `python/src/boros_brain/decision/engine.py` | service | request-response (sync per-order EV evaluator) | `python/src/boros_brain/loss_model/expected_loss.py` | exact (sync sub-100ms compute calling other sync models + writer reads) |
| `python/src/boros_brain/decision/schemas.py` | model | data shapes | `python/src/boros_brain/loss_model/schemas.py` | exact (dataclass + Pydantic StrictBase, custom RuntimeError subclasses) |
| `python/src/boros_brain/decision/config.py` | config | n/a | `python/src/boros_brain/fill_model/config.py` | exact (StrictBase sub-model with Field-bounded numeric knobs + nested sub-models) |
| `python/src/boros_brain/decision/gas_history.py` | service | request-response with TTL cache → external RPC | `python/src/boros_brain/data/chain_time.py` (ChainTimeCache) | role-match (TTL-cached value + RPC fallback + warn-log on stale) |
| `python/src/boros_brain/decision/__init__.py` | package init | n/a | `python/src/boros_brain/state/writers/__init__.py` | role-match (single-line per-module re-export) |

### Breakers family (12 files)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `python/src/boros_brain/decision/breakers/base.py` | model + ABC | data shape + interface | `python/src/boros_brain/reward_model/schemas.py` (StrictBase + Literal types) | role-match (no ABC analog exists; combine StrictBase pattern with stdlib `abc.ABC`) |
| `python/src/boros_brain/decision/breakers/__init__.py` | package init | n/a | `python/src/boros_brain/state/writers/__init__.py` | role-match |
| `python/src/boros_brain/decision/breakers/margin_trajectory.py` | service (stateful per-cycle) | reads `state.margin_history`, returns BreakerSignal | `python/src/boros_brain/reward_model/competition_tracker.py` (CompetitionTracker.run_one_cycle) | role-match (stateful per-cycle; reads SQLite history + writes downstream signal) |
| `python/src/boros_brain/decision/breakers/oracle_stale.py` | service | reads `findex_reader`, returns BreakerSignal | `python/src/boros_brain/data/findex_reader.py` (caller pattern) | role-match |
| `python/src/boros_brain/decision/breakers/clo_removal.py` | service | reads `state.clo_history`, returns BreakerSignal | competition_tracker `run_one_cycle` | role-match |
| `python/src/boros_brain/decision/breakers/clo_shift.py` | service | reads `state.clo_history`, returns BreakerSignal | competition_tracker | role-match |
| `python/src/boros_brain/decision/breakers/fill_rate.py` | service | reads `state.tx_receipts`, returns BreakerSignal | competition_tracker | role-match |
| `python/src/boros_brain/decision/breakers/competition.py` | service | reads `state.competition_history`, returns BreakerSignal | competition_tracker | role-match |
| `python/src/boros_brain/decision/breakers/maturity.py` | service | calls `gas_history`, returns BreakerSignal | engine.evaluate composition (this phase) | role-match |
| `python/src/boros_brain/decision/breakers/side_budget.py` | service | reads `state.market_reward_calibration`, returns BreakerSignal | competition_tracker | role-match |
| `python/src/boros_brain/decision/breakers/underlying_stale.py` | service | reads parquet via DuckDB, returns BreakerSignal | `python/src/boros_brain/duckdb_layer/` (CompetitionTracker `_read_sigma_others_from_parquet`) | role-match |
| `python/src/boros_brain/decision/breakers/loss_fit_degraded.py` | service | reads `state.loss_grid_artifacts`, returns BreakerSignal | competition_tracker | role-match |

### Coordinator + CLI (4 files)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `python/src/boros_brain/decision/breaker_coordinator.py` | service (event-driven) | calls `bus.cmd.send_kill`, writes `state.breaker_events` | `python/src/boros_brain/bus/cmd.py` (caller side from main.py) + competition_tracker | role-match (composes existing CmdBus + writer) |
| `python/src/boros_brain/decision/predeploy_gate.py` | CLI script | one-shot read+write+exit | `python/src/boros_brain/screener/` CLI scripts (call `screener.economics_gate` + `wiki_cite_lint` interaction) | role-match |
| `python/src/boros_brain/decision/cli.py` | CLI | argparse + asyncio.run + manifest-first | `python/src/boros_brain/fill_model/cli.py` | exact (subcommand argparse + manifest-first preamble + per-cmd dispatch) |
| `python/src/boros_brain/decision/__main__.py` | CLI entry | `python -m boros_brain.decision` | `python/src/boros_brain/fill_model/__main__.py` | exact (6-line passthrough) |

### State writers (4 files)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `python/src/boros_brain/state/writers/margin_history.py` | writer (single-writer-per-table) | INSERT INTO margin_history; SELECT for breaker reads | `python/src/boros_brain/state/writers/competition_history.py` | exact (chain_ts + market_id + run_id pattern with `insert_X` + `get_latest_X`) |
| `python/src/boros_brain/state/writers/competition_history.py` (touch — add new edge to existing module) | writer | (already exists) — Phase 4 adds edge from `brain.reward_model.competition_tracker → state.competition_history` to architecture.yml | n/a (file already exists) | n/a |
| `python/src/boros_brain/state/writers/breaker_events.py` | writer | INSERT INTO breaker_events; append-only audit log | `python/src/boros_brain/state/writers/decisions.py` | exact (slim INSERT-only writer with `kind` enum guarded by SQL CHECK) |
| `python/src/boros_brain/state/writers/predeploy_gate_records.py` | writer | INSERT INTO predeploy_gate_records (one row per CLI run) | `python/src/boros_brain/state/writers/run_manifests.py` | exact (config_json hash + git_sha row pattern) |

### Migrations + Pollers (2 files)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py` | migration | DDL for 4 new tables in one revision | `python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py` | exact (idempotent inspect-then-create pattern; 4 tables in one revision is allowed — see RESEARCH note "one new migration version covers all 4 new tables") |
| `python/src/boros_brain/data/poller/margin_poller.py` | poller (1 Hz) | POST `/accounts/get-net-margin` → INSERT INTO margin_history | `python/src/boros_brain/data/poller/e_liq_poller.py` | exact (run_one_cycle + loop + REST + writer + degraded-mode event after N consecutive failures) |

### Lint scripts (2 files)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `scripts/no_hardcoded_cancel_cost_lint.py` | lint script | walk .py files → grep regex → exit 0/1 | `scripts/no_time_time_lint.py` | exact (PROTECTED_DIRS + ALLOWED_FILES + PATTERN regex + main returning 0/1) |
| `scripts/no_threshold_dials_lint.py` | lint script | walk .py files → grep regex of forbidden tokens → exit 0/1 | `scripts/no_time_time_lint.py` | exact (same structure; different pattern) |

### Tests (17 files + 1 conftest extension)

| New Test File | Role | Closest Analog | Match Quality |
|---------------|------|----------------|---------------|
| `python/tests/test_decision_engine_ev_equation.py` | unit + hypothesis | `python/tests/test_fill_model_predict_contract.py` | exact (hypothesis property + `_seed_fit` helper + `_apply_migrations` + `pytest.raises` propagation) |
| `python/tests/test_decision_engine_voluntary_branch.py` | unit + parametrize | `test_fill_model_predict_contract.py` | exact |
| `python/tests/test_gas_history_ewma.py` | unit + mock w3 | `test_competition_tracker.py` (StubEventPub + `unittest.mock.AsyncMock`) | exact |
| `python/tests/test_no_threshold_dials_lint.py` | lint script test | `python/tests/test_no_time_time_in_hotpath.py` | exact (call lint `main()` directly, assert exit code) |
| `python/tests/test_breaker_*.py` (×10) | unit + writer-helper fixture | `test_fill_model_predict_contract.py::_seed_fit` + `test_competition_tracker.py::_migrated_db` | exact (use writer functions to seed history, then call breaker.check directly) |
| `python/tests/test_breaker_coordinator_exclusive.py` | unit + fake CmdBus | `test_zmq_kill_priority.py` | exact (KILL preempt pattern with real CmdBus over `ipc://` ipc_dir fixture) |
| `python/tests/test_predeploy_gate_cli.py` | integration | `test_fill_model_predict_contract.py` + screener CLI tests | role-match |
| `python/tests/test_main_decision_loop_spawn.py` | integration | `test_competition_tracker.py` (asyncio.run pattern + tracker spawn fixture) | role-match |
| `python/tests/test_phase4_manifest_leaves.py` | unit (reflection) | `python/tests/test_manifest_contains_all_knobs.py::test_phase3_leaves_surfaced` | exact (mirror line-for-line; assert `>=25 NEW Phase 4 leaves`) |
| `python/tests/conftest.py` (extension) | fixture | existing conftest.py | exact (append `breaker_history_fixtures` helper functions) |

### Infra delta (3 files)

| File | Role | Data Flow | Analog |
|------|------|-----------|--------|
| `python/src/boros_brain/main.py` (edit) | entry-point edit | spawn block extension + chain_cache.halt_callback wire-up | the existing `main.py` lines 144-196 (Phase 2/3 spawn pattern) |
| `docs/architecture.yml` (edit) | architecture manifest | append ~22 module nodes + 4 storage nodes + ~30 config_knob nodes + ~80 edges | existing architecture.yml (Plan 03-04 precedent: ATOMIC delta in last plan of phase) |
| `docs/ARCHITECTURE.md` (edit) | mermaid diagram | append nodes + edges to mirror yml | existing ARCHITECTURE.md |

---

## Pattern Assignments

### Engine family

#### `decision/engine.py` (service, sync request-response)

**Analog:** `python/src/boros_brain/loss_model/expected_loss.py` (lines 1-100)
**Why:** sync `<10ms` budget, raises typed errors (NEVER swallows), composes other sync models + writer reads, `current_chain_ts: int` parameter convention.

**Module-docstring + import pattern** (mirror lines 1-40 of `loss_model/expected_loss.py`):

```python
"""DECIDE-01/02 sync EV-based cancel rule.

Contract:
    - SYNC (not async) compute, callable from the 1 Hz loop. p95 < 100ms budget.
    - Errors propagate (NEVER swallow): FillModelStaleFeatureError,
      FillModelNoFreshFitError, LossModelNoFreshGridError.
    - Cancel iff EV_hold < 0.

Design-locked. Any change to this signature is a breaking change.
[[ev-cancel-rule]]
"""
from __future__ import annotations

from pathlib import Path

import structlog

from ..config.schema import BotConfig
from ..fill_model.predict import predict
from ..fill_model.schemas import (
    FillModelNoFreshFitError,
    FillModelStaleFeatureError,
    PredictInput,
)
from ..loss_model.expected_loss import expected_loss
from ..loss_model.schemas import ExpectedLossInput, LossModelNoFreshGridError
from ..reward_model.r_capped import r_capped_curve
from ..reward_model.schemas import RewardCurveInput
from .gas_history import GasHistoryCache
from .schemas import EvaluateInput, EvaluateOutput

log = structlog.get_logger(__name__)

__all__ = ["evaluate", "EvaluateInput", "EvaluateOutput"]
```

**Sync-function-with-typed-input/output pattern** (mirror `loss_model/expected_loss.py` lines 73-100 — the ExpectedLossInput → ExpectedLossOutput contract; engine.py is the same shape but composes 3 model calls + gas_cache):

The RESEARCH.md §"Code Examples" already gives the canonical engine.py body (lines 1329-1438). Copy that body verbatim.

**Copy:** module docstring style, sync compute pattern, typed-error propagation discipline (`raise X from None` is unnecessary — RuntimeError subclasses ARE the contract).
**Deviate:** engine.py is `async` (because `gas_cache.cancel_cost_pendle` awaits w3 RPC); expected_loss.py is sync. Keep `evaluate` async; the inner predict/expected_loss/r_capped calls remain sync.

---

#### `decision/schemas.py` (Pydantic models)

**Analog:** `python/src/boros_brain/loss_model/schemas.py` lines 1-30 + 47-75
**Why:** Local StrictBase, Literal types for enum-style fields, custom RuntimeError subclasses with structured payload.

**StrictBase + Literal + custom error pattern** (lines 47-65 + 116-122 of `loss_model/schemas.py`):

```python
"""Pydantic shapes for the decision engine (DECIDE-01/02/03/04).

Single home for all decision shape declarations so architecture.yml has a single
`brain.decision.schemas` node.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Local strict base — extra='forbid', frozen=True. Mirrors loss_model/schemas.py
    pattern (avoids circular import with config.schema)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluateInput(StrictBase):
    market_id: str
    side: Literal["long", "short"]
    order_id: str
    depth_from_mark_ticks: int
    queue_ahead_wei: int
    current_features: dict[str, float]
    time_to_epoch_end_s: float
    time_to_maturity_s: int
    q_me_pendle: float
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float
    t_frac: float
    p_purge: float
    r_me_per_epoch_pendle_accumulated_so_far: float
    current_chain_ts: int


class EvaluateOutput(StrictBase):
    decision_kind: Literal["CANCEL", "HOLD", "PLACE"]
    ev_hold_pendle: float
    r_share_per_epoch_pendle: float
    p_no_fill_and_unpurged: float
    e_loss_pendle: float
    p_fill: float
    cancel_cost_pendle: float
    p_purge: float
    fit_status_fill: Literal["ok", "degraded", "stale"]
    fit_status_loss: Literal["ok", "degraded", "stale"]
    voluntary_cancel_branch: Literal["benign", "punitive"]
    reasoning: dict[str, Any]
```

**Copy:** StrictBase ConfigDict, Literal-typed enums, frozen+forbid, no defaults on non-Field non-list scalars.
**Deviate:** EvaluateOutput must include the full reasoning trail dict so the operator can audit a single decision; loss/fill outputs are slimmer.

---

#### `decision/config.py` (Pydantic sub-model)

**Analog:** `python/src/boros_brain/fill_model/config.py` lines 1-90
**Why:** Field-bounded numeric knobs, StrictBase, nested sub-models, `default_factory` for collections.

**Pattern to mirror** (lines 28-78 of `fill_model/config.py`):

```python
"""DecisionEngineConfig — Pydantic sub-model for the EV cancel rule + breakers (PROTO-04).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MarginBreakerConfig(StrictBase):
    window_s: float = Field(30.0, ge=5.0, le=600.0)
    min_samples: int = Field(10, ge=2, le=200)
    time_to_mm_threshold_s: float = Field(30.0, ge=5.0, le=600.0)
    min_re_arm_s: float = Field(60.0, ge=0.0, le=600.0)


# … one class per breaker (10 of them) ……

class BreakerConfig(StrictBase):
    margin: MarginBreakerConfig = Field(default_factory=MarginBreakerConfig)
    oracle_stale: OracleStaleBreakerConfig = Field(default_factory=OracleStaleBreakerConfig)
    # … 8 more …


class DecisionEngineConfig(StrictBase):
    cancel_cost_ewma_alpha: float = Field(0.1, ge=0.0, le=1.0)
    cancel_cost_ttl_s: float = Field(60.0, ge=1.0, le=600.0)
    cancel_cost_block_window: int = Field(100, ge=10, le=1000)
    p_purge_default: float = Field(0.0, ge=0.0, le=1.0)
    decision_loop_interval_s: float = Field(1.0, ge=0.1, le=10.0)
    breakers: BreakerConfig = Field(default_factory=BreakerConfig)
```

**Copy:** Field bounds (ge/le), StrictBase pattern, default_factory for nested sub-models.
**Deviate:** New nested level — `decision.breakers.<name>.<knob>`. The reflection-based manifest builder (`test_phase4_manifest_leaves.py`) walks this depth automatically.

---

#### `decision/gas_history.py` (TTL-cached RPC fetch)

**Analog:** `python/src/boros_brain/data/chain_time.py` lines 76-180 (ChainTimeCache)
**Why:** TTL cache + `asyncio.wait_for` RPC timeout + warn-log on stale + dataclass-shaped state.

**TTL cache pattern** (mirror `chain_time.py` `ChainTimeCache`):

```python
"""DECIDE-03 — cancel_cost EWMA cache (gas history).

Reads eth_feeHistory over a rolling block window, computes EWMA over baseFeePerGas,
converts wei → PENDLE via config.pricing.{eth_price_usd, pendle_price_usd}.

TTL: cancel_cost_ttl_s (default 60s) — one RPC per minute. Mirrors ChainTimeCache
TTL pattern. Wall-clock is forbidden in decision/ — this file uses
chain_time.now_cached() exclusively (no_time_time_lint.py extends to decision/).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import structlog

from ..config.schema import BotConfig
from ..data import chain_time

log = structlog.get_logger(__name__)


@dataclass
class GasHistoryCache:
    last_fetch_chain_ts: int = 0
    last_value_pendle: float = 0.0
    ewma_state: float = field(default=0.0)

    async def cancel_cost_pendle(self, *, w3, config: BotConfig) -> float:
        now = await chain_time.now_cached()
        ttl = config.decision.cancel_cost_ttl_s
        if now - self.last_fetch_chain_ts < ttl and self.last_fetch_chain_ts != 0:
            return self.last_value_pendle
        try:
            base_fees = await asyncio.wait_for(
                w3.eth.fee_history(config.decision.cancel_cost_block_window, "latest"),
                timeout=5.0,
            )
        except (TimeoutError, Exception) as exc:  # noqa: BLE001
            log.warning("gas_history.fetch_failed", err=str(exc),
                        last_value_pendle=self.last_value_pendle)
            return self.last_value_pendle  # serve cached
        # EWMA reduction (one-line for-loop per RESEARCH "Don't Hand-Roll")
        alpha = config.decision.cancel_cost_ewma_alpha
        ewma = self.ewma_state or float(base_fees["baseFeePerGas"][0])
        for f in base_fees["baseFeePerGas"]:
            ewma = alpha * float(f) + (1 - alpha) * ewma
        self.ewma_state = ewma
        # wei → PENDLE conversion (uses pricing knobs — pitfall #5 watched)
        gas_units = config.execution.cancel_gas_units_estimate
        wei = ewma * gas_units
        eth = wei / 1e18
        usd = eth * config.pricing.eth_price_usd
        pendle = usd / config.pricing.pendle_price_usd
        self.last_value_pendle = float(pendle)
        self.last_fetch_chain_ts = int(now)
        return self.last_value_pendle
```

**Copy:** dataclass + TTL field, `asyncio.wait_for` RPC wrapper, warn-log + serve-cached fallback, `await chain_time.now_cached()` for time arithmetic (NEVER `time.time()`).
**Deviate:** EWMA reduction is a one-line for-loop (per RESEARCH §"Don't Hand-Roll" — closed-form, no scipy). The wei→PENDLE conversion path is unique to this file.

---

### Breakers family

#### `decision/breakers/base.py` (ABC + BreakerSignal)

**Analog:** `python/src/boros_brain/reward_model/schemas.py` (StrictBase + Literal pattern) + Python stdlib `abc`
**Why:** No ABC analog exists in the codebase yet — this is a new pattern. Combine the StrictBase shape from reward_model/schemas.py with stdlib ABC.

The RESEARCH.md §"Code Examples" lines 1485-1513 already gives the canonical body. Copy verbatim:

```python
# python/src/boros_brain/decision/breakers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict


class BreakerSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tripped: bool
    reason: str = ""
    payload: dict[str, Any] = {}
    kill_command_kind: Literal[
        "CANCEL_ALL", "EMERGENCY_CLOSE", "PAUSE_AND_ALERT",
        "ROLL_POSITION", "HALVE_POSITION_AND_ALERT", "HALT_AND_ALERT",
        "SHRINK_TO_Q_MIN", "CANCEL_ALL_HOLD_NO_REPLACE",
        "CANCEL_ALL_AND_RECALIBRATE", "CANCEL_ALL_AND_ALERT",
    ] = "CANCEL_ALL"


class Breaker(ABC):
    name: str

    @abstractmethod
    async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts) -> BreakerSignal:
        ...
```

**Copy:** RESEARCH §Code Examples body (verbatim). Add the `current_chain_ts: int` kw-arg per the Phase 2/3 grain (see `predict.py` line 53 + `expected_loss.py` line 73 — every sync model takes `current_chain_ts: int` from chain_time).
**Deviate:** No file like this exists yet — Phase 4 introduces ABC + BreakerSignal. Tests should import `Breaker` directly to ensure the abstract method is wired (`pytest.raises(TypeError)` on instantiation without override).

---

#### `decision/breakers/margin_trajectory.py` (per-breaker stateful service)

**Analog:** `python/src/boros_brain/reward_model/competition_tracker.py` lines 42-132 (CompetitionTracker class with `run_one_cycle`)
**Why:** Stateful per-cycle component that reads SQLite history, computes a derived signal, and emits a structured output. Per-breaker hysteresis (re-arm interval) maps to `_fail_count` / `_degraded_emitted` in CompetitionTracker.

**Per-cycle stateful read pattern** (mirror lines 84-132 of competition_tracker.py — adapted for breakers):

```python
"""SAFE-01: Margin trajectory breaker.

Reads the last `window_s` of state.margin_history for each market, fits a
linear regression via numpy.polyfit (per RESEARCH §"Don't Hand-Roll"), and
trips if extrapolated time-to-maintenance-margin < time_to_mm_threshold_s.

Pitfall #4: slope < 0 means margin SHRINKING. The hypothesis test
test_breaker_margin_trajectory.test_no_fire_when_growing injects positive-slope
samples and asserts no fire.

[[predictive-circuit-breakers-v05]]
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import structlog

from ..config.schema import BotConfig
from ..state.writers.margin_history import read_margin_history
from .base import Breaker, BreakerSignal

log = structlog.get_logger(__name__)


class MarginTrajectoryBreaker(Breaker):
    name = "margin_trajectory"

    async def check(
        self, *,
        sqlite_path: Path, w3, parquet_root: Path,
        config: BotConfig, current_chain_ts: int,
    ) -> BreakerSignal:
        cfg = config.decision.breakers.margin
        rows = read_margin_history(
            sqlite_path,
            since_ts=current_chain_ts - int(cfg.window_s),
        )
        if len(rows) < cfg.min_samples:
            return BreakerSignal(tripped=False, reason="insufficient_history",
                                 payload={"n": len(rows)})
        ts = np.array([r["chain_ts"] for r in rows], dtype=float)
        nm = np.array([r["net_margin_usd"] for r in rows], dtype=float)
        slope, intercept = np.polyfit(ts, nm, 1)  # slope < 0 = shrinking
        if slope >= 0:
            return BreakerSignal(tripped=False, reason="growing")
        # Extrapolate to mm: nm = slope*t + intercept = mm_floor → t = (mm - intercept)/slope
        mm_floor = config.sizer.maintenance_margin_floor_usd
        t_to_mm = (mm_floor - intercept) / slope - current_chain_ts
        if t_to_mm < cfg.time_to_mm_threshold_s:
            return BreakerSignal(
                tripped=True, reason="margin_trajectory",
                payload={"slope": float(slope), "t_to_mm_s": float(t_to_mm)},
                kill_command_kind="HALVE_POSITION_AND_ALERT",
            )
        return BreakerSignal(tripped=False, reason="ok",
                             payload={"slope": float(slope), "t_to_mm_s": float(t_to_mm)})
```

**Copy:** stateful per-cycle compute + structured BreakerSignal output, `current_chain_ts` parameter convention, log warnings on edge cases. Use `numpy.polyfit` (RESEARCH §Don't Hand-Roll), NEVER hand-rolled least squares.
**Deviate:** breakers don't write SQLite directly (the Coordinator does that via the breaker_events writer); breakers are pure computation + return signal. CompetitionTracker writes inside `run_one_cycle`.

---

#### `decision/breakers/oracle_stale.py` (other breakers follow same pattern)

**Analog:** Same as `margin_trajectory.py` (reward_model/competition_tracker.py + per-breaker reads).
**Why:** All 10 breaker modules share the same shape — the differences are (a) which writer/reader they call and (b) the threshold knob path.

The remaining 9 breaker modules (`oracle_stale.py`, `clo_removal.py`, `clo_shift.py`, `fill_rate.py`, `competition.py`, `maturity.py`, `side_budget.py`, `underlying_stale.py`, `loss_fit_degraded.py`) all instantiate the same `Breaker` ABC — copy `margin_trajectory.py`'s skeleton verbatim, swap the reader function, swap the knob path, swap the kill_command_kind enum, and swap the threshold logic. Each module is ~50 lines.

---

### Coordinator + CLI

#### `decision/breaker_coordinator.py` (event-driven gate + ZMQ KILL emitter)

**Analog:** `python/src/boros_brain/bus/cmd.py` (CmdBus) usage in `python/src/boros_brain/main.py` lines 99-107 + `competition_tracker.py` (per-cycle stateful logic)
**Why:** Composes existing `CmdBus.send_kill` + writer + per-cycle iteration.

**Coordinator wiring** (mirror lines 84-100 of competition_tracker.py + RESEARCH §main.py spawn block lines 1454-1480):

```python
"""SAFE-10 — BreakerCoordinator: exclusive kill authority + decision gate.

Runs all 10 breakers per tick (each with 200ms timeout per Pitfall #1).
Active breaker → fires KillCmd ONCE on rising edge (Pitfall #6 hysteresis),
suppresses ALL downstream PLACE/CANCEL cmds (SAFE-10), persists every
suppression to state.breaker_events (Pitfall #2 — never accumulate in-memory).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from ..bus.cmd import CmdBus
from ..bus.messages import KillCmd
from ..config.schema import BotConfig
from ..state.writers.breaker_events import insert_breaker_event
from .breakers.base import Breaker, BreakerSignal
from .gas_history import GasHistoryCache

log = structlog.get_logger(__name__)


class BreakerCoordinator:
    """Exclusive kill authority. Owns the per-breaker re-arm interval state."""

    def __init__(
        self, *,
        cmd_bus: CmdBus,
        config: BotConfig,
        run_id: str,
        gas_cache: GasHistoryCache,
        breakers: list[Breaker] | None = None,
    ) -> None:
        self._cmd_bus = cmd_bus
        self._config = config
        self._run_id = run_id
        self._gas_cache = gas_cache
        self._breakers: list[Breaker] = breakers or []
        self._tripped: dict[str, int] = {}  # breaker.name → first_tripped_chain_ts (hysteresis)

    async def tick(
        self, *, sqlite_path: Path, w3, parquet_root: Path, current_chain_ts: int,
    ) -> dict[str, BreakerSignal]:
        signals: dict[str, BreakerSignal] = {}
        for b in self._breakers:
            try:
                sig = await asyncio.wait_for(
                    b.check(
                        sqlite_path=sqlite_path, w3=w3, parquet_root=parquet_root,
                        config=self._config, current_chain_ts=current_chain_ts,
                    ),
                    timeout=0.2,  # Pitfall #1: 200ms per breaker
                )
            except TimeoutError:
                log.warning("breaker.timeout", name=b.name)
                sig = BreakerSignal(tripped=False, reason="timeout")
            signals[b.name] = sig
            if sig.tripped:
                # Rising edge — fire KillCmd ONCE per Pitfall #6 hysteresis
                if b.name not in self._tripped:
                    self._tripped[b.name] = current_chain_ts
                    await self._cmd_bus.send_kill(
                        KillCmd(reason=f"{b.name}:{sig.reason}", run_id=self._run_id),
                    )
                    insert_breaker_event(
                        sqlite_path,
                        kind="kill_emitted", breaker_name=b.name, reason=sig.reason,
                        chain_ts=current_chain_ts, run_id=self._run_id,
                        payload_json=sig.model_dump_json(),
                    )
            else:
                # Hysteresis: only un-trip after min_re_arm_s
                # ... (see Pitfall #6 spec)
                pass
        return signals

    async def gate(self, decisions: list[Any], *, current_chain_ts: int) -> None:
        """Suppress ALL PLACE/CANCEL cmds while any breaker tripped (SAFE-10)."""
        if self._tripped:
            for d in decisions:
                insert_breaker_event(
                    Path(self._config.infra.sqlite_path),
                    kind="suppression",
                    breaker_name=",".join(self._tripped.keys()),
                    reason="active_breaker", chain_ts=current_chain_ts,
                    run_id=self._run_id,
                    payload_json=d.model_dump_json(),
                )
            return
        # No active breaker — emit cmds via cmd_bus (Plan 04 wires this fully)
```

**Copy:** stateful per-cycle iteration, `asyncio.wait_for` per-breaker timeout (Pitfall #1), CmdBus.send_kill awaits, per-suppression SQLite write (Pitfall #2 — no in-memory log).
**Deviate:** the Coordinator NEVER calls `time.time()`; uses `current_chain_ts` arg. The Coordinator owns the hysteresis state — the breakers themselves are stateless.

---

#### `decision/cli.py` (subcommand argparse)

**Analog:** `python/src/boros_brain/fill_model/cli.py` lines 1-188
**Why:** subcommand argparse + manifest-first preamble + per-cmd dispatch + structured exit codes.

**Pattern to mirror** (lines 32-95 of fill_model/cli.py):

```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.decision",
        description="Decision engine CLI (DECIDE-01..04, predeploy_gate, reset_breaker)",
    )
    p.add_argument("--config", default="strategy/v0.5-default.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("predeploy-gate", help="Run economics gate + write predeploy_gate_records row")
    rst = sub.add_parser("reset-breaker", help="Manually clear a tripped breaker")
    rst.add_argument("--name", required=True, choices=[...10 breaker names...])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    manifest = build_run_manifest(config)
    configure_logging(run_id=manifest.run_id, tier="decision",
                      logs_dir=config.infra.logs_dir)
    write_manifest(manifest, ...)
    log = structlog.get_logger("decision.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump())
    # ... per-cmd dispatch ...
```

**Copy:** manifest-first preamble (PROTO-01), exit codes 0/1/2 convention, argparse with `dest='cmd', required=True`.
**Deviate:** subcommand list is decision-specific (`predeploy-gate`, `reset-breaker`), and `predeploy-gate` writes a SQLite row + a wiki page (per Pitfall #8 — record git_sha + config hash).

---

#### `decision/__main__.py`

**Analog:** `python/src/boros_brain/fill_model/__main__.py` (verbatim copy)

```python
"""Enables ``python -m boros_brain.decision``."""
from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
```

**Copy:** verbatim, swap the import.
**Deviate:** none.

---

### State writers

#### `state/writers/margin_history.py` (single-writer-per-table)

**Analog:** `python/src/boros_brain/state/writers/competition_history.py` lines 1-87
**Why:** chain_ts + market_id + run_id schema, both `insert_X(conn, ...)` writer + `get_latest_X(sqlite_path, ...)` self-managing reader, PROTO-02 single-writer guard via lint.

**Writer + reader pair pattern** (mirror lines 27-87 of competition_history.py):

```python
"""Single writer for the `margin_history` table (brain-owned). Plan 04-XX.

PROTO-02: any module outside this file that writes to margin_history is a bug.
scripts/sqlite_writer_lint.py grep-enforces the ownership map at commit time.
margin_poller.run_one_cycle is the only caller of insert_margin_snapshot.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["insert_margin_snapshot", "read_margin_history"]


def insert_margin_snapshot(
    conn: sqlite3.Connection,
    *,
    chain_ts: int,
    market_id: str,
    net_margin_usd: float,
    maintenance_margin_usd: float,
    available_collateral_usd: float,
    run_id: str,
) -> None:
    """Insert one margin_history row. Caller owns transaction lifecycle."""
    conn.execute(
        "INSERT INTO margin_history "
        "(chain_ts, market_id, net_margin_usd, maintenance_margin_usd, "
        " available_collateral_usd, run_id) VALUES (?, ?, ?, ?, ?, ?)",
        (chain_ts, market_id, net_margin_usd, maintenance_margin_usd,
         available_collateral_usd, run_id),
    )


def read_margin_history(
    sqlite_path: Path,
    *,
    market_id: str | None = None,
    since_ts: int | None = None,
) -> list[dict[str, object]]:
    from boros_brain.state.db import open_connection
    sql = "SELECT chain_ts, market_id, net_margin_usd, maintenance_margin_usd, " \
          "available_collateral_usd, run_id FROM margin_history WHERE 1=1"
    params: list[object] = []
    if market_id is not None:
        sql += " AND market_id = ?"; params.append(market_id)
    if since_ts is not None:
        sql += " AND chain_ts >= ?"; params.append(since_ts)
    sql += " ORDER BY chain_ts ASC"
    with open_connection(sqlite_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {"chain_ts": r[0], "market_id": r[1], "net_margin_usd": r[2],
         "maintenance_margin_usd": r[3], "available_collateral_usd": r[4],
         "run_id": r[5]}
        for r in rows
    ]
```

**Copy:** docstring with PROTO-02 reminder, low-level `insert_X(conn, ...)` (caller owns conn) + self-managed `read_X(sqlite_path, ...)` pair, run_id + chain_ts on every row.
**Deviate:** scripts/sqlite_writer_lint.py OWNER_MAP must be extended in the same plan (lines 35-44 of sqlite_writer_lint.py). 4 new entries.

---

#### `state/writers/breaker_events.py` (audit-log writer)

**Analog:** `python/src/boros_brain/state/writers/decisions.py` lines 1-52
**Why:** Slim INSERT-only writer, `kind` enum guarded by SQL CHECK, no read function (downstream consumers go through DuckDB).

**Pattern** (mirror lines 15-52 of decisions.py):

```python
"""Single writer for the `breaker_events` table (brain-owned). Plan 04-XX.

PROTO-02: any INSERT INTO breaker_events outside this file is a bug.
breaker_coordinator.tick + breaker_coordinator.gate are the only callers.
"""
from __future__ import annotations

import sqlite3


def insert_breaker_event(
    conn: sqlite3.Connection,
    *,
    kind: str,  # 'kill_emitted' | 'suppression' | 'rearmed' — DB CHECK enforces
    breaker_name: str,
    reason: str,
    chain_ts: int,
    run_id: str,
    payload_json: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO breaker_events (kind, breaker_name, reason, chain_ts, run_id, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kind, breaker_name, reason, chain_ts, run_id, payload_json),
    )
```

**Copy:** slim INSERT-only writer, no pre-validation (DB CHECK is the source of truth).
**Deviate:** `payload_json` is a stringified BreakerSignal — store the full audit trail per Pitfall #2.

---

#### `state/writers/predeploy_gate_records.py` (one row per CLI run)

**Analog:** `python/src/boros_brain/state/writers/run_manifests.py` lines 1-50 (config_json hash + git_sha pattern)
**Why:** One-row-per-CLI-invocation writer with git_sha + config_hash for Pitfall #8 mismatch detection.

**Copy:** the `insert_run_manifest` shape (config_json column, git_sha column).
**Deviate:** add a `gate_passed: bool` column and a `wiki_page_path: str` column for the postmortem trail.

---

### Migrations + Pollers

#### `state/migrations/versions/0007_phase4_tables.py` (4-table migration)

**Analog:** `python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py` lines 1-102
**Why:** Idempotent inspect-then-create pattern; CHECK constraints on enums; index per `market_id` + `chain_ts DESC` query pattern.

**Pattern to mirror** (lines 22-100 of 0006_market_reward_calibration.py):

```python
"""Add 4 Phase-4 tables in one revision: margin_history, competition_history (no-op
if 0005 created), breaker_events, predeploy_gate_records.

Revision ID: 0007_phase4_tables
Revises: 0006_market_reward_calibration
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0007_phase4_tables"
down_revision = "0006_market_reward_calibration"
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
    if not _has_table("margin_history"):
        op.create_table(
            "margin_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("chain_ts", sa.Integer(), nullable=False),
            sa.Column("market_id", sa.Text(), nullable=False),
            sa.Column("net_margin_usd", sa.Float(), nullable=False),
            sa.Column("maintenance_margin_usd", sa.Float(), nullable=False),
            sa.Column("available_collateral_usd", sa.Float(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
        )
    if not _has_index("margin_history", "ix_margin_history_market_chain_ts"):
        op.create_index(
            "ix_margin_history_market_chain_ts",
            "margin_history",
            ["market_id", sa.text("chain_ts DESC")],
        )
    # …(repeat for breaker_events, predeploy_gate_records)…
```

**Copy:** `_has_table` / `_has_index` helpers, idempotent inspect-then-create, CHECK constraints (e.g., `kind IN ('kill_emitted','suppression','rearmed')` for breaker_events), index on `(market_id, chain_ts DESC)`.
**Deviate:** one revision file lands all 4 tables (per RESEARCH §"one new migration version covers all 4 new tables"). 0006 is the precedent for one table per revision; this is a deliberate consolidation justified by atomic Phase 4 ship.

---

#### `data/poller/margin_poller.py` (1 Hz REST poller)

**Analog:** `python/src/boros_brain/data/poller/e_liq_poller.py` lines 1-152
**Why:** REST + writer + degraded-mode event after N consecutive failures + run_one_cycle/loop split.

**Pattern to mirror** (lines 46-152 of e_liq_poller.py):

```python
"""DATA-13 — 1 Hz margin poller. POST /accounts/get-net-margin → state.margin_history.

Mirrors e_liq_poller.ELiqPoller. Backoff: [0.5, 1, 2, 4, 8] on failure.
Degraded event 'poller.margin.degraded' published after 5 consecutive failures.
"""
from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

import structlog

from boros_brain.data.chain_time import now_cached as get_chain_time_cached
from boros_brain.state.writers.margin_history import insert_margin_snapshot

log = structlog.get_logger(__name__)
_BACKOFF_DELAYS = [0.5, 1.0, 2.0, 4.0, 8.0]


class MarginPoller:
    def __init__(self, config, conn: sqlite3.Connection, rest, run_id: str, event_pub) -> None:
        self.interval = config.data.margin_poll_interval_s
        self.markets = [m.market_id for m in config.markets]
        self.conn = conn; self.rest = rest; self.run_id = run_id
        self.event_pub = event_pub
        self._fail_count = 0

    async def run_one_cycle(self) -> None:
        try:
            margins = await self._get_with_backoff()
        except Exception as exc:
            log.error("margin_poller.fetch_failed", error=str(exc), fail_count=self._fail_count)
            if self._fail_count >= 5:
                await self.event_pub.publish("poller.margin.degraded", {"fail_count": self._fail_count})
            return
        self._fail_count = 0
        chain_ts = await get_chain_time_cached()
        for m in margins:
            insert_margin_snapshot(
                self.conn, chain_ts=chain_ts, market_id=m["marketId"],
                net_margin_usd=float(m["netMarginUsd"]),
                maintenance_margin_usd=float(m["maintenanceMarginUsd"]),
                available_collateral_usd=float(m["availableCollateralUsd"]),
                run_id=self.run_id,
            )
            self.conn.commit()

    async def loop(self) -> None:
        while True:
            await self.run_one_cycle()
            await asyncio.sleep(self.interval)


async def run_margin_poller_loop(config, run_id, conn, rest, event_pub) -> None:
    p = MarginPoller(config, conn, rest, run_id, event_pub)
    await p.loop()
```

**Copy:** the entire ELiqPoller class skeleton, swap the REST endpoint, swap the writer, add `data.margin_poll_interval_s` knob (1.0 default per RESEARCH).
**Deviate:** REST endpoint is `POST /accounts/get-net-margin` (different from `GET /markets`); margin is ALSO consumed by SAFE-01 — the poller writes; the breaker reads.

---

### Lint scripts

#### `scripts/no_hardcoded_cancel_cost_lint.py`

**Analog:** `scripts/no_time_time_lint.py` lines 1-104
**Why:** Identical structure: PROTECTED_DIRS, ALLOWED_FILES, regex PATTERN, walk + report + exit 0/1.

**Pattern to mirror** (lines 33-103 of no_time_time_lint.py):

```python
#!/usr/bin/env python3
"""Pre-commit hook: rejects hardcoded cancel_cost scalars in brain/decision/.

The single source of truth for cancel_cost is gas_history.GasHistoryCache
(DECIDE-03). Hardcoded scalars in decision/ are a regression to threshold-dial
discipline. See PITFALLS #5 (cancel_cost wei→PENDLE conversion drift).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROTECTED_DIRS = ("python/src/boros_brain/decision/",)
ALLOWED_FILES = {
    "python/src/boros_brain/decision/gas_history.py",  # the only legit owner
}
# Match literal float assignments to cancel_cost or cancel_cost_pendle that aren't 0.0
PATTERN = re.compile(r"\bcancel_cost(?:_pendle)?\s*=\s*\d+\.\d+")


def _all_protected_files() -> list[Path]:
    return [p for d in PROTECTED_DIRS for p in Path(d).rglob("*.py") if p.is_file()]


def _scan(path: Path) -> list[tuple[int, str]]:
    s = str(path).replace("\\", "/")
    if s in ALLOWED_FILES or not path.is_file():
        return []
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        if PATTERN.search(line):
            hits.append((i, line))
    return hits


def main() -> int:
    fail = 0
    for p in _all_protected_files():
        for lineno, line in _scan(p):
            print(f"[no_hardcoded_cancel_cost] {p}:{lineno}: "
                  f"use gas_history.GasHistoryCache — {line.strip()[:80]}", file=sys.stderr)
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
```

**Copy:** the entire structure (PROTECTED_DIRS, ALLOWED_FILES, _all_protected_files, _scan, main) — verbatim from no_time_time_lint.py with renamed PATTERN.
**Deviate:** the regex itself; the allowed-file allowlist (gas_history.py is the only legit owner).

---

#### `scripts/no_threshold_dials_lint.py`

**Analog:** `scripts/no_time_time_lint.py` (same structure)
**Why:** Same shape, different pattern.

**Pattern:** same as `no_hardcoded_cancel_cost_lint.py` above. The regex matches forbidden idioms like `cancel_threshold = ...`, `if depth > N:` magic-number comparisons in decision/, etc. Per RESEARCH DECIDE-04, the audit script must pass on Phase-4-final main.

**Copy:** entire structure from no_time_time_lint.py.
**Deviate:** the regex pattern is "any literal float compared to a 'cancel-priority-style' name". Project-specific token list.

---

#### Update `scripts/sqlite_writer_lint.py` OWNER_MAP

**Analog:** existing `scripts/sqlite_writer_lint.py` lines 35-50.
**Why:** 4 new tables need owner-map entries. This is a 4-line edit, not a new file.

```python
OWNER_MAP: dict[str, str] = {
    # …existing 8 entries…
    "margin_history": "python/src/boros_brain/state/writers/margin_history.py",
    "breaker_events": "python/src/boros_brain/state/writers/breaker_events.py",
    "predeploy_gate_records": "python/src/boros_brain/state/writers/predeploy_gate_records.py",
    # competition_history was added in 0005; if its lint entry is missing, add it now.
}
```

**Copy:** OWNER_MAP shape verbatim.
**Deviate:** none — pure additive edit.

---

#### Update `scripts/no_time_time_lint.py` PROTECTED_DIRS

**Analog:** existing `scripts/no_time_time_lint.py` lines 39-47.
**Why:** RESEARCH §INFRA-14 explicitly requires extending the lint to `python/src/boros_brain/decision/` (already listed at line 40 — confirm).

The file ALREADY lists `python/src/boros_brain/decision/` (line 40). No edit needed unless the breakers subpackage requires a more specific entry. Phase 4 should verify the decision/breakers/ subdirectory is covered by the recursive `rglob`.

---

### Tests

#### `python/tests/test_decision_engine_ev_equation.py`

**Analog:** `python/tests/test_fill_model_predict_contract.py` lines 1-120
**Why:** Hypothesis property tests + `_seed_fit` writer-helper + `_apply_migrations` + pytest.raises propagation.

**Test fixture pattern** (mirror lines 22-80 of test_fill_model_predict_contract.py):

```python
"""DECIDE-01 — engine.evaluate() EV equation tests.

T-04-D-01..T-04-D-04: hypothesis property + monotonicity + propagation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from boros_brain.config.schema import BotConfig
from boros_brain.decision.engine import evaluate
from boros_brain.decision.gas_history import GasHistoryCache
from boros_brain.decision.schemas import EvaluateInput
from boros_brain.fill_model.schemas import FitArtifact
from boros_brain.state.writers.fill_model_fits import insert_fit_artifact

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _apply_migrations(db: Path) -> None:
    from alembic import command
    from alembic.config import Config
    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def _seed_fit_and_grid(sqlite_path: Path) -> None:
    _apply_migrations(sqlite_path)
    insert_fit_artifact(sqlite_path, FitArtifact(...))  # mirror existing _seed_fit
    # ... insert loss grid via state.writers.loss_grid_artifacts ...


@given(p_fill=st.floats(0.0, 1.0), r_share=st.floats(0.0, 100.0))
@settings(max_examples=50)
def test_ev_monotonicity(p_fill: float, r_share: float, tmp_path: Path) -> None:
    """EV strictly decreasing in p_fill, strictly increasing in r_share."""
    db = tmp_path / "state.sqlite"
    _seed_fit_and_grid(db)
    # ... assert evaluate(req with higher p_fill) ev_hold < evaluate(req with lower p_fill) ...
```

**Copy:** `_apply_migrations` helper verbatim, `_seed_fit` writer-helper pattern (use the writer functions to seed state — never raw SQL), `pytest.raises` propagation tests.
**Deviate:** EvaluateInput needs more fields than PredictInput (q_me, sigma_others, etc.); the seed helper must populate competition_history + market_reward_calibration too.

---

#### `python/tests/test_breaker_*.py` (×10 — each breaker)

**Analog:** `test_fill_model_predict_contract.py::_seed_fit` + `test_competition_tracker.py::_migrated_db`.
**Why:** Each breaker test seeds its corresponding history table via the writer, then calls `breaker.check(...)` directly and asserts `BreakerSignal.tripped`.

**Per-breaker test pattern:**

```python
"""SAFE-01 — Margin trajectory breaker tests."""
from __future__ import annotations
from pathlib import Path
import pytest

from boros_brain.decision.breakers.margin_trajectory import MarginTrajectoryBreaker
from boros_brain.state.writers.margin_history import insert_margin_snapshot
from boros_brain.state.db import open_connection


def _seed_margin_history(db: Path, slope: float, n: int = 20) -> None:
    _apply_migrations(db)  # same helper as test_decision_engine_ev_equation
    with open_connection(db) as conn:
        for i in range(n):
            insert_margin_snapshot(
                conn, chain_ts=1_700_000_000 + i,
                market_id="BINANCE-ETHUSDT-29MAY2026",
                net_margin_usd=100.0 + slope * i,
                maintenance_margin_usd=10.0,
                available_collateral_usd=200.0,
                run_id="test-001",
            )


@pytest.mark.asyncio
async def test_predicts_breach(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    _seed_margin_history(db, slope=-1.0, n=20)
    breaker = MarginTrajectoryBreaker()
    sig = await breaker.check(sqlite_path=db, w3=None, parquet_root=tmp_path,
                              config=_test_config(), current_chain_ts=1_700_000_020)
    assert sig.tripped is True
    assert "margin_trajectory" in sig.reason


@pytest.mark.asyncio
async def test_no_fire_when_growing(tmp_path: Path) -> None:
    """Pitfall #4 sign-confusion test: positive slope MUST NOT fire."""
    db = tmp_path / "state.sqlite"
    _seed_margin_history(db, slope=+1.0, n=20)
    breaker = MarginTrajectoryBreaker()
    sig = await breaker.check(sqlite_path=db, w3=None, parquet_root=tmp_path,
                              config=_test_config(), current_chain_ts=1_700_000_020)
    assert sig.tripped is False
```

**Copy:** `_apply_migrations` helper, writer-helper seed pattern (RESEARCH §Don't Hand-Roll: "use pytest parametrize + writer-helper-functions"), `@pytest.mark.asyncio` for async breakers.
**Deviate:** each breaker test seeds a different table (margin_history, clo_history, tx_receipts, etc.). Pitfall-specific tests (e.g., Pitfall #4 sign-confusion) per breaker.

---

#### `python/tests/test_breaker_coordinator_exclusive.py`

**Analog:** `python/tests/test_zmq_kill_priority.py` lines 1-85
**Why:** Real CmdBus over `ipc://` ipc_dir fixture, KILL preempt assertion, no PlaceCmd should be sent while breaker active.

**Pattern to mirror** (verbatim lines 17-85 of test_zmq_kill_priority.py):

```python
"""SAFE-10 — BreakerCoordinator exclusive kill authority tests."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import zmq
import zmq.asyncio

from boros_brain.bus.cmd import CmdBus
from boros_brain.bus.messages import KillCmd, PlaceCmd
from boros_brain.decision.breaker_coordinator import BreakerCoordinator
from boros_brain.decision.breakers.base import Breaker, BreakerSignal


class _AlwaysTrippedBreaker(Breaker):
    name = "test_always"
    async def check(self, **kw) -> BreakerSignal:
        return BreakerSignal(tripped=True, reason="test", kill_command_kind="CANCEL_ALL")


@pytest.mark.asyncio
async def test_kill_fires_once(ipc_dir: Path) -> None:
    cmd_endpoint = f"ipc://{ipc_dir}/cmd"
    kill_endpoint = f"ipc://{ipc_dir}/cmd.kill"
    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)
    ctx = zmq.asyncio.Context.instance()
    kill_pull = ctx.socket(zmq.PULL); kill_pull.connect(kill_endpoint)
    await asyncio.sleep(0.05)

    coord = BreakerCoordinator(cmd_bus=bus, config=_test_config(),
                               run_id="r-test", gas_cache=None,
                               breakers=[_AlwaysTrippedBreaker()])
    # First tick: should emit KILL.
    await coord.tick(sqlite_path=ipc_dir / "state.sqlite",
                     w3=None, parquet_root=ipc_dir, current_chain_ts=1_700_000_000)
    msg = await asyncio.wait_for(kill_pull.recv_json(), timeout=0.5)
    assert msg["kind"] == "kill"
    # Second tick (still tripped): should NOT re-emit (Pitfall #6 hysteresis).
    await coord.tick(sqlite_path=ipc_dir / "state.sqlite",
                     w3=None, parquet_root=ipc_dir, current_chain_ts=1_700_000_001)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(kill_pull.recv_json(), timeout=0.1)
```

**Copy:** the `ipc://` + `ipc_dir` fixture pattern verbatim — this is the proven way to test ZMQ end-to-end without mocking. Use `CmdBus` directly (no fake bus).
**Deviate:** the test uses a fake `_AlwaysTrippedBreaker` to deterministically trip on every tick; assertions check both rising-edge fire AND hysteresis no-refire.

---

#### `python/tests/test_phase4_manifest_leaves.py`

**Analog:** `python/tests/test_manifest_contains_all_knobs.py::test_phase3_leaves_surfaced` lines 137-197
**Why:** Reflection-based leaf-count assertion, same shape mirrored line-for-line.

**Pattern to mirror** (lines 137-197 of test_manifest_contains_all_knobs.py):

```python
def test_phase4_leaves_surfaced(default_config: BotConfig) -> None:
    """PROTO-04 (Plan 04-XX): every Phase-4 knob auto-surfaces via reflection.

    Covers decision.* (5 top-level + 10 breakers × ~2-4 knobs each = ~25+ leaves).
    """
    leaves = _collect_leaf_paths(BotConfig)
    leaf_strs = [".".join(leaf) for leaf in leaves]
    decision_leaves = [s for s in leaf_strs if s.startswith("decision.")]
    assert len(decision_leaves) >= 25, (
        f"expected >=25 decision leaves, got {len(decision_leaves)}: {decision_leaves}"
    )
    # Spot-check critical knobs
    assert "decision.cancel_cost_ewma_alpha" in decision_leaves
    assert "decision.breakers.margin.window_s" in decision_leaves
    assert "decision.breakers.oracle_stale.fraction_of_max" in decision_leaves
    # ... 8 more breaker spot-checks ...
```

**Copy:** `_collect_leaf_paths` is already shared in conftest-adjacent test file; reuse its import.
**Deviate:** assert `>=25` (Phase 4 target per RESEARCH BotConfig Knob Delta).

---

#### `python/tests/conftest.py` (extension)

**Analog:** existing `python/tests/conftest.py` lines 1-62 (shared fixtures)
**Why:** RESEARCH §Wave 0 Gaps says "extend with breaker_history_fixtures (margin / clo / competition seed helpers); already exists".

**Pattern:** APPEND to the existing file; do not rewrite. Add small fixture functions:

```python
@pytest.fixture
def seed_margin_history(tmp_sqlite_path: Path):
    def _seed(slope: float, n: int = 20, market_id: str = "BINANCE-ETHUSDT-29MAY2026"):
        from boros_brain.state.writers.margin_history import insert_margin_snapshot
        from boros_brain.state.db import open_connection
        # apply migrations
        # ... seed N rows on slope ...
    return _seed


@pytest.fixture
def seed_clo_history(tmp_sqlite_path: Path):
    def _seed(rows: list[tuple]):
        from boros_brain.state.writers.clo_history import insert_clo_snapshot
        # ...
    return _seed
```

**Copy:** existing conftest fixture function shape (e.g., `tmp_sqlite_path`, `frozen_chain_time`).
**Deviate:** parameterized fixture-factory pattern (return inner function, not value) — required because each breaker test wants different slopes / row counts.

---

### Infra delta

#### `python/src/boros_brain/main.py` (edit — append spawn block)

**Analog:** the existing `main.py` lines 144-196 (Phase 2 fill_model + Phase 3 loss_model + competition_tracker spawn pattern)
**Why:** Phase 4 mirrors this pattern exactly.

**Pattern to mirror** (verbatim from RESEARCH §main.py spawn block, lines 1441-1483):

```python
# python/src/boros_brain/main.py — appended to existing run() between
# competition_tracker spawn and stop.wait()

from .decision.breaker_coordinator import BreakerCoordinator
from .decision.gas_history import GasHistoryCache
from .decision.engine import evaluate as evaluate_decision

gas_cache = GasHistoryCache()
coord = BreakerCoordinator(
    cmd_bus=cmd_bus, config=cfg, run_id=manifest.run_id,
    gas_cache=gas_cache, breakers=[ ... 10 breakers ... ],
)

# Wire ChainTimeCache halt_callback to coordinator (replaces the log-only default)
chain_cache.halt_callback = coord.halt_via_chain_time

async def _decision_loop():
    while not stop.is_set():
        current_chain_ts = await chain_cache.now_cached()
        coord_state = await coord.tick(
            sqlite_path=Path(cfg.infra.sqlite_path), w3=w3,
            parquet_root=Path("data/parquet"), current_chain_ts=current_chain_ts,
        )
        decisions = []
        for order in read_open_orders(Path(cfg.infra.sqlite_path), market_id=cfg.market_id):
            req = build_evaluate_input(order, cfg, current_chain_ts)
            try:
                out = await evaluate_decision(req, sqlite_path=Path(cfg.infra.sqlite_path),
                                              config=cfg, gas_cache=gas_cache, w3=w3)
                decisions.append(out)
                insert_decision(Path(cfg.infra.sqlite_path), out, run_id=manifest.run_id)
            except (FillModelStaleFeatureError, FillModelNoFreshFitError, LossModelNoFreshGridError) as exc:
                log.warning("decision_engine.skipped_on_stale_input",
                            order_id=order.order_id, error_class=type(exc).__name__)
                continue
        await coord.gate(decisions, current_chain_ts=current_chain_ts)
        await asyncio.sleep(cfg.decision.decision_loop_interval_s)

decision_task = asyncio.create_task(_decision_loop())

# ... append decision_task to the cancellation list at line 202 ...
```

**Copy:** the existing `asyncio.create_task` + `t.cancel(); contextlib.suppress(asyncio.CancelledError)` cancellation pattern at lines 200-211.
**Deviate:** the chain_cache.halt_callback wire-up REPLACES `_default_halt_callback` (chain_time.py line 67) — this is a NEW capability, not just a spawn.

---

## Shared Patterns

### Pattern: `current_chain_ts: int` parameter convention

**Source:** `python/src/boros_brain/fill_model/predict.py` line 53 (`def predict(req: PredictInput, ...) -> PredictOutput`) + line 91 (`fit_age_s = float(req.current_chain_ts - fit.fit_window_end_ts)`).
**Apply to:** ALL breaker `.check()` methods, `engine.evaluate`, `gas_history.cancel_cost_pendle`, every new sync-or-async function in `decision/`.

```python
# Every Phase 4 sync function takes current_chain_ts as a typed int kw-arg.
# NEVER call time.time() inside decision/ — the no_time_time_lint.py pre-commit
# hook covers decision/ (line 40 of the lint script).
```

**Why:** Per CLAUDE.md INFRA-14 (chain-time cache) + Phase 2/3 grain. The 1 Hz loop fetches `current_chain_ts = await chain_cache.now_cached()` ONCE per tick and passes it down to every breaker + the engine.

---

### Pattern: structlog get_logger + structured warn-log

**Source:** every Phase 2/3 module — e.g., `python/src/boros_brain/loss_model/expected_loss.py` line 40 (`log = structlog.get_logger(__name__)`) + lines 92-100 (`log.warning("loss_model.no_fresh_grid", market_id=req.market_id, ...)`).
**Apply to:** every new `decision/` module.

```python
import structlog
log = structlog.get_logger(__name__)

# Always use structured kwargs, NEVER f-strings:
log.warning("breaker.timeout", name=b.name, timeout_ms=200)
log.info("decision_engine.skipped_on_stale_input", order_id=order.order_id,
         error_class=type(exc).__name__)
```

**Why:** structlog auto-binds `run_id` via contextvars (configured at boot in main.py line 78). Every log line in production carries the active `run_id` — required for the RUN_MANIFEST audit chain.

---

### Pattern: Pydantic StrictBase (`extra='forbid', frozen=True`)

**Source:** `python/src/boros_brain/loss_model/schemas.py` lines 50-54, repeated verbatim in `fill_model/schemas.py` line 67-71, `reward_model/schemas.py` line 17-23.
**Apply to:** every new `decision/schemas.py`, `decision/config.py`, `decision/breakers/base.py` Pydantic class.

```python
class StrictBase(BaseModel):
    """Local strict base — extra='forbid', frozen=True. Mirrors loss_model/schemas.py
    pattern (avoids circular import with config.schema)."""
    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Why:** PROTO-04 manifest-reflection invariant + T-03-04 unvalidated-input defense. Frozen prevents accidental mutation; forbid catches API drift.

---

### Pattern: Single-writer-per-table (PROTO-02)

**Source:** every file under `python/src/boros_brain/state/writers/` (existing 13 modules) + `scripts/sqlite_writer_lint.py` OWNER_MAP (lines 35-44).
**Apply to:** the 4 new writers (margin_history, breaker_events, predeploy_gate_records, and the existing competition_history if its lint entry was missing).

```python
"""Single writer for the `<table>` table (brain-owned). Plan 04-XX.

PROTO-02: any module outside this file that writes to <table> is a bug.
scripts/sqlite_writer_lint.py grep-enforces this at commit time.
<the_one_caller>.run_one_cycle is the only caller of insert_<table>.
"""
```

**Why:** A single point of write per table makes audit trivial (grep + lint), enables strong type/CHECK guards in one place, prevents the "two-writer race" anti-pattern.

---

### Pattern: chain_time.now_cached() for all chain-relevant time arithmetic

**Source:** `python/src/boros_brain/fill_model/refit_loop.py` line 41 (`now_s = await chain_time.now_cached()`).
**Apply to:** every new poller, breaker, engine, gas_history.

```python
from boros_brain.data import chain_time
# Inside any async function:
now = await chain_time.now_cached()  # NEVER time.time()
```

**Why:** PITFALLS §C7 (clock drift during macOS sleep/wake) — chain_time monotonically tracks the Arbitrum chain clock; wall-clock can silently drift after laptop suspend. The `no_time_time_lint.py` hook enforces this in `decision/`.

---

### Pattern: Try-with-typed-error catch + warn log + continue (poller anti-pattern)

**Source:** `python/src/boros_brain/data/poller/markets_poller.py` lines 95-117 + `e_liq_poller.py` lines 88-101 + `competition_tracker.py` lines 96-117 + `loss_model/refit_loop.py` lines 79-84.
**Apply to:** the new `margin_poller.py` per-tick error handling, the `breaker_coordinator.tick` per-breaker timeout, the engine's per-decision exception loop in main.py.

```python
try:
    result = await some_external_call()
except (TimeoutError, SpecificError) as exc:
    log.warning("module.operation_name_failed", err=str(exc), market_id=mkt)
    continue  # never halt the brain on a per-X failure
```

**Why:** "Dead poller > dead brain." The 1 Hz loop must keep running even if one breaker times out or one market's REST call fails.

---

## No Analog Found

All 28 net-new source files have a strong analog under `python/src/boros_brain/{fill_model,loss_model,reward_model,data,state,bus}/`. There are zero "no analog" files in this phase.

The following two NEW sub-architectures (not files) lack a direct in-codebase analog and rely on the RESEARCH §Code Examples sections for the canonical body:

| Concept | Why no analog | Source-of-truth |
|---------|--------------|-----------------|
| ABC + BreakerSignal model | First ABC in the brain — Phase 2/3 used plain functions | RESEARCH 04-RESEARCH.md lines 1485-1513 (canonical body) |
| Per-breaker hysteresis (re-arm interval) | First hysteresis logic in the brain | RESEARCH §Pitfall #6 (lines 1301-1306) |

These are research-defined patterns; planner should cite the RESEARCH excerpts directly in the relevant plans.

---

## Metadata

**Analog search scope:** `python/src/boros_brain/{fill_model,loss_model,reward_model,data,state,bus,manifest}/`, `python/tests/`, `scripts/`, `ts/src/boros_hands/bus/`
**Files scanned:** 38 source files + 14 test files + 4 scripts + 6 migrations
**Pattern extraction date:** 2026-04-25
**Cross-references:**
- `boros_consolidated_plan.md` (canonical strategy spec — DECIDE-01..04 origin)
- `.planning/research/PITFALLS.md` (pitfalls #5/#6 lineage)
- `.planning/phases/03-reward-model/03-04-SUMMARY.md` (precedent for ATOMIC architecture.yml delta in last plan of phase, leaf-count test mirror)
- `.planning/phases/02-fill-model/02-04-SUMMARY.md` (precedent for spawn-block pattern in main.py)
