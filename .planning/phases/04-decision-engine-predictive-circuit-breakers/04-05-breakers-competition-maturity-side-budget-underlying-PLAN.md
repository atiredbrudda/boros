---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 05
type: execute
wave: 2
depends_on: [01, 02]
autonomous: true
requirements: [SAFE-06, SAFE-07, SAFE-08, SAFE-09]
files_modified:
  - python/src/boros_brain/decision/breakers/competition.py
  - python/src/boros_brain/decision/breakers/maturity.py
  - python/src/boros_brain/decision/breakers/side_budget.py
  - python/src/boros_brain/decision/breakers/underlying_stale.py
  - python/src/boros_brain/data/underlying_apr_reader.py
  - python/src/boros_brain/reward_model/competition_tracker.py
  - python/src/boros_brain/state/writers/competition_history.py
  - python/src/boros_brain/state/writers/market_reward_calibration.py
  - python/src/boros_brain/state/writers/decisions.py
  - python/src/boros_brain/state/writers/tx_receipts.py
  - python/tests/test_breaker_competition.py
  - python/tests/test_breaker_maturity.py
  - python/tests/test_breaker_side_budget.py
  - python/tests/test_breaker_underlying_stale.py

user_setup: []

must_haves:
  truths:
    - "Four economic / data-feed breakers fire on documented trigger conditions and stay silent below threshold."
    - "CompetitionTracker now writes a competition_history row on every cycle (the existing Plan 03-02 code only emitted Sigma_others to the EV equation; this plan adds the SQLite write alongside)."
    - "MaturityBreaker computes migration_cost = entrance_fee_pendle + 2 x cancel_cost_pendle and rolls when remaining EV is below it."
    - "UnderlyingStaleBreaker reads parquet underlying_apr via DuckDB; per-exchange cadence is operator-tunable."
    - "First-day operator-pause noise (Pitfall #3) is mitigated: SAFE-06/08 explicitly check len(rows) >= 2 and return reason='insufficient_history' otherwise."
    - "Architecture nodes/edges for this plan's modules (competition, maturity, side_budget, underlying_stale, underlying_apr_reader, plus the new competition_tracker -> competition_history WRITES edge) are added by 04-06's atomic Phase-4 architecture delta task. This plan does not touch docs/architecture.yml or docs/ARCHITECTURE.md to avoid parallel-execution merge conflicts with sibling Wave-2 plans 04-03 and 04-04."
  artifacts:
    - path: "python/src/boros_brain/decision/breakers/competition.py"
      provides: "SAFE-06 — Q_total_in_range drop > 50% in 1 epoch"
      contains: "class CompetitionBreaker"
    - path: "python/src/boros_brain/decision/breakers/maturity.py"
      provides: "SAFE-07 — time_to_maturity x R_me < migration_cost -> ROLL_POSITION"
      contains: "class MaturityBreaker"
    - path: "python/src/boros_brain/decision/breakers/side_budget.py"
      provides: "SAFE-08 — long/short split drift > 30% in 1 epoch"
      contains: "class SideBudgetBreaker"
    - path: "python/src/boros_brain/decision/breakers/underlying_stale.py"
      provides: "SAFE-09 — underlying_apr feed > 2x expected cadence"
      contains: "class UnderlyingStaleBreaker"
    - path: "python/src/boros_brain/reward_model/competition_tracker.py"
      provides: "Now also writes state.competition_history alongside emitting Sigma_others"
      contains: "insert_competition_row"
    - path: "python/src/boros_brain/state/writers/competition_history.py"
      provides: "Adds read_competition_history_since helper for SAFE-06"
      contains: "read_competition_history_since"
  key_links:
    - from: "python/src/boros_brain/decision/breakers/competition.py"
      to: "python/src/boros_brain/state/writers/competition_history.py"
      via: "read_competition_history call"
      pattern: "competition_history"
    - from: "python/src/boros_brain/decision/breakers/maturity.py"
      to: "python/src/boros_brain/decision/gas_history.py"
      via: "cancel_cost_pendle reused as part of migration_cost"
      pattern: "gas_history"
    - from: "python/src/boros_brain/decision/breakers/side_budget.py"
      to: "python/src/boros_brain/state/writers/market_reward_calibration.py"
      via: "history read"
      pattern: "market_reward_calibration"
    - from: "python/src/boros_brain/decision/breakers/underlying_stale.py"
      to: "data/parquet/underlying_apr"
      via: "DuckDB read"
      pattern: "underlying_apr"
---

<objective>
Wave 2 plan C — implement SAFE-06..09 (four breakers) and finalize the existing CompetitionTracker to ALSO write competition_history rows (the Plan 03-02 tracker emits Sigma_others to the EV equation but does not persist; SAFE-06 needs that persistence). The 04-06 BreakerCoordinator collects all 10 breakers; this plan delivers the remaining 4.

Architecture-file edits (docs/architecture.yml + docs/ARCHITECTURE.md) for the 4 breaker module nodes, the new underlying_apr_reader helper module, and the new competition_tracker -> competition_history WRITES edge are deferred to plan 04-06's atomic Phase-4 architecture delta task. This plan deliberately does NOT touch the architecture files so it can run in parallel with Wave-2 sibling plans 04-03 and 04-04 without merge conflict.

Purpose: Land the slow-tempo / economic breakers (competition collapse, maturity migration, per-side budget rebalance, underlying-feed stale) that protect the bot from the second-order Phase-3 / external-feed failure modes.

Output: 4 breaker modules + GREEN tests + competition_tracker SQLite write. (Architecture delta lands in 04-06.)
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
@python/src/boros_brain/state/writers/competition_history.py
@python/src/boros_brain/state/writers/market_reward_calibration.py
@python/src/boros_brain/reward_model/competition_tracker.py
@python/src/boros_brain/duckdb_layer

<interfaces>
Existing readers:
  state/writers/competition_history.py: get_latest_competition(sqlite_path, market_id) -> dict | None
  state/writers/market_reward_calibration.py: writers + readers from Plan 03-02
  reward_model/competition_tracker.py: CompetitionTracker.run_one_cycle (existing — we ADD a SQLite write call)

NEW config knobs (already in BotConfig from Plan 04-02):
  decision.breakers.competition.{drop_threshold=0.5, min_re_arm_s=60.0}
  decision.breakers.maturity.{migration_cost_buffer_pct=1.0, min_re_arm_s=60.0}
  decision.breakers.side_budget.{drift_threshold=0.30, min_re_arm_s=60.0}
  decision.breakers.underlying_stale.{expected_cadence_s_per_exchange={...}, min_re_arm_s=60.0}
  execution.entrance_fee_pendle (operator-calibrated)
  MarketCalibration.maturity_ts (existing)
  MarketCalibration.underlying_exchange (Plan 04-02 — default "binance")
  MarketCalibration.underlying_symbol (Plan 04-02 — default "")

Phase 3 readers reused unchanged:
  reward_share_model.epoch_days (BotConfig.reward_share_model.epoch_days)
  market_reward_calibration history read (long_side_split, short_side_split, calibrated_at_utc)

NEW reads to add (helpers — not new writers):
  read_competition_history_since(sqlite_path, market_id, since_ts) -> list[dict]
  read_market_reward_calibration_history(sqlite_path, market_id, limit=10) -> list[dict]
  read_underlying_apr_max_ts(parquet_root, exchange, symbol) -> int | None  (DuckDB SELECT MAX(snapshot_ts) FROM read_parquet(...))
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: CompetitionTracker SQLite write + SAFE-06 CompetitionBreaker</name>
  <files>
    python/src/boros_brain/reward_model/competition_tracker.py,
    python/src/boros_brain/state/writers/competition_history.py,
    python/src/boros_brain/decision/breakers/competition.py,
    python/tests/test_breaker_competition.py
  </files>
  <read_first>
    - python/src/boros_brain/reward_model/competition_tracker.py (full file — find the spot where Sigma_others is emitted; we add insert_competition_row alongside)
    - python/src/boros_brain/state/writers/competition_history.py (full — has insert_competition_row; ADD read_competition_history_since helper)
    - python/src/boros_brain/decision/config.py (CompetitionBreakerConfig.drop_threshold)
    - python/src/boros_brain/decision/breakers/base.py
    - python/tests/test_competition_tracker.py (existing — we MUST not break)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-06 §, lines 642-670; Pitfall #3 first-day operator-pause noise lines 1283-1287)
  </read_first>
  <behavior>
    Step A — CompetitionTracker SQLite write:
    The existing run_one_cycle in competition_tracker.py computes Sigma_others and emits to the EV equation. Currently it does not persist. Plan 04-05 adds:
      insert_competition_row(self.conn, polled_at_utc=polled_at, chain_ts=chain_ts,
                             market_id=market_id, q_me_pendle=q_me, sigma_others_pendle=sigma_others,
                             run_id=self.run_id, data_source=data_source)
      self.conn.commit()
    The existing tests for CompetitionTracker MUST still pass — verify by running test_competition_tracker.py post-change.

    Step B — read helper in competition_history.py:
    Add module-level function:
      def read_competition_history_since(sqlite_path: Path, market_id: str, since_ts: int) -> list[dict]:
          from boros_brain.state.db import open_connection
          with open_connection(sqlite_path) as conn:
              rows = conn.execute(
                  "SELECT polled_at_utc, chain_ts, q_me_pendle, sigma_others_pendle, data_source, run_id "
                  "FROM competition_history WHERE market_id = ? AND chain_ts >= ? "
                  "ORDER BY chain_ts ASC",
                  (market_id, since_ts),
              ).fetchall()
          return [dict(zip(["polled_at_utc","chain_ts","q_me_pendle","sigma_others_pendle","data_source","run_id"], r)) for r in rows]

    Step C — SAFE-06 CompetitionBreaker:
      class CompetitionBreaker(Breaker):
          name = "competition"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              cfg = config.decision.breakers.competition
              market = config.markets[0]
              one_epoch_ago = current_chain_ts - int(config.reward_share_model.epoch_days * 86400)
              rows = read_competition_history_since(sqlite_path, market.market_id, one_epoch_ago)
              if len(rows) < 2:
                  return BreakerSignal(tripped=False, reason="insufficient_history",
                                       payload={"n": len(rows)})
              # Compute Q_total = q_me + sigma_others per row
              q_total_now = rows[-1]["q_me_pendle"] + rows[-1]["sigma_others_pendle"]
              q_total_lag = rows[0]["q_me_pendle"] + rows[0]["sigma_others_pendle"]
              if q_total_lag <= 0:
                  return BreakerSignal(tripped=False, reason="zero_baseline")
              drop_pct = (q_total_lag - q_total_now) / q_total_lag
              if drop_pct > cfg.drop_threshold:
                  return BreakerSignal(
                      tripped=True, reason="competition_collapse",
                      payload={"drop_pct": drop_pct, "q_total_now": q_total_now,
                               "q_total_lag": q_total_lag},
                      kill_command_kind="PAUSE_AND_ALERT",
                  )
              return BreakerSignal(tripped=False, reason="ok",
                                   payload={"drop_pct": drop_pct})

    Tests:
    - test_fires_on_50_pct_drop: seed two competition_history rows where the lag row has Q_total=200 (q_me=50, sigma_others=150) and the latest has Q_total=80 (q_me=20, sigma_others=60); drop_pct=0.6 > 0.5; assert tripped True, kill_command_kind="PAUSE_AND_ALERT".
    - test_silent_on_30_pct_drop: drop_pct=0.3; assert tripped False.
    - test_silent_on_zero_baseline: lag row Q_total=0; assert tripped False, reason "zero_baseline".
    - test_silent_on_insufficient_history: only 1 row in history; assert reason "insufficient_history" (Pitfall #3 first-day guard).
  </behavior>
  <action>
1. Read python/src/boros_brain/reward_model/competition_tracker.py to find the spot where the cycle completes (after Sigma_others is computed). Add:
   ```python
   from ..state.writers.competition_history import insert_competition_row
   ```
   at the top, and inside run_one_cycle right after `self._fail_count[market_id] = 0` (or equivalent success path), call:
   ```python
   insert_competition_row(
       self.conn, polled_at_utc=polled_at, chain_ts=chain_ts,
       market_id=market_id, q_me_pendle=q_me,
       sigma_others_pendle=sigma_others, run_id=self.run_id,
       data_source=data_source,
   )
   self.conn.commit()
   ```
   Confirm test_competition_tracker.py still passes (it may need `_migrated_db` to apply migration 0007 too — already done by Plan 04-02; the test fixtures should already migrate to head).

2. Add to python/src/boros_brain/state/writers/competition_history.py the new read_competition_history_since helper per <behavior>. The function is read-only — sqlite_writer_lint does not gate it.

3. Create python/src/boros_brain/decision/breakers/competition.py per <behavior>. Module docstring cites [[breaker-competition-collapse]] and SAFE-06 with Pitfall #3 reference (first-day operator-pause noise).

4. Update python/tests/test_breaker_competition.py — remove importorskip; implement four tests using seed_competition_history fixture. The fixture inserts q_me_pendle and sigma_others_pendle as separate fields; the breaker computes Q_total = q_me + sigma_others.

Self-verification: cd python ; uv run pytest tests/test_breaker_competition.py tests/test_competition_tracker.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_competition.py tests/test_competition_tracker.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/competition.py contains "class CompetitionBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/competition.py contains "PAUSE_AND_ALERT"
    - File python/src/boros_brain/decision/breakers/competition.py contains "epoch_days"
    - File python/src/boros_brain/decision/breakers/competition.py contains "insufficient_history"
    - grep -q "insert_competition_row" python/src/boros_brain/reward_model/competition_tracker.py
    - grep -q "read_competition_history_since" python/src/boros_brain/state/writers/competition_history.py
    - cd python ; uv run pytest tests/test_breaker_competition.py -x exits 0
    - cd python ; uv run pytest tests/test_competition_tracker.py -x exits 0
    - python3 scripts/sqlite_writer_lint.py --root . exits 0
  </acceptance_criteria>
  <done>SAFE-06 implemented; CompetitionTracker now persists competition_history rows; existing tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: SAFE-07 MaturityBreaker</name>
  <files>
    python/src/boros_brain/decision/breakers/maturity.py,
    python/tests/test_breaker_maturity.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/decision/gas_history.py (cancel_cost_pendle reused for migration_cost component)
    - python/src/boros_brain/state/writers/decisions.py (last r_me_per_epoch_pendle from prior decision rows — read pattern)
    - python/src/boros_brain/decision/config.py (MaturityBreakerConfig.migration_cost_buffer_pct, ExecutionConfig.entrance_fee_pendle)
    - python/src/boros_brain/config/schema.py (MarketCalibration.maturity_ts)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-07 §, lines 674-700)
  </read_first>
  <behavior>
    MaturityBreaker:
      class MaturityBreaker(Breaker):
          name = "maturity"
          def __init__(self, gas_cache: GasHistoryCache | None = None):
              self._gas_cache = gas_cache  # injected by coordinator; None acceptable for tests that mock cancel_cost via test fixture
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              cfg = config.decision.breakers.maturity
              market = config.markets[0]
              time_to_mat_s = market.maturity_ts - current_chain_ts
              if time_to_mat_s <= 0:
                  return BreakerSignal(tripped=True, reason="market_matured",
                                       kill_command_kind="ROLL_POSITION")
              epochs_remaining = time_to_mat_s / (config.reward_share_model.epoch_days * 86400)
              last_r_me = read_last_r_me_pendle(sqlite_path, market.market_id, config.side)
              if last_r_me is None:
                  return BreakerSignal(tripped=False, reason="no_decision_history_yet")
              expected_remaining_pendle = epochs_remaining * last_r_me
              # migration_cost = entrance_fee + 2 x cancel_cost
              if self._gas_cache is not None and w3 is not None:
                  cancel_cost = await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)
              else:
                  cancel_cost = 0.0  # test path
              migration_cost = (config.execution.entrance_fee_pendle +
                                2.0 * cancel_cost) * cfg.migration_cost_buffer_pct
              if expected_remaining_pendle < migration_cost:
                  return BreakerSignal(
                      tripped=True, reason="maturity_migration_due",
                      payload={"epochs_remaining": epochs_remaining,
                               "expected_pendle": expected_remaining_pendle,
                               "migration_cost_pendle": migration_cost},
                      kill_command_kind="ROLL_POSITION",
                  )
              return BreakerSignal(tripped=False, reason="ok",
                                   payload={"epochs_remaining": epochs_remaining,
                                            "expected_pendle": expected_remaining_pendle})

    NEW helper to add to decisions.py (or as a separate read module):
      def read_last_r_me_pendle(sqlite_path: Path, market_id: str, side: str) -> float | None:
          from boros_brain.state.db import open_connection
          with open_connection(sqlite_path) as conn:
              row = conn.execute(
                  "SELECT r_share_per_epoch_pendle FROM decisions "
                  "WHERE market_id = ? AND side = ? "
                  "ORDER BY chain_ts DESC LIMIT 1",
                  (market_id, side),
              ).fetchone()
          return float(row[0]) if row else None

    Pre-condition: state.decisions table from Plan 01-02 has columns including market_id, side, r_share_per_epoch_pendle, chain_ts. If the schema does not include r_share_per_epoch_pendle, we add a fallback returning None and document the gap (Plan 04-06 first decision-loop write populates the column).

    Tests:
    - test_fires_when_remaining_below_migration_cost: build BotConfig with markets[0].maturity_ts=current_chain_ts+3600 (1 hour out), epoch_days=7 -> epochs_remaining≈0.0059, last_r_me=0.001 PENDLE; expected_remaining = 5.9e-6; entrance_fee_pendle=0.5; cancel_cost=0; migration_cost=0.5 > 5.9e-6. Assert tripped=True, kill_command_kind="ROLL_POSITION".
    - test_silent_when_remaining_above_migration_cost: maturity_ts=current_chain_ts + 86400*30 (30 days), epochs≈4.28, last_r_me=10 PENDLE -> expected=42.8 PENDLE; migration_cost=0.5 PENDLE; assert tripped=False.
    - test_no_decision_history_yet: no rows in decisions; assert tripped=False, reason="no_decision_history_yet".
  </behavior>
  <action>
1. Add to python/src/boros_brain/state/writers/decisions.py the new read helper read_last_r_me_pendle. (Plan 01-02 schema is the source of truth; if r_share_per_epoch_pendle column is absent, the SQL query can be updated by Plan 04-06 when the engine starts persisting decisions; for now the function returns None on missing column too — wrap the query in try/except OperationalError.)

2. Create python/src/boros_brain/decision/breakers/maturity.py per <behavior>. Module docstring cites [[breaker-maturity-migration]] and SAFE-07. Note that gas_cache is injected — the coordinator (Plan 04-06) constructs `MaturityBreaker(gas_cache=gas_cache_instance)`.

3. Update python/tests/test_breaker_maturity.py — remove importorskip; implement three tests. For test_fires_when_remaining_below_migration_cost, seed a state.decisions row via direct SQL INSERT in the test (or via a new TEST_ONLY decisions writer if needed). Use BotConfig with execution.entrance_fee_pendle=0.5.

   For tests that need cancel_cost > 0, instantiate MaturityBreaker(gas_cache=None) — the breaker uses 0.0 for cancel_cost in that path, simplifying the test.

Self-verification: cd python ; uv run pytest tests/test_breaker_maturity.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_maturity.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/maturity.py contains "class MaturityBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/maturity.py contains "ROLL_POSITION"
    - File python/src/boros_brain/decision/breakers/maturity.py contains "entrance_fee_pendle"
    - File python/src/boros_brain/decision/breakers/maturity.py contains "migration_cost_buffer_pct"
    - grep -q "read_last_r_me_pendle" python/src/boros_brain/state/writers/decisions.py
    - cd python ; uv run pytest tests/test_breaker_maturity.py -x exits 0
  </acceptance_criteria>
  <done>SAFE-07 implemented; ROLL_POSITION signal encoded; gas_cache dependency-injected.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: SAFE-08 SideBudgetBreaker</name>
  <files>
    python/src/boros_brain/decision/breakers/side_budget.py,
    python/src/boros_brain/state/writers/market_reward_calibration.py,
    python/tests/test_breaker_side_budget.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/state/writers/market_reward_calibration.py (full — find existing read helpers; we ADD read_market_reward_calibration_history if not present)
    - python/src/boros_brain/decision/config.py (SideBudgetBreakerConfig.drift_threshold)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-08 §, lines 704-734; Pitfall #3 line 1287)
  </read_first>
  <behavior>
    SideBudgetBreaker:
      class SideBudgetBreaker(Breaker):
          name = "side_budget"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              cfg = config.decision.breakers.side_budget
              market = config.markets[0]
              rows = read_market_reward_calibration_history(sqlite_path, market.market_id, limit=10)
              if len(rows) < 2:
                  return BreakerSignal(tripped=False, reason="insufficient_calibration_history",
                                       payload={"n": len(rows)})
              # rows ordered DESC by calibrated_at_utc; row[0] = latest, row[-1] = oldest within limit
              latest = rows[0]
              # Find the row that is approximately 1 epoch older than latest
              one_epoch_iso = (datetime.fromisoformat(latest["calibrated_at_utc"].replace("Z","+00:00"))
                              - timedelta(days=config.reward_share_model.epoch_days)).isoformat()
              epoch_lag_row = next((r for r in rows if r["calibrated_at_utc"] <= one_epoch_iso), rows[-1])
              latest_split = latest["long_side_split"] if config.side == "long" else latest["short_side_split"]
              lag_split = epoch_lag_row["long_side_split"] if config.side == "long" else epoch_lag_row["short_side_split"]
              if lag_split <= 0:
                  return BreakerSignal(tripped=False, reason="zero_baseline_split")
              drift_pct = (lag_split - latest_split) / lag_split
              if drift_pct > cfg.drift_threshold:
                  return BreakerSignal(
                      tripped=True, reason="side_budget_rebalance",
                      payload={"drift_pct": drift_pct,
                               "latest_split": latest_split, "lag_split": lag_split},
                      kill_command_kind="HALVE_POSITION_AND_ALERT",
                  )
              return BreakerSignal(tripped=False, reason="ok",
                                   payload={"drift_pct": drift_pct})

    NEW read helper (add to market_reward_calibration.py):
      def read_market_reward_calibration_history(sqlite_path: Path, market_id: str,
                                                  limit: int = 10) -> list[dict]:
          from boros_brain.state.db import open_connection
          with open_connection(sqlite_path) as conn:
              rows = conn.execute(
                  "SELECT market_id, e_liq_per_epoch_pendle, long_side_split, short_side_split, "
                  "calibrated_at_utc, source FROM market_reward_calibration WHERE market_id = ? "
                  "ORDER BY calibrated_at_utc DESC LIMIT ?",
                  (market_id, limit),
              ).fetchall()
          return [dict(zip(["market_id","e_liq_per_epoch_pendle","long_side_split",
                            "short_side_split","calibrated_at_utc","source"], r)) for r in rows]

    Tests:
    - test_fires_at_30_pct_drift: seed two market_reward_calibration rows. Latest: long_side_split=0.34. Lag (1 epoch ago): long_side_split=0.5. drift_pct=(0.5-0.34)/0.5=0.32 > 0.30. config.side="long"; assert tripped=True, kill_command_kind="HALVE_POSITION_AND_ALERT".
    - test_silent_at_20_pct_drift: latest 0.4, lag 0.5. drift_pct=0.20; assert tripped=False.
    - test_silent_on_zero_baseline: lag long_side_split=0; assert reason "zero_baseline_split".
    - test_silent_on_insufficient_history: only 1 row; assert reason "insufficient_calibration_history" (Pitfall #3).
  </behavior>
  <action>
1. Read python/src/boros_brain/state/writers/market_reward_calibration.py to find existing read helpers. If a `read_market_reward_calibration_history` is absent, add it per <behavior>. The function is read-only.

2. Create python/src/boros_brain/decision/breakers/side_budget.py per <behavior>. Imports include `from datetime import datetime, timedelta`. Module docstring cites [[breaker-side-budget-rebalance]] and SAFE-08 (A2 absorbed). Documents Pitfall #3 first-day guard.

3. Update python/tests/test_breaker_side_budget.py — remove importorskip; implement four tests using seed_market_reward_calibration fixture. Configure config.side via `BotConfig(..., side="long")` for the long-side tests.

Self-verification: cd python ; uv run pytest tests/test_breaker_side_budget.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_side_budget.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/side_budget.py contains "class SideBudgetBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/side_budget.py contains "HALVE_POSITION_AND_ALERT"
    - File python/src/boros_brain/decision/breakers/side_budget.py contains "drift_threshold"
    - File python/src/boros_brain/decision/breakers/side_budget.py contains "insufficient_calibration_history"
    - grep -q "read_market_reward_calibration_history" python/src/boros_brain/state/writers/market_reward_calibration.py
    - cd python ; uv run pytest tests/test_breaker_side_budget.py -x exits 0
  </acceptance_criteria>
  <done>SAFE-08 implemented; HALVE_POSITION_AND_ALERT signal encoded; first-day operator-pause noise mitigated.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: SAFE-09 UnderlyingStaleBreaker (DuckDB read of underlying_apr parquet)</name>
  <files>
    python/src/boros_brain/decision/breakers/underlying_stale.py,
    python/src/boros_brain/data/underlying_apr_reader.py,
    python/tests/test_breaker_underlying_stale.py
  </files>
  <read_first>
    - python/src/boros_brain/decision/breakers/base.py
    - python/src/boros_brain/duckdb_layer (existing — find the underlying_apr read pattern; mirror)
    - python/src/boros_brain/decision/config.py (UnderlyingStaleBreakerConfig.expected_cadence_s_per_exchange dict)
    - python/src/boros_brain/config/schema.py (MarketCalibration.underlying_exchange, MarketCalibration.underlying_symbol)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-09 §, lines 738-763)
  </read_first>
  <behavior>
    UnderlyingStaleBreaker:
      class UnderlyingStaleBreaker(Breaker):
          name = "underlying_stale"
          async def check(self, *, sqlite_path, w3, parquet_root, config, current_chain_ts):
              cfg = config.decision.breakers.underlying_stale
              market = config.markets[0]
              expected_cadence_s = cfg.expected_cadence_s_per_exchange.get(market.underlying_exchange)
              if expected_cadence_s is None:
                  return BreakerSignal(tripped=False, reason=f"no_cadence_for_exchange_{market.underlying_exchange}")
              last_ts = read_underlying_apr_max_ts(parquet_root, market.underlying_exchange, market.underlying_symbol)
              if last_ts is None:
                  return BreakerSignal(tripped=False, reason="no_parquet_data_yet")
              age_s = current_chain_ts - last_ts
              if age_s > 2 * expected_cadence_s:
                  return BreakerSignal(
                      tripped=True, reason="underlying_feed_stale",
                      payload={"age_s": age_s, "expected_cadence_s": expected_cadence_s,
                               "exchange": market.underlying_exchange, "symbol": market.underlying_symbol},
                      kill_command_kind="HALT_AND_ALERT",
                  )
              return BreakerSignal(tripped=False, reason="fresh",
                                   payload={"age_s": age_s, "expected_cadence_s": expected_cadence_s})

    NEW read function read_underlying_apr_max_ts (place in a new module python/src/boros_brain/data/underlying_apr_reader.py — keeps the breaker module slim):
      def read_underlying_apr_max_ts(parquet_root: Path, exchange: str, symbol: str) -> int | None:
          import duckdb
          partition_path = parquet_root / "underlying_apr" / f"exchange={exchange}" / f"symbol={symbol}"
          if not partition_path.exists():
              return None
          glob = str(partition_path / "*.parquet")
          conn = duckdb.connect(":memory:")
          try:
              row = conn.execute(f"SELECT MAX(snapshot_ts) FROM read_parquet('{glob}')").fetchone()
              return int(row[0]) if row and row[0] is not None else None
          finally:
              conn.close()

    Tests (parametrized):
      @parametrize (exchange, age_s, expected_fire):
        ("binance", 17_280, False)   # 0.6 x 28800
        ("binance", 60_000, True)    # 2.08 x 28800
        ("hyperliquid", 121, True)   # 2.02 x 60
        ("hyperliquid", 119, False)  # 1.98 x 60
      Use seed_underlying_apr_parquet fixture to write a row with snapshot_ts=current_chain_ts-age_s under the appropriate partition.
  </behavior>
  <action>
1. Create python/src/boros_brain/data/underlying_apr_reader.py with the read_underlying_apr_max_ts function. Module docstring cites [[underlying-apr-cadence-by-exchange]] and SAFE-09.

2. Create python/src/boros_brain/decision/breakers/underlying_stale.py per <behavior>. Module docstring cites [[breaker-underlying-feed-stale]] and SAFE-09 (A7 absorbed). Imports include `from ...data.underlying_apr_reader import read_underlying_apr_max_ts`.

3. Update python/tests/test_breaker_underlying_stale.py — remove importorskip; implement parametrized test per <behavior>. The seed_underlying_apr_parquet fixture must:
   - Accept (last_ts, exchange, symbol, parquet_root) — write a parquet file under parquet_root/underlying_apr/exchange={exchange}/symbol={symbol}/snapshot.parquet with at least one row {snapshot_ts: last_ts, rate: 0.0001}.
   - Use polars (already a project dep) or pyarrow if simpler — consult conftest.py for the fixture body.

   Note: the fixture from Plan 04-01 was specified to use polars; verify the implementation matches (polars.DataFrame(...).write_parquet(path)).

   The test passes `parquet_root=tmp_path` to the breaker.check.

Self-verification: cd python ; uv run pytest tests/test_breaker_underlying_stale.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_underlying_stale.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breakers/underlying_stale.py contains "class UnderlyingStaleBreaker(Breaker)"
    - File python/src/boros_brain/decision/breakers/underlying_stale.py contains "HALT_AND_ALERT"
    - File python/src/boros_brain/decision/breakers/underlying_stale.py contains "expected_cadence_s_per_exchange"
    - File python/src/boros_brain/data/underlying_apr_reader.py contains "def read_underlying_apr_max_ts"
    - File python/src/boros_brain/data/underlying_apr_reader.py contains "duckdb.connect"
    - cd python ; uv run pytest tests/test_breaker_underlying_stale.py -x exits 0
    - python3 scripts/no_time_time_lint.py exits 0
  </acceptance_criteria>
  <done>SAFE-09 implemented; HALT_AND_ALERT signal encoded; per-exchange cadence honored.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Wiki write-back — 4 breaker pages + supersede A2/A7 pitfall pages</name>
  <files>
    python/tests/test_breaker_competition.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (LLM Wiki Pages to Write-Back, lines 1532-1557; PROTO-05 supersedence at line 1556)
  </read_first>
  <behavior>
    File four wiki pages:
    - breaker-competition-collapse.md (SAFE-06)
    - breaker-maturity-migration.md (SAFE-07)
    - breaker-side-budget-rebalance.md (SAFE-08; SUPERSEDES A2 portion of [[live-e-liq-polling-data-11]])
    - breaker-underlying-feed-stale.md (SAFE-09; A7 absorbed)
    - underlying-apr-cadence-by-exchange.md (cadence reference)

    Plus PROTO-05 supersedences:
    - Append to [[live-e-liq-polling-data-11]] (existing): "Status: Current — A2 portion superseded by [[breaker-side-budget-rebalance]]"
    - Update [[circuit-breakers-v05]] index to mark all 10 breakers as Current.

    Touch test_breaker_competition.py module docstring with cross-references.

    Note: architecture.yml + ARCHITECTURE.md edits for the 4 breakers, the new underlying_apr_reader module, and the new competition_tracker -> competition_history WRITES edge are deferred to plan 04-06's atomic Phase-4 architecture delta task.
  </behavior>
  <action>
1. File breaker-competition-collapse.md: Status Current; SAFE-06 spec; default drop_threshold=0.5; Pitfall #3 first-day guard. Cite [[circuit-breakers-v05]].

2. File breaker-maturity-migration.md: Status Current; SAFE-07 spec; migration_cost = entrance_fee + 2 x cancel_cost; ROLL_POSITION semantics (operator confirms; v0.5 does NOT auto-roll). Cite [[boros-fee-schedule]] and [[circuit-breakers-v05]].

3. File breaker-side-budget-rebalance.md: Status Current; SAFE-08 spec; drift_threshold=0.30; A2 absorbed. Cite [[circuit-breakers-v05]].

4. Update /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/live-e-liq-polling-data-11.md (existing): change Status field to "Status: Current — A2 portion superseded by [[breaker-side-budget-rebalance]]" and add a one-line PROTO-05 entry: "2026-04-25 Plan 04-05: A2 (per-side budget rebalance) absorbed by SAFE-08 breaker." (PROTO-05 supersedence in same commit.)

5. File breaker-underlying-feed-stale.md: Status Current; SAFE-09 spec; per-exchange cadence dict; A7 absorbed. Cite [[underlying-apr-cadence-by-exchange]] and [[circuit-breakers-v05]].

6. File underlying-apr-cadence-by-exchange.md: Status Current; cadence table by exchange (binance=28800s, okx=3600s, hyperliquid=60s); justification per RESEARCH §SAFE-09 line 740. Cite [[breaker-underlying-feed-stale]].

7. Update /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/circuit-breakers-v05.md to mark all 10 breakers as Current (the Plan 04-04 version had SAFE-06..09 marked TBD).

8. Append to test_breaker_competition.py module docstring: "See [[breaker-competition-collapse]] and [[circuit-breakers-v05]]."

Self-verification: 5 new wiki pages + 1 update + 1 supersedence.
  </action>
  <verify>
    <automated>test -f "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-competition-collapse.md"</automated>
  </verify>
  <acceptance_criteria>
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-competition-collapse.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-maturity-migration.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-side-budget-rebalance.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-underlying-feed-stale.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/underlying-apr-cadence-by-exchange.md" exists
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-competition-collapse.md"
    - grep -q "superseded by .breaker-side-budget-rebalance." "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/live-e-liq-polling-data-11.md"
    - grep -q "breaker-competition-collapse\|circuit-breakers-v05" python/tests/test_breaker_competition.py
  </acceptance_criteria>
  <done>5 wiki pages filed; A2 supersedence atomic in same commit; circuit-breakers-v05 index updated to all-Current.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| state.competition_history -> SAFE-06 | First-day operator-pause noise mitigated by len(rows) >= 2 guard. |
| state.market_reward_calibration -> SAFE-08 | Operator-supplied calibration; SAFE-08 reads the operator's own table. |
| parquet.underlying_apr -> SAFE-09 | Ingested by Phase 1 underlying_apr ingester; 2x cadence threshold tolerates a single missed snapshot. |
| state.decisions -> SAFE-07 | r_me_per_epoch_pendle written by Plan 04-06 engine loop; SAFE-07 returns "no_decision_history_yet" until first decision lands. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-05-01 | T (Tampering) | First-day operator-pause noise (Pitfall #3) | mitigate | Each of SAFE-06 / SAFE-08 explicitly checks `len(rows) < 2` and returns tripped=False with reason="insufficient_*" — false-fire on day 1 is impossible. Tests cover this edge. |
| T-04-05-02 | I (Information disclosure) | competition_history persistence | accept | The CompetitionTracker now persists q_me + sigma_others on every cycle. q_me is the operator's own commitment (no privacy leak; the operator already controls it); sigma_others is computed from the public order book. |
| T-04-05-03 | T (Tampering) | side_budget timestamp parsing | mitigate | calibrated_at_utc is ISO8601 with explicit timezone; the breaker uses datetime.fromisoformat with `Z` -> `+00:00` substitution to handle both Pendle docs format ("2026-04-25T00:00:00Z") and Python's datetime ("2026-04-25T00:00:00+00:00"). |
| T-04-05-04 | D (Denial of service) | DuckDB read of underlying_apr | mitigate | The function opens a fresh in-memory DuckDB conn per call (low overhead — ~1ms per call); the parquet path glob is bounded to one exchange/symbol partition. The breaker's overall budget is 200ms (coordinator timeout in Plan 04-06). |
| T-04-05-05 | E (Elevation of privilege) | competition_tracker NEW write path | mitigate | The new insert_competition_row call goes through the existing single-writer module (state/writers/competition_history.py); sqlite_writer_lint OWNER_MAP already includes competition_history (added in Plan 04-02). The reward_model module is the legitimate upstream caller — no lint exception needed because reward_model imports the writer function (does not write the SQL itself). |
| T-04-05-06 | R (Repudiation) | Maturity ROLL_POSITION decision | mitigate | The signal is persisted to state.breaker_events by the coordinator (Plan 04-06); the operator manually confirms the roll by editing BotConfig.markets[0].market_id (v0.5 has no auto-roll). The wiki page [[breaker-maturity-migration]] documents the operator workflow. |
</threat_model>

<verification>
After all tasks complete, run:

```
cd python ; uv run pytest tests/test_breaker_competition.py tests/test_breaker_maturity.py tests/test_breaker_side_budget.py tests/test_breaker_underlying_stale.py tests/test_competition_tracker.py -x

python3 scripts/no_threshold_dials_lint.py
python3 scripts/no_time_time_lint.py
python3 scripts/sqlite_writer_lint.py --root .
```

All MUST exit 0.

Note: `python3 scripts/architecture_lint.py` is NOT run after this plan because this plan does NOT touch docs/architecture.yml or docs/ARCHITECTURE.md. The architecture nodes/edges for these 4 breakers + the underlying_apr_reader helper + the new competition_tracker -> competition_history WRITES edge land atomically in plan 04-06's final delta task; architecture_lint is the gate at the end of 04-06.
</verification>

<success_criteria>
- [ ] 4 breaker source modules exist; each subclasses Breaker ABC.
- [ ] CompetitionTracker now persists competition_history rows on every cycle.
- [ ] All 4 corresponding test files PASS plus existing test_competition_tracker still PASSES.
- [ ] First-day operator-pause noise (Pitfall #3) mitigated for SAFE-06 and SAFE-08.
- [ ] 5 wiki pages filed + 1 supersedence + 1 index update.
- [ ] All non-arch lint scripts exit 0 (architecture_lint deferred to 04-06).
- [ ] Architecture delta deferred to 04-06: this plan does NOT modify docs/architecture.yml or docs/ARCHITECTURE.md.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-05-SUMMARY.md` documenting:
- 4 breaker modules implemented
- CompetitionTracker SQLite write added
- Test coverage by requirement (SAFE-06..09)
- 5 wiki pages filed + supersedence
- Architecture delta deferred to plan 04-06 (explicit note: this plan owns NO architecture-file edits)
</output>
