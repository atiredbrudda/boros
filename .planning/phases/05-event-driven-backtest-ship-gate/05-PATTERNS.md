# Phase 5: Event-Driven Backtest (Ship-Gate) — Pattern Map

**Mapped:** 2026-04-26
**Files analyzed:** 27 (24 NEW + 3 MODIFY)
**Analogs found:** 27 / 27 (100% coverage — Phase 5 is composition over Phase 1–4 modules)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `python/src/boros_brain/backtest/__init__.py` | package-marker | n/a | `python/src/boros_brain/decision/__init__.py` | exact |
| `python/src/boros_brain/backtest/__main__.py` | entrypoint-shim | n/a | `python/src/boros_brain/decision/__main__.py` | exact |
| `python/src/boros_brain/backtest/cli.py` | CLI | request-response | `python/src/boros_brain/decision/cli.py` | exact |
| `python/src/boros_brain/backtest/config.py` | config sub-model | n/a | `python/src/boros_brain/decision/config.py` | exact |
| `python/src/boros_brain/backtest/schemas.py` | Pydantic schemas | n/a | `python/src/boros_brain/decision/schemas.py` | exact |
| `python/src/boros_brain/backtest/replay.py` | engine | event-driven streaming | `python/src/boros_brain/fill_model/queue_tracker.py` + `decision/breaker_coordinator.py` | role-match (composition) |
| `python/src/boros_brain/backtest/synthetic_orders.py` | model (in-memory ledger) | CRUD | `python/src/boros_brain/decision/breaker_coordinator.py` (`_tripped` dict pattern) | role-match |
| `python/src/boros_brain/backtest/cancel_latency.py` | utility (latency simulator) | transform | `python/src/boros_brain/decision/gas_history.py` (small stateful class) | role-match |
| `python/src/boros_brain/backtest/bootstrap.py` | utility (Monte Carlo) | batch | `python/src/boros_brain/loss_model/expected_loss.py` (numpy/pure-fn pattern) | partial — no MC analog yet |
| `python/src/boros_brain/backtest/ship_gate.py` | runner + report | request-response | `python/src/boros_brain/screener/economics_gate.py` + `screener/kill_report.py` | exact (threshold-vs-baseline + halt-report) |
| `python/src/boros_brain/backtest/report.py` | parquet writer | file-I/O | `python/src/boros_brain/loss_model/artifact.py` (parquet sidecar dual-write) | exact |
| `python/src/boros_brain/backtest/sweeps/__init__.py` | package-marker | n/a | `python/src/boros_brain/decision/breakers/__init__.py` (treated as `external` in arch.yml) | exact |
| `python/src/boros_brain/backtest/sweeps/cancel_latency.py` | runner (sweep) | batch | `python/src/boros_brain/screener/rescreen.py`-style loop pattern + replay calls | partial |
| `python/src/boros_brain/backtest/sweeps/competition.py` | runner (sweep) | batch | same as cancel_latency sweep | partial |
| `python/src/boros_brain/backtest/sweeps/forfeit_branch.py` | runner (sweep) | batch | same as cancel_latency sweep | partial |
| `python/src/boros_brain/backtest/sweeps/perturbation.py` | runner (Pydantic-reflection grid) | batch | `python/tests/test_manifest_contains_all_knobs.py::_collect_leaf_paths` | exact (reflection idiom) |
| `python/src/boros_brain/config/schema.py` (MODIFY) | config-attachment | n/a | `BotConfig.decision: DecisionEngineConfig` Plan-04-02 attachment (line 227) | exact |
| `python/tests/test_backtest_replay_event_index_order.py` | test | property | `python/tests/test_decision_engine_ev_equation.py` (importorskip + RED-skip pattern) | exact |
| `python/tests/test_backtest_amm_conservation_replay.py` | test | integration | `python/tests/test_amm_conservation.py` (existing) + `test_decision_engine_ev_equation.py` shape | exact |
| `python/tests/test_backtest_cancel_latency_two_axis.py` | test | unit | `python/tests/test_decision_engine_ev_equation.py` | exact |
| `python/tests/test_backtest_sweep_cancel_latency.py` | test | unit | `python/tests/test_decision_engine_voluntary_branch.py` | exact |
| `python/tests/test_backtest_bootstrap_idempotent.py` | test | property | `python/tests/test_phase4_manifest_leaves.py` (reflection assertion pattern) | partial |
| `python/tests/test_backtest_ship_gate_threshold_assembly.py` | test | unit | `python/tests/test_economics_kill_switch.py` (existing economics-gate threshold test) | exact |
| `python/tests/test_backtest_perturbation_grid_pydantic.py` | test | property | `python/tests/test_manifest_contains_all_knobs.py` (`_collect_leaf_paths`) | exact |
| `python/tests/test_backtest_run_manifest_first.py` | test | unit | `python/tests/test_manifest_contains_all_knobs.py` + Phase-1 RUN_MANIFEST tests | exact |
| `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py` (MODIFY) | test (Wave-0 fix) | unit | itself, lines 99 + 141 (the leak source) | self |
| `python/tests/conftest.py` (MODIFY) | fixtures | n/a | itself, `seed_underlying_apr_parquet` (lines 357–379) — already correct shape | exact |
| `scripts/no_zmq_singleton_in_tests_lint.py` | lint | request-response | `scripts/no_threshold_dials_lint.py` | exact |
| `python/pyproject.toml` (MODIFY) | config (deps) | n/a | itself (lines 23–33 dev group) | self |
| `docs/architecture.yml` (MODIFY) | docs (manifest) | n/a | itself, `brain.decision.*` block (lines 1107–1392) + edges 2612–2641 | self |
| `docs/ARCHITECTURE.md` (MODIFY) | docs (Mermaid) | n/a | itself, brain subgraph lines 44–60 | self |

**Quality legend:**
- `exact` — same role + same data flow + canonical pattern in repo (copy idiom directly)
- `role-match` — same role, slightly different data flow (adapt with discipline)
- `partial` — no perfect analog; combine 2 patterns OR use RESEARCH.md spec as authority

---

## Pattern Assignments

### `python/src/boros_brain/backtest/__init__.py` (package-marker)

**Analog:** `python/src/boros_brain/decision/__init__.py` (1–22)

**Pattern to copy** (lines 1–22): module docstring lists submodules in dependency order, cites wiki pages, exports empty `__all__`.

```python
"""Backtest package — event-driven replay + ship-gate (BACK-01..08, Phase 5).

Sub-modules (in dependency order):
  backtest.schemas          — BacktestRunOutput / SweepResult / ShipGateVerdict
  backtest.config           — BacktestConfig (~10 knobs, PROTO-04 SSoT)
  backtest.synthetic_orders — in-memory order ledger (mirrors state.open_orders shape)
  backtest.cancel_latency   — two-axis latency simulator (BACK-02)
  backtest.replay           — eventIndex-ordered event loop (BACK-01)
  backtest.bootstrap        — block-bootstrap RNG (BACK-07)
  backtest.ship_gate        — 5th-pct vs alt_yield+all_fees verdict (BACK-07)
  backtest.report           — parquet writer (BACK-05) + plot generator
  backtest.sweeps.*         — cancel_latency (BACK-03) / competition (BACK-04) /
                              forfeit_branch (BACK-06) / perturbation (BACK-08)
  backtest.cli              — argparse entry-point (BACK-* run command)

[[backtest-replay-engine-v05]]
[[backtest-bootstrap-methodology-v05]]
"""

__all__: list[str] = []
```

**Rationale:** Phase 4 set the precedent for documentation-marker `__init__.py` files; the `architecture_lint.py` skips `__init__.py` files starting with underscore-or-not, so they get registered as `type: external` in `architecture.yml` (matching the `brain.decision` and `brain.decision.breakers` pattern at lines 1111–1119).

---

### `python/src/boros_brain/backtest/__main__.py` (entrypoint-shim)

**Analog:** `python/src/boros_brain/decision/__main__.py` (1–8) — exact 8-line file

**Pattern to copy** (lines 1–8):

```python
"""Enables ``python -m boros_brain.backtest``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
```

**Rationale:** Identical 8-line shim used by every CLI sub-package (decision, screener, loss_model, sizer). No deviation expected.

---

### `python/src/boros_brain/backtest/cli.py` (CLI, request-response)

**Analog:** `python/src/boros_brain/decision/cli.py` (1–119)

**Imports + module docstring** (lines 1–25):

```python
"""CLI entry point for the backtest engine (BACK-01..08, Phase 5).

Subcommands: run, plot.

MANIFEST-FIRST (PROTO-01): RUN_MANIFEST written as first log record before any
subcommand executes. tier='backtest-cli'. Bootstrap RNG seed is derived from
manifest.run_id (ULID tail) → bit-for-bit reproducibility.

Exit codes:
    0  -- success / ship-gate passes
    1  -- ship-gate fails (5th-pct < alt_yield + all_fees) — kill-report written
    2  -- unrecognised subcommand / config error

[[backtest-replay-engine-v05]]
[[backtest-ship-gate-threshold-assembly]]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

__all__ = ["main", "build_parser"]
```

**Argparse subcommand pattern** (lines 28–67):

```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m boros_brain.backtest",
        description="Event-driven backtest + ship-gate (BACK-01..08)",
    )
    p.add_argument(
        "--config",
        default="strategy/v0.5-default.yaml",
        help="Path to BotConfig YAML (PROTO-04 SSoT).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run full backtest grid + ship-gate verdict.")
    run_p.add_argument("--market", required=True, help="market_id")
    run_p.add_argument("--side", required=True, choices=["long", "short"])

    plot_p = sub.add_parser("plot", help="Re-render plots from existing run_id parquet output.")
    plot_p.add_argument("--run-id", required=True, help="ULID of an existing run")
    return p
```

**MANIFEST-FIRST boot block** (lines 70–99 of decision/cli.py — copy verbatim, change `tier='decision-cli'` → `tier='backtest-cli'`):

```python
def main(argv: list[str] | None = None) -> int:
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
        tier="backtest-cli",
        logs_dir=config.infra.logs_dir,
    )
    write_manifest(
        manifest,
        logs_dir=config.infra.logs_dir,
        sqlite_path=config.infra.sqlite_path,
    )
    log = structlog.get_logger("backtest.cli")
    log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))
    log.info("backtest.cli_started", subcommand=args.cmd)
```

**Rationale:** `decision/cli.py` is the freshest (Plan 04-06) MANIFEST-FIRST CLI. Copy the boot block verbatim. The screener CLI (`screener/cli.py:108–122`) does the same; both are valid analogs but `decision/cli.py` is closer in shape because it dispatches on `args.cmd` to different runners (matches `run` vs `plot`).

---

### `python/src/boros_brain/backtest/config.py` (config sub-model — NEW Pydantic class)

**Analog:** `python/src/boros_brain/decision/config.py` (1–198)

**Strict-base pattern** (lines 1–21):

```python
"""BacktestConfig — Pydantic sub-model for Phase 5 knobs (PROTO-04).

Re-declares a local StrictBase to avoid circular imports with brain.config.schema.
All ~9 leaf knobs are the single source of truth (PROTO-04). Adding a knob in
backtest/ code without adding it here is a bug — test_phase4_manifest_leaves.py
(extended) verifies every knob round-trips through manifest reflection.

[[backtest-bootstrap-methodology-v05]]: bootstrap_n_resamples, bootstrap_block_seconds
[[backtest-ship-gate-threshold-assembly]]: all_fees_threshold, alt_yield + all_fees
[[backtest-perturbation-grid-pydantic-reflection]]: perturbation_pct, contour_2d_knobs
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictBase(BaseModel):
    """Strict frozen base — mirrors decision/config.py and fill_model/config.py pattern."""

    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Top-level config class** (lines 157–198 of decision/config.py — adapt structure):

```python
class BacktestConfig(StrictBase):
    """Top-level config for the Phase-5 backtest harness (PROTO-04 SSoT).

    The ~9 leaf knobs below are reflection-surfaced in RUN_MANIFEST via
    BotConfig.model_dump() AND drive the perturbation grid (BACK-08) so adding
    a knob without registering here mechanically breaks the perturbation runner.
    """

    bootstrap_n_resamples: int = Field(2000, ge=100, le=100_000)
    """Number of bootstrap resamples (BACK-07). N=2000 → MC error ≈1.5% on 5th-pct."""

    bootstrap_block_seconds: int = Field(86400, ge=3600, le=604800)
    """Block-bootstrap block length (1 day default; preserves intra-day autocorrelation)."""

    cancel_latency_grid: list[float] = Field(
        default_factory=lambda: [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]
    )
    """Fixed cancel-latency sweep grid (BACK-03 verbatim)."""

    competition_multipliers: list[float] = Field(
        default_factory=lambda: [0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
    )
    """Competition multiplier sweep (BACK-04). 1.0 is the unperturbed baseline."""

    all_fees_threshold: float = Field(0.01, ge=0.0, le=1.0)
    """Annualized all_fees floor for the ship-gate threshold (BACK-07).
    Default 0.01 (1% APR) is conservative; operator overrides after first real run."""

    budget_haircut_pessimistic: float = Field(0.5, ge=0.0, le=1.0)
    """A/B summary row haircut on e_liq_per_epoch_pendle (B6 absorption)."""

    perturbation_pct: float = Field(0.20, ge=0.01, le=1.0)
    """±perturbation_pct relative knob delta for BACK-08 sign-flip detection."""

    contour_2d_knobs: list[str] = Field(
        default_factory=lambda: [
            "execution.cancel_latency_budget_s",
            "decision.p_purge_default",
        ],
        min_length=2,
        max_length=2,
    )
    """Two-most-uncertain knobs for the 2D contour heatmap (BACK-08)."""

    output_parquet_root: str = "data/parquet/backtest_results"
    """Hive-partitioned parquet root for run output (BACK-05)."""


__all__ = ["BacktestConfig"]
```

**Rationale:** `decision/config.py` is the freshest example (Plan 04-02) of a top-level Pydantic sub-model attached into `BotConfig`. Same `extra='forbid'`, `frozen=True`, `Field(...)` validators, same docstring discipline (every knob explains rationale + bound).

---

### `python/src/boros_brain/backtest/schemas.py` (Pydantic schemas)

**Analog:** `python/src/boros_brain/decision/schemas.py` (1–69)

**Local StrictBase + frozen Pydantic models** (lines 1–22):

```python
"""Pydantic shapes for the backtest engine (BACK-01..08).

Single home for all Phase-5 shape declarations so architecture.yml has a single
`brain.backtest.schemas` node.

[[backtest-output-schema-and-parquet-partitioning]]
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class StrictBase(BaseModel):
    """Local strict base — extra='forbid', frozen=True.

    Mirrors decision/schemas.py pattern (avoids circular import with config.schema).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
```

**Output-row schema** — derive from RESEARCH.md §"Row shape (one row per [run, sweep_axis, perturbation, bootstrap_idx])" (lines 1108–1156). Same `Literal[...]` + 16-field discipline as `EvaluateInput` (decision/schemas.py:25–46).

**ShipGateVerdict** — derive from RESEARCH.md `bootstrap_ship_gate(...)` return shape (line 439–448): `p5_annualized_pnl`, `threshold`, `passed`, `n_resamples`, `block_seconds`, `seed`, `manifest_run_id`.

**Rationale:** `decision/schemas.py` is the canonical small-shapes module; same `StrictBase` re-declaration pattern, `Literal` enums, frozen invariants. Phase 5 schemas slot into the same architecture.yml node-shape (`type: module`, `public_functions: []`).

---

### `python/src/boros_brain/backtest/replay.py` (engine, event-driven streaming)

**Analog 1:** `python/src/boros_brain/fill_model/queue_tracker.py` (1–100) — parquet scan + eventIndex sort
**Analog 2:** `python/src/boros_brain/decision/breaker_coordinator.py` (83–200) — async tick loop + structured exception handling
**Analog 3:** `python/src/boros_brain/main.py::_decision_loop` (lines 239–301) — driving `evaluate()` + `coord.tick()` per tick

**Imports pattern** (synthesis of queue_tracker.py:21–33 + breaker_coordinator.py:20–37):

```python
"""BACK-01: event-driven replay engine.

Sorted iterator over (blockTimestamp, eventIndex) from market-trades parquet,
interleaved with hourly raw+combined snapshot anchors and 1 Hz decision ticks.
Reuses fill_model.queue_tracker + fill_model.amm_consumption (mandatory — by
construction backtest semantics MUST match Phase 2 fit semantics).

NEVER catches FillModel*Error / LossModelNoFreshGridError / AMMConsumptionIdentityError —
let them propagate; the coordinator (or top-level CLI try/except) is the boundary.

[[backtest-replay-engine-v05]]
[[queue-tracker-algorithm-v05]]
[[amm-consumption-model-v05]]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import polars as pl
import structlog

from ..config.schema import BotConfig
from ..decision.breaker_coordinator import BreakerCoordinator
from ..decision.engine import evaluate as evaluate_decision
from ..decision.gas_history import GasHistoryCache
from ..decision.schemas import EvaluateInput
from ..fill_model.amm_consumption import (
    assert_epoch_conservation,
    compute_amm_share_timeseries,
)
from ..fill_model.queue_tracker import QueueTracker
from .schemas import BacktestRunOutput
from .synthetic_orders import SyntheticOrderLedger

log = structlog.get_logger(__name__)
```

**eventIndex sort pattern** (queue_tracker.py:100–104 — copy verbatim, change root path):

```python
trades = (
    pl.scan_parquet("data/parquet/market_trades/**/*.parquet")
    .filter(
        (pl.col("blockTimestamp") >= window_start_ts)
        & (pl.col("blockTimestamp") < window_end_ts)
        & (pl.col("market_id") == self.market_id)
    )
    .sort(["blockTimestamp", pl.col("eventIndex").fill_null(0)])
    .collect()
)
```

**Per-tick evaluate loop** (synthesized from main.py:_decision_loop:271–301):

```python
async def _emit_tick(self, current_ts: int, calib: dict[str, Any]) -> None:
    """1 Hz decision cadence. Drives the LIVE engine — no shortcut.

    Mirrors main.py::_decision_loop exactly; the only differences are:
      - current_chain_ts comes from the event stream, not chain_time.now_cached()
      - gas_cache is pre-seeded from state.tx_receipts historical fixture
      - w3=None (gas_cache.last_value_pendle short-circuits the RPC)
    """
    decisions = []
    for order in self.synthetic_orders.in_flight():
        req = self._build_evaluate_input(order, calib, current_ts)
        try:
            out = await evaluate_decision(
                req,
                sqlite_path=self.sqlite_path,
                config=self.config,
                gas_cache=self.gas_cache,
                w3=None,
            )
            decisions.append(out)
        except Exception as exc:  # noqa: BLE001 — propagate via log+raise after gate
            log.warning("backtest.evaluate_skipped", order_id=order.id, err=str(exc))
            raise

    await self.coord.tick(
        sqlite_path=self.sqlite_path,
        w3=None,
        parquet_root=self.parquet_root,
        current_chain_ts=current_ts,
    )
    await self.coord.gate(decisions, current_chain_ts=current_ts)
```

**AMM conservation assertion** (RESEARCH.md L827–841 + amm_consumption.py:36 — let propagate):

```python
amm_share_df = compute_amm_share_timeseries(
    raw=raw_at_T0, combined=combined_at_T0,
    epoch_start_ts=T0, epoch_end_ts=T1,
)
# AMMConsumptionIdentityError MUST propagate — never swallow ([[amm-consumption-model-v05]])
assert_epoch_conservation(
    book_ahead_start=book_state.book_ahead_start,
    book_ahead_end=book_state.book_ahead_end,
    taker_consumption_ahead=window_taker,
    amm_consumption=window_amm,
    net_placements_ahead=window_placements,
)
```

**Rationale:** `queue_tracker.py` already implements the eventIndex-sorted parquet scan that BACK-01 mandates. Reusing it is mandatory per RESEARCH.md (line 141, "Backtest semantics MUST match Phase 2 fit semantics by construction"). `breaker_coordinator.py` provides the async-tick + exception-discipline pattern. `main.py::_decision_loop` is the canonical "drive evaluate per in-flight order" pattern. Replay engine is a composition of all three — pattern is already in the tree.

---

### `python/src/boros_brain/backtest/synthetic_orders.py` (model, in-memory ledger)

**Analog:** `python/src/boros_brain/decision/breaker_coordinator.py` (76–82) — `_tripped: dict[str, int]` in-memory dict pattern

**Pattern to copy** (breaker_coordinator.py:64–82 — small dataclass holding mutable dict):

```python
"""BACK-01: in-memory synthetic-order ledger.

Mirrors state.open_orders shape but lives in-memory only — backtest is hermetic
and never writes to SQLite (single-writer-per-table discipline; backtest is
read-only on state).

The ledger is a plain dict[order_id, SyntheticOrder] with .in_flight() iterator.
PLACE/CANCEL decisions from engine.evaluate() mutate this dict; the dict is the
input to the next decision tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Literal


@dataclass(frozen=True)
class SyntheticOrder:
    order_id: str  # synthetic ULID generated at PLACE
    market_id: str
    side: Literal["long", "short"]
    tick: int
    q_me_pendle: float
    placed_at_ts: int
    queue_ahead_wei: int = 0  # updated by QueueTracker
    r_accum: float = 0.0  # accumulated reward (punitive branch only)
    status: Literal["active", "filled", "cancelled", "purged"] = "active"


class SyntheticOrderLedger:
    """In-memory order book mirror. NEVER persisted; backtest is hermetic."""

    def __init__(self) -> None:
        self._orders: dict[str, SyntheticOrder] = {}

    def place(self, order: SyntheticOrder) -> None:
        self._orders[order.order_id] = order

    def in_flight(self) -> Iterator[SyntheticOrder]:
        return (o for o in self._orders.values() if o.status == "active")
```

**Rationale:** `breaker_coordinator._tripped` is the tree's canonical in-memory state-tracking dict (Pitfall #2 says these MUST be coupled to a DB writer for live; backtest is the documented exception per RESEARCH.md L514–524). `dataclass(frozen=True)` matches the in-engine `ScheduledClose` from RESEARCH.md L383–389.

---

### `python/src/boros_brain/backtest/cancel_latency.py` (utility, transform)

**Analog:** `python/src/boros_brain/decision/gas_history.py` — small stateful class with a single computed-output method, no I/O hot-path. (Read confirmed; same shape: `__init__(self, ...)` + `def compute(...)`.)

**Pattern to copy** (RESEARCH.md L884–916 — already a complete recipe; matches gas_history shape):

```python
"""BACK-02: two-axis cancel-latency simulator.

Latency has two compounding axes:
  Axis 1 (order-of-event): the bot's decision lands at the next 1 Hz tick AFTER a fill.
  Axis 2 (time-since-event): close-at-market is scheduled L seconds after fill detection.

Both apply to the same fill — they compound, they do not multiplex. PITFALLS §C2.

[[backtest-cancel-latency-two-axis]]
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduledClose:
    order_id: str
    fill_ts: float          # blockTimestamp of fill (axis-1 reference)
    decision_ts: float      # ceil(fill_ts) — next 1Hz tick (axis-1 effect)
    close_at_ts: float      # decision_ts + L (axis-2 effect)
    fill_rate: float


class LatencyScheduler:
    """Two-axis latency. NEVER calls time.time() — replay engine passes blockTimestamp."""

    def __init__(self, L_seconds: float, decision_period_s: float = 1.0) -> None:
        self.L = L_seconds
        self.dt = decision_period_s

    def schedule(self, fill_ts: float, fill_rate: float, order_id: str) -> ScheduledClose:
        decision_ts = math.ceil(fill_ts / self.dt) * self.dt
        return ScheduledClose(
            order_id=order_id,
            fill_ts=fill_ts,
            decision_ts=decision_ts,
            close_at_ts=decision_ts + self.L,
            fill_rate=fill_rate,
        )
```

**Rationale:** `decision/gas_history.py` is the closest small-stateful-utility analog (small class, one knob `cancel_cost_ewma_alpha`, no I/O hot-path, frozen `ConfigDict` upstream). Same `__init__` + single computational method shape. RESEARCH.md provides the body verbatim.

---

### `python/src/boros_brain/backtest/bootstrap.py` (utility, batch Monte Carlo)

**Analog:** `python/src/boros_brain/loss_model/expected_loss.py` (pure-function pattern with explicit RNG) + RESEARCH.md L420–457 — no preexisting MC analog in repo.

**Pattern to copy** (RESEARCH.md L427–457):

```python
"""BACK-07: block-bootstrap ship-gate evaluator.

5th-percentile of resampled annualized P&L vs threshold (alt_yield + all_fees).
RNG is seeded from RUN_MANIFEST — bit-for-bit reproducibility.

PITFALL #6 (Phase-5 NEW): never call top-level numpy.random.* — always pass
an explicit Generator instance. RNG state contamination kills idempotence.

[[backtest-bootstrap-methodology-v05]]
[[backtest-reproducibility-rng-seed-from-manifest]]
"""

from __future__ import annotations

import numpy as np
import structlog
import ulid

from ..manifest.schema import RunManifest
from ..config.schema import BotConfig
from .schemas import ShipGateVerdict

log = structlog.get_logger(__name__)


def seed_from_manifest(manifest: RunManifest) -> int:
    """ULID -> uint64 seed. Idempotent: same manifest -> same seed.

    ULID is 26-char Crockford base32 (128 bits). Take the low 64 bits
    of the byte representation as the seed.
    """
    u = ulid.from_str(manifest.run_id)
    return int.from_bytes(u.bytes[-8:], byteorder="big") & ((1 << 64) - 1)


def make_rng(manifest: RunManifest) -> np.random.Generator:
    return np.random.default_rng(seed_from_manifest(manifest))


def block_bootstrap_pnl(
    daily_pnl: np.ndarray,
    *,
    rng: np.random.Generator,
    n_resamples: int = 2000,
) -> np.ndarray:
    """Returns N annualized P&L values resampled with replacement on day-blocks."""
    n_days = len(daily_pnl)
    out = np.empty(n_resamples)
    for i in range(n_resamples):
        sample = rng.choice(daily_pnl, size=n_days, replace=True)
        out[i] = sample.sum() * (365.0 / n_days)
    return out
```

**Rationale:** No prior MC analog in repo. Use RESEARCH.md verbatim and `loss_model/expected_loss.py` for the "pure function, explicit RNG, never globals, structured logging on entry" discipline. Pitfall #6 of RESEARCH.md (line 565) is non-negotiable — pass an explicit `Generator` everywhere.

---

### `python/src/boros_brain/backtest/ship_gate.py` (runner + halt-report writer)

**Analog 1 (threshold logic):** `python/src/boros_brain/screener/economics_gate.py` (134–214) — assemble threshold + halt-on-empty pattern
**Analog 2 (halt-report writer):** `python/src/boros_brain/screener/kill_report.py` (47–125) — Markdown report from template + JSON knob tree
**Analog 3 (ProjectHalt SystemExit subclass):** `economics_gate.py` (42–47)

**Threshold assembly** (synthesis of economics_gate.py:160–162 + RESEARCH.md L985–999):

```python
"""BACK-07: ship-gate verdict + threshold assembly.

5th-percentile annualized P&L from N=2000 bootstrap resamples must exceed
alt_yield + all_fees to ship. Point-estimate above threshold is INSUFFICIENT
(PITFALLS §B7).

Mirrors screener.economics_gate halt-on-empty discipline + screener.kill_report
template-rendered Markdown halt artifact.

[[backtest-ship-gate-threshold-assembly]]
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from ..config.schema import BotConfig
from ..manifest.schema import RunManifest
from .bootstrap import block_bootstrap_pnl, make_rng
from .schemas import ShipGateVerdict, ThresholdComponents

log = structlog.get_logger(__name__)


class ShipGateHalt(SystemExit):
    """Phase 5 ship-gate fail. CLI converts to exit code 1.

    Inherits SystemExit so bare `except Exception` does NOT swallow it. Mirrors
    screener.economics_gate.ProjectHalt (lines 42–47) verbatim.
    """


def assemble_threshold(config: BotConfig) -> ThresholdComponents:
    """Per BACK-07: alt_yield (config.screener.alt_yield) + all_fees (config.backtest.all_fees_threshold).

    Both are decimal-fraction APRs. Components persisted to ship_gate_verdict.json
    so operator can audit alongside the verdict.
    """
    alt = config.screener.alt_yield
    fees = config.backtest.all_fees_threshold  # NEW Phase-5 knob
    return ThresholdComponents(
        alternative_yield=alt,
        all_fees=fees,
        total=alt + fees,
        components={"alt_yield": alt, "all_fees": fees},
    )


def evaluate_ship_gate(
    daily_pnl: np.ndarray,
    *,
    manifest: RunManifest,
    config: BotConfig,
) -> ShipGateVerdict:
    rng = make_rng(manifest)
    resampled = block_bootstrap_pnl(
        daily_pnl,
        rng=rng,
        n_resamples=config.backtest.bootstrap_n_resamples,
    )
    p5 = float(np.percentile(resampled, 5))
    threshold = assemble_threshold(config)
    return ShipGateVerdict(
        p5_annualized_pnl=p5,
        threshold=threshold.total,
        passed=(p5 > threshold.total),
        n_resamples=config.backtest.bootstrap_n_resamples,
        block_seconds=config.backtest.bootstrap_block_seconds,
        seed=int(rng.bit_generator.state["state"]["state"]),
        manifest_run_id=manifest.run_id,
    )
```

**Halt-report writer** (mirrors `kill_report.write_kill_report` lines 47–125 — template + `config.model_dump(mode='json')` knob-tree dump):

```python
def write_ship_gate_report(
    verdict: ShipGateVerdict,
    *,
    config: BotConfig,
    manifest: RunManifest,
    output_dir: Path | None = None,
) -> Path:
    """Write docs/ship-gate-report-YYYYMMDD.md. Mirrors kill_report.write_kill_report:
    timestamp + git_sha + run_id + threshold + full knob tree as JSON.
    """
    today = datetime.now(UTC)
    out_dir = output_dir if output_dir is not None else Path("docs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"ship-gate-report-{today.strftime('%Y%m%d')}.md"

    # Reuse kill_report's git_sha helper pattern (lines 84–95 of kill_report.py)
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL,
        ).decode().strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_sha = "unknown"

    body = (
        f"# Phase 5 Ship-Gate Verdict\n\n"
        f"**Status:** {'PASSED' if verdict.passed else 'FAILED'}\n"
        f"**Run ID:** {verdict.manifest_run_id}\n"
        f"**Git SHA:** {git_sha}\n"
        f"**Timestamp:** {today.isoformat()}\n\n"
        f"## Verdict\n\n"
        f"- 5th-percentile annualized P&L: {verdict.p5_annualized_pnl:.4f}\n"
        f"- Threshold (alt_yield + all_fees): {verdict.threshold:.4f}\n"
        f"- Bootstrap resamples: {verdict.n_resamples}\n"
        f"- Block length (seconds): {verdict.block_seconds}\n"
        f"- RNG seed (manifest-derived): {verdict.seed}\n\n"
        f"## Full Knob Tree\n\n"
        f"```json\n{json.dumps(config.model_dump(mode='json'), indent=2)}\n```\n"
    )
    out.write_text(body)
    return out
```

**Rationale:** `screener/economics_gate.py` is the canonical "threshold-vs-baseline + halt-on-fail" runner — Phase 5 ship-gate is a structural twin (replace `r_apr < threshold` with `p5 < threshold`). `screener/kill_report.py` is the canonical halt-report writer (template + git_sha + knob-tree dump). `ShipGateHalt(SystemExit)` mirrors `ProjectHalt(SystemExit)` exactly so the CLI exit-code 0/1/2 contract is identical.

---

### `python/src/boros_brain/backtest/report.py` (parquet writer, file-I/O)

**Analog:** `python/src/boros_brain/loss_model/artifact.py` (29–110) — parquet sidecar dual-write with path-traversal guard

**Pattern to copy** (loss_model/artifact.py:29–62 — Hive-partitioned write + path-traversal guard):

```python
"""BACK-05: backtest output writer. Hive-partitioned parquet + ship-gate verdict JSON.

Output layout:
    data/parquet/backtest_results/run_id=<ulid>/
      ├── sweep_axis=base/results.parquet
      ├── sweep_axis=cancel_latency/L=<value>/results.parquet
      ├── sweep_axis=competition/m=<value>/results.parquet
      ├── sweep_axis=forfeit_branch/branch=<benign|punitive>/results.parquet
      ├── sweep_axis=perturbation/knob_path=<path>/sign=<low|high>/results.parquet
      ├── bootstrap/results.parquet
      ├── ship_gate_verdict.json
      └── lineage_a_b_row.json

Plot generation is a SEPARATE subcommand (`python -m boros_brain.backtest plot`)
NOT called by this writer — plotting is decoupled from replay determinism.

[[backtest-output-schema-and-parquet-partitioning]]
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import structlog

from .schemas import BacktestRunOutput, ShipGateVerdict

log = structlog.get_logger(__name__)


def write_backtest_row(
    row: BacktestRunOutput,
    *,
    parquet_root: Path = Path("data/parquet/backtest_results"),
) -> Path:
    """Write a single output row to its Hive-partitioned location.

    Path-traversal guard pattern copied verbatim from loss_model/artifact.py:51–61:
    resolve() and is_relative_to() check before mkdir.
    """
    parquet_root_resolved = parquet_root.resolve()
    out_dir = (
        parquet_root
        / f"run_id={row.run_id}"
        / f"sweep_axis={row.sweep_axis}"
    )
    if row.sweep_axis != "base":
        out_dir = out_dir / f"sweep_value={row.sweep_value}"
    out_dir = out_dir.resolve()
    if not out_dir.is_relative_to(parquet_root_resolved):
        raise ValueError(
            f"backtest_results path traversal blocked: {out_dir} "
            f"is outside {parquet_root_resolved}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "results.parquet"

    pl.DataFrame([row.model_dump(mode="json")]).write_parquet(out_path)
    log.info("backtest.row_written", run_id=row.run_id, sweep_axis=row.sweep_axis,
             parquet=str(out_path))
    return out_path


def write_ship_gate_verdict_json(
    verdict: ShipGateVerdict,
    *,
    parquet_root: Path = Path("data/parquet/backtest_results"),
) -> Path:
    """Write ship_gate_verdict.json sidecar to the run_id partition root."""
    out = (parquet_root / f"run_id={verdict.manifest_run_id}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "ship_gate_verdict.json"
    path.write_text(json.dumps(verdict.model_dump(mode="json"), indent=2))
    return path
```

**Rationale:** `loss_model/artifact.py` is the only existing Hive-partitioned parquet writer with a path-traversal guard (T-03-01). Same `Path.resolve() + is_relative_to()` discipline is mandatory for any operator-controlled path component (sweep_value can be operator-overridden via competition_multipliers list). Same atomic dual-write pattern (parquet + JSON sidecar).

---

### `python/src/boros_brain/backtest/sweeps/cancel_latency.py` + `competition.py` + `forfeit_branch.py` (sweep runners, batch)

**Analog:** No exact analog (no existing sweep code). Closest patterns: `screener/rescreen.py` (sequential per-market loop) + RESEARCH.md L932–940.

**Pattern to copy** (RESEARCH.md L930–940 verbatim — copy as scaffold):

```python
"""BACK-03: cancel-latency sweep. Fixed grid L ∈ {0.5, 1, 2, 3, 5, 10}s.

Emits one BacktestRunOutput row per L value. dP&L/dL computed downstream by
the report module via central finite difference.

[[backtest-cancel-latency-two-axis]]
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import structlog

from ..manifest.schema import RunManifest
from ...manifest.writer import build_run_manifest
from ..replay import ReplayEngine, ReplayConfig
from ..report import write_backtest_row
from ..schemas import BacktestRunOutput

log = structlog.get_logger(__name__)


def run_cancel_latency_sweep(
    base_run: ReplayConfig,
    *,
    parent_manifest: RunManifest,
    config,
) -> list[BacktestRunOutput]:
    """Per BACK-03: deterministic 6-point grid. Each child run gets a fresh
    manifest with parent_run_id=base.run_id (PROTO-01 mid-run knob-change semantics)."""
    rows: list[BacktestRunOutput] = []
    for L in config.backtest.cancel_latency_grid:
        cfg = replace(base_run, cancel_latency_s=L)
        # Fresh manifest per child run — anti-pattern: single manifest covering all sweep
        # children is the D2 pitfall (RESEARCH.md L485).
        child_manifest = build_run_manifest(config, parent_run_id=parent_manifest.run_id)
        engine = ReplayEngine(cfg, manifest=child_manifest)
        result = engine.run()
        write_backtest_row(result, parquet_root=Path(config.backtest.output_parquet_root))
        rows.append(result)
        log.info("backtest.sweep.cancel_latency.row", L=L, p_n_l=result.annualized_pnl_pct)
    return rows
```

**Rationale:** No exact analog exists; RESEARCH.md L930–940 provides the contract. The pattern is "sequential `for value in grid:` calling `ReplayEngine`, each gets a child manifest, write parquet row per iteration." `competition.py` and `forfeit_branch.py` are structural copies with different sweep axis (`m ∈ multipliers`, `voluntary_cancel_forfeits_accumulated ∈ {True, False}`).

---

### `python/src/boros_brain/backtest/sweeps/perturbation.py` (Pydantic-reflection grid runner)

**Analog 1 (reflection):** `python/tests/test_manifest_contains_all_knobs.py::_collect_leaf_paths` (lines 53–76) — exact reflection idiom
**Analog 2 (grid execution):** `cancel_latency.py` sweep runner (above)

**Reflection pattern** (RESEARCH.md L1011–1029 + test_manifest_contains_all_knobs.py:53–76 — closer to canon):

```python
"""BACK-08: perturbation grid runner. ±20% per-knob individually, sign-flip detection.

Reflection-driven enumeration of BotConfig.model_dump(mode='json') leaves —
adding a knob to BotConfig automatically extends the grid. NO hand-maintained
list (PROTO-04 SSoT).

The reflection idiom is the same _collect_leaf_paths pattern from
tests/test_manifest_contains_all_knobs.py:53–76 — but operates on the dumped
JSON dict (numeric leaves only) instead of the model class hierarchy.

[[backtest-perturbation-grid-pydantic-reflection]]
"""

from __future__ import annotations

from dataclasses import dataclass

from ...config.schema import BotConfig


@dataclass(frozen=True)
class KnobLeaf:
    path: str            # dotted path, e.g. "decision.p_purge_default"
    value: float


def enumerate_perturbable_leaves(config: BotConfig) -> list[KnobLeaf]:
    """Walk config.model_dump(mode='json') for all numeric leaves.

    Numeric leaves = float | int (NOT bool — booleans handled by BACK-06, not here).
    """
    out: list[KnobLeaf] = []

    def _walk(d, path: list[str]) -> None:
        if isinstance(d, dict):
            for k, v in d.items():
                _walk(v, path + [k])
        elif isinstance(d, list):
            for i, v in enumerate(d):
                _walk(v, path + [str(i)])
        elif isinstance(d, (int, float)) and not isinstance(d, bool):
            out.append(KnobLeaf(path=".".join(path), value=float(d)))

    _walk(config.model_dump(mode="json"), [])
    return out
```

**Sign-flip detection** (RESEARCH.md L1036–1045 — verbatim):

```python
def detect_sign_flip(unperturbed_pnl: float, low_pnl: float, high_pnl: float) -> bool:
    """A knob is `fragile` if perturbing ±perturbation_pct flips P&L sign."""
    sign_unp = (unperturbed_pnl > 0) - (unperturbed_pnl < 0)
    sign_low = (low_pnl > 0) - (low_pnl < 0)
    sign_high = (high_pnl > 0) - (high_pnl < 0)
    return sign_unp != sign_low or sign_unp != sign_high
```

**Rationale:** `test_manifest_contains_all_knobs.py::_collect_leaf_paths` is the canonical Pydantic reflection idiom — already used by 2 phases. Here we adapt it to operate on the dumped JSON dict (closer to PROTO-04 manifest-writer reflection in `manifest/writer.py:80`). The two reflections are linked: adding a `BotConfig` leaf must surface in BOTH the manifest writer AND the perturbation grid — the `test_phase4_manifest_leaves.py` test (lines 48–96) is the CI guard.

---

### `python/src/boros_brain/config/schema.py` (MODIFY — add `backtest: BacktestConfig`)

**Analog:** Existing line 227 of the same file — `decision: DecisionEngineConfig = Field(default_factory=DecisionEngineConfig)`

**Insertion pattern** (mirror line 227 verbatim — add directly after the `decision:` line):

```python
# Edit at line ~228 of python/src/boros_brain/config/schema.py:
from ..backtest.config import BacktestConfig  # NEW import alongside existing sub-models

# Inside class BotConfig, after the `decision:` line:
    decision: DecisionEngineConfig = Field(default_factory=DecisionEngineConfig)  # type: ignore  # existing
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)  # type: ignore  # NEW Plan 5
    markets: list[MarketCalibration] = Field(default_factory=list, max_length=1)  # existing
```

**Rationale:** The Plan-04-02 attachment of `DecisionEngineConfig` (line 227) is the exact precedent — same `Field(default_factory=...)` + `# type: ignore` pattern. Phase 4 added `from ..decision.config import DecisionEngineConfig` (line 19); Phase 5 adds the symmetric `from ..backtest.config import BacktestConfig`. The `test_phase4_manifest_leaves.py` test will need a sibling `test_phase5_backtest_leaves.py` asserting >=8 `backtest.*` knobs surface (mirrors lines 48–96 of the Phase-4 test verbatim).

---

### `python/tests/test_backtest_replay_event_index_order.py` (test, property)

**Analog:** `python/tests/test_decision_engine_ev_equation.py` (1–80)

**Imports + RED-skip preamble** (lines 1–35 — copy verbatim, change module names):

```python
"""BACK-01 — Event-driven replay processes events in (blockTimestamp, eventIndex) order.

This module RED-skips via pytest.importorskip until brain.backtest.replay lands.
Tests will turn GREEN when the engine module exists.

[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# RED state guard: module under test lands in Phase 5.
replay = pytest.importorskip("boros_brain.backtest.replay")
schemas = pytest.importorskip("boros_brain.backtest.schemas")

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
```

**Test body shape** (test_decision_engine_ev_equation.py:80–117 + RESEARCH.md L805–812):

```python
@pytest.mark.asyncio
async def test_replay_processes_events_in_event_index_order(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_trades_parquet,  # NEW fixture (conftest extension)
) -> None:
    """Property: replay yields events monotone in (blockTimestamp, eventIndex)."""
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID, with_ties=True)
    engine = replay.ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_path / "state.sqlite",
        cancel_latency_s=2.0,
        run_id="test-001",
    )
    seen_ts, seen_ei = -1, -1
    for evt in engine.iter_events():
        assert (evt["blockTimestamp"], evt["eventIndex"]) >= (seen_ts, seen_ei)
        seen_ts, seen_ei = evt["blockTimestamp"], evt["eventIndex"]
```

**Rationale:** `test_decision_engine_ev_equation.py` is the freshest RED-skip test pattern (Plan 04-03). Same `pytest.importorskip` preamble, same fixture-factory pattern (`seed_loss_grid_artifact`, `seed_fill_model_fit`). All Phase-5 tests follow this template. `test_amm_conservation.py` (existing) provides the polars-side AMM-identity test pattern (used as the analog for `test_backtest_amm_conservation_replay.py`).

---

### `python/tests/test_backtest_perturbation_grid_pydantic.py` (test, property)

**Analog:** `python/tests/test_manifest_contains_all_knobs.py` (1–115)

**Pattern to copy** (lines 96–106 — adapt to assert reflection enumeration):

```python
"""BACK-08 — perturbation grid enumerates all numeric BotConfig leaves.

Adding a numeric leaf to BotConfig MUST surface in enumerate_perturbable_leaves
without code changes elsewhere — the perturbation runner is reflection-driven.
Mirrors test_manifest_contains_all_knobs.py::test_manifest_contains_all_knobs.

[[backtest-perturbation-grid-pydantic-reflection]]
"""

from __future__ import annotations

import pytest

perturbation = pytest.importorskip("boros_brain.backtest.sweeps.perturbation")

from boros_brain.config.schema import BotConfig  # noqa: E402


def test_perturbation_grid_contains_all_numeric_leaves(default_config: BotConfig) -> None:
    """T-03-01-style guard: every numeric BotConfig leaf appears in the grid."""
    leaves = perturbation.enumerate_perturbable_leaves(default_config)
    leaf_paths = {leaf.path for leaf in leaves}

    # Spot-check 5 known numeric leaves from each phase.
    required = {
        "decision.cancel_cost_ewma_alpha",
        "decision.p_purge_default",
        "execution.cancel_latency_budget_s",
        "screener.alt_yield",
        "backtest.bootstrap_n_resamples",   # Phase-5 NEW
    }
    missing = required - leaf_paths
    assert not missing, f"perturbation grid missing leaves: {missing}"
    # Phase-1+2+3+4+5 grand total ≈ 30+ numeric leaves
    assert len(leaves) >= 30
```

**Rationale:** `test_manifest_contains_all_knobs.py` is the existing Pydantic-reflection-correctness test. Phase 5 adds a sibling that asserts the SAME leaves are enumerated by the perturbation runner. Same `_collect_leaf_paths` idiom (test:53–76) is mirrored in `enumerate_perturbable_leaves` — when the reflection ever drifts, both tests fail in lockstep.

---

### `python/tests/test_backtest_run_manifest_first.py` (test, unit)

**Analog:** `python/tests/test_manifest_contains_all_knobs.py` (96–115) + `decision/cli.py:85–98` (the manifest-FIRST contract)

**Pattern to copy** (synthesis):

```python
"""BACK-* PROTO-01 — backtest CLI emits RUN_MANIFEST as first log record.

Mirrors test_manifest_contains_all_knobs.py shape; asserts the CLI hooks into
build_run_manifest+write_manifest+structlog before any other log line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

cli_mod = pytest.importorskip("boros_brain.backtest.cli")

from boros_brain.config.schema import BotConfig  # noqa: E402


def test_backtest_cli_emits_run_manifest_first(
    tmp_path: Path,
    default_config: BotConfig,
    monkeypatch,
) -> None:
    """First log line via structlog must be the RUN_MANIFEST record."""
    # Pattern from existing test_main_decision_loop_spawn.py — capture log lines,
    # assert manifest record is record[0] with mode='backtest'.
    ...  # exact body lifted from test_main_decision_loop_spawn.py shape
```

**Rationale:** Phase 1+4 already established the "first log line is RUN_MANIFEST" contract (`test_manifest_contains_all_knobs.py` + the CLI inspections). Phase 5 needs a smoke-style sibling test that checks the backtest CLI honors the same boot order. Use the existing CLI test patterns; no novel idiom needed.

---

## Wave-0 Specific Patterns

### `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py` (MODIFY — Wave-0 ZMQ fix)

**Analog:** itself, line 99 (broken) → fix in lines 99–142

**Bad pattern to remove** (lines 99–142 — the leak):

```python
ctx = zmq.asyncio.Context.instance()        # ← LINE 99 — PROCESS-WIDE SINGLETON LEAK
kill_pull = ctx.socket(zmq.PULL)
kill_pull.bind(kill_endpoint)
# ... existing body unchanged ...
kill_pull.close()    # ← LINE 141 — closes socket but NOT context
bus.close()
# ← MISSING ctx.term() — singleton leaks state across parametrize iterations
```

**Good pattern to apply** (RESEARCH.md L729–742 — copy verbatim):

```python
ctx = zmq.asyncio.Context()                 # NOT Context.instance()
try:
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.bind(kill_endpoint)
    # ... existing test body 100% unchanged ...
finally:
    kill_pull.close()
    bus.close()
    ctx.term()                              # MUST term, not just close
```

**Rationale:** `Context.instance()` is the documented pyzmq process-wide singleton; using `Context()` per-test plus `try/finally: ctx.term()` is the canonical fix per pyzmq docs. RESEARCH.md L572–578 contains the full root-cause analysis. Fix is 5 lines.

---

### `scripts/no_zmq_singleton_in_tests_lint.py` (NEW — regression guard)

**Analog:** `scripts/no_threshold_dials_lint.py` (1–119) — exact structural twin

**Imports + module docstring** (lines 1–47 — copy, change PROTECTED_DIRS + PATTERN):

```python
#!/usr/bin/env python3
"""Pre-commit hook: rejects ``zmq.asyncio.Context.instance()`` under python/tests/.

Wave-0 prerequisite: BACK-07 success criterion #6 requires `cd python && uv run pytest -q`
produces 322/322+1-skipped green with no `--ignore`. The Phase-4 carried hang in
test_breaker_coordinator_publishes_kill_lane_per_safe.py was caused by the
process-wide singleton at line 99: leaked Context state across parametrize
iterations under specific test-order interactions.

The fix replaces Context.instance() with Context() + try/finally: ctx.term().
This lint enforces the discipline so the next test author who copies the old
pattern is blocked at commit time.

See [[wave-0-zmq-fixture-leak-fix]].

Usage
-----
Pre-commit (normal operation)::

    python3 scripts/no_zmq_singleton_in_tests_lint.py

Direct invocation (CI / test)::

    python3 scripts/no_zmq_singleton_in_tests_lint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROTECTED_DIRS = (
    "python/tests/",
)

# No allowed exceptions — Context.instance() is universally banned in tests.
ALLOWED_FILES: set[str] = set()

PATTERN = re.compile(r"\bzmq\.asyncio\.Context\.instance\s*\(")
```

**Scan + main pattern** (lines 72–115 of no_threshold_dials_lint.py — copy verbatim):

```python
def _all_protected_files() -> list[Path]:
    """Return every existing .py file under PROTECTED_DIRS."""
    return [
        p
        for d in PROTECTED_DIRS
        for p in Path(d).rglob("*.py")
        if p.is_file()
    ]


def _scan(path: Path) -> list[tuple[int, str]]:
    s = str(path).replace("\\", "/")
    if s in ALLOWED_FILES:
        return []
    if not path.is_file():
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
            print(
                f"[no_zmq_singleton_in_tests] {p}:{lineno}: "
                f"use Context() + try/finally: ctx.term() instead of Context.instance() — "
                f"{line.strip()[:80]}",
                file=sys.stderr,
            )
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
```

**Rationale:** `no_threshold_dials_lint.py` is the exact structural twin — same `PROTECTED_DIRS` + `PATTERN` + `_all_protected_files` + `_scan` + `main` shape. Line-for-line copy with PATTERN swap is the path of least friction; the corresponding test (`test_no_zmq_singleton_in_tests_lint.py`) mirrors `test_no_threshold_dials_lint.py:36–84` verbatim.

---

### `python/pyproject.toml` (MODIFY — add pytest-timeout + timeout=30)

**Analog:** itself, lines 23–33 (dev group) + lines 42–50 (`[tool.pytest.ini_options]`)

**Modifications:**

```toml
# Add to existing [dependency-groups].dev list (after line 33, before closing `]`)
[dependency-groups]
dev = [
  "pytest>=8,<9",
  "pytest-asyncio>=0.24",
  "pytest-testmon>=2",
  "pytest-timeout>=2.3,<3",     # ← NEW — Wave-0 prerequisite (BACK-07 #6)
  "ruff>=0.7",
  "mypy>=1.13",
  "hypothesis>=6",
  "pre-commit>=4",
  "types-pyyaml>=6.0.12.20260408",
]

# Add to existing [tool.pytest.ini_options] block (after `addopts` line 45)
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra --strict-markers"
timeout = 30                    # ← NEW — Wave-0 prerequisite; any test > 30s fails fast
pythonpath = ["src"]
markers = [
  "slow: long-running (skipped by quick pass)",
  "wave0_scaffold: tracer-bullet stubs wired once dependent plan lands",
]
```

**Rationale:** `pytest-timeout` is a stable plugin (>=2.3, since 2014). Both edits are sub-line additions to existing TOML blocks — no structural change. RESEARCH.md L753–756 specifies version pin verbatim.

---

### `python/tests/conftest.py` (MODIFY — add backtest fixtures)

**Analog:** itself, `seed_underlying_apr_parquet` (lines 357–379) — exact shape for parquet seed-fixtures.

**Pattern to copy** (lines 357–379 — adapt for market_trades and order_book):

```python
@pytest.fixture
def seed_market_trades_parquet(tmp_path: Path) -> Callable:
    """Fixture-factory for market_trades parquet snapshots (BACK-01 testbench).

    Returns a callable: _seed(market_id, with_ties, parquet_root) -> Path.
    Writes a polars DataFrame with deterministic (blockTimestamp, eventIndex) rows
    so eventIndex-ordering tests have ties to test against.
    """

    def _seed(
        market_id: str = "BINANCE-ETHUSDT-29MAY2026",
        with_ties: bool = False,
        parquet_root: Path | None = None,
    ) -> Path:
        import polars as pl

        root = parquet_root if parquet_root is not None else tmp_path / "parquet"
        out_dir = root / "market_trades" / f"market_id={market_id}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "snapshot.parquet"

        # 10 events at 5 different blockTimestamps; with_ties=True makes 2 events
        # share each blockTimestamp differing only by eventIndex
        if with_ties:
            ts = [1_700_000_000, 1_700_000_000, 1_700_000_001, 1_700_000_001, 1_700_000_002]
            ei = [0, 1, 0, 1, 0]
        else:
            ts = [1_700_000_000 + i for i in range(5)]
            ei = [0] * 5
        pl.DataFrame({
            "market_id": [market_id] * 5,
            "blockTimestamp": ts,
            "eventIndex": ei,
            "rate": [0.05] * 5,
            "size_wei": [10**18] * 5,
            "side": ["buy"] * 5,
        }).write_parquet(out_file)
        return root

    return _seed


@pytest.fixture
def seed_order_book_raw_parquet(tmp_path: Path) -> Callable:
    """Mirror of seed_market_trades_parquet for order_book_raw/."""
    # Identical shape — substitute schema columns
    ...  # see seed_market_trades_parquet for template


@pytest.fixture
def seed_order_book_combined_parquet(tmp_path: Path) -> Callable:
    """Mirror for order_book_combined/. Combined - raw = AMM share."""
    # Identical shape — substitute schema columns
    ...  # see seed_market_trades_parquet for template
```

**Rationale:** `seed_underlying_apr_parquet` (lines 357–379) already exists with the exact Hive-partitioned-write shape backtest needs. Phase 5 adds three structural twins for `market_trades/`, `order_book_raw/`, `order_book_combined/` — same closure + same polars + same Hive layout.

---

### `docs/architecture.yml` (MODIFY)

**Analog:** itself, the `brain.decision.*` block (lines 1107–1392 nodes; lines 2612–2641 edges) — exact precedent for adding a new sub-package.

**New nodes** (mirror the brain.decision.* block lines 1107–1132 — same `type: module`, `process: brain`, empty `public_functions: []` for class-only modules; copy idiomatically):

```yaml
  # ── Phase 5 Plan 5 — backtest package ──────────────────────────────────
  - id: brain.backtest
    type: external
    notes: "backtest package __init__ — documentation marker; lint skips __init__.py"
    path: python/src/boros_brain/backtest/__init__.py

  - id: brain.backtest.config
    type: module
    process: brain
    path: python/src/boros_brain/backtest/config.py
    public_functions: []

  - id: brain.backtest.schemas
    type: module
    process: brain
    path: python/src/boros_brain/backtest/schemas.py
    public_functions: []

  - id: brain.backtest.replay
    type: module
    process: brain
    path: python/src/boros_brain/backtest/replay.py
    public_functions: []  # ReplayEngine class only

  - id: brain.backtest.synthetic_orders
    type: module
    process: brain
    path: python/src/boros_brain/backtest/synthetic_orders.py
    public_functions: []  # SyntheticOrderLedger class only

  - id: brain.backtest.cancel_latency
    type: module
    process: brain
    path: python/src/boros_brain/backtest/cancel_latency.py
    public_functions: []  # LatencyScheduler class only

  - id: brain.backtest.bootstrap
    type: module
    process: brain
    path: python/src/boros_brain/backtest/bootstrap.py
    public_functions: [seed_from_manifest, make_rng, block_bootstrap_pnl]

  - id: brain.backtest.ship_gate
    type: module
    process: brain
    path: python/src/boros_brain/backtest/ship_gate.py
    public_functions: [assemble_threshold, evaluate_ship_gate, write_ship_gate_report]

  - id: brain.backtest.report
    type: module
    process: brain
    path: python/src/boros_brain/backtest/report.py
    public_functions: [write_backtest_row, write_ship_gate_verdict_json]

  - id: brain.backtest.cli
    type: module
    process: brain
    path: python/src/boros_brain/backtest/cli.py
    public_functions: [build_parser, main]

  - id: brain.backtest.sweeps.cancel_latency
    type: module
    process: brain
    path: python/src/boros_brain/backtest/sweeps/cancel_latency.py
    public_functions: [run_cancel_latency_sweep]

  - id: brain.backtest.sweeps.competition
    type: module
    process: brain
    path: python/src/boros_brain/backtest/sweeps/competition.py
    public_functions: [run_competition_sweep]

  - id: brain.backtest.sweeps.forfeit_branch
    type: module
    process: brain
    path: python/src/boros_brain/backtest/sweeps/forfeit_branch.py
    public_functions: [run_forfeit_branch_sweep]

  - id: brain.backtest.sweeps.perturbation
    type: module
    process: brain
    path: python/src/boros_brain/backtest/sweeps/perturbation.py
    public_functions: [enumerate_perturbable_leaves, detect_sign_flip, run_perturbation_grid]

  - id: scripts.no_zmq_singleton_in_tests_lint
    type: external
    notes: "pre-commit hook: rejects zmq.asyncio.Context.instance() under python/tests/ (Wave-0 fixture leak guard)"
    path: scripts/no_zmq_singleton_in_tests_lint.py

  - id: parquet.backtest_results
    type: parquet
    notes: "Hive-partitioned: run_id=<ulid>/sweep_axis=<...>/sweep_value=<...>/results.parquet"
    path: data/parquet/backtest_results/
```

**New edges** (mirror lines 2612–2641 — same compact `{from: ..., to: ..., type: ...}` shape, RESEARCH.md §"Architecture Manifest Delta" L1402–1421 enumerates all):

```yaml
  # ── Phase 5 — backtest edges ───────────────────────────────────────────
  - {from: brain.backtest.replay, to: brain.fill_model.queue_tracker, type: calls}
  - {from: brain.backtest.replay, to: brain.fill_model.amm_consumption, type: calls}
  - {from: brain.backtest.replay, to: brain.decision.engine, type: calls}
  - {from: brain.backtest.replay, to: brain.decision.breaker_coordinator, type: calls}
  - {from: brain.backtest.replay, to: brain.decision.gas_history, type: calls}
  - {from: brain.backtest.replay, to: state.market_reward_calibration, type: reads, notes: "WHERE data_source='operator' (LOCKED D-01)"}
  - {from: brain.backtest.replay, to: state.fill_model_fits, type: reads}
  - {from: brain.backtest.replay, to: state.loss_grid_artifacts, type: reads}
  - {from: brain.backtest.replay, to: state.competition_history, type: reads}
  - {from: brain.backtest.replay, to: state.tx_receipts, type: reads, notes: "synthetic gas baseline only"}
  - {from: brain.backtest.replay, to: state.clo_history, type: reads}
  - {from: brain.backtest.replay, to: parquet.market_trades, type: reads}
  - {from: brain.backtest.replay, to: parquet.order_book_raw, type: reads}
  - {from: brain.backtest.replay, to: parquet.order_book_combined, type: reads}
  - {from: brain.backtest.replay, to: parquet.underlying_apr, type: reads}
  - {from: brain.backtest.bootstrap, to: brain.manifest.schema, type: depends-on}
  - {from: brain.backtest.ship_gate, to: brain.screener.economics_gate, type: reads, notes: "alt_yield baseline"}
  - {from: brain.backtest.ship_gate, to: brain.backtest.bootstrap, type: calls}
  - {from: brain.backtest.report, to: parquet.backtest_results, type: writes}
  - {from: brain.backtest.cli, to: brain.manifest.writer, type: calls, notes: "MANIFEST-FIRST (PROTO-01)"}
  - {from: brain.backtest.cli, to: state.run_manifests, type: writes, notes: "via manifest.writer.write_manifest"}
  - {from: brain.backtest.sweeps.cancel_latency, to: brain.backtest.replay, type: calls}
  - {from: brain.backtest.sweeps.competition, to: brain.backtest.replay, type: calls}
  - {from: brain.backtest.sweeps.forfeit_branch, to: brain.backtest.replay, type: calls}
  - {from: brain.backtest.sweeps.perturbation, to: brain.backtest.replay, type: calls}
  - {from: brain.config.schema, to: brain.backtest.config, type: calls, notes: "BotConfig.backtest: BacktestConfig — Plan 5 attached"}
  - {from: brain.backtest.replay, to: config.execution.cancel_latency_budget_s, type: depends-on-config}
  - {from: brain.backtest.bootstrap, to: config.backtest.bootstrap_n_resamples, type: depends-on-config}
  - {from: brain.backtest.bootstrap, to: config.backtest.bootstrap_block_seconds, type: depends-on-config}
  - {from: brain.backtest.ship_gate, to: config.backtest.all_fees_threshold, type: depends-on-config}
  - {from: brain.backtest.ship_gate, to: config.screener.alt_yield, type: depends-on-config}
```

**Rationale:** Phase 4 added an entire sub-package (decision/) and 30+ edges — exactly the same shape Phase 5 needs. Copy the structure, swap names. The compact `{from: …, to: …, type: …}` edge shape (lines 2622+) is the modern style for new edges; older blocks use the `- from: ... \n  to: ... \n  type: ...` multi-line form. Phase 5 follows the modern compact style for consistency with Phase 4 Plans 04-03/04-07.

---

### `docs/ARCHITECTURE.md` (MODIFY — add `backtest` subgraph)

**Analog:** itself, brain subgraph lines 44–60

**Pattern to copy** (subgraph block):

```markdown
    subgraph backtest["backtest — Python offline analysis (Phase 5)"]
        bt_replay["backtest/replay.py<br/>ReplayEngine (BACK-01)"]
        bt_synth["backtest/synthetic_orders.py<br/>SyntheticOrderLedger"]
        bt_latency["backtest/cancel_latency.py<br/>LatencyScheduler (BACK-02)"]
        bt_bootstrap["backtest/bootstrap.py<br/>block_bootstrap_pnl (BACK-07)"]
        bt_ship["backtest/ship_gate.py<br/>evaluate_ship_gate (BACK-07)"]
        bt_report["backtest/report.py<br/>write_backtest_row (BACK-05)"]
        bt_sweeps["backtest/sweeps/{cancel_latency,competition,forfeit_branch,perturbation}.py<br/>(BACK-03/04/06/08)"]
        bt_cli["backtest/cli.py<br/>python -m boros_brain.backtest"]
    end
```

**Rationale:** ARCHITECTURE.md uses Mermaid `subgraph` blocks for each major package. Phase 4 added the `decision/` subgraph using the same structure (each module → 1 node, brief one-line role description, BACK-* / SAFE-* tag in parens). Phase 5 follows the same convention.

---

## Shared Patterns

### Authentication / Authorization

**N/A** — Phase 5 is Python-only, single-operator local CLI. No auth surface (RESEARCH.md L1268–1274).

---

### Error Handling

**Source:** `python/src/boros_brain/decision/engine.py` (lines 88–96 — docstring "Raises" block) + `decision/breaker_coordinator.py` (lines 115–124)

**Apply to:** All `backtest/` modules.

**Pattern:** Two-level discipline:

1. **Engine-side (let propagate):** Mirror `decision/engine.py`'s "NEVER swallow model errors" contract. The replay engine MUST let `FillModel*Error`, `LossModelNoFreshGridError`, and `AMMConsumptionIdentityError` propagate (RESEARCH.md L490 anti-pattern). One try/except at the CLI boundary, NOT scattered in the engine.

```python
# AT THE BOUNDARY ONLY — backtest/cli.py:
try:
    return run_backtest(args, manifest, config)
except (FillModelStaleFeatureError, LossModelNoFreshGridError) as exc:
    log.error("backtest.fatal_model_error", err=str(exc))
    return 1
except AMMConsumptionIdentityError as exc:
    log.error("backtest.amm_identity_violation", err=str(exc))
    return 1  # MUST not be retried — data ingest is broken
```

2. **Coordinator-side (200ms timeout pattern):** Mirror `breaker_coordinator.tick`'s `asyncio.wait_for(..., timeout=0.2)` discipline (lines 105–124) — bounded execution per breaker, never blocks the loop.

---

### Validation (Pydantic + frozen invariants)

**Source:** `python/src/boros_brain/decision/config.py` (StrictBase + Field validators) + `manifest/schema.py` (StrictBase, frozen=True)

**Apply to:** All `backtest/config.py` knobs, `backtest/schemas.py` shapes, `backtest/synthetic_orders.SyntheticOrder`, `backtest/cancel_latency.ScheduledClose`.

```python
# Frozen dataclass for in-memory ledger entries:
from dataclasses import dataclass

@dataclass(frozen=True)  # immutable; mutation is the bug-finder
class SyntheticOrder:
    ...

# Frozen Pydantic for serialized output rows:
from pydantic import BaseModel, ConfigDict

class StrictBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class BacktestRunOutput(StrictBase):
    ...
```

**Rationale:** PROTO-04 (single Pydantic source of truth) + RESEARCH.md §"Validation Architecture" (line 1273). Adding a knob to `BacktestConfig` without validation is a regression caught by `test_phase4_manifest_leaves.py`-style reflection tests.

---

### Logging (structlog + manifest contextvars)

**Source:** `python/src/boros_brain/manifest/writer.py` (lines 86–127 — sidecar + SQLite atomic write) + `decision/cli.py` (lines 85–98 — RUN_MANIFEST first)

**Apply to:** All `backtest/cli.py` boot, all sweep runners, all logger creation.

```python
# Top of every backtest module:
import structlog
log = structlog.get_logger(__name__)

# Top of every CLI subcommand:
log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))
log.info("backtest.subcommand_started", subcommand=args.cmd)

# Per-row in sweeps:
log.info("backtest.sweep.cancel_latency.row", L=L, p_n_l=result.annualized_pnl_pct)
```

**Rationale:** `configure_logging` already binds `run_id` via contextvars; every backtest log line auto-tags with the active run. The sweep runners explicitly log per-row at INFO so the operator can grep `run_id=ulid AND sweep_axis=cancel_latency` and reconstruct the curve from the log alone.

---

### Path-traversal guard for parquet writes

**Source:** `python/src/boros_brain/loss_model/artifact.py` (lines 51–62) — `Path.resolve()` + `is_relative_to()` + `ValueError`

**Apply to:** All `backtest/report.py` writers (operator-controlled `sweep_value` and `knob_path` are formatted into directory names → traversal risk).

```python
parquet_root_resolved = parquet_root.resolve()
out_dir = (parquet_root / f"sweep_value={value}").resolve()
if not out_dir.is_relative_to(parquet_root_resolved):
    raise ValueError(f"backtest_results path traversal blocked: {out_dir}")
out_dir.mkdir(parents=True, exist_ok=True)
```

**Rationale:** T-03-01 mitigation. `competition_multipliers` and `cancel_latency_grid` are operator-overridable; values get formatted into Hive directory names; without the guard a malicious YAML can escape parquet_root.

---

### Reflection over BotConfig (PROTO-04 SSoT)

**Source:** `python/src/boros_brain/manifest/writer.py` (line 80 — `config.model_dump(mode="json")`) + `python/tests/test_manifest_contains_all_knobs.py` (lines 53–76 — `_collect_leaf_paths`)

**Apply to:** `backtest/sweeps/perturbation.py::enumerate_perturbable_leaves` MUST use the same reflection so adding a `BotConfig` knob automatically extends both the manifest AND the perturbation grid.

```python
# Same idiom, applied to dumped JSON dict instead of model class:
config.model_dump(mode="json")  # source of truth — walked by both manifest writer + perturbation grid
```

**Rationale:** Pitfall #5 of RESEARCH.md (D2 line 558–563). The forcing function for "knob registered in BotConfig before code uses it" is mechanically the perturbation runner — if the runner can't see a knob via reflection, the knob can't be in code, by construction.

---

### MANIFEST-FIRST boot (PROTO-01)

**Source:** `python/src/boros_brain/decision/cli.py` (lines 85–99) + `screener/cli.py` (lines 110–122)

**Apply to:** `backtest/cli.py` MUST follow this exact boot order (load_config → build_run_manifest → configure_logging → write_manifest → first log line is RUN_MANIFEST).

```python
config = load_config(args.config)
manifest = build_run_manifest(config)              # PROTO-01 step 1
configure_logging(run_id=manifest.run_id, ...)     # PROTO-01 step 2
write_manifest(manifest, ...)                       # PROTO-01 step 3 (sidecar + SQLite)
log = structlog.get_logger("backtest.cli")
log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))  # PROTO-01 step 4 — first log line
```

**Rationale:** All three existing CLI entrypoints (`decision`, `screener`, `loss_model`, `sizer`) follow this exact 4-step preamble. Phase 5 is no exception. Sweep child runs additionally pass `parent_run_id=parent_manifest.run_id` to `build_run_manifest` (RESEARCH.md L485 anti-pattern).

---

## Files With No Existing Analog

| File | Role | Data Flow | Mitigation |
|------|------|-----------|------------|
| `backtest/bootstrap.py` | Monte Carlo | batch | Use RESEARCH.md L420–457 verbatim + `loss_model/expected_loss.py` for pure-fn discipline + Pitfall #6 (explicit RNG everywhere) |
| `backtest/sweeps/{cancel_latency,competition,forfeit_branch}.py` | sweep runner | batch | Use RESEARCH.md L930–940 + main.py decision-loop iteration shape |
| `data/parquet/backtest_results/` | NEW Hive partition | output | Mirror existing Hive partitions (`market_trades/`, `loss_grid_artifacts/`); same path-traversal guard as `loss_model/artifact.py:51–62` |

Total: 4 files require RESEARCH.md as primary authority instead of an exact in-tree analog. All four are well-specified in RESEARCH.md with paste-ready code blocks; none introduce a novel idiom.

---

## Metadata

**Analog search scope:**
- `python/src/boros_brain/{config,decision,fill_model,loss_model,screener,manifest,duckdb_layer,main.py}/` — primary search
- `python/tests/` — test analogs (focus on Phase-4 test patterns)
- `scripts/no_*_lint.py` — lint hook analogs
- `docs/architecture.yml` + `docs/ARCHITECTURE.md` — manifest delta analogs

**Files scanned (read in full or targeted ranges):** 22

- `python/src/boros_brain/decision/engine.py` (full)
- `python/src/boros_brain/decision/cli.py` (full)
- `python/src/boros_brain/decision/__main__.py` (full)
- `python/src/boros_brain/decision/__init__.py` (full)
- `python/src/boros_brain/decision/config.py` (full)
- `python/src/boros_brain/decision/schemas.py` (full)
- `python/src/boros_brain/decision/breaker_coordinator.py` (full)
- `python/src/boros_brain/manifest/writer.py` (full)
- `python/src/boros_brain/manifest/schema.py` (full)
- `python/src/boros_brain/config/schema.py` (full)
- `python/src/boros_brain/screener/cli.py` (full)
- `python/src/boros_brain/screener/economics_gate.py` (lines 1–230)
- `python/src/boros_brain/screener/kill_report.py` (full)
- `python/src/boros_brain/screener/report.py` (full)
- `python/src/boros_brain/main.py` (lines 1–437 sampled in 2 ranges)
- `python/src/boros_brain/loss_model/artifact.py` (lines 1–110)
- `python/src/boros_brain/loss_model/cli.py` (lines 1–80)
- `python/src/boros_brain/duckdb_layer/setup.py` (full)
- `python/src/boros_brain/fill_model/queue_tracker.py` (lines 1–100)
- `python/src/boros_brain/fill_model/amm_consumption.py` (lines 1–50)
- `python/tests/conftest.py` (lines 1–379)
- `python/tests/test_decision_engine_ev_equation.py` (lines 1–120)
- `python/tests/test_manifest_contains_all_knobs.py` (lines 1–120)
- `python/tests/test_phase4_manifest_leaves.py` (full)
- `python/tests/test_no_threshold_dials_lint.py` (full)
- `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py` (full)
- `scripts/no_threshold_dials_lint.py` (full)
- `scripts/no_time_time_lint.py` (full)
- `python/pyproject.toml` (full)
- `docs/architecture.yml` (targeted: lines 1–100 + 1100–1180 + 1380–1394 + 2530–2641)
- `docs/ARCHITECTURE.md` (lines 1–60)

**Pattern extraction date:** 2026-04-26

**Coverage:**
- Files with exact analog: 23
- Files with role-match analog: 3
- Files with partial analog (RESEARCH.md primary): 4

Phase 5 is heavily composition over Phase 1–4 modules — the analog density is high because backtest deliberately reuses the live engine, predict/expected_loss/r_capped, breaker_coordinator, queue_tracker, amm_consumption, and the manifest writer unchanged. The four `partial`-classified files are exactly where Phase 5 introduces NEW capability (Monte Carlo, sweep runners, perturbation reflection-runner, new parquet partition) — and even those have RESEARCH.md paste-ready code as authority.
