---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 02
type: execute
wave: 1
depends_on: [01]
autonomous: true
requirements: [DECIDE-03, DECIDE-04, SAFE-01, SAFE-02, SAFE-05, SAFE-06, SAFE-07, SAFE-08, SAFE-09, SAFE-10]
files_modified:
  - python/src/boros_brain/config/schema.py
  - python/src/boros_brain/decision/__init__.py
  - python/src/boros_brain/decision/config.py
  - python/src/boros_brain/decision/schemas.py
  - python/src/boros_brain/decision/breakers/__init__.py
  - python/src/boros_brain/decision/breakers/base.py
  - python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
  - python/src/boros_brain/state/writers/margin_history.py
  - python/src/boros_brain/state/writers/breaker_events.py
  - python/src/boros_brain/state/writers/predeploy_gate_records.py
  - python/src/boros_brain/data/poller/margin_poller.py
  - python/src/boros_brain/data/rest_client.py
  - python/src/boros_brain/pricing/config.py
  - scripts/sqlite_writer_lint.py
  - docs/architecture.yml
  - docs/ARCHITECTURE.md

user_setup: []

must_haves:
  truths:
    - "BotConfig has new top-level field decision (DecisionEngineConfig) with ~25 leaves; schema round-trip test passes."
    - "Alembic migration 0007 creates 4 net-new tables (margin_history, breaker_events, predeploy_gate_records, defensive competition_history) and adds tx_receipts.event_type column."
    - "Three new state writers exist (margin_history, breaker_events, predeploy_gate_records) and pass single-writer-per-table lint."
    - "MarginPoller exists at 1 Hz cadence and writes to margin_history mirroring ELiqPoller's degraded-mode pattern."
    - "MarketCalibration extended with max_update_delay_s, underlying_exchange, underlying_symbol fields with safe defaults."
    - "Breaker base ABC + BreakerSignal land — every Wave-2 breaker subclasses Breaker."
    - "decision.schemas.EvaluateInput / EvaluateOutput exist as Pydantic StrictBase models — engine 04-03 only fills the function body."
  artifacts:
    - path: "python/src/boros_brain/decision/__init__.py"
      provides: "decision package init"
      min_lines: 5
    - path: "python/src/boros_brain/decision/config.py"
      provides: "DecisionEngineConfig + 10 BreakerConfig sub-models (PROTO-04 SSoT for ~25 new leaves)"
      contains: "class DecisionEngineConfig"
    - path: "python/src/boros_brain/decision/schemas.py"
      provides: "EvaluateInput, EvaluateOutput Pydantic models"
      contains: "class EvaluateInput"
    - path: "python/src/boros_brain/decision/breakers/__init__.py"
      provides: "breakers package init"
    - path: "python/src/boros_brain/decision/breakers/base.py"
      provides: "Breaker ABC + BreakerSignal"
      contains: "class Breaker(ABC)"
    - path: "python/src/boros_brain/state/writers/margin_history.py"
      provides: "Single writer for margin_history (PROTO-02)"
      contains: "def insert_margin_snapshot"
    - path: "python/src/boros_brain/state/writers/breaker_events.py"
      provides: "Single writer for breaker_events audit table"
      contains: "def insert_breaker_event"
    - path: "python/src/boros_brain/state/writers/predeploy_gate_records.py"
      provides: "Single writer for predeploy_gate_records (Pitfall #8)"
      contains: "def insert_predeploy_gate_record"
    - path: "python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py"
      provides: "Migration 0007 creating 4 tables + event_type column"
      contains: "0007_phase4_tables"
    - path: "python/src/boros_brain/data/poller/margin_poller.py"
      provides: "1 Hz POST /accounts/get-net-margin -> margin_history"
      contains: "class MarginPoller"
    - path: "scripts/sqlite_writer_lint.py"
      provides: "OWNER_MAP extended with new tables"
      contains: "margin_history"
  key_links:
    - from: "python/src/boros_brain/decision/config.py"
      to: "python/src/boros_brain/config/schema.py"
      via: "BotConfig.decision field wired"
      pattern: "decision: DecisionEngineConfig"
    - from: "python/src/boros_brain/state/writers/margin_history.py"
      to: "python/src/boros_brain/state/db.py"
      via: "open_connection import"
      pattern: "from boros_brain.state.db import open_connection"
    - from: "python/src/boros_brain/data/poller/margin_poller.py"
      to: "python/src/boros_brain/state/writers/margin_history.py"
      via: "insert_margin_snapshot calls"
      pattern: "insert_margin_snapshot"
    - from: "scripts/sqlite_writer_lint.py"
      to: "python/src/boros_brain/state/writers"
      via: "OWNER_MAP"
      pattern: "margin_history"
---

<objective>
Wave 1 lands the foundation that every Wave 2 plan depends on: BotConfig schema delta, alembic migration for 4 new tables, three new state writers, the MarginPoller, the Breaker ABC and BreakerSignal Pydantic, EvaluateInput/Output schemas, and OWNER_MAP / lint extensions. After this plan, every Phase-4 test from 04-01 advances one step (imports succeed for schemas/writers/breaker base) but breaker .check and engine.evaluate function bodies are still RED. The full architecture.yml + Mermaid Phase-4 delta lands atomically in Plan 04-06; this plan registers only the foundation nodes (writers, migration, base classes, poller).

Purpose: Lock CONTRACTS so 04-03 / 04-04 / 04-05 can run in parallel without coordination overhead. The ABC and Pydantic shapes lock function signatures; the migration locks table schemas; the writers lock single-writer ownership.

Output: BotConfig schema extended in-place; 4 new tables (alembic 0007); 3 new writers; 1 poller; ABC + Pydantic shapes; lint extensions; foundation arch nodes registered.
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
@CLAUDE.md
@python/src/boros_brain/config/schema.py
@python/src/boros_brain/fill_model/config.py
@python/src/boros_brain/loss_model/schemas.py
@python/src/boros_brain/state/writers/competition_history.py
@python/src/boros_brain/state/writers/clo_history.py
@python/src/boros_brain/state/writers/decisions.py
@python/src/boros_brain/state/writers/run_manifests.py
@python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py
@python/src/boros_brain/data/poller/e_liq_poller.py
@scripts/sqlite_writer_lint.py
@scripts/no_time_time_lint.py
@docs/architecture.yml

<interfaces>
Existing (we extend, do NOT replace):

From python/src/boros_brain/config/schema.py:
  class StrategyConfig(StrictBase): voluntary_cancel_forfeits_accumulated: bool = False
  class ExecutionConfig(StrictBase): cancel_latency_budget_s, agent_wallet_gas_*, ...
  class DataConfig(StrictBase): markets_poll_interval_s, e_liq_poll_interval_s, chain_time_cache_ttl_s, rpc_url_arbitrum, boros_rest_base
  class MarketCalibration(StrictBase): market_id, scale, s, clo_lower_thresh, clo_upper_thresh, fIndex_oracle_address, maturity_ts, reward_calibration

From python/src/boros_brain/pricing/config.py:
  class PricingConfig(StrictBase): pendle_price_usd: float (LOCKED-D-01 operator-supplied, no default)

NEW Pydantic shapes to create (decision/schemas.py + decision/breakers/base.py):
  class EvaluateInput(StrictBase) — 16 fields per RESEARCH §DECIDE-01
  class EvaluateOutput(StrictBase) — 12 fields per RESEARCH §DECIDE-01
  class BreakerSignal(BaseModel) — frozen+forbid; tripped, reason, payload, kill_command_kind
  class Breaker(ABC) — name + abstract async check(*, sqlite_path, w3, parquet_root, config, current_chain_ts) -> BreakerSignal

NEW DecisionEngineConfig (decision/config.py — ~25 leaves):
  Top-level: cancel_cost_ewma_alpha=0.1, cancel_cost_ttl_s=60.0, cancel_cost_block_window=100,
             p_purge_default=0.0, decision_loop_interval_s=1.0, breakers (sub-model)
  Per-breaker (10 sub-models): margin/oracle_stale/clo_removal/clo_shift/fill_rate/competition/maturity/side_budget/underlying_stale/loss_fit_degraded

NEW writers (state/writers/*):
  insert_margin_snapshot(conn, *, chain_ts, market_id, net_margin_usd, maintenance_margin_usd, available_collateral_usd, run_id) -> None
  read_margin_history(sqlite_path, *, market_id=None, since_ts=None) -> list[dict]
  insert_breaker_event(conn, *, kind, breaker_name, reason, chain_ts, run_id, payload_json=None) -> None
  insert_predeploy_gate_record(conn, *, gate_passed, git_sha, git_dirty, config_hash, wiki_page_path, run_id, chain_ts) -> None
  get_latest_predeploy_gate_record(sqlite_path) -> dict | None

NEW poller:
  class MarginPoller(config, conn, rest, run_id, event_pub)
  async def run_one_cycle()
  async def loop()
  async def run_margin_poller_loop(config, run_id, conn, rest, event_pub)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Pydantic schemas and BotConfig extensions</name>
  <files>
    python/src/boros_brain/decision/__init__.py,
    python/src/boros_brain/decision/config.py,
    python/src/boros_brain/decision/schemas.py,
    python/src/boros_brain/decision/breakers/__init__.py,
    python/src/boros_brain/decision/breakers/base.py,
    python/src/boros_brain/config/schema.py,
    python/src/boros_brain/pricing/config.py
  </files>
  <read_first>
    - python/src/boros_brain/config/schema.py (lines 1-200, BotConfig structure; we EXTEND, not replace)
    - python/src/boros_brain/fill_model/config.py (canonical Pydantic sub-model with Field bounds and StrictBase pattern, lines 1-100)
    - python/src/boros_brain/loss_model/schemas.py (lines 1-100, Pydantic StrictBase + Literal pattern + dataclass)
    - python/src/boros_brain/reward_model/schemas.py (lines 1-50, local StrictBase to avoid circular imports)
    - python/src/boros_brain/pricing/config.py (current PricingConfig — we ADD eth_price_usd field)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (BotConfig Knob Delta lines 1093-1149; DECIDE-01 EvaluateInput/Output lines 281-313; Code Examples Breaker ABC lines 1485-1513)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (schemas.py pattern lines 153-216; config.py pattern lines 219-265; base.py pattern lines 343-381)
  </read_first>
  <behavior>
    - decision/__init__.py: package marker docstring listing the future sub-modules.
    - decision/breakers/__init__.py: package marker.
    - decision/schemas.py: local StrictBase + EvaluateInput (16 fields) + EvaluateOutput (12 fields) per <interfaces>.
    - decision/breakers/base.py: ABC Breaker + Pydantic BreakerSignal with kill_command_kind Literal of 10 strings.
    - decision/config.py: 10 per-breaker StrictBase classes + BreakerConfig + DecisionEngineConfig with EXACT defaults from RESEARCH §BotConfig Knob Delta.
    - pricing/config.py: add eth_price_usd: float = Field(..., gt=0.0) and eth_price_usd_calibrated_at_utc: str.
    - config/schema.py: extend BotConfig with decision: DecisionEngineConfig; extend ExecutionConfig with cancel_gas_units_estimate=200_000 and entrance_fee_pendle=0.0; extend MarketCalibration with max_update_delay_s=600, underlying_exchange="binance", underlying_symbol="".

    Default values for the 10 per-breaker config classes (per RESEARCH lines 1129-1148):
      MarginBreakerConfig: window_s=30.0, min_samples=10, time_to_mm_threshold_s=30.0, min_re_arm_s=60.0
      OracleStaleBreakerConfig: fraction_of_max=0.7, min_re_arm_s=60.0
      CloRemovalBreakerConfig: min_re_arm_s=60.0
      CloShiftBreakerConfig: n_ticks=5, min_re_arm_s=60.0
      FillRateBreakerConfig: k_fills_per_hour=3, min_re_arm_s=600.0
      CompetitionBreakerConfig: drop_threshold=0.5, min_re_arm_s=60.0
      MaturityBreakerConfig: migration_cost_buffer_pct=1.0, min_re_arm_s=60.0
      SideBudgetBreakerConfig: drift_threshold=0.30, min_re_arm_s=60.0
      UnderlyingStaleBreakerConfig: expected_cadence_s_per_exchange={"binance":28800.0,"okx":3600.0,"hyperliquid":60.0}, min_re_arm_s=60.0
      LossFitDegradedBreakerConfig: min_re_arm_s=60.0
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/__init__.py with module docstring listing the sub-modules and a comment that the engine, gas_history, breaker_coordinator, predeploy_gate, cli land in later plans (04-03, 04-06). Cite [[ev-cancel-rule]] and [[circuit-breakers-v05]].

2. Create python/src/boros_brain/decision/breakers/__init__.py with one-line docstring and `__all__ = []` (modules added in 04-04 / 04-05).

3. Create python/src/boros_brain/decision/schemas.py — copy structure verbatim from PATTERNS.md §schemas.py lines 153-216. Use:
   - `from __future__ import annotations`
   - `from typing import Any, Literal`
   - `from pydantic import BaseModel, ConfigDict`
   - Local `class StrictBase(BaseModel): model_config = ConfigDict(extra="forbid", frozen=True)` (avoid circular import)
   - `class EvaluateInput(StrictBase):` with 16 fields exactly per <interfaces>
   - `class EvaluateOutput(StrictBase):` with 12 fields exactly per <interfaces>
   - `__all__ = ["StrictBase", "EvaluateInput", "EvaluateOutput"]`

4. Create python/src/boros_brain/decision/breakers/base.py — copy verbatim from PATTERNS.md lines 350-377 (the canonical body from RESEARCH §Code Examples). Add structlog import and `log = structlog.get_logger(__name__)`. Add `__all__ = ["Breaker", "BreakerSignal"]`. Use `from __future__ import annotations` to avoid the BotConfig forward-reference. The abstract check signature is exactly: `async def check(self, *, sqlite_path: Path, w3, parquet_root: Path, config, current_chain_ts: int) -> BreakerSignal: ...`

5. Create python/src/boros_brain/decision/config.py — define 10 per-breaker StrictBase classes with the exact defaults from <behavior>, then BreakerConfig with `default_factory=...` for each, then DecisionEngineConfig with the 5 top-level knobs and `breakers: BreakerConfig = Field(default_factory=BreakerConfig)`. EVERY numeric Field MUST have ge and le bounds. Re-declare local StrictBase. The expected_cadence_s_per_exchange default uses `Field(default_factory=lambda: dict(binance=28800.0, okx=3600.0, hyperliquid=60.0))`.

6. Update python/src/boros_brain/pricing/config.py — add field `eth_price_usd: float = Field(..., gt=0.0)` with docstring citing [[gas-history-ewma-cancel-cost]] and Pitfall #5 (operator-calibrated, daily refresh, mirrors pendle_price_usd LOCKED-D-01). Also add `eth_price_usd_calibrated_at_utc: str = Field(...)` (ISO8601, mandatory) for staleness checks.

7. Update python/src/boros_brain/config/schema.py:
   - Add `from .decision.config import DecisionEngineConfig` at top (decision/config.py has no reverse-import so this is safe).
   - On BotConfig, after the `sizer` field append: `decision: DecisionEngineConfig = Field(default_factory=DecisionEngineConfig)  # type: ignore`.
   - On ExecutionConfig append: `cancel_gas_units_estimate: int = Field(200_000, ge=10_000, le=2_000_000)` and `entrance_fee_pendle: float = Field(0.0, ge=0.0)`.
   - On MarketCalibration append: `max_update_delay_s: int = Field(600, ge=60, le=86400)`; `underlying_exchange: Literal["binance","okx","hyperliquid"] = "binance"`; `underlying_symbol: str = Field("", max_length=64)`.

Self-verification: `cd python ; uv run python -c "from boros_brain.config.schema import BotConfig; from boros_brain.decision.config import DecisionEngineConfig; cfg = DecisionEngineConfig(); assert cfg.breakers.margin.window_s == 30.0; print('OK')"` exits 0.

Note: strategy/v0.5-default.yaml may need a NEW pricing.eth_price_usd entry — Task 6 of this plan adds that.
  </action>
  <verify>
    <automated>cd python ; uv run python -c "from boros_brain.config.schema import BotConfig; from boros_brain.decision.config import DecisionEngineConfig; from boros_brain.decision.schemas import EvaluateInput, EvaluateOutput; from boros_brain.decision.breakers.base import Breaker, BreakerSignal; cfg = DecisionEngineConfig(); assert cfg.breakers.margin.window_s == 30.0; assert cfg.breakers.oracle_stale.fraction_of_max == 0.7; assert cfg.breakers.fill_rate.k_fills_per_hour == 3; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/__init__.py exists
    - File python/src/boros_brain/decision/config.py contains "class DecisionEngineConfig"
    - File python/src/boros_brain/decision/config.py contains "class MarginBreakerConfig"
    - File python/src/boros_brain/decision/config.py contains "window_s: float = Field(30.0"
    - File python/src/boros_brain/decision/config.py contains "fraction_of_max: float = Field(0.7"
    - File python/src/boros_brain/decision/config.py contains "n_ticks: int = Field(5"
    - File python/src/boros_brain/decision/config.py contains "k_fills_per_hour: int = Field(3"
    - File python/src/boros_brain/decision/config.py contains "drop_threshold: float = Field(0.5"
    - File python/src/boros_brain/decision/config.py contains "drift_threshold: float = Field(0.30"
    - File python/src/boros_brain/decision/config.py contains "expected_cadence_s_per_exchange"
    - File python/src/boros_brain/decision/schemas.py contains "class EvaluateInput"
    - File python/src/boros_brain/decision/schemas.py contains 'voluntary_cancel_branch: Literal'
    - File python/src/boros_brain/decision/breakers/base.py contains "class Breaker(ABC)"
    - File python/src/boros_brain/decision/breakers/base.py contains "class BreakerSignal"
    - File python/src/boros_brain/decision/breakers/base.py contains "kill_command_kind: Literal"
    - grep -q "decision: DecisionEngineConfig" python/src/boros_brain/config/schema.py
    - grep -q "cancel_gas_units_estimate" python/src/boros_brain/config/schema.py
    - grep -q "max_update_delay_s" python/src/boros_brain/config/schema.py
    - grep -q "underlying_exchange" python/src/boros_brain/config/schema.py
    - grep -q "eth_price_usd" python/src/boros_brain/pricing/config.py
    - cd python ; uv run python -c "from boros_brain.decision.config import DecisionEngineConfig; cfg = DecisionEngineConfig(); assert cfg.breakers.margin.window_s == 30.0" exits 0
  </acceptance_criteria>
  <done>BotConfig extended with DecisionEngineConfig (~25 leaves) plus ExecutionConfig and MarketCalibration fields plus PricingConfig.eth_price_usd; Breaker ABC and Pydantic shapes ready for Wave 2.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Alembic migration 0007 — 4 new tables and tx_receipts.event_type column</name>
  <files>
    python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
  </files>
  <read_first>
    - python/src/boros_brain/state/migrations/versions/0006_market_reward_calibration.py (verbatim structural model — _has_table / _has_index / op.create_table)
    - python/src/boros_brain/state/migrations/versions/0005_competition_history.py (CHECK constraint pattern)
    - python/src/boros_brain/state/migrations/versions/0001_initial_8_tables.py (verify whether tx_receipts.event_type already exists)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (Migrations section lines 757-820)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-01 margin_history schema lines 488-491; SAFE-06 competition_history lines 644-651; SAFE-05 tx_receipts.event_type lines 619-620)
  </read_first>
  <behavior>
    Migration creates four tables idempotently and adds event_type column to tx_receipts if absent.

    margin_history columns: id PK auto, chain_ts INTEGER NOT NULL, market_id TEXT NOT NULL, net_margin_usd REAL NOT NULL, maintenance_margin_usd REAL NOT NULL, available_collateral_usd REAL NOT NULL, run_id TEXT NOT NULL.
    Index ix_margin_history_market_chain_ts on (market_id, chain_ts DESC).

    breaker_events columns: id PK auto, kind TEXT NOT NULL CHECK kind IN ('kill_emitted','suppression','rearmed'), breaker_name TEXT NOT NULL, reason TEXT NOT NULL, chain_ts INTEGER NOT NULL, run_id TEXT NOT NULL, payload_json TEXT NULL.
    Indexes: ix_breaker_events_breaker_chain_ts on (breaker_name, chain_ts DESC); ix_breaker_events_kind on (kind).

    predeploy_gate_records columns: id PK auto, gate_passed INTEGER NOT NULL CHECK 0,1, git_sha TEXT NOT NULL, git_dirty INTEGER NOT NULL CHECK 0,1, config_hash TEXT NOT NULL, wiki_page_path TEXT NOT NULL, run_id TEXT NOT NULL, chain_ts INTEGER NOT NULL.
    Index ix_predeploy_gate_records_chain_ts on (chain_ts DESC).

    Defensive competition_history creation in case 0005 was skipped (e.g. test fixtures applying head only).

    tx_receipts.event_type — _has_column guard; if missing, op.add_column with nullable=False server_default='unknown' so existing rows stay valid.
  </behavior>
  <action>
1. Read python/src/boros_brain/state/migrations/versions/0001_initial_8_tables.py to confirm whether tx_receipts has event_type already. Document the finding in the migration docstring.

2. Create python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py — copy verbatim header pattern from 0006_market_reward_calibration.py (revision string, down_revision, _has_table, _has_index helpers). Add a third helper:

```
def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in sa_inspect(bind).get_columns(table)]
```

3. Body of upgrade(): four `if not _has_table(...)` blocks (margin_history, breaker_events, predeploy_gate_records, defensive competition_history), each followed by index creates with `if not _has_index(...)` guard. Use the EXACT column types and CHECK constraints from <behavior>.

4. After table creation, add the column-add block:

```
if _has_table("tx_receipts") and not _has_column("tx_receipts", "event_type"):
    op.add_column(
        "tx_receipts",
        sa.Column("event_type", sa.Text(), nullable=False, server_default="unknown"),
    )
```

5. downgrade() body: just `pass` with comment "No downgrade — Phase 4 tables stay forward-compatible."

6. Run apply_alembic_migration.py against a fresh tmp DB to verify the migration applies cleanly.

Self-verification: existing tests in test_sqlite_migrations.py still pass.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_sqlite_migrations.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py exists
    - grep -q 'revision = "0007_phase4_tables"' python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - grep -q 'down_revision = "0006_market_reward_calibration"' python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - grep -q '"margin_history"' python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - grep -q '"breaker_events"' python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - grep -q '"predeploy_gate_records"' python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - grep -q "kill_emitted" python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - grep -q "event_type" python/src/boros_brain/state/migrations/versions/0007_phase4_tables.py
    - cd python ; uv run pytest tests/test_sqlite_migrations.py -x exits 0
  </acceptance_criteria>
  <done>Migration 0007 lands; existing migration tests still pass; 4 tables created plus event_type column added.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: State writers — margin_history, breaker_events, predeploy_gate_records (PROTO-02)</name>
  <files>
    python/src/boros_brain/state/writers/margin_history.py,
    python/src/boros_brain/state/writers/breaker_events.py,
    python/src/boros_brain/state/writers/predeploy_gate_records.py,
    scripts/sqlite_writer_lint.py
  </files>
  <read_first>
    - python/src/boros_brain/state/writers/competition_history.py (lines 1-90, verbatim model for insert + read_latest pair)
    - python/src/boros_brain/state/writers/decisions.py (slim INSERT-only writer pattern)
    - python/src/boros_brain/state/writers/run_manifests.py (config_hash + git_sha pattern)
    - python/src/boros_brain/state/db.py (open_connection contract)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (State writers lines 633-755)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-01 margin_history schema lines 488-491; SAFE-10 breaker_events lines 1273-1281)
    - scripts/sqlite_writer_lint.py (current OWNER_MAP lines 35-50; we EXTEND not replace)
  </read_first>
  <behavior>
    margin_history.py exports:
      insert_margin_snapshot(conn, *, chain_ts: int, market_id: str, net_margin_usd: float, maintenance_margin_usd: float, available_collateral_usd: float, run_id: str) -> None  (caller owns transaction lifecycle, NO conn.commit inside)
      read_margin_history(sqlite_path: Path, *, market_id: str|None=None, since_ts: int|None=None) -> list[dict]  (self-managing connection)

    breaker_events.py exports:
      insert_breaker_event(conn, *, kind: Literal["kill_emitted","suppression","rearmed"], breaker_name: str, reason: str, chain_ts: int, run_id: str, payload_json: str|None=None) -> None  (validates kind via Python ValueError before SQL CHECK fires)

    predeploy_gate_records.py exports:
      insert_predeploy_gate_record(conn, *, gate_passed: bool, git_sha: str, git_dirty: bool, config_hash: str, wiki_page_path: str, run_id: str, chain_ts: int) -> None
      get_latest_predeploy_gate_record(sqlite_path: Path) -> dict | None

    sqlite_writer_lint.py: extend OWNER_MAP with margin_history, breaker_events, predeploy_gate_records, competition_history, market_reward_calibration, loss_grid_artifacts, fill_model_fits if any are missing.
  </behavior>
  <action>
1. Create python/src/boros_brain/state/writers/margin_history.py — copy structure verbatim from competition_history.py lines 1-90 then replace the table name and column set. Module docstring cites [[boros-rest-api-margin-endpoint]] and PROTO-02 single-writer discipline. Both functions match <behavior>. Do NOT call conn.commit() inside insert_margin_snapshot — caller owns the transaction.

2. Create python/src/boros_brain/state/writers/breaker_events.py — copy structure from decisions.py (slim INSERT-only). Validate kind against the literal set ALLOWED = frozenset({"kill_emitted","suppression","rearmed"}) via Python ValueError BEFORE the SQL CHECK fires (matches competition_history.py lines 33-36). Module docstring cites [[breaker-coordinator-kill-mutex]] and Pitfall #2 (no in-memory log).

3. Create python/src/boros_brain/state/writers/predeploy_gate_records.py — copy structure from run_manifests.py for the config_hash + git_sha shape. The function body for insert_predeploy_gate_record converts bools to ints (1/0) before the INSERT. The get_latest_predeploy_gate_record helper opens its own connection via open_connection and returns a dict with bool-converted gate_passed and git_dirty.

4. Update scripts/sqlite_writer_lint.py — add the four new entries to OWNER_MAP between the existing entries:
   - "margin_history": "python/src/boros_brain/state/writers/margin_history.py"
   - "breaker_events": "python/src/boros_brain/state/writers/breaker_events.py"
   - "predeploy_gate_records": "python/src/boros_brain/state/writers/predeploy_gate_records.py"
   - "competition_history": "python/src/boros_brain/state/writers/competition_history.py"
   - "market_reward_calibration": "python/src/boros_brain/state/writers/market_reward_calibration.py"
   - "loss_grid_artifacts": "python/src/boros_brain/state/writers/loss_grid_artifacts.py"
   - "fill_model_fits": "python/src/boros_brain/state/writers/fill_model_fits.py"

   (Read the current file first; only ADD entries that are not already present. Some Phase-2/3 tables may have been registered already.)

5. Run python3 scripts/sqlite_writer_lint.py --root . — must exit 0. The lint walks python/src/ and ts/src/ looking for INSERT INTO <table> outside the owner; the new tables only have INSERTs in the new writer files we just created.

Self-verification: round-trip insert and read works against a migration-0007 DB.
  </action>
  <verify>
    <automated>python3 scripts/sqlite_writer_lint.py --root . ; cd python ; uv run pytest tests/test_sqlite_single_writer.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/state/writers/margin_history.py contains "def insert_margin_snapshot"
    - File python/src/boros_brain/state/writers/margin_history.py contains "def read_margin_history"
    - File python/src/boros_brain/state/writers/breaker_events.py contains "def insert_breaker_event"
    - File python/src/boros_brain/state/writers/breaker_events.py contains "kill_emitted"
    - File python/src/boros_brain/state/writers/predeploy_gate_records.py contains "def insert_predeploy_gate_record"
    - File python/src/boros_brain/state/writers/predeploy_gate_records.py contains "def get_latest_predeploy_gate_record"
    - grep -q "margin_history" scripts/sqlite_writer_lint.py
    - grep -q "breaker_events" scripts/sqlite_writer_lint.py
    - grep -q "predeploy_gate_records" scripts/sqlite_writer_lint.py
    - python3 scripts/sqlite_writer_lint.py --root . exits 0
    - cd python ; uv run pytest tests/test_sqlite_single_writer.py -x exits 0
  </acceptance_criteria>
  <done>Three new writers plus OWNER_MAP extension; sqlite_writer_lint passes; existing single-writer tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: MarginPoller — 1 Hz POST /accounts/get-net-margin to margin_history</name>
  <files>
    python/src/boros_brain/data/poller/margin_poller.py,
    python/src/boros_brain/data/rest_client.py,
    python/src/boros_brain/config/schema.py
  </files>
  <read_first>
    - python/src/boros_brain/data/poller/e_liq_poller.py (lines 1-180, verbatim structural model)
    - python/src/boros_brain/data/poller/markets_poller.py (alternate poller pattern)
    - python/src/boros_brain/data/rest_client.py (current — we ADD post_get_net_margin)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-01 lines 484-522)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (Pollers section lines 824-893)
    - python/src/boros_brain/state/writers/margin_history.py (just created — confirms insert_margin_snapshot signature)
    - scripts/no_time_time_lint.py (verify python/src/boros_brain/data/ already in PROTECTED_DIRS)
  </read_first>
  <behavior>
    MarginPoller mirrors ELiqPoller exactly:
    __init__(self, config, conn, rest, run_id, event_pub) -> None
    self.interval = config.data.margin_poll_interval_s (NEW knob, default 1.0)
    self.markets = [m.market_id for m in config.markets]
    self._fail_count: int = 0
    async def run_one_cycle() -> None: try fetch via _get_with_backoff; on Exception log error and possibly publish degraded event after 5 consecutive fails, return without writing rows; on success reset counter, fetch chain_ts via get_chain_time_cached, loop over markets calling insert_margin_snapshot then conn.commit().
    async def _get_with_backoff(): five retry windows [0.5, 1, 2, 4, 8] mirroring e_liq_poller.
    async def loop(): while True: run_one_cycle then asyncio.sleep(interval).
    Module-level run_margin_poller_loop(config, run_id, conn, rest, event_pub) thin wrapper.

    BorosRestClient: add async def post_get_net_margin(self, account_id: int) -> dict that calls POST /accounts/get-net-margin with body {"accountId": account_id} and returns parsed JSON.

    BotConfig.DataConfig: add margin_poll_interval_s: float = Field(1.0, ge=0.1, le=60.0) and boros_account_id: int = Field(0, ge=0).

    no_time_time_lint.py: VERIFY python/src/boros_brain/data/ already in PROTECTED_DIRS (it is — line 40 of the lint script). No change needed.
  </behavior>
  <action>
1. Read python/src/boros_brain/data/rest_client.py to learn the existing httpx wrapper shape.

2. Add to rest_client.py a new method on the existing BorosRestClient class:
   - Method name: post_get_net_margin
   - Args: self, account_id: int
   - Body: await self._client.post("/accounts/get-net-margin", json={"accountId": account_id}); resp.raise_for_status(); return resp.json()
   - Docstring cites [[boros-rest-api-margin-endpoint]] and SAFE-01

3. Add to BotConfig.DataConfig in python/src/boros_brain/config/schema.py:
   - margin_poll_interval_s: float = Field(1.0, ge=0.1, le=60.0) with docstring "SAFE-01 — 1 Hz cadence matching the decision loop."
   - boros_account_id: int = Field(0, ge=0) with docstring "Boros account_id for /accounts/get-net-margin. Operator-supplied. 0 = unset."

4. Create python/src/boros_brain/data/poller/margin_poller.py — copy verbatim from e_liq_poller.py and replace:
   - Class name ELiqPoller to MarginPoller
   - REST call get_markets() to post_get_net_margin(account_id=config.data.boros_account_id)
   - Writer insert_reward_budget_row to insert_margin_snapshot
   - Topic poller.e_liq.degraded to poller.margin.degraded
   - Field extraction m["liquidityRewardPerEpoch"] etc. to m["netMargin"] cast to float (USD-denominated per RESEARCH A1)
   - The result of post_get_net_margin is per-account aggregate not per-market — adapt the loop to write ONE row per market_id in self.markets (same margin values; per-market dimension is captured in margin_history.market_id for query convenience). RESEARCH.md A1 calls out this assumption.
   - Module docstring cites [[boros-rest-api-margin-endpoint]] and SAFE-01.

5. Verify scripts/no_time_time_lint.py PROTECTED_DIRS already contains "python/src/boros_brain/data/" (line 40 of the lint script). No change needed.

Self-verification: import path resolves and the new knob is reflected in DataConfig.
  </action>
  <verify>
    <automated>cd python ; uv run python -c "from boros_brain.data.poller.margin_poller import MarginPoller, run_margin_poller_loop; from boros_brain.config.schema import DataConfig; assert 'margin_poll_interval_s' in DataConfig.model_fields; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/data/poller/margin_poller.py contains "class MarginPoller"
    - File python/src/boros_brain/data/poller/margin_poller.py contains "insert_margin_snapshot"
    - File python/src/boros_brain/data/poller/margin_poller.py contains "poller.margin.degraded"
    - File python/src/boros_brain/data/poller/margin_poller.py contains "post_get_net_margin"
    - grep -q "post_get_net_margin" python/src/boros_brain/data/rest_client.py
    - grep -q "margin_poll_interval_s" python/src/boros_brain/config/schema.py
    - grep -q "boros_account_id" python/src/boros_brain/config/schema.py
    - cd python ; uv run python -c "from boros_brain.data.poller.margin_poller import MarginPoller; print('OK')" exits 0
    - python3 scripts/no_time_time_lint.py exits 0
  </acceptance_criteria>
  <done>MarginPoller exists with 1 Hz cadence and degraded-mode handling; BorosRestClient gets post_get_net_margin; DataConfig gets the two new knobs; no_time_time lint clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Architecture foundation nodes — atomic registration of writers, migration, ABC, poller</name>
  <files>
    docs/architecture.yml,
    docs/ARCHITECTURE.md
  </files>
  <read_first>
    - docs/architecture.yml (current end-of-nodes around line 1095, edges section starts ~1096)
    - docs/ARCHITECTURE.md (current Phase-3 Mermaid section)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (Architecture Manifest Delta lines 957-1090 — full Phase-4 delta; for THIS plan we register only the foundation nodes)
    - .planning/phases/03-loss-reward-share-models-sizing/03-04-SUMMARY.md (precedent: full architecture delta lands in LAST plan of phase; foundation-only delta in earlier plans is allowed for incremental wiring)
    - scripts/architecture_lint.py (must pass after the edit)
  </read_first>
  <behavior>
    Register ONLY the foundation Phase-4 nodes from this plan:
    - Module: brain.decision (package init)
    - Module: brain.decision.config
    - Module: brain.decision.schemas
    - Module: brain.decision.breakers (package init)
    - Module: brain.decision.breakers.base
    - Module: brain.state.writers.margin_history
    - Module: brain.state.writers.breaker_events
    - Module: brain.state.writers.predeploy_gate_records
    - Module: brain.data.poller.margin_poller
    - Storage: state.margin_history
    - Storage: state.breaker_events
    - Storage: state.predeploy_gate_records
    - External: external.boros.rest.get_net_margin (new endpoint)
    - Config knobs (~25 leaves): decision.cancel_cost_ewma_alpha, decision.cancel_cost_ttl_s, decision.cancel_cost_block_window, decision.p_purge_default, decision.decision_loop_interval_s, decision.breakers.margin.{window_s,min_samples,time_to_mm_threshold_s,min_re_arm_s}, decision.breakers.oracle_stale.{fraction_of_max,min_re_arm_s}, decision.breakers.clo_removal.min_re_arm_s, decision.breakers.clo_shift.{n_ticks,min_re_arm_s}, decision.breakers.fill_rate.{k_fills_per_hour,min_re_arm_s}, decision.breakers.competition.{drop_threshold,min_re_arm_s}, decision.breakers.maturity.{migration_cost_buffer_pct,min_re_arm_s}, decision.breakers.side_budget.{drift_threshold,min_re_arm_s}, decision.breakers.underlying_stale.{expected_cadence_s_per_exchange,min_re_arm_s}, decision.breakers.loss_fit_degraded.min_re_arm_s, execution.cancel_gas_units_estimate, execution.entrance_fee_pendle, pricing.eth_price_usd, pricing.eth_price_usd_calibrated_at_utc, data.margin_poll_interval_s, data.boros_account_id, MarketCalibration.max_update_delay_s, MarketCalibration.underlying_exchange, MarketCalibration.underlying_symbol.
    - Edges to land NOW (more arrive in 04-03/04/05/06):
      - brain.data.poller.margin_poller calls external.boros.rest.get_net_margin
      - brain.data.poller.margin_poller writes state.margin_history (via brain.state.writers.margin_history)
      - brain.state.writers.margin_history writes state.margin_history
      - brain.state.writers.breaker_events writes state.breaker_events
      - brain.state.writers.predeploy_gate_records writes state.predeploy_gate_records

    Do NOT register engine, gas_history, breaker_coordinator, predeploy_gate, cli, or the 10 individual breaker modules — those land in 04-03/04/05/06 atomically with their source.

    Mermaid update in ARCHITECTURE.md: append a "Phase 4 Wave 1 foundation" subgraph under the Phase 3 section, with the foundation nodes and their edges.
  </behavior>
  <action>
1. Read docs/architecture.yml to find the end of `nodes:` (just before `edges:` around line 1095).

2. Append before `edges:` the foundation node block. Use the exact yaml shape from existing entries (e.g. lines 24-30 of architecture.yml for the brain.config.schema node):

   ```yaml
   # ── Phase 4 Wave 1 foundation — Plan 04-02 ─────────────────────
   - id: brain.decision
     type: module
     process: brain
     path: python/src/boros_brain/decision/__init__.py
     public_functions: []

   - id: brain.decision.config
     type: module
     process: brain
     path: python/src/boros_brain/decision/config.py
     public_functions: []

   - id: brain.decision.schemas
     type: module
     process: brain
     path: python/src/boros_brain/decision/schemas.py
     public_functions: []

   - id: brain.decision.breakers
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/__init__.py
     public_functions: []

   - id: brain.decision.breakers.base
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/base.py
     public_functions: [Breaker, BreakerSignal]

   - id: brain.state.writers.margin_history
     type: module
     process: brain
     path: python/src/boros_brain/state/writers/margin_history.py
     public_functions: [insert_margin_snapshot, read_margin_history]

   - id: brain.state.writers.breaker_events
     type: module
     process: brain
     path: python/src/boros_brain/state/writers/breaker_events.py
     public_functions: [insert_breaker_event]

   - id: brain.state.writers.predeploy_gate_records
     type: module
     process: brain
     path: python/src/boros_brain/state/writers/predeploy_gate_records.py
     public_functions: [insert_predeploy_gate_record, get_latest_predeploy_gate_record]

   - id: brain.data.poller.margin_poller
     type: module
     process: brain
     path: python/src/boros_brain/data/poller/margin_poller.py
     public_functions: [run_margin_poller_loop, MarginPoller]

   # ── Storage nodes ──────────────────────────────────────────────
   - id: state.margin_history
     type: storage
     path: state/state.sqlite#margin_history

   - id: state.breaker_events
     type: storage
     path: state/state.sqlite#breaker_events

   - id: state.predeploy_gate_records
     type: storage
     path: state/state.sqlite#predeploy_gate_records

   # ── External ──────────────────────────────────────────────────
   - id: external.boros.rest.get_net_margin
     type: external_api
     process: external
     path: https://api.boros.finance/open-api/v1/accounts/get-net-margin
     public_functions: []
   ```

3. Append the ~25 config_knob leaf nodes under nodes: using the exact shape from existing config_knob nodes (e.g. config.loss_model.depth_bucket_edges around line 986). Each one has type: config_knob and pydantic_path: BotConfig.<path>. Example:

   ```yaml
   - id: config.decision.cancel_cost_ewma_alpha
     type: config_knob
     pydantic_path: BotConfig.decision.cancel_cost_ewma_alpha
   ```

   Repeat for all ~25 leaves. Use the dot-paths from <behavior>.

4. After the existing edges: section, add the foundation edges:

   ```yaml
   # ── Phase 4 Wave 1 foundation edges — Plan 04-02 ───────────────
   - {from: brain.data.poller.margin_poller, to: external.boros.rest.get_net_margin, type: calls}
   - {from: brain.data.poller.margin_poller, to: brain.state.writers.margin_history, type: calls}
   - {from: brain.state.writers.margin_history, to: state.margin_history, type: writes}
   - {from: brain.state.writers.breaker_events, to: state.breaker_events, type: writes}
   - {from: brain.state.writers.predeploy_gate_records, to: state.predeploy_gate_records, type: writes}
   - {from: brain.data.poller.margin_poller, to: config.data.margin_poll_interval_s, type: depends-on-config}
   - {from: brain.data.poller.margin_poller, to: config.data.boros_account_id, type: depends-on-config}
   ```

5. Update docs/ARCHITECTURE.md — append a new section after the Phase 3 Mermaid block:

   ```markdown
   ## Phase 4 Wave 1 — Decision Engine + Breakers Foundation (Plan 04-02)

   ```mermaid
   flowchart LR
     subgraph p4w1[Phase 4 Wave 1 foundation]
       margin_poller[margin_poller<br/>1 Hz REST]
       w_margin[margin_history writer]
       w_break[breaker_events writer]
       w_pre[predeploy_gate_records writer]
       base[Breaker ABC + BreakerSignal]
       s_margin[(state.margin_history)]
       s_break[(state.breaker_events)]
       s_pre[(state.predeploy_gate_records)]
     end
     ext_rest((external.boros.rest.get_net_margin))
     margin_poller --> ext_rest
     margin_poller --> w_margin --> s_margin
     w_break --> s_break
     w_pre --> s_pre
   ```

   Phase 4 Wave 2 (engine + breakers) and Wave 3 (coordinator + main.py wiring) extend this in plans 04-03..04-06.
   ```

6. Run `python3 scripts/architecture_lint.py` — must exit 0. Any drift means a node was forgotten or an unused declaration sneaked in.

Self-verification: `grep -c "^  - id: brain.decision" docs/architecture.yml` returns at least 5 (the 5 new decision modules).
  </action>
  <verify>
    <automated>python3 scripts/architecture_lint.py</automated>
  </verify>
  <acceptance_criteria>
    - grep -q "brain.decision.config" docs/architecture.yml
    - grep -q "brain.decision.schemas" docs/architecture.yml
    - grep -q "brain.decision.breakers.base" docs/architecture.yml
    - grep -q "brain.state.writers.margin_history" docs/architecture.yml
    - grep -q "brain.state.writers.breaker_events" docs/architecture.yml
    - grep -q "brain.state.writers.predeploy_gate_records" docs/architecture.yml
    - grep -q "brain.data.poller.margin_poller" docs/architecture.yml
    - grep -q "state.margin_history" docs/architecture.yml
    - grep -q "external.boros.rest.get_net_margin" docs/architecture.yml
    - grep -q "config.decision.cancel_cost_ewma_alpha" docs/architecture.yml
    - grep -q "config.decision.breakers.margin.window_s" docs/architecture.yml
    - grep -q "config.decision.breakers.oracle_stale.fraction_of_max" docs/architecture.yml
    - grep -q "Phase 4 Wave 1" docs/ARCHITECTURE.md
    - python3 scripts/architecture_lint.py exits 0
  </acceptance_criteria>
  <done>Architecture foundation atomic delta lands; lint passes; Mermaid documents the Wave-1 sub-architecture.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 6: strategy/v0.5-default.yaml — wire eth_price_usd, account_id, MarketCalibration extensions</name>
  <files>
    strategy/v0.5-default.yaml,
    python/tests/test_config_round_trip.py
  </files>
  <read_first>
    - strategy/v0.5-default.yaml (current — find pricing section, markets section, data section)
    - python/tests/test_config_round_trip.py (current — verify it loads default_yaml)
    - python/src/boros_brain/pricing/config.py (after Task 1 — eth_price_usd is mandatory no-default)
    - python/src/boros_brain/config/schema.py (after Task 1 — new fields and their defaults)
  </read_first>
  <behavior>
    The default YAML must load cleanly after schema changes:
    - pricing.eth_price_usd: 3000.0 (placeholder; operator overrides)
    - pricing.eth_price_usd_calibrated_at_utc: "2026-04-25T00:00:00Z" (placeholder)
    - data.boros_account_id: 0 (default; operator overrides for live)
    - data.margin_poll_interval_s: optional (uses default 1.0)
    - markets[0] entries acquire safe defaults for max_update_delay_s, underlying_exchange, underlying_symbol — only set explicitly if the existing entry needs custom values.

    test_config_round_trip.py: existing test must still pass.
  </behavior>
  <action>
1. Read strategy/v0.5-default.yaml to find the pricing block and the markets block.

2. Add to the pricing block:
   ```yaml
   pricing:
     pendle_price_usd: ...   # existing
     pendle_price_usd_calibrated_at_utc: ...   # existing
     eth_price_usd: 3000.0
     eth_price_usd_calibrated_at_utc: "2026-04-25T00:00:00Z"
   ```

3. Add to the data block (if the field is mandatory in the schema, otherwise skip — boros_account_id has default 0):
   ```yaml
   data:
     ...   # existing
     boros_account_id: 0
   ```

4. The MarketCalibration extensions all have safe defaults (max_update_delay_s=600, underlying_exchange="binance", underlying_symbol="") so existing market entries do not require updates. If the round-trip test fails because frozen=True and extra='forbid' rejects new fields with defaults — Pydantic v2 with default values is fine; verify by running the test.

5. Run `cd python ; uv run pytest tests/test_config_round_trip.py -x` — must exit 0. If any test breaks, fix the YAML to provide the new fields explicitly.

Self-verification: `cd python ; uv run python -c "from boros_brain.config.loader import load_config; from pathlib import Path; cfg = load_config(Path('strategy/v0.5-default.yaml')); assert cfg.pricing.eth_price_usd == 3000.0; assert cfg.decision.breakers.margin.window_s == 30.0; print('OK')"` exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_config_round_trip.py -x</automated>
  </verify>
  <acceptance_criteria>
    - grep -q "eth_price_usd: 3000.0" strategy/v0.5-default.yaml
    - grep -q "eth_price_usd_calibrated_at_utc:" strategy/v0.5-default.yaml
    - cd python ; uv run pytest tests/test_config_round_trip.py -x exits 0
    - cd python ; uv run python -c "from boros_brain.config.loader import load_config; from pathlib import Path; cfg = load_config(Path('strategy/v0.5-default.yaml')); assert cfg.pricing.eth_price_usd == 3000.0" exits 0
  </acceptance_criteria>
  <done>Default YAML loads cleanly after Phase 4 schema extensions; existing config round-trip tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 7: Foundation wiki write-back</name>
  <files>
    python/tests/test_decision_engine_voluntary_branch.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (LLM Wiki Pages to Write-Back, lines 1532-1557)
  </read_first>
  <behavior>
    File two new wiki pages capturing the Wave-1 foundation decisions:
    - boros-rest-api-margin-endpoint.md (SAFE-01 data source contract)
    - phase4-foundation-schema-and-tables.md (BotConfig delta + 4 new tables documented for downstream waves)

    Touch test_decision_engine_voluntary_branch.py with a docstring update referencing the wiki page (no test logic change).
  </behavior>
  <action>
1. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/boros-rest-api-margin-endpoint.md with content:

   ```
   ---
   title: Boros REST API — get-net-margin endpoint
   status: Current
   phase: 4
   plan: 04-02
   date: 2026-04-25
   ---

   # Boros REST API — accounts/get-net-margin

   **Status:** Current — SAFE-01 data source

   ## Endpoint

   `POST /open-api/v1/accounts/get-net-margin`

   ## Request body

   ```json
   {"accountId": <int>}
   ```

   ## Response (assumed shape — verify in Plan 04-04 SAFE-01 stage)

   ```json
   {
     "netMargin": <float, USD>,
     "maintenanceMargin": <float, USD>,
     "availableCollateral": <float, USD>
   }
   ```

   Per RESEARCH.md A1 (assumption); exact field shape verified by Plan 04-04 SAFE-01 test stage with stubbed response. Live verification deferred to Phase 6 dev wallet smoke.

   ## Cadence

   1 Hz polling matching the decision loop. Per-account aggregate (NOT per-market); writer fans out one row per market for query convenience.

   ## Degraded mode

   After 5 consecutive failures, MarginPoller publishes `poller.margin.degraded` event and stops writing rows until the next successful fetch.

   ## Cross-references

   - [[circuit-breakers-v05]]
   - [[zmq-bus-topology-v05]]
   ```

2. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/phase4-foundation-schema-and-tables.md with content listing:
   - BotConfig delta (DecisionEngineConfig with 25 leaves; ExecutionConfig 2 new fields; MarketCalibration 3 new fields; PricingConfig 2 new fields)
   - 4 new SQLite tables (margin_history, breaker_events, predeploy_gate_records, defensive competition_history) and 1 column (tx_receipts.event_type)
   - Status: Current — Phase 4 Wave 1 foundation
   - Cross-references: [[ev-cancel-rule]], [[circuit-breakers-v05]]

3. Append a one-line reference to test_decision_engine_voluntary_branch.py module docstring: "See [[boros-rest-api-margin-endpoint]] and [[phase4-foundation-schema-and-tables]] for Wave-1 foundation."

Self-verification: both wiki pages exist with Status: Current line and cite at least one wiki link.
  </action>
  <verify>
    <automated>test -f "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/boros-rest-api-margin-endpoint.md"</automated>
  </verify>
  <acceptance_criteria>
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/boros-rest-api-margin-endpoint.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/phase4-foundation-schema-and-tables.md" exists
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/boros-rest-api-margin-endpoint.md"
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/phase4-foundation-schema-and-tables.md"
    - grep -q "POST /open-api/v1/accounts/get-net-margin" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/boros-rest-api-margin-endpoint.md"
    - grep -q "phase4-foundation-schema-and-tables" python/tests/test_decision_engine_voluntary_branch.py
  </acceptance_criteria>
  <done>Two wiki pages filed with Status: Current; cross-references in place.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| BotConfig YAML loader to brain runtime | Operator-supplied YAML feeds Pydantic strict validation; new fields receive bounded defaults so the YAML cannot silently widen knob ranges. |
| Boros REST `/accounts/get-net-margin` to brain | External service; field shape is currently ASSUMED — Plan 04-04 SAFE-01 stage is the verification surface. |
| Migration 0007 to existing DBs | Rolling forward only; no downgrade. event_type column add uses server_default to keep existing rows valid. |
| New writers to SQLite | Caller-owned transactions for batched inserts; sqlite_writer_lint blocks new writers from outside the OWNER_MAP. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-02-01 | T (Tampering) | sqlite_writer_lint OWNER_MAP | mitigate | OWNER_MAP is checked in via PROTO-02; lint walks both python/src and ts/src; CHECK constraints on breaker_events.kind and predeploy_gate_records.gate_passed enforce row-level integrity in the DB itself even if a future writer bypasses the Python guard. |
| T-04-02-02 | I (Information disclosure) | predeploy_gate_records.config_hash | accept | config_hash is a hash of BotConfig (no secrets — secrets come from .env.vault, never from BotConfig). The git_sha is public information. No PII risk. |
| T-04-02-03 | S (Spoofing) | MarginPoller fetched JSON | mitigate | Plan 04-04 SAFE-01 test exercises with stubbed JSON; live verification at Phase 6 dev wallet smoke; if exact field shape differs from RESEARCH A1, the wiki page [[boros-rest-api-margin-endpoint]] is updated and the poller field-extraction code is patched in same commit. |
| T-04-02-04 | D (Denial of service) | MarginPoller backoff | mitigate | Backoff window of [0.5, 1, 2, 4, 8] seconds caps RPC pressure. After 5 consecutive failures, poller publishes degraded event and stops writing rows until next successful cycle (mirrors ELiqPoller pattern). The brain's chain_drift halt also catches the case where the entire RPC layer goes down. |
| T-04-02-05 | E (Elevation of privilege) | sqlite_writer_lint pre-commit hook | mitigate | The lint script's PATTERN regex is anchored to literal SQL token boundaries (`INSERT\s+INTO\s+<table>\b`). A malicious source file cannot evade the lint by spelling tricks — the table name appears verbatim. The TEST_ONLY=True exception is gated by literal string match in the source file. |
| T-04-02-06 | R (Repudiation) | predeploy_gate_records git_sha + config_hash | mitigate | Per Pitfall #8 the gate record stamps both at gate-time; Phase 7 boot reads the latest record and refuses to start on hash mismatch. Operator cannot deploy with a config that was never gate-validated. |
| T-04-02-07 | T (Tampering) | event_type column on tx_receipts | mitigate | Column added with `server_default='unknown'` so existing rows auto-migrate to a known sentinel. SAFE-05 fill-rate breaker filters by `event_type='fill'` only — pre-migration rows are excluded from the count, conservatively under-counting fills (false negative is preferable to over-firing the breaker). |
</threat_model>

<verification>
After all tasks complete, run:

```
cd python ; uv run python -c "from boros_brain.decision.config import DecisionEngineConfig; from boros_brain.decision.schemas import EvaluateInput, EvaluateOutput; from boros_brain.decision.breakers.base import Breaker, BreakerSignal; from boros_brain.data.poller.margin_poller import MarginPoller; cfg = DecisionEngineConfig(); assert cfg.breakers.margin.window_s == 30.0; print('OK')"

cd python ; uv run pytest tests/test_sqlite_migrations.py tests/test_sqlite_single_writer.py tests/test_config_round_trip.py -x

python3 scripts/sqlite_writer_lint.py --root .
python3 scripts/no_time_time_lint.py
python3 scripts/architecture_lint.py
```

All commands MUST exit 0.
</verification>

<success_criteria>
- [ ] BotConfig + DecisionEngineConfig schema landed; existing v0.5-default.yaml still loads.
- [ ] EvaluateInput / EvaluateOutput / BreakerSignal / Breaker ABC importable from boros_brain.decision.*.
- [ ] Migration 0007 applies cleanly to a fresh DB; 4 tables present plus tx_receipts.event_type column.
- [ ] Three new writers exist; sqlite_writer_lint passes with the extended OWNER_MAP.
- [ ] MarginPoller exists with 1 Hz cadence and degraded-mode handling.
- [ ] Architecture.yml and Mermaid foundation delta atomic; architecture_lint passes.
- [ ] Two wiki pages filed with Status: Current.
- [ ] Existing Phase 1-3 test suite still green.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-02-SUMMARY.md` documenting:
- BotConfig schema delta (~25 new leaves)
- Migration 0007 (4 tables + 1 column)
- Three new state writers
- MarginPoller and BorosRestClient.post_get_net_margin
- Architecture foundation delta (modules + storage + external + edges + ~25 config_knob leaves)
- Two wiki pages filed
</output>
