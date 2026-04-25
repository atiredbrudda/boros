---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 01
type: execute
wave: 0
depends_on: []
autonomous: true
requirements: [DECIDE-01, DECIDE-02, DECIDE-03, DECIDE-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06, SAFE-07, SAFE-08, SAFE-09, SAFE-10]
files_modified:
  - python/tests/conftest.py
  - python/tests/test_decision_engine_ev_equation.py
  - python/tests/test_decision_engine_voluntary_branch.py
  - python/tests/test_gas_history_ewma.py
  - python/tests/test_no_threshold_dials_lint.py
  - python/tests/test_breaker_margin_trajectory.py
  - python/tests/test_breaker_oracle_stale.py
  - python/tests/test_breaker_clo_removal.py
  - python/tests/test_breaker_clo_shift.py
  - python/tests/test_breaker_fill_rate.py
  - python/tests/test_breaker_competition.py
  - python/tests/test_breaker_maturity.py
  - python/tests/test_breaker_side_budget.py
  - python/tests/test_breaker_underlying_stale.py
  - python/tests/test_breaker_loss_fit_degraded.py
  - python/tests/test_breaker_coordinator_exclusive.py
  - python/tests/test_predeploy_gate_cli.py
  - python/tests/test_main_decision_loop_spawn.py
  - python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
  - python/tests/test_phase4_manifest_leaves.py
  - scripts/no_hardcoded_cancel_cost_lint.py
  - scripts/no_threshold_dials_lint.py
  - docs/architecture.yml
  - docs/ARCHITECTURE.md

must_haves:
  truths:
    - "All 17 Phase 4 test files exist with at least one failing test that imports from the future module (RED state)."
    - "Conftest exposes seed-helper fixtures for every Phase 4 history table (margin, clo, tx_receipts/fill, competition, market_reward_calibration, loss_grid_artifacts)."
    - "scripts/no_hardcoded_cancel_cost_lint.py and scripts/no_threshold_dials_lint.py exist as executable Python files (skeleton; final regex tightened in 04-03)."
    - "docs/architecture.yml + docs/ARCHITECTURE.md declare the new lint-script module nodes so architecture_lint passes (Engineering Protocol 2)."
  artifacts:
    - path: "python/tests/test_decision_engine_ev_equation.py"
      provides: "DECIDE-01 RED tests (test_ev_sign_matches_decision, test_ev_monotonicity, test_propagates_predict_errors, test_propagates_loss_errors)"
      contains: "from boros_brain.decision.engine import evaluate"
    - path: "python/tests/test_decision_engine_voluntary_branch.py"
      provides: "DECIDE-02 RED tests"
      contains: "voluntary_cancel_forfeits_accumulated"
    - path: "python/tests/test_gas_history_ewma.py"
      provides: "DECIDE-03 RED tests"
      contains: "from boros_brain.decision.gas_history import GasHistoryCache"
    - path: "python/tests/test_no_threshold_dials_lint.py"
      provides: "DECIDE-04 lint script test"
      contains: "scripts/no_threshold_dials_lint.py"
    - path: "python/tests/test_breaker_margin_trajectory.py"
      provides: "SAFE-01 RED tests (predicts_breach, no_fire_when_growing — Pitfall #4 sign-confusion guard)"
    - path: "python/tests/test_breaker_oracle_stale.py"
      provides: "SAFE-02 RED tests (boundary at 0.7×maxUpdateDelay)"
    - path: "python/tests/test_breaker_clo_removal.py"
      provides: "SAFE-03 RED tests"
    - path: "python/tests/test_breaker_clo_shift.py"
      provides: "SAFE-04 RED tests + stay-out-of-range branch test"
    - path: "python/tests/test_breaker_fill_rate.py"
      provides: "SAFE-05 RED tests (K=4 fires, K=3 silent)"
    - path: "python/tests/test_breaker_competition.py"
      provides: "SAFE-06 RED tests (>50% drop)"
    - path: "python/tests/test_breaker_maturity.py"
      provides: "SAFE-07 RED tests"
    - path: "python/tests/test_breaker_side_budget.py"
      provides: "SAFE-08 RED tests (>=30% drift)"
    - path: "python/tests/test_breaker_underlying_stale.py"
      provides: "SAFE-09 RED tests (>2× cadence)"
    - path: "python/tests/test_breaker_loss_fit_degraded.py"
      provides: "B5 absorption RED tests"
    - path: "python/tests/test_breaker_coordinator_exclusive.py"
      provides: "SAFE-10 RED tests (kill_fires_once, suppression, hysteresis no-refire)"
    - path: "python/tests/test_predeploy_gate_cli.py"
      provides: "A5 absorption RED tests"
    - path: "python/tests/test_main_decision_loop_spawn.py"
      provides: "main.py spawn-block integration RED test"
    - path: "python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py"
      provides: "SAFE composition RED test (parametrized over SAFE-01..09 + B5; turns GREEN in Plan 04-06 Task 6)"
      contains: "pytest.importorskip"
    - path: "python/tests/test_phase4_manifest_leaves.py"
      provides: "PROTO-04 leaf-count assertion (>=25 decision.* leaves)"
    - path: "python/tests/conftest.py"
      provides: "Extended with breaker-history seed fixtures"
      contains: "seed_margin_history"
    - path: "scripts/no_hardcoded_cancel_cost_lint.py"
      provides: "DECIDE-03 linter skeleton (PROTECTED_DIRS, PATTERN, main exit-0/1)"
      contains: "PROTECTED_DIRS"
    - path: "scripts/no_threshold_dials_lint.py"
      provides: "DECIDE-04 audit script skeleton"
      contains: "PROTECTED_DIRS"
    - path: "docs/architecture.yml"
      provides: "Lint-script nodes registered (scripts.no_hardcoded_cancel_cost_lint, scripts.no_threshold_dials_lint)"
    - path: "docs/ARCHITECTURE.md"
      provides: "Mermaid edits acknowledging the two new lint scripts"
  key_links:
    - from: "python/tests/test_decision_engine_ev_equation.py"
      to: "boros_brain.decision.engine"
      via: "import statement (RED until 04-03 lands)"
      pattern: "from boros_brain.decision.engine import evaluate"
    - from: "python/tests/test_breaker_margin_trajectory.py"
      to: "boros_brain.decision.breakers.margin_trajectory"
      via: "import statement (RED until 04-04 lands)"
      pattern: "from boros_brain.decision.breakers.margin_trajectory import MarginTrajectoryBreaker"
    - from: "python/tests/test_breaker_coordinator_exclusive.py"
      to: "boros_brain.decision.breaker_coordinator"
      via: "import statement (RED until 04-06 lands)"
      pattern: "from boros_brain.decision.breaker_coordinator import BreakerCoordinator"
    - from: "scripts/no_hardcoded_cancel_cost_lint.py"
      to: "scripts/no_time_time_lint.py"
      via: "structural pattern copy"
      pattern: "PROTECTED_DIRS = .*decision/"
---

<objective>
Wave 0: Land the RED-test scaffolding (18 test files + conftest extension) and the two new lint-script skeletons before any engine/breaker source code is written. Per RESEARCH.md § Validation Architecture, these tests are the sole verification surface for Phases 04-02..04-06; the implementation plans turn each `xfail`/`pytest.raises(ImportError)` into a passing assertion.

Purpose: Make Phase 4 testable from day 1 of execution. Wave 1 cannot start until this lands because every subsequent task's `<verify>` block points at one of these files.

Output: 18 new pytest files + extended conftest + 2 executable lint script skeletons + atomic architecture.yml/Mermaid registration of the lint scripts (Engineering Protocol 2).
</objective>

<execution_context>
@$HOME/.claude-personal-personal/get-shit-done/workflows/execute-plan.md
@$HOME/.claude-personal-personal/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/REQUIREMENTS.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md
@CLAUDE.md
@python/tests/conftest.py
@python/tests/test_fill_model_predict_contract.py
@python/tests/test_competition_tracker.py
@python/tests/test_zmq_kill_priority.py
@python/tests/test_manifest_contains_all_knobs.py
@scripts/no_time_time_lint.py
@docs/architecture.yml

<interfaces>
<!-- Test scaffolding imports the FUTURE modules — this section pins the exact
     symbol names so downstream waves cannot drift. The tests will RED-fail at
     ImportError until each implementation plan lands. -->

Future module: boros_brain.decision.engine
  - async def evaluate(req: EvaluateInput, *, sqlite_path: Path, config: BotConfig, gas_cache: GasHistoryCache, w3) -> EvaluateOutput
  (lands Plan 04-03)

Future module: boros_brain.decision.gas_history
  - class GasHistoryCache
  - async def cancel_cost_pendle(self, *, w3, config: BotConfig) -> float
  (lands Plan 04-03)

Future module: boros_brain.decision.schemas
  - class EvaluateInput(StrictBase): market_id, side, order_id, depth_from_mark_ticks, queue_ahead_wei, current_features, time_to_epoch_end_s, time_to_maturity_s, q_me_pendle, sigma_others_pendle, e_liq_per_epoch_pendle, side_split, t_frac, p_purge, r_me_per_epoch_pendle_accumulated_so_far, current_chain_ts
  - class EvaluateOutput(StrictBase): decision_kind, ev_hold_pendle, r_share_per_epoch_pendle, p_no_fill_and_unpurged, e_loss_pendle, p_fill, cancel_cost_pendle, p_purge, fit_status_fill, fit_status_loss, voluntary_cancel_branch, reasoning
  (lands Plan 04-03)

Future module: boros_brain.decision.breakers.base
  - class BreakerSignal(BaseModel): tripped, reason, payload, kill_command_kind
  - class Breaker(ABC): name; async def check(*, sqlite_path, w3, parquet_root, config, current_chain_ts) -> BreakerSignal
  (lands Plan 04-04)

Future modules: boros_brain.decision.breakers.{margin_trajectory, oracle_stale, clo_removal, clo_shift, fill_rate, loss_fit_degraded}
  - classes MarginTrajectoryBreaker, OracleStaleBreaker, CloRemovalBreaker, CloShiftBreaker, FillRateBreaker, LossFitDegradedBreaker
  (land Plan 04-04)

Future modules: boros_brain.decision.breakers.{competition, maturity, side_budget, underlying_stale}
  - classes CompetitionBreaker, MaturityBreaker, SideBudgetBreaker, UnderlyingStaleBreaker
  (land Plan 04-05)

Future module: boros_brain.decision.breaker_coordinator
  - class BreakerCoordinator(*, cmd_bus, config, run_id, gas_cache, breakers)
  - async def tick(*, sqlite_path, w3, parquet_root, current_chain_ts) -> dict[str, BreakerSignal]
  - async def gate(decisions, *, current_chain_ts) -> None
  (lands Plan 04-06)

Future module: boros_brain.decision.predeploy_gate
  - def run_predeploy_gate(config, *, sqlite_path, run_id) -> int  (CLI entry)
  (lands Plan 04-06)

Future state writers (land Plan 04-02):
  - boros_brain.state.writers.margin_history.{insert_margin_snapshot, read_margin_history}
  - boros_brain.state.writers.breaker_events.insert_breaker_event
  - boros_brain.state.writers.predeploy_gate_records.{insert_predeploy_gate_record, get_latest_predeploy_gate_record}

Existing reusable interfaces (already in repo; tests import directly):
From python/src/boros_brain/state/writers/clo_history.py:
  - def insert_clo_snapshot(conn, *, snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, run_id) -> None
From python/src/boros_brain/state/writers/competition_history.py:
  - def insert_competition_row(conn, *, polled_at_utc, chain_ts, market_id, q_me_pendle, sigma_others_pendle, run_id, data_source='live') -> None
From python/src/boros_brain/state/db.py:
  - @contextmanager def open_connection(sqlite_path: Path) -> Iterator[sqlite3.Connection]
From python/src/boros_brain/bus/cmd.py:
  - class CmdBus(cmd_endpoint, kill_endpoint); async def send_cmd; async def send_kill
From python/src/boros_brain/bus/messages.py:
  - class KillCmd, PlaceCmd, CancelCmd
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Extend conftest with Phase 4 seed-helper fixtures</name>
  <files>python/tests/conftest.py</files>
  <read_first>
    - python/tests/conftest.py (current state — 62 lines; we APPEND, never rewrite)
    - python/tests/test_competition_tracker.py (mirror `_migrated_db` + parametrized seed pattern)
    - python/tests/test_fill_model_predict_contract.py (mirror `_apply_migrations` helper)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (lines 1212-1240 — conftest extension pattern)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (§ Validation Architecture, "Ground-truth fixtures (per breaker)" table line 1231-1244)
    - python/src/boros_brain/state/writers/competition_history.py (insert_competition_row signature — model for new writers)
    - python/src/boros_brain/state/writers/clo_history.py (insert_clo_snapshot signature)
    - python/src/boros_brain/state/db.py (open_connection contract)
  </read_first>
  <behavior>
    - apply_migrations(db_path) helper applies all alembic migrations against a sqlite:// URL — copy verbatim from python/tests/test_fill_model_predict_contract.py lines 22-40.
    - seed_margin_history fixture-factory: pytest fixture that returns inner function (slope: float, n: int=20, market_id: str="BINANCE-ETHUSDT-29MAY2026", base_chain_ts: int=1_700_000_000) — applies migrations then loops i in range(n) inserting via insert_margin_snapshot(conn, chain_ts=base_chain_ts+i, market_id=market_id, net_margin_usd=100.0+slope*i, maintenance_margin_usd=10.0, available_collateral_usd=200.0, run_id="test-001"). Wrap inserts in `with open_connection(db_path) as conn: ... conn.commit()`.
    - seed_clo_history fixture-factory: returns inner function (rows: list[tuple[int, float, float]], market_id: str) — each tuple is (snapshot_ts, clo_lower_thresh, clo_upper_thresh); inserts via insert_clo_snapshot.
    - seed_competition_history fixture-factory: returns inner function (rows: list[tuple[str, int, float, float]], market_id: str) — each tuple is (polled_at_utc, chain_ts, q_me_pendle, sigma_others_pendle); inserts via insert_competition_row with data_source='live'.
    - seed_market_reward_calibration fixture-factory: returns inner function (rows: list[dict]) — inserts directly via existing market_reward_calibration writer (Phase 3 Plan 03-02).
    - seed_loss_grid_artifact fixture-factory: returns inner function (fit_status: Literal["ok", "degraded", "stale"], market_id: str, side: str) — inserts a minimal LossGridArtifact via existing loss_grid_artifacts writer.
    - seed_tx_receipts_fills fixture-factory: returns inner function (n_fills: int, since_chain_ts: int, market_id: str) — inserts n_fills tx_receipts rows with event_type='fill' (uses TEST_ONLY=True writer). Document that this fixture depends on the event_type column added by Plan 04-02 migration.
    - seed_underlying_apr_parquet fixture-factory: returns inner function (last_ts: int, exchange: str, symbol: str, parquet_root: Path) — writes a minimal polars DataFrame with at least one row to data/parquet/underlying_apr/exchange={exchange}/symbol={symbol}/*.parquet.
  </behavior>
  <action>
APPEND to python/tests/conftest.py (do NOT rewrite the existing 62 lines). Add the following imports at the top (or extend existing import block):

```python
from typing import Callable, Literal
from datetime import UTC, datetime
```

Add the apply_migrations helper at module scope (NOT a fixture):

```python
def apply_migrations(db: Path) -> None:
    """Run alembic migrations to head against db. Mirrors test_fill_model_predict_contract.py."""
    from alembic import command
    from alembic.config import Config
    ALEMBIC_DIR = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations"
    cfg = Config(str(ALEMBIC_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
```

Add the seven fixture-factory functions, exactly as in <behavior>. For the writer functions that do NOT yet exist (`insert_margin_snapshot`, `insert_breaker_event`, `insert_predeploy_gate_record`), import them inside the inner function body (NOT at module top) so the conftest itself does not raise ImportError before Plan 04-02 lands. Pattern:

```python
@pytest.fixture
def seed_margin_history(tmp_sqlite_path: Path) -> Callable:
    def _seed(slope: float, n: int = 20, market_id: str = "BINANCE-ETHUSDT-29MAY2026",
              base_chain_ts: int = 1_700_000_000) -> Path:
        from boros_brain.state.writers.margin_history import insert_margin_snapshot
        from boros_brain.state.db import open_connection
        apply_migrations(tmp_sqlite_path)
        with open_connection(tmp_sqlite_path) as conn:
            for i in range(n):
                insert_margin_snapshot(
                    conn,
                    chain_ts=base_chain_ts + i,
                    market_id=market_id,
                    net_margin_usd=100.0 + slope * i,
                    maintenance_margin_usd=10.0,
                    available_collateral_usd=200.0,
                    run_id="test-001",
                )
            conn.commit()
        return tmp_sqlite_path
    return _seed
```

Repeat the same shape for the other six fixture-factories. For seed_underlying_apr_parquet, accept a parquet_root argument (typically `tmp_path / "parquet"`) and write to `parquet_root / "underlying_apr" / f"exchange={exchange}" / f"symbol={symbol}" / "snapshot.parquet"` using `polars.DataFrame({"snapshot_ts": [last_ts], "rate": [0.0001]}).write_parquet(...)`.

Self-verification: do not touch existing fixtures (default_yaml_path, default_config, tmp_sqlite_path, frozen_chain_time, ipc_dir). Existing tests must still pass.
  </action>
  <verify>
    <automated>cd python && uv run pytest tests/conftest.py --collect-only 2>&1 | grep -q "no tests ran" && cd python && uv run pytest -x tests/test_fill_model_predict_contract.py 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - python/tests/conftest.py contains def apply_migrations(
    - python/tests/conftest.py contains def seed_margin_history(
    - python/tests/conftest.py contains def seed_clo_history(
    - python/tests/conftest.py contains def seed_competition_history(
    - python/tests/conftest.py contains def seed_market_reward_calibration(
    - python/tests/conftest.py contains def seed_loss_grid_artifact(
    - python/tests/conftest.py contains def seed_tx_receipts_fills(
    - python/tests/conftest.py contains def seed_underlying_apr_parquet(
    - python/tests/conftest.py still contains def default_yaml_path( (existing fixture preserved)
    - python/tests/conftest.py still contains def ipc_dir( (existing fixture preserved)
    - cd python && uv run python -c "import tests.conftest" exits 0 (conftest itself imports cleanly even though writer modules do not yet exist)
    - cd python && uv run pytest tests/test_fill_model_predict_contract.py -x exits 0 (existing tests not broken)
  </acceptance_criteria>
  <done>conftest.py extended with 7 new fixture-factories + apply_migrations helper; existing tests unaffected; conftest imports cleanly.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create RED test files for engine + lint scripts (DECIDE-01..04)</name>
  <files>
    python/tests/test_decision_engine_ev_equation.py,
    python/tests/test_decision_engine_voluntary_branch.py,
    python/tests/test_gas_history_ewma.py,
    python/tests/test_no_threshold_dials_lint.py,
    python/tests/test_phase4_manifest_leaves.py,
    python/tests/test_main_decision_loop_spawn.py
  </files>
  <read_first>
    - python/tests/test_fill_model_predict_contract.py (canonical hypothesis + pytest.raises pattern)
    - python/tests/test_competition_tracker.py (StubEventPub + AsyncMock pattern)
    - python/tests/test_manifest_contains_all_knobs.py (lines 53-200 — `_collect_leaf_paths` + `test_phase3_leaves_surfaced`)
    - python/tests/test_no_time_time_in_hotpath.py (lint-script invocation pattern)
    - python/tests/test_zmq_kill_priority.py (CmdBus + ipc_dir fixture)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (§ DECIDE-01 EvaluateInput/Output, lines 281-385; § DECIDE-02 voluntary branch test, lines 388-411; § DECIDE-03 GasHistoryCache, lines 415-462; § DECIDE-04 lint, lines 466-481; § Validation Architecture test map, lines 1172-1230)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (§ Tests, lines 1004-1208)
    - python/src/boros_brain/loss_model/expected_loss.py (current sync model whose errors propagate — pattern for engine.evaluate's error-propagation tests)
    - python/src/boros_brain/main.py (lines 144-220 — spawn pattern that test_main_decision_loop_spawn validates)
  </read_first>
  <behavior>
    - test_decision_engine_ev_equation.py — DECIDE-01:
      * test_ev_sign_matches_decision: builds EvaluateInput with calibrated values (r_share=10, p_fill=0.05, e_loss=0.5, cancel_cost=0.1, p_purge=0.0); asserts decision_kind=="HOLD" and ev_hold_pendle > 0.
      * test_ev_sign_negative_yields_cancel: with r_share=0.1, p_fill=0.9, e_loss=20, cancel_cost=0.1; asserts decision_kind=="CANCEL" and ev_hold_pendle < 0.
      * test_ev_monotonicity: hypothesis `@given(p_fill=st.floats(0.01, 0.99), r_share=st.floats(0.1, 100.0))` — calling evaluate twice with p_fill_1 < p_fill_2 (others equal) yields ev_1 > ev_2; with r_share_1 < r_share_2 yields ev_1 < ev_2.
      * test_propagates_predict_errors: monkeypatch fill_model.predict.predict to raise FillModelStaleFeatureError; pytest.raises(FillModelStaleFeatureError).
      * test_propagates_loss_errors: monkeypatch loss_model.expected_loss.expected_loss to raise LossModelNoFreshGridError; pytest.raises(LossModelNoFreshGridError).
    - test_decision_engine_voluntary_branch.py — DECIDE-02:
      * test_branches_diverge_on_calibrated_scenario: parametrize `forfeits` ∈ {False, True}. Build a scenario calibrated so the BENIGN branch (False) returns HOLD and PUNITIVE branch (True) returns CANCEL — calibration: r_share=2 PENDLE, p_fill=0.05, e_loss=20 PENDLE, sunk=8 PENDLE. Assert out.voluntary_cancel_branch matches; assert out.decision_kind diverges across branches.
      * test_default_branch_is_benign: build BotConfig() with default values; call evaluate; assert out.voluntary_cancel_branch == "benign".
    - test_gas_history_ewma.py — DECIDE-03:
      * test_ewma_correctness: mock w3.eth.fee_history to return baseFeePerGas=[100,100,...], reward=[[10],[10],...] (101 entries) — assert cancel_cost_pendle returns wei→PENDLE conversion via the formula `(110*200_000) / 1e18 * eth_price_usd / pendle_price_usd`. Use known eth_price_usd=3000.0, pendle_price_usd=3.0 in the BotConfig fixture.
      * test_ttl_cache: call cancel_cost_pendle twice; second call MUST NOT invoke w3.eth.fee_history. Use AsyncMock and assert call_count == 1.
      * test_linter_catches_hardcoded: write a temp file with `cancel_cost = 0.5` to `python/src/boros_brain/decision/`; invoke scripts.no_hardcoded_cancel_cost_lint.main(); assert exit code == 1.
      * test_linter_passes_when_clean: invoke main() against the actual decision/ dir AFTER 04-03 lands gas_history.py; assert exit code == 0. (xfail until 04-03.)
    - test_no_threshold_dials_lint.py — DECIDE-04:
      * test_audit_passes_on_main: invoke scripts.no_threshold_dials_lint.main(); assert exit code == 0. (xfail until 04-03.)
      * test_audit_catches_threshold_field: write a temp Pydantic file with `cancel_threshold: float = 0.5` under decision/; invoke main(); assert exit code == 1.
    - test_phase4_manifest_leaves.py — PROTO-04:
      * test_phase4_leaves_surfaced: collect leaves via the existing _collect_leaf_paths helper from test_manifest_contains_all_knobs.py; assert len([s for s in leaves if s.startswith("decision.")]) >= 25; spot-check 10 specific leaves: decision.cancel_cost_ewma_alpha, decision.breakers.margin.window_s, decision.breakers.oracle_stale.fraction_of_max, decision.breakers.clo_shift.n_ticks, decision.breakers.fill_rate.k_fills_per_hour, decision.breakers.competition.drop_threshold, decision.breakers.maturity.migration_cost_buffer_pct, decision.breakers.side_budget.drift_threshold, decision.breakers.underlying_stale.expected_cadence_s_per_exchange, decision.decision_loop_interval_s.
    - test_main_decision_loop_spawn.py — main.py wiring:
      * test_decision_loop_task_created: monkeypatch the post-fit boot path; assert a task named "_decision_loop" (or matching the create_task object) exists in asyncio.all_tasks() after run() boot; cleanly cancel.
      * test_chain_cache_halt_callback_wired: assert chain_cache.halt_callback is coord.halt_via_chain_time after boot (replaces _default_halt_callback). xfail until 04-06.
  </behavior>
  <action>
Create six new test files. EVERY new test file uses the SAME header — copy verbatim from python/tests/test_fill_model_predict_contract.py lines 1-15:

```python
"""<DOCSTRING describing requirement coverage>."""
from __future__ import annotations
from pathlib import Path
import pytest
from boros_brain.config.schema import BotConfig
```

For each file, structure as follows. Use `pytest.importorskip("boros_brain.decision.engine")` AT MODULE TOP for files testing modules that don't yet exist (so pytest collects but skips with a clear "module not yet implemented" message — this is the RED state). Wave 1 plans turn the importorskip into an actual import.

File 1: python/tests/test_decision_engine_ev_equation.py
```python
"""DECIDE-01 — engine.evaluate() EV-equation tests (RED until 04-03 lands).

Covers:
  - test_ev_sign_matches_decision (success criterion #1, sign-line-by-line)
  - test_ev_sign_negative_yields_cancel
  - test_ev_monotonicity (hypothesis property — RESEARCH.md §"Composition properties")
  - test_propagates_predict_errors (Pitfall #7 — never swallow)
  - test_propagates_loss_errors
"""
from __future__ import annotations
from pathlib import Path
import pytest
from hypothesis import given, settings, strategies as st

# RED state guard: module under test lands in Plan 04-03.
engine = pytest.importorskip("boros_brain.decision.engine")
schemas = pytest.importorskip("boros_brain.decision.schemas")
gas_mod = pytest.importorskip("boros_brain.decision.gas_history")

from boros_brain.config.schema import BotConfig
# ... (rest of imports for fixtures) ...

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _build_eval_input(**overrides) -> "schemas.EvaluateInput":
    defaults = dict(
        market_id=MARKET_ID, side="long", order_id="test-1",
        depth_from_mark_ticks=5, queue_ahead_wei=0,
        current_features={"sigma_5min": 0.01},
        time_to_epoch_end_s=3600.0, time_to_maturity_s=86400 * 30,
        q_me_pendle=10.0, sigma_others_pendle=100.0,
        e_liq_per_epoch_pendle=1000.0, side_split=0.5, t_frac=1.0,
        p_purge=0.0, r_me_per_epoch_pendle_accumulated_so_far=0.0,
        current_chain_ts=1_700_000_000,
    )
    defaults.update(overrides)
    return schemas.EvaluateInput(**defaults)


@pytest.mark.asyncio
async def test_ev_sign_matches_decision(tmp_path: Path, default_config: BotConfig,
                                          seed_loss_grid_artifact, seed_competition_history,
                                          seed_market_reward_calibration) -> None:
    """DECIDE-01 success #1: sign-of-EV matches sign-of-decision line-by-line."""
    db = tmp_path / "state.sqlite"
    seed_loss_grid_artifact(fit_status="ok", market_id=MARKET_ID, side="long")
    seed_competition_history([("2026-04-25T00:00:00Z", 1_700_000_000, 10.0, 100.0)], market_id=MARKET_ID)
    seed_market_reward_calibration([{
        "market_id": MARKET_ID, "e_liq_per_epoch_pendle": 1000.0,
        "long_side_split": 0.5, "short_side_split": 0.5,
        "calibrated_at_utc": "2026-04-25T00:00:00Z", "source": "dapp_ui",
    }])
    # Calibrated for HOLD: ev = 10 * 0.95 - 0.5 * 0.05 - 0.1 * 0.0 = 9.475 > 0
    req = _build_eval_input(p_purge=0.0)
    gas_cache = gas_mod.GasHistoryCache()
    out = await engine.evaluate(req, sqlite_path=db, config=default_config, gas_cache=gas_cache, w3=None)
    assert out.decision_kind == "HOLD"
    assert out.ev_hold_pendle > 0.0


# ... (4 more tests as per <behavior>) ...
```

Apply the SAME importorskip-at-top pattern for every test file. The required test functions per file are EXACTLY as enumerated in <behavior>. Copy the pattern from test_fill_model_predict_contract.py for: (a) `_apply_migrations` import, (b) `pytest.raises` propagation, (c) `@given/@settings` hypothesis decorators, (d) parametrize idiom.

For test_phase4_manifest_leaves.py — copy verbatim lines 137-200 of test_manifest_contains_all_knobs.py and rename the function to `test_phase4_leaves_surfaced`; tighten the assertion to `>=25` and the prefix to "decision.". Spot-check the 10 leaves listed in <behavior>.

For test_no_threshold_dials_lint.py and test_gas_history_ewma.py linter sub-tests, the lint scripts are skeleton-only after this plan, so the linter tests should be `@pytest.mark.xfail(reason="lint script regex tightened in 04-03")` until 04-03 hardens them.

For test_main_decision_loop_spawn.py: use `@pytest.mark.asyncio` and a `monkeypatch.setattr(...)` to stub out the heavy refit-once calls so the test can assert on task creation without a full boot. Use `pytest.importorskip("boros_brain.decision.breaker_coordinator")` since the spawn requires Plan 04-06.

Self-verification: Run `cd python && uv run pytest tests/test_decision_engine_ev_equation.py --collect-only` — must return at least 5 collected items (4 test_ functions + 1 hypothesis test). All tests must SKIP (not error) before Plan 04-03.
  </action>
  <verify>
    <automated>cd python && uv run pytest tests/test_decision_engine_ev_equation.py tests/test_decision_engine_voluntary_branch.py tests/test_gas_history_ewma.py tests/test_no_threshold_dials_lint.py tests/test_phase4_manifest_leaves.py tests/test_main_decision_loop_spawn.py --collect-only 2>&1 | grep -E "^[0-9]+ tests collected" </automated>
  </verify>
  <acceptance_criteria>
    - File python/tests/test_decision_engine_ev_equation.py exists
    - File python/tests/test_decision_engine_voluntary_branch.py exists
    - File python/tests/test_gas_history_ewma.py exists
    - File python/tests/test_no_threshold_dials_lint.py exists
    - File python/tests/test_phase4_manifest_leaves.py exists
    - File python/tests/test_main_decision_loop_spawn.py exists
    - grep -q "pytest.importorskip" python/tests/test_decision_engine_ev_equation.py
    - grep -q "test_ev_monotonicity" python/tests/test_decision_engine_ev_equation.py
    - grep -q "test_propagates_predict_errors" python/tests/test_decision_engine_ev_equation.py
    - grep -q "test_branches_diverge_on_calibrated_scenario" python/tests/test_decision_engine_voluntary_branch.py
    - grep -q "test_ewma_correctness" python/tests/test_gas_history_ewma.py
    - grep -q "test_ttl_cache" python/tests/test_gas_history_ewma.py
    - grep -q "test_phase4_leaves_surfaced" python/tests/test_phase4_manifest_leaves.py
    - grep -q ">=25" python/tests/test_phase4_manifest_leaves.py
    - cd python && uv run pytest tests/test_decision_engine_ev_equation.py --collect-only exits 0 (tests collect but skip due to importorskip)
    - cd python && uv run pytest tests/test_phase4_manifest_leaves.py --collect-only exits 0
  </acceptance_criteria>
  <done>Six engine + lint + manifest test files exist, all skip cleanly via pytest.importorskip until downstream waves implement the modules.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Create RED test files for the 10 breakers + coordinator + predeploy_gate</name>
  <files>
    python/tests/test_breaker_margin_trajectory.py,
    python/tests/test_breaker_oracle_stale.py,
    python/tests/test_breaker_clo_removal.py,
    python/tests/test_breaker_clo_shift.py,
    python/tests/test_breaker_fill_rate.py,
    python/tests/test_breaker_competition.py,
    python/tests/test_breaker_maturity.py,
    python/tests/test_breaker_side_budget.py,
    python/tests/test_breaker_underlying_stale.py,
    python/tests/test_breaker_loss_fit_degraded.py,
    python/tests/test_breaker_coordinator_exclusive.py,
    python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py,
    python/tests/test_predeploy_gate_cli.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (§ SAFE-01..09 algorithms — lines 484-770; § SAFE-10 coordinator — lines 768-846; § Predeploy gate — lines 870-887)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (§ Tests, breaker tests pattern lines 1064-1180; coordinator test pattern lines 1124-1180)
    - python/tests/test_zmq_kill_priority.py (CmdBus + ipc_dir + zmq.PULL pattern — verbatim model for coordinator tests)
    - python/tests/test_competition_tracker.py (StubEventPub + writer-helper pattern)
    - python/tests/test_fill_model_predict_contract.py (parametrize + pytest.raises pattern)
    - python/src/boros_brain/state/writers/competition_history.py (insert_competition_row signature)
    - python/src/boros_brain/state/writers/clo_history.py (insert_clo_snapshot signature)
    - python/src/boros_brain/state/writers/loss_grid_artifacts.py (LossGridArtifact insert + fit_status field)
    - python/src/boros_brain/state/writers/market_reward_calibration.py (insert signature)
  </read_first>
  <behavior>
    Per RESEARCH.md § Per-Requirement Research, each breaker test file has the following test functions:

    - test_breaker_margin_trajectory.py (SAFE-01):
      * test_predicts_breach: seed margin_history slope=-1.0 (1 USD/s loss), n=20; assert tripped=True, kill_command_kind in ("HALVE_POSITION_AND_ALERT","EMERGENCY_CLOSE"); reason contains "margin_trajectory".
      * test_no_fire_when_growing (Pitfall #4 sign guard): seed slope=+1.0, n=20; assert tripped=False, reason=="growing".
      * test_no_fire_with_insufficient_history: seed n=5; assert tripped=False, reason=="insufficient_history".
    - test_breaker_oracle_stale.py (SAFE-02):
      * test_fires_above_threshold: mock findex_reader.read_latest_findex to return f_time = current_chain_ts - 0.71*max_update_delay; assert tripped=True.
      * test_silent_below_threshold: f_time = current_chain_ts - 0.69*max_update_delay; assert tripped=False.
      * test_boundary_exactly_at_threshold: f_time = current_chain_ts - 0.70*max_update_delay; assert tripped (per spec the inequality is strict `>`; either both tests passing the boundary inclusively or exclusively are correct as long as documented — pin the comparison to `age_s > 0.7*max_delay` per RESEARCH §SAFE-02 line 539).
    - test_breaker_clo_removal.py (SAFE-03):
      * @parametrize (clo_lower, clo_upper) — fires when either is 0.0:
         (0.0, 100.0) → tripped=True
         (100.0, 0.0) → tripped=True
         (50.0, 100.0) → tripped=False
         (None — no rows) → tripped=False, reason="no_clo_history_yet"
    - test_breaker_clo_shift.py (SAFE-04):
      * test_fires_on_n_tick_shift: seed two clo_history rows where new.clo_lower differs from old.clo_lower by > 5 / scale (config.markets[0].scale=10000 — so 5 ticks = 0.0005 APR shift); assert tripped=True, kill_command_kind=="CANCEL_ALL_AND_RECALIBRATE".
      * test_silent_under_threshold: shift of 3 ticks; assert tripped=False.
      * test_stay_out_of_range_branch_under_punitive: same fixture as test_fires_on_n_tick_shift but with config.strategy.voluntary_cancel_forfeits_accumulated=True; assert kill_command_kind=="CANCEL_ALL_HOLD_NO_REPLACE" (A1×A3 compound).
    - test_breaker_fill_rate.py (SAFE-05):
      * test_fires_at_4_fills: seed_tx_receipts_fills(n_fills=4, since_chain_ts=current_chain_ts-3600); assert tripped=True, kill_command_kind=="PAUSE_AND_ALERT".
      * test_silent_at_3_fills: n_fills=3; assert tripped=False.
    - test_breaker_competition.py (SAFE-06):
      * test_fires_on_50_pct_drop: seed two rows ((-1 epoch ago, q_total=200), (now, q_total=80)); drop_pct=(200-80)/200=0.6 > 0.5; assert tripped=True.
      * test_silent_on_30_pct_drop: q_total drops 200→140; drop_pct=0.3; assert tripped=False.
      * test_silent_on_zero_baseline: lag_split=0; assert tripped=False, reason=="zero_baseline".
    - test_breaker_maturity.py (SAFE-07):
      * test_fires_when_remaining_below_migration_cost: build BotConfig with markets[0].maturity_ts=current_chain_ts+3600 (1 hour out); set last_r_me_pendle=0.001 (tiny); assert tripped=True, kill_command_kind=="ROLL_POSITION".
      * test_silent_when_remaining_above_migration_cost: maturity_ts=current_chain_ts+86400*30 (30 days), r_me=10; assert tripped=False.
    - test_breaker_side_budget.py (SAFE-08):
      * test_fires_at_30_pct_drift: seed two market_reward_calibration rows where long_side_split moves from 0.5 → 0.34 over 1 epoch (drift_pct=(0.5-0.34)/0.5=0.32 > 0.30); assert tripped=True, kill_command_kind=="HALVE_POSITION_AND_ALERT".
      * test_silent_at_20_pct_drift: long_side_split 0.5 → 0.4 (drift_pct=0.2); assert tripped=False.
    - test_breaker_underlying_stale.py (SAFE-09):
      * @parametrize (exchange, age_s, expected_cadence_s, should_fire):
         ("binance", 17_280, 28_800, False),  # 0.6×
         ("binance", 60_000, 28_800, True),   # 2.08×
         ("hyperliquid", 121, 60, True),      # 2.02×
         ("hyperliquid", 119, 60, False),     # 1.98×
      * Use seed_underlying_apr_parquet to write a row with snapshot_ts=current_chain_ts-age_s.
    - test_breaker_loss_fit_degraded.py (B5 absorbed):
      * test_fires_on_degraded_status: seed_loss_grid_artifact(fit_status="degraded"); assert tripped=True, kill_command_kind=="SHRINK_TO_Q_MIN".
      * test_silent_on_ok_status: seed_loss_grid_artifact(fit_status="ok"); assert tripped=False.
    - test_breaker_coordinator_exclusive.py (SAFE-10):
      * test_kill_fires_once: build CmdBus with cmd_endpoint=ipc://{ipc_dir}/cmd, kill_endpoint=ipc://{ipc_dir}/cmd.kill; build a fake `_AlwaysTrippedBreaker` that returns BreakerSignal(tripped=True, reason="test", kill_command_kind="CANCEL_ALL"); coord = BreakerCoordinator(...); call coord.tick() once; PULL on kill_endpoint; assert one msg received with kind="kill". Call tick() again; PULL with timeout 0.1s; assert TimeoutError (Pitfall #6 hysteresis no-refire).
      * test_suppression: with same coord, build a fake PLACE EvaluateOutput; call coord.gate([place_decision]); assert NO message arrives on cmd_endpoint within 0.1s timeout (kill-authority exclusivity).
      * test_suppression_logged: after test_suppression, query state.breaker_events; assert at least one row with kind='suppression'.
    - test_breaker_coordinator_publishes_kill_lane_per_safe.py (SAFE composition RED stub):
      * Parametrized over the 10 trip cases SAFE-01..09 + B5 (loss_fit_degraded). Each parameter
        is the breaker name + the trigger fixture that the corresponding plan 04-04/05 unit-test
        builds; the test will be turned GREEN in plan 04-06 Task 6 (real per-SAFE breaker
        instantiation, real CmdBus, ipc_dir fixture, assert correct ZMQ message kind on the
        priority KILL lane). For Wave 0 the file is RED-skipped via
        `pytest.importorskip("boros_brain.decision.breaker_coordinator")` at module top so the
        test collects but skips until plan 04-06 lands the coordinator.
    - test_predeploy_gate_cli.py (A5 absorbed):
      * test_gate_passes_on_clean_run: monkeypatch screener.economics_gate.run_screener to return a non-empty shortlist containing config.markets[0].market_id; invoke run_predeploy_gate; assert exit code == 0; assert one row in state.predeploy_gate_records with gate_passed=True.
      * test_gate_fails_when_market_dropped: monkeypatch run_screener to return shortlist NOT containing config.markets[0].market_id; assert exit code == 1; assert state.predeploy_gate_records row has gate_passed=False.
      * test_gate_records_git_sha_and_config_hash (Pitfall #8): assert the row contains a non-empty git_sha string and a non-empty config_hash string (from BotConfig.model_dump(mode='json') hash).
  </behavior>
  <action>
Create 12 new test files. Every file uses the `pytest.importorskip("boros_brain.decision.breakers.<name>")` pattern at module top to RED-skip until implementation lands.

For breaker tests, every test function uses `@pytest.mark.asyncio` and the exact body shape:

```python
@pytest.mark.asyncio
async def test_predicts_breach(tmp_path: Path, default_config: BotConfig, seed_margin_history) -> None:
    db = seed_margin_history(slope=-1.0, n=20)  # fixture returns the sqlite_path
    breaker = MarginTrajectoryBreaker()
    sig = await breaker.check(
        sqlite_path=db, w3=None, parquet_root=tmp_path,
        config=default_config, current_chain_ts=1_700_000_020,
    )
    assert sig.tripped is True
    assert "margin_trajectory" in sig.reason
```

For the coordinator test, use the EXACT pattern from test_zmq_kill_priority.py — bind PULL sockets BEFORE creating CmdBus + sleep 0.05 to avoid slow-joiner. The `_AlwaysTrippedBreaker` fake breaker class is defined inline in the test file:

```python
class _AlwaysTrippedBreaker:
    name = "test_always"
    async def check(self, **kw):
        from boros_brain.decision.breakers.base import BreakerSignal
        return BreakerSignal(tripped=True, reason="test", kill_command_kind="CANCEL_ALL")
```

For the coordinator hysteresis no-refire test:
```python
# Second tick — still tripped, must NOT re-fire (Pitfall #6 hysteresis)
await coord.tick(sqlite_path=tmp_path / "state.sqlite", w3=None,
                 parquet_root=tmp_path, current_chain_ts=1_700_000_001)
with pytest.raises(asyncio.TimeoutError):
    await asyncio.wait_for(kill_pull.recv_json(), timeout=0.1)
```

For the predeploy_gate test, use `monkeypatch.setattr("boros_brain.screener.economics_gate.run_screener", lambda *a, **kw: [...])` to stub the screener.

Self-verification: pytest collects all 12 files; every test_ function is collected; every file contains an importorskip guard at module top; the coordinator test imports from `boros_brain.bus.cmd` (existing) AND `boros_brain.decision.breaker_coordinator` (RED).
  </action>
  <verify>
    <automated>cd python && uv run pytest tests/test_breaker_margin_trajectory.py tests/test_breaker_oracle_stale.py tests/test_breaker_clo_removal.py tests/test_breaker_clo_shift.py tests/test_breaker_fill_rate.py tests/test_breaker_competition.py tests/test_breaker_maturity.py tests/test_breaker_side_budget.py tests/test_breaker_underlying_stale.py tests/test_breaker_loss_fit_degraded.py tests/test_breaker_coordinator_exclusive.py tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py tests/test_predeploy_gate_cli.py --collect-only 2>&1 | grep -E "^[0-9]+ tests collected"</automated>
  </verify>
  <acceptance_criteria>
    - All 12 files exist (one per breaker + coordinator + predeploy_gate)
    - grep -q "pytest.importorskip" python/tests/test_breaker_margin_trajectory.py
    - grep -q "pytest.importorskip" python/tests/test_breaker_coordinator_exclusive.py
    - grep -q "test_no_fire_when_growing" python/tests/test_breaker_margin_trajectory.py (Pitfall #4 sign guard)
    - grep -q "CANCEL_ALL_HOLD_NO_REPLACE" python/tests/test_breaker_clo_shift.py (A1×A3 compound)
    - grep -q "test_kill_fires_once" python/tests/test_breaker_coordinator_exclusive.py
    - grep -q "test_suppression_logged" python/tests/test_breaker_coordinator_exclusive.py
    - grep -q "ipc_dir" python/tests/test_breaker_coordinator_exclusive.py (uses real ZMQ over ipc://, not mocks)
    - grep -q "test_gate_records_git_sha_and_config_hash" python/tests/test_predeploy_gate_cli.py (Pitfall #8)
    - File python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py exists
    - grep -q "pytest.importorskip" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -Eq "SAFE-01.*SAFE-09|@pytest.mark.parametrize.*safe" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "SHRINK_TO_Q_MIN" python/tests/test_breaker_loss_fit_degraded.py
    - grep -q "ROLL_POSITION" python/tests/test_breaker_maturity.py
    - cd python && uv run pytest tests/test_breaker_margin_trajectory.py --collect-only exits 0 (collects but skips)
    - cd python && uv run pytest tests/test_breaker_coordinator_exclusive.py --collect-only exits 0
  </acceptance_criteria>
  <done>All 13 breaker + coordinator + predeploy_gate test files exist (12 originals + new SAFE composition stub), RED-skipped via importorskip until downstream waves.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Lint script skeletons + atomic architecture.yml/Mermaid registration</name>
  <files>
    scripts/no_hardcoded_cancel_cost_lint.py,
    scripts/no_threshold_dials_lint.py,
    docs/architecture.yml,
    docs/ARCHITECTURE.md
  </files>
  <read_first>
    - scripts/no_time_time_lint.py (lines 1-104 — verbatim structural model)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (lines 898-996 — both lint scripts and OWNER_MAP edits)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (lines 446-481 — DECIDE-03 + DECIDE-04 lint patterns)
    - docs/architecture.yml (current — last 20 lines for append point; line 967+ for storage section conventions)
    - docs/ARCHITECTURE.md (current — append point near "What's declared in docs/architecture.yml" section)
    - scripts/architecture_lint.py (validate the lint will pass after our edits)
  </read_first>
  <behavior>
    - scripts/no_hardcoded_cancel_cost_lint.py: skeleton with all structural elements but a deliberately LOOSE regex that matches NO real code yet (e.g. `PATTERN = re.compile(r"\bcancel_cost(?:_pendle)?\s*=\s*\d+\.\d+")`). The regex tightening lands in 04-03 once gas_history.py exists and the only legit assignment is `self.last_value_pendle = float(pendle)` (which uses neither `cancel_cost = ...` nor `cancel_cost_pendle = ...` literals so the regex will pass).
    - scripts/no_threshold_dials_lint.py: skeleton mirroring no_time_time_lint structure. PROTECTED_DIRS=("python/src/boros_brain/decision/",). PATTERN matches identifiers ending in `_threshold` or `_dial` or `_cutoff` outside the BreakerConfig family. ALLOWED_FILES initially empty (will be populated in 04-03 once decision/config.py exists with breaker_config sub-models).
    - docs/architecture.yml: append two new module nodes under the existing scripts.* section (or create one if absent):
      ```yaml
      - id: scripts.no_hardcoded_cancel_cost_lint
        type: module
        process: scripts
        path: scripts/no_hardcoded_cancel_cost_lint.py
        public_functions: [main]

      - id: scripts.no_threshold_dials_lint
        type: module
        process: scripts
        path: scripts/no_threshold_dials_lint.py
        public_functions: [main]
      ```
    - docs/ARCHITECTURE.md: append a one-line bullet under "Engineering Protocol enforcement scripts" or similar, listing the two new scripts.
  </behavior>
  <action>
Create scripts/no_hardcoded_cancel_cost_lint.py — copy verbatim from scripts/no_time_time_lint.py, then change:
- The module docstring to: "Pre-commit hook: rejects hardcoded cancel_cost scalars in brain/decision/. The single source of truth for cancel_cost is gas_history.GasHistoryCache (DECIDE-03). See PITFALLS #5 ([[gas-history-ewma-cancel-cost]])."
- PROTECTED_DIRS = ("python/src/boros_brain/decision/",)
- ALLOWED_FILES = set() — empty for now (Plan 04-03 adds gas_history.py to allowlist if needed)
- PATTERN = re.compile(r"\bcancel_cost(?:_pendle)?\s*=\s*\d+\.\d+")
- main() print prefix: `[no_hardcoded_cancel_cost]` instead of `[no_time_time]`
- Help message: "use gas_history.GasHistoryCache" instead of "use chain_time.now_cached()"

Create scripts/no_threshold_dials_lint.py — copy verbatim from scripts/no_time_time_lint.py, then change:
- Module docstring: "Pre-commit hook: rejects threshold-dial knob names in brain/decision/. DECIDE-04 invariant — only EV-input model parameters and breaker thresholds (under decision.breakers.*) may be tunable. Generic `_threshold` / `_dial` / `_cutoff` field names anywhere else under decision/ are a regression. See [[ev-cancel-rule]]."
- PROTECTED_DIRS = ("python/src/boros_brain/decision/",)
- ALLOWED_FILES = {"python/src/boros_brain/decision/config.py", "python/src/boros_brain/decision/breakers/__init__.py"} — these legitimately house breaker thresholds. Plan 04-03 may need to extend the list.
- PATTERN = re.compile(r"\b(\w+_(?:threshold|dial|cutoff))\s*[:=]") — matches `something_threshold:` or `something_threshold =`
- main() print prefix: `[no_threshold_dials]`
- Help message: "if this is a breaker threshold, place it in decision.breakers.* in BotConfig (and add this file to ALLOWED_FILES)"

Make BOTH files executable: ensure they have the `#!/usr/bin/env python3` shebang and `if __name__ == "__main__": sys.exit(main())` block. Do NOT chmod from this task — the executor's filesystem may apply default permissions; if needed Plan 04-03 makes them executable.

Update docs/architecture.yml:
1. Use Read to find the last node in the existing `nodes:` list (around line 1095 just before `edges:`).
2. Append immediately before `edges:`:
```yaml
  # ── Phase 4 Plan 04-01 — lint scripts (scaffolding) ────────────────────
  - id: scripts.no_hardcoded_cancel_cost_lint
    type: module
    process: scripts
    path: scripts/no_hardcoded_cancel_cost_lint.py
    public_functions: [main]

  - id: scripts.no_threshold_dials_lint
    type: module
    process: scripts
    path: scripts/no_threshold_dials_lint.py
    public_functions: [main]
```

Update docs/ARCHITECTURE.md:
1. Use Read to locate the "What's declared in docs/architecture.yml" section.
2. Append a Phase 4 paragraph stating: "Phase 4 Plan 04-01 registers two new lint scripts: scripts.no_hardcoded_cancel_cost_lint (DECIDE-03 enforcement) and scripts.no_threshold_dials_lint (DECIDE-04 enforcement). The full Phase 4 module + storage + edge delta lands atomically in Plan 04-06 [[ev-cancel-rule]] [[circuit-breakers-v05]]."

Run `python scripts/architecture_lint.py` locally — must exit 0 (no drift).

Self-verification: lint scripts can be invoked: `python3 scripts/no_hardcoded_cancel_cost_lint.py` exits 0 on a clean tree; `python3 scripts/no_threshold_dials_lint.py` exits 0 on a clean tree (no protected files exist yet).
  </action>
  <verify>
    <automated>python3 scripts/no_hardcoded_cancel_cost_lint.py && python3 scripts/no_threshold_dials_lint.py && python3 scripts/architecture_lint.py</automated>
  </verify>
  <acceptance_criteria>
    - File scripts/no_hardcoded_cancel_cost_lint.py exists
    - File scripts/no_threshold_dials_lint.py exists
    - grep -q 'PROTECTED_DIRS = ("python/src/boros_brain/decision/' scripts/no_hardcoded_cancel_cost_lint.py
    - grep -q 'PROTECTED_DIRS = ("python/src/boros_brain/decision/' scripts/no_threshold_dials_lint.py
    - grep -q 'cancel_cost(?:_pendle)?' scripts/no_hardcoded_cancel_cost_lint.py
    - grep -q '_threshold|_dial|_cutoff' scripts/no_threshold_dials_lint.py
    - python3 scripts/no_hardcoded_cancel_cost_lint.py exits 0
    - python3 scripts/no_threshold_dials_lint.py exits 0
    - grep -q "scripts.no_hardcoded_cancel_cost_lint" docs/architecture.yml
    - grep -q "scripts.no_threshold_dials_lint" docs/architecture.yml
    - grep -q "DECIDE-03 enforcement\|DECIDE-04 enforcement" docs/ARCHITECTURE.md
    - python3 scripts/architecture_lint.py exits 0
  </acceptance_criteria>
  <done>Two lint script skeletons created with shape mirroring no_time_time_lint.py; architecture.yml and Mermaid record the new nodes atomically; architecture_lint passes.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Wave-0 sign-off — full collection check + wiki write-back</name>
  <files>
    python/tests/test_decision_engine_ev_equation.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md (Validation Sign-Off checklist line 99-112)
    - All 17 test files just created (verify presence)
  </read_first>
  <behavior>
    - Touch python/tests/test_decision_engine_ev_equation.py to add a top-of-file invariant doctest:
      ```python
      """... (existing docstring) ...

      >>> # Wave 0 sign-off invariant: this module RED-skips cleanly until 04-03 lands.
      >>> import pytest
      >>> import importlib
      >>> with pytest.raises((ImportError, ModuleNotFoundError)):
      ...     importlib.import_module('boros_brain.decision.engine')
      """
      ```
    - File a wiki page `wave-0-test-scaffolding-phase4.md` at the LLM Wiki workspace path.
  </behavior>
  <action>
1. Append the doctest header invariant block to python/tests/test_decision_engine_ev_equation.py (after the existing module docstring).

2. File a wiki page at /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/wave-0-test-scaffolding-phase4.md with the following content:

```
---
title: Phase 4 Wave 0 — Test Scaffolding
status: Current
phase: 4
plan: 04-01
date: 2026-04-25
---

# Phase 4 Wave 0 — RED Test Scaffolding

**Status:** Current — Wave 0 lands the 17 test files + conftest extension + 2 lint script skeletons before any engine/breaker source code.

## What this is

Phase 4 follows TDD discipline: RED tests first (this plan), GREEN implementation (04-02..04-06). All 17 test files use `pytest.importorskip("boros_brain.decision.<module>")` at module top to skip cleanly until the corresponding implementation plan lands.

## Test→Plan Map

| Test File | Implements | Lands GREEN in |
|-----------|------------|----------------|
| test_decision_engine_ev_equation.py | DECIDE-01 | 04-03 |
| test_decision_engine_voluntary_branch.py | DECIDE-02 | 04-03 |
| test_gas_history_ewma.py | DECIDE-03 | 04-03 |
| test_no_threshold_dials_lint.py | DECIDE-04 | 04-03 |
| test_breaker_margin_trajectory.py | SAFE-01 | 04-04 |
| test_breaker_oracle_stale.py | SAFE-02 | 04-04 |
| test_breaker_clo_removal.py | SAFE-03 | 04-04 |
| test_breaker_clo_shift.py | SAFE-04 | 04-04 |
| test_breaker_fill_rate.py | SAFE-05 | 04-04 |
| test_breaker_loss_fit_degraded.py | B5 absorbed | 04-04 |
| test_breaker_competition.py | SAFE-06 | 04-05 |
| test_breaker_maturity.py | SAFE-07 | 04-05 |
| test_breaker_side_budget.py | SAFE-08 | 04-05 |
| test_breaker_underlying_stale.py | SAFE-09 | 04-05 |
| test_breaker_coordinator_exclusive.py | SAFE-10 | 04-06 |
| test_predeploy_gate_cli.py | A5 absorbed | 04-06 |
| test_main_decision_loop_spawn.py | main.py wiring | 04-06 |
| test_phase4_manifest_leaves.py | PROTO-04 | 04-06 |
| test_breaker_coordinator_publishes_kill_lane_per_safe.py | SAFE-01..09 + B5 composition | 04-06 (Task 6) |

## Conftest Extensions

7 new fixture-factories in python/tests/conftest.py:
- seed_margin_history(slope, n) — for SAFE-01
- seed_clo_history(rows) — for SAFE-03/04
- seed_competition_history(rows) — for SAFE-06
- seed_market_reward_calibration(rows) — for SAFE-08
- seed_loss_grid_artifact(fit_status) — for B5
- seed_tx_receipts_fills(n_fills) — for SAFE-05
- seed_underlying_apr_parquet(last_ts, exchange) — for SAFE-09

Plus apply_migrations(db_path) module-level helper (NOT a fixture) — copy of existing test_fill_model_predict_contract.py pattern.

## Lint Script Skeletons

- scripts/no_hardcoded_cancel_cost_lint.py — DECIDE-03 enforcement; tightened in 04-03 once gas_history.py is the only legit owner of cancel_cost assignments.
- scripts/no_threshold_dials_lint.py — DECIDE-04 enforcement; tightened in 04-03 once decision/config.py BreakerConfig sub-models exist.

## Wave-0 Invariant

`pytest --collect-only tests/test_*.py` MUST collect all 18 Phase 4 test files. Every test MUST skip via importorskip until its implementation plan lands. No test should ERROR (only SKIP or PASS for fixture-only tests).

## Cross-references

- [[ev-cancel-rule]]
- [[circuit-breakers-v05]]
- [[zmq-bus-topology-v05]]
```

Self-verification: Wiki file written with `Status: Current` line; doctest in test_decision_engine_ev_equation.py demonstrates the RED state holds.
  </action>
  <verify>
    <automated>cd python && uv run pytest tests/test_decision_engine_ev_equation.py tests/test_decision_engine_voluntary_branch.py tests/test_gas_history_ewma.py tests/test_no_threshold_dials_lint.py tests/test_phase4_manifest_leaves.py tests/test_main_decision_loop_spawn.py tests/test_breaker_margin_trajectory.py tests/test_breaker_oracle_stale.py tests/test_breaker_clo_removal.py tests/test_breaker_clo_shift.py tests/test_breaker_fill_rate.py tests/test_breaker_competition.py tests/test_breaker_maturity.py tests/test_breaker_side_budget.py tests/test_breaker_underlying_stale.py tests/test_breaker_loss_fit_degraded.py tests/test_breaker_coordinator_exclusive.py tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py tests/test_predeploy_gate_cli.py --collect-only 2>&1 | tail -3</automated>
  </verify>
  <acceptance_criteria>
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/wave-0-test-scaffolding-phase4.md" exists
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/wave-0-test-scaffolding-phase4.md"
    - grep -q "DECIDE-01\|SAFE-01\|SAFE-10" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/wave-0-test-scaffolding-phase4.md"
    - cd python && uv run pytest tests/test_decision_engine_ev_equation.py tests/test_breaker_coordinator_exclusive.py --collect-only 2>&1 | grep -E "^[0-9]+ tests collected" | grep -v "^0 tests"
    - cd python && uv run pytest tests/ --collect-only 2>&1 | tail -1 | grep -v "errors during collection"
  </acceptance_criteria>
  <done>Wave 0 sign-off complete: all 17 test files collect cleanly with importorskip-driven RED state; wiki page filed; existing tests unaffected.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pytest harness → conftest fixtures | Test code is local-trusted; fixtures may write to tmp_path SQLite/parquet. No external network. |
| lint scripts → filesystem | Lint scripts read .py source files via Path.rglob — read-only, but a malicious file path could cause Path traversal in CI (low risk on a single-user repo). |
| wiki write-back → external filesystem | The wiki page lives at /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/ — outside the repo. We trust the operator's filesystem. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01-01 | T (Tampering) | Test scaffolding | mitigate | Tests use `tmp_path` fixtures only — no shared state between runs. Conftest seed fixtures explicitly call `apply_migrations(db)` before any insert so a stale DB cannot corrupt a test run. |
| T-04-01-02 | I (Information disclosure) | Wiki write-back | accept | Wiki content is plan-level metadata (which test maps to which requirement). No secrets, no PII. Operator filesystem permissions guard the wiki dir. |
| T-04-01-03 | D (Denial of service) | Test collection | mitigate | All 17 test files use `pytest.importorskip` at module top — pytest-collect must NOT raise ImportError. `acceptance_criteria` includes `cd python && uv run pytest tests/ --collect-only` exit 0 to catch a missing skip guard. |
| T-04-01-04 | E (Elevation of privilege) | Lint scripts | mitigate | Lint scripts read-only walk PROTECTED_DIRS — no writes. PATTERN regexes are anchored to literal token boundaries (`\b`) and no `eval()` / `exec()`. ALLOWED_FILES allowlist tightens in 04-03; until then both linters protect against drift on net-new code. |
| T-04-01-05 | S (Spoofing) | RED state — pytest.importorskip | mitigate | Importorskip is preferred over `try/except ImportError: pytest.skip(...)` because importorskip emits a SKIPPED reason that the operator sees in pytest output. A test that *silently* passes would be a Phase 4 false-negative — the doctest invariant in Task 5 catches the case where importorskip is accidentally removed. |
| T-04-01-06 | R (Repudiation) | Wave 0 sign-off | mitigate | The wiki write-back records the test→plan map at filing time. Wave 1+ plans cite this wiki page so any later attempt to alter the test scope is grep-discoverable. |

## Deferred to downstream plans

Plan 04-01 is Wave 0 scaffolding only. The 5 production-risk threats below are NOT yet live in this plan's deliverables — they are surfaced and mitigated in downstream Phase-4 plans. Each is listed here with an explicit forward reference so a future audit can verify the chain.

| Production Threat | Forward Reference (Plan / Task / Test) |
|-------------------|----------------------------------------|
| Coordinator bypass — a breaker (or the engine) calls CmdBus.send_cmd directly, sidestepping BreakerCoordinator.gate | T-04-06-01 — `python/tests/test_breaker_coordinator_exclusive.py` proves no other component can submit orders while any breaker is tripped (Plan 04-06 Task 1 turns the RED test GREEN). |
| Stale gas history fed to cancel_cost — `gas_history.GasHistoryCache` returns a value past the 60s TTL without refreshing, or someone hardcodes a `cancel_cost = 0.5` literal in `decision/` | T-04-03-02 — `scripts/no_hardcoded_cancel_cost_lint.py` (skeleton lands in Plan 04-01 Task 4; regex tightened in Plan 04-03) + the EWMA-with-TTL semantic in `gas_history.py`. |
| ZMQ KILL message reordering or dropping — KILL messages reach hands AFTER queued PLACE/CANCEL messages, defeating the priority lane | T-04-06-02 — `python/tests/test_zmq_kill_priority.py` (existing) plus the SAFE composition test `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py` (Plan 04-06 Task 6) verify priority-lane PUSH/PULL HWM behavior end-to-end. |
| Hardcoded threshold-dial regression — a future contributor adds `cancel_threshold: float = 0.5` (or any `_threshold`/`_dial`/`_cutoff` field) outside the breaker config family | T-04-03-02 — `scripts/no_threshold_dials_lint.py` (skeleton lands in Plan 04-01 Task 4; regex + ALLOWED_FILES tightened in Plan 04-03 once `decision/config.py` exists). |
| Voluntary-cancel flag flip — `config.strategy.voluntary_cancel_forfeits_accumulated` flipped from False (default per P0-01) to True without operator awareness | T-04-06-05 — Plan 04-03's `test_decision_engine_voluntary_branch.py::test_branches_diverge_on_calibrated_scenario` (DECIDE-02 dual-branch divergence) + RUN_MANIFEST stamping every flag at boot, so any flip produces a new run_id and audit trail. |

Wave 0 deliverables are pure test scaffolding + lint skeletons; the threats above cannot manifest in this plan's commits because no production engine, breaker, or coordinator code lands here. The forward references are the audit chain.
</threat_model>

<verification>
After all tasks complete, run:
```bash
cd python && uv run pytest tests/ --collect-only -q 2>&1 | tail -10
# Must show all Phase 4 tests collected and skipped (no errors).

python3 scripts/no_hardcoded_cancel_cost_lint.py
python3 scripts/no_threshold_dials_lint.py
python3 scripts/architecture_lint.py
# All exit 0.

cd python && uv run pytest tests/test_fill_model_predict_contract.py tests/test_loss_model_replay.py tests/test_competition_tracker.py -x
# Existing tests still pass — conftest extensions are additive.
```
</verification>

<success_criteria>
- [ ] 18 net-new pytest files exist (one per requirement / per breaker / per coordinator concern), all RED-skipped via `pytest.importorskip` at module top.
- [ ] python/tests/conftest.py extended with 7 new fixture-factories + apply_migrations helper; existing fixtures preserved.
- [ ] scripts/no_hardcoded_cancel_cost_lint.py and scripts/no_threshold_dials_lint.py exist as executable Python files; both exit 0 on a clean tree.
- [ ] docs/architecture.yml + docs/ARCHITECTURE.md atomically register the two new lint-script module nodes (Engineering Protocol 2).
- [ ] `python scripts/architecture_lint.py` exits 0.
- [ ] LLM Wiki page wave-0-test-scaffolding-phase4.md filed with `Status: Current` (Engineering Protocol 1).
- [ ] `cd python && uv run pytest tests/ --collect-only` collects all Phase 4 tests with no collection errors.
- [ ] Existing Phase 1-3 test suite still green: `cd python && uv run pytest -x` is at most as broken as it was before this plan (no new failures).
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-01-SUMMARY.md` documenting:
- Test files created (18) and which requirement each covers
- Conftest fixtures added (7) and their seed-helper signatures
- Lint scripts created (2) and their initial regex
- Architecture.yml/Mermaid delta (2 new module nodes)
- Wiki page filed (wave-0-test-scaffolding-phase4.md)
- RED state confirmed: pytest collection clean, all Phase 4 tests skip via importorskip
</output>
