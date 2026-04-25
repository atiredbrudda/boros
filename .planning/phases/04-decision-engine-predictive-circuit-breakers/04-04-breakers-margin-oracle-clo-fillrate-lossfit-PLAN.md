---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 04
type: execute
wave: 2
depends_on: [01, 02]
autonomous: true
requirements: [SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05]
files_modified:
  - python/src/boros_brain/decision/breakers/margin_trajectory.py
  - python/src/boros_brain/decision/breakers/oracle_stale.py
  - python/src/boros_brain/decision/breakers/clo_removal.py
  - python/src/boros_brain/decision/breakers/clo_shift.py
  - python/src/boros_brain/decision/breakers/fill_rate.py
  - python/src/boros_brain/decision/breakers/loss_fit_degraded.py
  - python/tests/test_breaker_margin_trajectory.py
  - python/tests/test_breaker_oracle_stale.py
  - python/tests/test_breaker_clo_removal.py
  - python/tests/test_breaker_clo_shift.py
  - python/tests/test_breaker_fill_rate.py
  - python/tests/test_breaker_loss_fit_degraded.py

user_setup: []

must_haves:
  truths:
    - "Six predictive breakers fire under their documented trigger conditions and stay silent below threshold."
    - "MarginTrajectoryBreaker uses np.polyfit linear regression — Pitfall #4 sign-confusion test PASSES (positive slope NEVER fires)."
    - "CloShiftBreaker emits CANCEL_ALL_HOLD_NO_REPLACE under the A1xA3 compound risk (voluntary_cancel_forfeits_accumulated=True)."
    - "LossFitDegradedBreaker fires when state.loss_grid_artifacts.fit_status == 'degraded' and emits SHRINK_TO_Q_MIN."
    - "Each breaker is a separate module with grep-discoverable boundary."
    - "Architecture nodes/edges for this plan's modules (margin_trajectory, oracle_stale, clo_removal, clo_shift, fill_rate, loss_fit_degraded) are added by 04-06's atomic Phase-4 architecture delta task. This plan does not touch docs/architecture.yml or docs/ARCHITECTURE.md to avoid parallel-execution merge conflicts with sibling Wave-2 plans 04-03 and 04-05."
  artifacts:
    - path: "python/src/boros_brain/decision/breakers/margin_trajectory.py"
      provides: "SAFE-01 — sliding-window linear regression on margin_history"
      contains: "class MarginTrajectoryBreaker"
    - path: "python/src/boros_brain/decision/breakers/oracle_stale.py"
      provides: "SAFE-02 — fTime vs 0.7 x maxUpdateDelay"
      contains: "class OracleStaleBreaker"
    - path: "python/src/boros_brain/decision/breakers/clo_removal.py"
      provides: "SAFE-03 — clo_lower or clo_upper == 0"
      contains: "class CloRemovalBreaker"
    - path: "python/src/boros_brain/decision/breakers/clo_shift.py"
      provides: "SAFE-04 — N-tick shift + stay-out-of-range branch"
      contains: "class CloShiftBreaker"
    - path: "python/src/boros_brain/decision/breakers/fill_rate.py"
      provides: "SAFE-05 — K=3 fills/hour"
      contains: "class FillRateBreaker"
    - path: "python/src/boros_brain/decision/breakers/loss_fit_degraded.py"
      provides: "B5 absorbed — fit_status='degraded' -> SHRINK_TO_Q_MIN"
      contains: "class LossFitDegradedBreaker"
  key_links:
    - from: "python/src/boros_brain/decision/breakers/margin_trajectory.py"
      to: "python/src/boros_brain/state/writers/margin_history.py"
      via: "read_margin_history call"
      pattern: "from .*state.writers.margin_history import"
    - from: "python/src/boros_brain/decision/breakers/oracle_stale.py"
      to: "python/src/boros_brain/data/findex_reader.py"
      via: "read_latest_findex call"
      pattern: "findex_reader"
    - from: "python/src/boros_brain/decision/breakers/clo_removal.py"
      to: "python/src/boros_brain/state/writers/clo_history.py"
      via: "latest clo_history row read"
      pattern: "clo_history"
    - from: "python/src/boros_brain/decision/breakers/loss_fit_degraded.py"
      to: "python/src/boros_brain/state/writers/loss_grid_artifacts.py"
      via: "fit_status read"
      pattern: "loss_grid_artifacts"
---

<objective>
Wave 2 plan B — implement SAFE-01..05 + B5 absorbed (six breakers). Each is a separate Python module under decision/breakers/ subclassing the Breaker ABC from Plan 04-02. Their .check() methods turn the corresponding Plan 04-01 RED tests GREEN. The 04-06 BreakerCoordinator collects all 10 breakers; this plan delivers 6 of them.

Architecture-file edits (docs/architecture.yml + docs/ARCHITECTURE.md) for the 6 breaker module nodes and their edges are deferred to plan 04-06's atomic Phase-4 architecture delta task. This plan deliberately does NOT touch the architecture files so it can run in parallel with Wave-2 sibling plans 04-03 and 04-05 without merge conflict.

Purpose: Land the high-frequency / chain-state breakers (margin trajectory, oracle staleness, CLO removal, CLO shift, fill-rate runaway, loss-fit degraded) that protect the bot from the first-order Phase-2/3 failure modes.

Output: Six breaker modules + GREEN tests. (Architecture delta lands in 04-06.)
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
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-01-test-scaffolding-and-lint-stubs-PLAN.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-02-foundation-schema-migration-writers-PLAN.md
@CLAUDE.md
@python/src/boros_brain/decision/breakers/base.py
@python/src/boros_brain/decision/config.py
@python/src/boros_brain/state/writers/margin_history.py
@python/src/boros_brain/state/writers/clo_history.py
@python/src/boros_brain/state/writers/loss_grid_artifacts.py
@python/src/boros_brain/state/writers/tx_receipts.py
@python/src/boros_brain/data/findex_reader.py
@python/src/boros_brain/data/chain_time.py
@python/src/boros_brain/reward_model/competition_tracker.py

<interfaces>
Base ABC and Pydantic (Plan 04-02):
  class Breaker(ABC):
      name: str
      @abstractmethod
      async def check(self, *, sqlite_path: Path, w3, parquet_root: Path,
                      config, current_chain_ts: int) -> BreakerSignal: ...

  class BreakerSignal(BaseModel):
      tripped: bool
      reason: str = ""
      payload: dict[str, Any] = {}
      kill_command_kind: Literal[
          "CANCEL_ALL", "EMERGENCY_CLOSE", "PAUSE_AND_ALERT",
          "ROLL_POSITION", "HALVE_POSITION_AND_ALERT", "HALT_AND_ALERT",
          "SHRINK_TO_Q_MIN", "CANCEL_ALL_HOLD_NO_REPLACE",
          "CANCEL_ALL_AND_RECALIBRATE", "CANCEL_ALL_AND_ALERT",
      ] = "CANCEL_ALL"

Config knobs (Plan 04-02 BreakerConfig):
  decision.breakers.margin.{window_s=30.0, min_samples=10, time_to_mm_threshold_s=30.0, min_re_arm_s=60.0}
  decision.breakers.oracle_stale.{fraction_of_max=0.7, min_re_arm_s=60.0}
  decision.breakers.clo_removal.{min_re_arm_s=60.0}
  decision.breakers.clo_shift.{n_ticks=5, min_re_arm_s=60.0}
  decision.breakers.fill_rate.{k_fills_per_hour=3, min_re_arm_s=600.0}
  decision.breakers.loss_fit_degraded.{min_re_arm_s=60.0}

State writers (Plan 04-02):
  read_margin_history(sqlite_path, *, market_id=None, since_ts=None) -> list[dict]

Existing readers/writers reused unchanged:
  python/src/boros_brain/state/writers/clo_history.py:
    def read_latest_clo_history(sqlite_path, market_id) -> dict | None  (verify exact name; if not present, the lower-level open_connection + SELECT pattern is allowed)
  python/src/boros_brain/state/writers/loss_grid_artifacts.py:
    def get_latest_loss_grid_artifact(sqlite_path, market_id, side) -> LossGridArtifact | None
  python/src/boros_brain/data/findex_reader.py:
    async def read_latest_findex(w3, oracle_address) -> FIndex  (with .f_time field)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: SAFE-01 MarginTrajectoryBreaker</name>
  <files>
    python/src/boros_brain/decision/breakers/margin_trajectory.py,
    python/tests/test_breaker_margin_trajectory.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py (Breaker ABC, BreakerSignal — verbatim subclass model)
    - python/src/boros_brain/state/writers/margin_history.py (read_margin_history signature)
    - python/src/boros_brain/decision/config.py (MarginBreakerConfig fields)
    - python/src/boros_brain/reward_model/competition_tracker.py (lines 84-132 — stateful per-cycle compute pattern)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-01 §, lines 484-522; Pitfall #4 sign-confusion lines 1289-1294)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (margin_trajectory pattern lines 384-454)
    - python/tests/test_breaker_margin_trajectory.py (RED tests from 04-01 — must turn GREEN)
  </read_first>
  <behavior>
    MarginTrajectoryBreaker:
      class MarginTrajectoryBreaker(Breaker):
          name = "margin_trajectory"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts) -> BreakerSignal:
              cfg = config.decision.breakers.margin
              market_id = config.markets[0].market_id if config.markets else None
              rows = read_margin_history(sqlite_path, market_id=market_id,
                                          since_ts=current_chain_ts - int(cfg.window_s))
              if len(rows) < cfg.min_samples:
                  return BreakerSignal(tripped=False, reason="insufficient_history", payload={"n": len(rows)})
              ts = np.array([r["chain_ts"] for r in rows], dtype=float)
              nm = np.array([r["net_margin_usd"] for r in rows], dtype=float)
              mm = float(rows[-1]["maintenance_margin_usd"])
              slope, intercept = np.polyfit(ts, nm, 1)
              if slope >= 0:
                  return BreakerSignal(tripped=False, reason="growing",
                                       payload={"slope_usd_per_s": float(slope)})
              # Extrapolate: nm(t) = slope*t + intercept; t* = (mm - intercept)/slope
              t_star = (mm - intercept) / slope
              t_to_mm = t_star - current_chain_ts
              if t_to_mm < cfg.time_to_mm_threshold_s:
                  return BreakerSignal(
                      tripped=True, reason="margin_trajectory_predicted_breach",
                      payload={"slope_usd_per_s": float(slope), "t_to_mm_s": float(t_to_mm),
                               "mm_floor_usd": mm},
                      kill_command_kind="EMERGENCY_CLOSE",
                  )
              return BreakerSignal(tripped=False, reason="ok",
                                   payload={"slope_usd_per_s": float(slope), "t_to_mm_s": float(t_to_mm)})

    Tests turn GREEN:
    - test_predicts_breach: seed slope=-1.0 (1 USD/s loss) and confirm tripped=True with reason "margin_trajectory_predicted_breach", kill_command_kind=="EMERGENCY_CLOSE".
    - test_no_fire_when_growing: seed slope=+1.0; assert tripped=False, reason=="growing".
    - test_no_fire_with_insufficient_history: seed n=5 (less than min_samples=10); assert tripped=False, reason=="insufficient_history".

    Pitfall #4 sign-confusion: docstring on the function explicitly states "slope < 0 means margin SHRINKING; positive slope = healthy growth = NO fire."
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/breakers/margin_trajectory.py with the structure from PATTERNS.md §margin_trajectory and the body from <behavior>. Imports:
   - from __future__ import annotations
   - from pathlib import Path
   - import numpy as np
   - import structlog
   - from ..base.. wait correct path: from .base import Breaker, BreakerSignal
   - from ...state.writers.margin_history import read_margin_history
   - log = structlog.get_logger(__name__)

   The class instance is stateless (the Coordinator owns hysteresis). Name attribute = "margin_trajectory".

   Module docstring includes:
   - SAFE-01 reference
   - [[breaker-margin-trajectory]] wiki cite (filed in Task 7)
   - Pitfall #4 docstring: "slope < 0 means net margin is SHRINKING. Positive slope = NO fire (healthy growth)."

2. Update python/tests/test_breaker_margin_trajectory.py:
   - Remove importorskip guard (margin_trajectory.py now exists)
   - Implement test_predicts_breach: seed_margin_history(slope=-1.0, n=20); breaker.check; assert tripped True, kill_command_kind == "EMERGENCY_CLOSE".
   - Implement test_no_fire_when_growing: seed slope=+1.0; assert tripped False.
   - Implement test_no_fire_with_insufficient_history: seed n=5; assert tripped False, reason "insufficient_history".

   Use `@pytest.mark.asyncio` and `default_config` + `seed_margin_history` fixtures.

Self-verification: cd python ; uv run pytest tests/test_breaker_margin_trajectory.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_margin_trajectory.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/margin_trajectory.py contains "class MarginTrajectoryBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/margin_trajectory.py contains "np.polyfit"
    - File python/src/boros_brain/decision/breakers/margin_trajectory.py contains "EMERGENCY_CLOSE"
    - File python/src/boros_brain/decision/breakers/margin_trajectory.py contains "if slope >= 0"
    - cd python ; uv run pytest tests/test_breaker_margin_trajectory.py::test_predicts_breach -x exits 0
    - cd python ; uv run pytest tests/test_breaker_margin_trajectory.py::test_no_fire_when_growing -x exits 0
    - python3 scripts/no_threshold_dials_lint.py exits 0
    - python3 scripts/no_time_time_lint.py exits 0
  </acceptance_criteria>
  <done>SAFE-01 implemented; Pitfall #4 sign-confusion test PASSES; lint clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: SAFE-02 OracleStaleBreaker</name>
  <files>
    python/src/boros_brain/decision/breakers/oracle_stale.py,
    python/tests/test_breaker_oracle_stale.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/data/findex_reader.py (full file — read_latest_findex signature, FIndex.f_time access)
    - python/src/boros_brain/decision/config.py (OracleStaleBreakerConfig.fraction_of_max field)
    - python/src/boros_brain/config/schema.py (MarketCalibration.max_update_delay_s — added Plan 04-02)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-02 §, lines 526-548)
  </read_first>
  <behavior>
    OracleStaleBreaker:
      class OracleStaleBreaker(Breaker):
          name = "oracle_stale"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts) -> BreakerSignal:
              cfg = config.decision.breakers.oracle_stale
              market = config.markets[0]
              if w3 is None:
                  return BreakerSignal(tripped=False, reason="no_w3_yet")
              try:
                  f_index = await read_latest_findex(w3, market.fIndex_oracle_address)
              except Exception as exc:
                  log.warning("oracle_stale.read_failed", err=str(exc))
                  return BreakerSignal(tripped=False, reason="read_failed")
              f_time = f_index.f_time
              max_delay = market.max_update_delay_s
              age_s = current_chain_ts - f_time
              threshold_s = cfg.fraction_of_max * max_delay
              if age_s > threshold_s:
                  return BreakerSignal(
                      tripped=True, reason="oracle_stale",
                      payload={"f_time": f_time, "age_s": age_s, "threshold_s": threshold_s},
                      kill_command_kind="CANCEL_ALL",
                  )
              return BreakerSignal(tripped=False, reason="fresh",
                                   payload={"age_s": age_s, "threshold_s": threshold_s})

    Tests:
    - test_fires_above_threshold: monkeypatch findex_reader.read_latest_findex to return FIndex with f_time = current_chain_ts - 0.71 * max_update_delay (default 600); assert tripped True.
    - test_silent_below_threshold: f_time = current_chain_ts - 0.69 * max_update_delay; assert tripped False.
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/breakers/oracle_stale.py with the body from <behavior>. Imports include `from ...data.findex_reader import read_latest_findex`.

2. Update python/tests/test_breaker_oracle_stale.py — remove importorskip; implement two tests using `monkeypatch.setattr("boros_brain.decision.breakers.oracle_stale.read_latest_findex", _stub)` where `_stub` returns an object with `.f_time` attribute set to the desired value.

   Hint: build a tiny stub `class _F: f_time = ...` and `async def _stub(w3, addr): return _F()`.

   The test uses default_config which includes markets[0] with max_update_delay_s=600 (default from Plan 04-02 schema extension).

Self-verification: cd python ; uv run pytest tests/test_breaker_oracle_stale.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_oracle_stale.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/oracle_stale.py contains "class OracleStaleBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/oracle_stale.py contains "fraction_of_max"
    - File python/src/boros_brain/decision/breakers/oracle_stale.py contains "max_update_delay_s"
    - File python/src/boros_brain/decision/breakers/oracle_stale.py contains "CANCEL_ALL"
    - cd python ; uv run pytest tests/test_breaker_oracle_stale.py -x exits 0
    - python3 scripts/no_threshold_dials_lint.py exits 0
  </acceptance_criteria>
  <done>SAFE-02 implemented; both threshold tests PASS.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: SAFE-03 + SAFE-04 — CloRemovalBreaker + CloShiftBreaker</name>
  <files>
    python/src/boros_brain/decision/breakers/clo_removal.py,
    python/src/boros_brain/decision/breakers/clo_shift.py,
    python/tests/test_breaker_clo_removal.py,
    python/tests/test_breaker_clo_shift.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/state/writers/clo_history.py (full file — read latest two rows pattern)
    - python/src/boros_brain/decision/config.py (CloRemovalBreakerConfig, CloShiftBreakerConfig.n_ticks)
    - python/src/boros_brain/config/schema.py (MarketCalibration.scale, MarketCalibration.s)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-03 §, lines 552-573; SAFE-04 §, lines 576-611 — including stay-out-of-range branch under voluntary_cancel_forfeits_accumulated=True)
  </read_first>
  <behavior>
    CloRemovalBreaker:
      class CloRemovalBreaker(Breaker):
          name = "clo_removal"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              market = config.markets[0]
              row = read_latest_clo_history(sqlite_path, market.market_id)
              if row is None:
                  return BreakerSignal(tripped=False, reason="no_clo_history_yet")
              if row["clo_lower_thresh"] == 0.0 or row["clo_upper_thresh"] == 0.0:
                  return BreakerSignal(
                      tripped=True, reason="clo_removed",
                      payload={"clo_lower": row["clo_lower_thresh"], "clo_upper": row["clo_upper_thresh"]},
                      kill_command_kind="CANCEL_ALL_AND_ALERT",
                  )
              return BreakerSignal(tripped=False, reason="clo_present")

    CloShiftBreaker:
      class CloShiftBreaker(Breaker):
          name = "clo_shift"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              cfg = config.decision.breakers.clo_shift
              market = config.markets[0]
              rows = read_clo_history_latest_n(sqlite_path, market.market_id, n=2)
              if len(rows) < 2:
                  return BreakerSignal(tripped=False, reason="insufficient_history")
              new, old = rows[0], rows[1]  # DESC order
              scale = market.scale
              delta_lower_ticks = abs(new["clo_lower_thresh"] - old["clo_lower_thresh"]) * scale
              delta_upper_ticks = abs(new["clo_upper_thresh"] - old["clo_upper_thresh"]) * scale
              max_delta_ticks = max(delta_lower_ticks, delta_upper_ticks)
              if max_delta_ticks > cfg.n_ticks:
                  payload = {"delta_ticks": float(max_delta_ticks),
                             "delta_lower_ticks": float(delta_lower_ticks),
                             "delta_upper_ticks": float(delta_upper_ticks)}
                  if config.strategy.voluntary_cancel_forfeits_accumulated:
                      return BreakerSignal(
                          tripped=True, reason="clo_shifted",
                          payload=payload,
                          kill_command_kind="CANCEL_ALL_HOLD_NO_REPLACE",
                      )
                  return BreakerSignal(
                      tripped=True, reason="clo_shifted",
                      payload=payload,
                      kill_command_kind="CANCEL_ALL_AND_RECALIBRATE",
                  )
              return BreakerSignal(tripped=False, reason="clo_stable", payload={"delta_ticks": float(max_delta_ticks)})

    NEW helper to add to clo_history writer module: read_clo_history_latest_n(sqlite_path, market_id, n=2) — returns the latest n rows ordered DESC by snapshot_ts. If the existing module already has a similar helper, reuse; otherwise add it (single-writer-per-table is about WRITES; reads are unrestricted).

    Tests:
    - test_breaker_clo_removal.py: parametrize (clo_lower, clo_upper) combinations; assert tripped truth pattern.
    - test_breaker_clo_shift.py:
      * test_fires_on_n_tick_shift: seed two clo_history rows where new.clo_lower differs from old.clo_lower by > 5/scale (config.markets[0].scale=10000 means 5 ticks = 0.0005 APR shift); assert tripped True, kill_command_kind="CANCEL_ALL_AND_RECALIBRATE".
      * test_silent_under_threshold: shift 3 ticks; assert tripped False.
      * test_stay_out_of_range_branch_under_punitive: same fixture but config.strategy.voluntary_cancel_forfeits_accumulated=True; assert kill_command_kind=="CANCEL_ALL_HOLD_NO_REPLACE".
  </behavior>
  <action>
1. Read python/src/boros_brain/state/writers/clo_history.py to see if read_latest_clo_history and a multi-row read helper exist. If get_latest_clo_history exists, use it directly. If a multi-row helper does not exist, add it as `def read_clo_history_latest_n(sqlite_path: Path, market_id: str, n: int = 2) -> list[dict]` (reading is not write-restricted).

2. Create python/src/boros_brain/decision/breakers/clo_removal.py per the body in <behavior>. Module docstring cites [[breaker-clo-removal-and-shift]] and SAFE-03.

3. Create python/src/boros_brain/decision/breakers/clo_shift.py per the body in <behavior>. Module docstring cites [[breaker-clo-removal-and-shift]] and SAFE-04 + the A1xA3 compound risk note (under punitive branch, repost loses accumulation, so HOLD_NO_REPLACE is preferable).

4. Update python/tests/test_breaker_clo_removal.py — remove importorskip; implement parametrized test per <behavior> using seed_clo_history fixture.

5. Update python/tests/test_breaker_clo_shift.py — remove importorskip; implement three tests:
   - test_fires_on_n_tick_shift: seed_clo_history with rows demonstrating an APR shift > 5/scale; assert "CANCEL_ALL_AND_RECALIBRATE".
   - test_silent_under_threshold: shift below threshold; assert tripped=False.
   - test_stay_out_of_range_branch_under_punitive: clone the first test's fixture, override config via `default_config.model_copy(update={"strategy": StrategyConfig(voluntary_cancel_forfeits_accumulated=True)})` (or build a fresh BotConfig); assert kill_command_kind=="CANCEL_ALL_HOLD_NO_REPLACE".

Self-verification: both test files PASS.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_clo_removal.py tests/test_breaker_clo_shift.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/clo_removal.py contains "class CloRemovalBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/clo_removal.py contains "CANCEL_ALL_AND_ALERT"
    - File python/src/boros_brain/decision/breakers/clo_shift.py contains "class CloShiftBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/clo_shift.py contains "CANCEL_ALL_HOLD_NO_REPLACE"
    - File python/src/boros_brain/decision/breakers/clo_shift.py contains "CANCEL_ALL_AND_RECALIBRATE"
    - File python/src/boros_brain/decision/breakers/clo_shift.py contains "voluntary_cancel_forfeits_accumulated"
    - cd python ; uv run pytest tests/test_breaker_clo_removal.py -x exits 0
    - cd python ; uv run pytest tests/test_breaker_clo_shift.py -x exits 0
    - python3 scripts/sqlite_writer_lint.py --root . exits 0
  </acceptance_criteria>
  <done>SAFE-03 + SAFE-04 implemented including the A1xA3 compound stay-out-of-range branch; tests GREEN.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: SAFE-05 FillRateBreaker</name>
  <files>
    python/src/boros_brain/decision/breakers/fill_rate.py,
    python/src/boros_brain/state/writers/tx_receipts.py,
    python/tests/test_breaker_fill_rate.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/state/writers/tx_receipts.py (current — note that hands writes; brain has TEST_ONLY=True writer; we ADD a read_only helper here)
    - python/src/boros_brain/decision/config.py (FillRateBreakerConfig.k_fills_per_hour=3)
    - python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py (event_type column added)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-05 §, lines 615-637)
    - python/tests/test_breaker_fill_rate.py (RED tests — fixture seed_tx_receipts_fills)
  </read_first>
  <behavior>
    FillRateBreaker:
      class FillRateBreaker(Breaker):
          name = "fill_rate"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              cfg = config.decision.breakers.fill_rate
              one_hour_ago = current_chain_ts - 3600
              n_fills = read_tx_receipts_fill_count(sqlite_path,
                                                    market_id=config.markets[0].market_id if config.markets else None,
                                                    since_ts=one_hour_ago)
              if n_fills > cfg.k_fills_per_hour:
                  return BreakerSignal(
                      tripped=True, reason="fill_rate_runaway",
                      payload={"n_fills_last_hour": n_fills, "threshold": cfg.k_fills_per_hour},
                      kill_command_kind="PAUSE_AND_ALERT",
                  )
              return BreakerSignal(tripped=False, reason="ok",
                                   payload={"n_fills_last_hour": n_fills})

    NEW read helper to add to tx_receipts.py:
      def read_tx_receipts_fill_count(sqlite_path: Path, *, market_id: str | None = None,
                                       since_ts: int | None = None) -> int:
          from boros_brain.state.db import open_connection
          sql = "SELECT COUNT(*) FROM tx_receipts WHERE event_type = 'fill'"
          params = []
          if market_id is not None:
              sql += " AND market_id = ?"
              params.append(market_id)
          if since_ts is not None:
              sql += " AND chain_ts >= ?"
              params.append(since_ts)
          with open_connection(sqlite_path) as conn:
              row = conn.execute(sql, params).fetchone()
          return int(row[0]) if row else 0

      Reads are NOT restricted by sqlite_writer_lint (it only checks INSERT/UPDATE/DELETE).

    Tests:
    - test_fires_at_4_fills: seed_tx_receipts_fills(n_fills=4, since_chain_ts=current_chain_ts-3600); assert tripped True, kill_command_kind == "PAUSE_AND_ALERT".
    - test_silent_at_3_fills: n_fills=3; assert tripped False (3 not greater than 3).
  </behavior>
  <action>
1. Read python/src/boros_brain/state/writers/tx_receipts.py to find existing writer + read functions; verify whether the file is TEST_ONLY=True for the Python side (per Plan 01-02 single-writer discipline; hands owns the writes; Python has TEST_ONLY=True writer).

2. Add to tx_receipts.py the new read_tx_receipts_fill_count helper per <behavior>. The function does NOT INSERT/UPDATE/DELETE so it is allowed in the brain-side module without TEST_ONLY guard.

3. Create python/src/boros_brain/decision/breakers/fill_rate.py per <behavior>. Module docstring cites [[breaker-fill-rate-runaway]] and SAFE-05. Note: PAUSE_AND_ALERT is non-self-clearing — the operator must use the reset-breaker CLI subcommand (Plan 04-06).

4. Update python/tests/test_breaker_fill_rate.py — remove importorskip; implement two tests using seed_tx_receipts_fills fixture. The fixture must use the TEST_ONLY=True writer path; verify the fixture inserts rows with event_type='fill'.

Note for the conftest fixture: the seed_tx_receipts_fills fixture in conftest.py imports the TEST_ONLY=True writer (e.g. `from boros_brain.state.writers.tx_receipts import insert_tx_receipt`); ensure the writer accepts an event_type kwarg. If the existing TEST_ONLY writer signature does not accept event_type, extend it in this task (the change is local to tx_receipts.py and does not break TS-side writes which have their own ts/src/boros_hands/state/sqlite_writer.ts).

Self-verification: cd python ; uv run pytest tests/test_breaker_fill_rate.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_fill_rate.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/fill_rate.py contains "class FillRateBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/fill_rate.py contains "PAUSE_AND_ALERT"
    - File python/src/boros_brain/decision/breakers/fill_rate.py contains "k_fills_per_hour"
    - grep -q "read_tx_receipts_fill_count" python/src/boros_brain/state/writers/tx_receipts.py
    - cd python ; uv run pytest tests/test_breaker_fill_rate.py -x exits 0
    - python3 scripts/sqlite_writer_lint.py --root . exits 0 (the new helper is a SELECT, not write)
  </acceptance_criteria>
  <done>SAFE-05 implemented; PAUSE_AND_ALERT semantics encoded; read helper added without breaking single-writer discipline.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: B5 absorbed — LossFitDegradedBreaker (-> SHRINK_TO_Q_MIN)</name>
  <files>
    python/src/boros_brain/decision/breakers/loss_fit_degraded.py,
    python/tests/test_breaker_loss_fit_degraded.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/state/writers/loss_grid_artifacts.py (full file — get_latest_loss_grid_artifact signature, fit_status field on LossGridArtifact)
    - python/src/boros_brain/loss_model/schemas.py (LossGridArtifact.fit_status Literal)
    - python/src/boros_brain/decision/config.py (LossFitDegradedBreakerConfig)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (B5 absorbed §, lines 850-868)
  </read_first>
  <behavior>
    LossFitDegradedBreaker:
      class LossFitDegradedBreaker(Breaker):
          name = "loss_fit_degraded"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              market = config.markets[0]
              artifact = get_latest_loss_grid_artifact(sqlite_path, market.market_id, config.side)
              if artifact is None:
                  return BreakerSignal(tripped=False, reason="no_grid_yet")
              if artifact.fit_status == "degraded":
                  return BreakerSignal(
                      tripped=True, reason="loss_fit_degraded",
                      payload={"window_end_ts": artifact.window_end_ts,
                               "fit_status": artifact.fit_status},
                      kill_command_kind="SHRINK_TO_Q_MIN",
                  )
              return BreakerSignal(tripped=False, reason=f"fit_status_{artifact.fit_status}")

    Tests:
    - test_fires_on_degraded_status: seed_loss_grid_artifact(fit_status="degraded", market_id=..., side="long"); assert tripped True, kill_command_kind=="SHRINK_TO_Q_MIN".
    - test_silent_on_ok_status: seed_loss_grid_artifact(fit_status="ok"); assert tripped False.
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/breakers/loss_fit_degraded.py per <behavior>. Module docstring cites [[breaker-loss-fit-degraded]], B5 absorbed, and SHRINK_TO_Q_MIN semantic (does NOT cancel orders — overrides next placement size to Q_min via the coordinator's force_q_min flag landed in 04-06).

2. Update python/tests/test_breaker_loss_fit_degraded.py — remove importorskip; implement two tests using seed_loss_grid_artifact fixture.

Self-verification: cd python ; uv run pytest tests/test_breaker_loss_fit_degraded.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_loss_fit_degraded.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/loss_fit_degraded.py contains "class LossFitDegradedBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/loss_fit_degraded.py contains "SHRINK_TO_Q_MIN"
    - File python/src/boros_brain/decision/breakers/loss_fit_degraded.py contains "fit_status"
    - cd python ; uv run pytest tests/test_breaker_loss_fit_degraded.py -x exits 0
  </acceptance_criteria>
  <done>B5 absorbed; SHRINK_TO_Q_MIN signal encoded.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 6: Wiki write-back — 6 breaker pages</name>
  <files>
    python/tests/test_breaker_margin_trajectory.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (LLM Wiki Pages to Write-Back, lines 1532-1557)
  </read_first>
  <behavior>
    File six wiki pages (one per breaker in this plan):
    - breaker-margin-trajectory.md (SAFE-01)
    - breaker-oracle-stale.md (SAFE-02)
    - breaker-clo-removal-and-shift.md (SAFE-03/04 — single page covers both per RESEARCH)
    - clo-shift-stay-out-of-range-branch.md (SAFE-04 A1xA3 compound risk)
    - breaker-fill-rate-runaway.md (SAFE-05)
    - breaker-loss-fit-degraded.md (B5 absorbed)
    Plus an index page circuit-breakers-v05.md listing all 10 breakers (4 in this plan slot are TBD, marked Pending Plan 04-05).

    Touch test_breaker_margin_trajectory.py module docstring with cross-references.

    Note: architecture.yml + ARCHITECTURE.md edits for these breakers are deferred to plan 04-06's atomic Phase-4 architecture delta task.
  </behavior>
  <action>
1. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/circuit-breakers-v05.md as the index page with Status: Current and a table of all 10 breakers, their requirement IDs, kill_command_kind, and the wiki page filename for each. Mark the SAFE-06..09 rows as "TBD — Plan 04-05" if not yet filed.

2. File breaker-margin-trajectory.md — Status Current; SAFE-01 spec; np.polyfit linear regression; Pitfall #4 sign-confusion guard; default knobs (window_s=30, min_samples=10, time_to_mm_threshold_s=30). Cite [[circuit-breakers-v05]].

3. File breaker-oracle-stale.md — Status Current; SAFE-02 spec; 0.7 x maxUpdateDelay early-fire discipline (predictive vs reactive). Cite [[circuit-breakers-v05]].

4. File breaker-clo-removal-and-shift.md — Status Current; covers SAFE-03 + SAFE-04; tick conversion via MarketCalibration.scale; default n_ticks=5 anchor justification (5bp shift > typical 5h drift). Cite [[circuit-breakers-v05]] and [[clo-shift-stay-out-of-range-branch]].

5. File clo-shift-stay-out-of-range-branch.md — Status Current; A1xA3 compound risk; under voluntary_cancel_forfeits_accumulated=True the breaker emits CANCEL_ALL_HOLD_NO_REPLACE instead of CANCEL_ALL_AND_RECALIBRATE; rationale with the EV equation comparing repost-and-lose-accumulation vs stay-out-of-range. Cite [[breaker-clo-removal-and-shift]] and [[voluntary-cancel-reward-behavior]].

6. File breaker-fill-rate-runaway.md — Status Current; SAFE-05 spec; PAUSE_AND_ALERT non-self-clearing semantics; operator-reset-via-CLI workflow (Plan 04-06). Cite [[circuit-breakers-v05]].

7. File breaker-loss-fit-degraded.md — Status Current; B5 absorbed; SHRINK_TO_Q_MIN signal; coordinator force_q_min flag flow (Plan 04-06). Cite [[circuit-breakers-v05]] and [[ou-on-basis-loss-scaffold]].

8. Append to test_breaker_margin_trajectory.py module docstring: "See [[breaker-margin-trajectory]] and [[circuit-breakers-v05]] for spec."

Self-verification: all 6+1 wiki pages exist with Status: Current.
  </action>
  <verify>
    <automated>test -f "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/circuit-breakers-v05.md"</automated>
  </verify>
  <acceptance_criteria>
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/circuit-breakers-v05.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-margin-trajectory.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-oracle-stale.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-clo-removal-and-shift.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/clo-shift-stay-out-of-range-branch.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-fill-rate-runaway.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-loss-fit-degraded.md" exists
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/circuit-breakers-v05.md"
    - grep -q "circuit-breakers-v05" python/tests/test_breaker_margin_trajectory.py
  </acceptance_criteria>
  <done>7 wiki pages filed (6 breaker + 1 index); cross-references in place.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.margin_history -> margin_trajectory | Stale or missing margin_history rows produce false "insufficient_history" — preferable to false-fire. |
| findex_reader RPC -> oracle_stale | RPC stall produces "read_failed"; preferable to false-fire. |
| state.tx_receipts -> fill_rate | Pre-migration rows have event_type='unknown' (server_default); SAFE-05 query filters by 'fill' so it under-counts fills that pre-date the migration. Conservative direction. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-04-01 | T (Tampering) | Margin slope sign confusion (Pitfall #4) | mitigate | Hypothesis test test_no_fire_when_growing injects positive slope and asserts no fire. The function docstring states "slope < 0 means SHRINKING" explicitly. The np.polyfit return value is unpacked as `(slope, intercept)` matching numpy convention. |
| T-04-04-02 | D (Denial of service) | Per-breaker RPC stall (oracle_stale) | mitigate | The check function catches general Exception and returns tripped=False with reason="read_failed"; the coordinator (Plan 04-06) wraps each .check() in asyncio.wait_for(timeout=200ms) per Pitfall #1; a stalled breaker NEVER blocks the 1 Hz loop. |
| T-04-04-03 | I (Information disclosure) | breaker payload dict | accept | payload contains numeric thresholds and observed values (no secrets, no PII). Used for forensic replay via state.breaker_events. |
| T-04-04-04 | T (Tampering) | clo_shift A1xA3 compound branch | mitigate | The branch is keyed off config.strategy.voluntary_cancel_forfeits_accumulated which is LOCKED in BotConfig with default=False. Test test_stay_out_of_range_branch_under_punitive verifies the punitive branch path works; Phase 5 backtest sweeps both as a sanity-check. |
| T-04-04-05 | E (Elevation of privilege) | tx_receipts read helper | mitigate | The new read_tx_receipts_fill_count function uses parameterized SQL (`?` placeholders) — no string-format injection vector. The function is read-only (SELECT) so sqlite_writer_lint does not need to allowlist it. |
| T-04-04-06 | R (Repudiation) | Loss-fit-degraded -> SHRINK_TO_Q_MIN signal | mitigate | The signal is persisted to state.breaker_events (Plan 04-06 BreakerCoordinator); the LossGridArtifact.fit_status='degraded' upstream signal is persisted to state.loss_grid_artifacts by Phase 3 — full audit trail across both layers. |
</threat_model>

<verification>
After all tasks complete, run:

```
cd python ; uv run pytest tests/test_breaker_margin_trajectory.py tests/test_breaker_oracle_stale.py tests/test_breaker_clo_removal.py tests/test_breaker_clo_shift.py tests/test_breaker_fill_rate.py tests/test_breaker_loss_fit_degraded.py -x

python3 scripts/no_threshold_dials_lint.py
python3 scripts/no_time_time_lint.py
python3 scripts/sqlite_writer_lint.py --root .
```

All MUST exit 0.

Note: `python3 scripts/architecture_lint.py` is NOT run after this plan because this plan does NOT touch docs/architecture.yml or docs/ARCHITECTURE.md. The architecture nodes/edges for these 6 breakers land atomically in plan 04-06's final delta task; architecture_lint is the gate at the end of 04-06.
</verification>

<success_criteria>
- [ ] 6 breaker source modules exist; each subclasses Breaker ABC.
- [ ] All 6 corresponding test files PASS.
- [ ] Pitfall #4 sign-confusion guard test PASSES (positive slope NEVER fires).
- [ ] CloShift A1xA3 compound branch test PASSES.
- [ ] Lint scripts (sqlite_writer, no_threshold_dials, no_time_time) all exit 0.
- [ ] 7 wiki pages filed (6 breaker pages + 1 index).
- [ ] Architecture delta deferred to 04-06: this plan does NOT modify docs/architecture.yml or docs/ARCHITECTURE.md.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-04-SUMMARY.md` documenting:
- 6 breaker modules implemented
- Tests turned GREEN (6 files)
- Wiki pages filed (7 — 6 breaker + 1 index)
- Architecture delta deferred to plan 04-06 (explicit note: this plan owns NO architecture-file edits)
</output>
