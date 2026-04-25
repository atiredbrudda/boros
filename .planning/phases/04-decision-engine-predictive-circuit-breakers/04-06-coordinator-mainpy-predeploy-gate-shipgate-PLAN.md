---
phase: 04-decision-engine-predictive-circuit-breakers
plan: 06
type: execute
wave: 3
depends_on: [01, 02, 03, 04, 05]
autonomous: true
requirements: [DECIDE-01, DECIDE-02, DECIDE-03, DECIDE-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06, SAFE-07, SAFE-08, SAFE-09, SAFE-10]
files_modified:
  - python/src/boros_brain/decision/breaker_coordinator.py
  - python/src/boros_brain/decision/predeploy_gate.py
  - python/src/boros_brain/decision/cli.py
  - python/src/boros_brain/decision/__main__.py
  - python/src/boros_brain/main.py
  - python/tests/test_breaker_coordinator_exclusive.py
  - python/tests/test_predeploy_gate_cli.py
  - python/tests/test_main_decision_loop_spawn.py
  - python/tests/test_phase4_manifest_leaves.py
  - python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
  - docs/architecture.yml
  - docs/ARCHITECTURE.md
  - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md

user_setup: []

must_haves:
  truths:
    - "BreakerCoordinator owns the brain-side kill mutex; on rising edge of any breaker fires KillCmd EXACTLY ONCE (Pitfall #6 hysteresis)."
    - "While any breaker is tripped, coordinator.gate suppresses ALL PLACE/CANCEL cmds and persists the suppression event to state.breaker_events."
    - "main.py spawns a 1 Hz _decision_loop async task that calls coord.tick then engine.evaluate per in-flight order then coord.gate per cycle."
    - "ChainTimeCache.halt_callback is replaced with coord.halt_via_chain_time so chain_drift halt routes through the coordinator's KILL lane."
    - "predeploy_gate CLI re-runs the economics gate, writes a state.predeploy_gate_records row with git_sha + config_hash (Pitfall #8), and writes a wiki page; exits 0 on pass and 1 on fail."
    - "Phase 4 leaf-count test (>=25 decision.* leaves) PASSES after final BotConfig is fully wired."
    - "Atomic Phase-4 architecture delta — coordinator + cli + predeploy_gate + main.py edits land together; full Phase 4 nodes/edges in same commit."
  artifacts:
    - path: "python/src/boros_brain/decision/breaker_coordinator.py"
      provides: "SAFE-10 — BreakerCoordinator class with tick + gate + hysteresis state"
      contains: "class BreakerCoordinator"
      min_lines: 100
    - path: "python/src/boros_brain/decision/predeploy_gate.py"
      provides: "A5 absorbed — pre-deployment re-screen CLI subcommand"
      contains: "def run_predeploy_gate"
    - path: "python/src/boros_brain/decision/cli.py"
      provides: "argparse + manifest-first preamble + subcommands (predeploy_gate, reset_breaker)"
      contains: "def main"
    - path: "python/src/boros_brain/decision/__main__.py"
      provides: "python -m boros_brain.decision entry"
      min_lines: 5
    - path: "python/src/boros_brain/main.py"
      provides: "Spawns 1 Hz decision loop + wires chain_cache.halt_callback to coord"
      contains: "_decision_loop"
  key_links:
    - from: "python/src/boros_brain/main.py"
      to: "python/src/boros_brain/decision/breaker_coordinator.py"
      via: "BreakerCoordinator instantiation in run()"
      pattern: "from .decision.breaker_coordinator import BreakerCoordinator"
    - from: "python/src/boros_brain/main.py"
      to: "python/src/boros_brain/decision/engine.py"
      via: "evaluate call in _decision_loop"
      pattern: "from .decision.engine import evaluate"
    - from: "python/src/boros_brain/decision/breaker_coordinator.py"
      to: "python/src/boros_brain/bus/cmd.py"
      via: "send_kill on rising edge"
      pattern: "send_kill"
    - from: "python/src/boros_brain/decision/predeploy_gate.py"
      to: "python/src/boros_brain/screener/economics_gate.py"
      via: "run_screener invocation"
      pattern: "economics_gate"
---

<objective>
Wave 3 — the SHIP gate. Implement BreakerCoordinator (SAFE-10 exclusive kill authority), predeploy_gate CLI (A5 absorbed), the python -m boros_brain.decision CLI entry, the main.py 1 Hz _decision_loop spawn, and the final Phase 4 architecture delta. After this plan, all 17 RED tests from Plan 04-01 are GREEN, scripts/architecture_lint.py + sqlite_writer_lint + no_*_lint all pass, and `gsd-verify-work 4` can be invoked.

Purpose: Connect the engine + 10 breakers + ZMQ KILL lane + chain_time halt + screener into a single coherent loop with mechanical kill-authority enforcement.

Output: BreakerCoordinator + predeploy_gate + cli + main.py wiring + atomic Phase-4 architecture delta + 18 RED tests turned GREEN (17 from plan 04-01 plus the new SAFE composition test added by plan 04-01 Task 3).

Scope note: this plan has 6 tasks. Tasks 5 and 6 are integration-only — no new source files. Task 5 is the final ship-gate (run full suite + 6 lint scripts + file two final wiki pages + flip the 04-VALIDATION.md frontmatter flags). Task 6 is the SAFE composition end-to-end test parametrized over SAFE-01..09 + B5. The 6-task count is justified because Tasks 5+6 are lightweight (no new source modules) and the plan must remain atomic: predeploy_gate, BreakerCoordinator, main.py wiring, and the final architecture delta are tightly coupled, and the atomic ship-gate property is more important than rigid task-count limits. Splitting into 04-06a / 04-06b would fragment the architecture delta and break the atomic-delta invariant.
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
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-03-decision-engine-gas-history-linters-PLAN.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-04-breakers-margin-oracle-clo-fillrate-lossfit-PLAN.md
@.planning/phases/04-decision-engine-predictive-circuit-breakers/04-05-breakers-competition-maturity-side-budget-underlying-PLAN.md
@CLAUDE.md
@python/src/boros_brain/main.py
@python/src/boros_brain/bus/cmd.py
@python/src/boros_brain/bus/messages.py
@python/src/boros_brain/data/chain_time.py
@python/src/boros_brain/screener/economics_gate.py
@python/src/boros_brain/state/writers/breaker_events.py
@python/src/boros_brain/state/writers/predeploy_gate_records.py
@python/src/boros_brain/state/writers/decisions.py
@python/src/boros_brain/decision/engine.py
@python/src/boros_brain/decision/gas_history.py
@python/src/boros_brain/decision/breakers/base.py
@python/src/boros_brain/decision/breakers/margin_trajectory.py
@python/src/boros_brain/decision/breakers/oracle_stale.py
@python/src/boros_brain/decision/breakers/clo_removal.py
@python/src/boros_brain/decision/breakers/clo_shift.py
@python/src/boros_brain/decision/breakers/fill_rate.py
@python/src/boros_brain/decision/breakers/competition.py
@python/src/boros_brain/decision/breakers/maturity.py
@python/src/boros_brain/decision/breakers/side_budget.py
@python/src/boros_brain/decision/breakers/underlying_stale.py
@python/src/boros_brain/decision/breakers/loss_fit_degraded.py
@python/src/boros_brain/fill_model/cli.py
@python/src/boros_brain/fill_model/__main__.py
@python/tests/test_zmq_kill_priority.py

<interfaces>
Existing in main.py (Phase 3 wiring at lines 144-220):
  - run(config_path, dry_run=False) -> int  (entrypoint)
  - cmd_bus, event_bus, chain_cache instantiated and threaded through
  - Phase 2 fill_model + Phase 3 loss_model + competition_tracker spawn pattern (asyncio.create_task)
  - Cancellation tuple at lines 200-211 (each task t.cancel() ; await t)

ChainTimeCache (chain_time.py):
  - chain_cache.halt_callback: callable | None  (replaceable; default _default_halt_callback logs only)

Bus messages (bus/messages.py):
  - class KillCmd(StrictMsg): reason, run_id

Engine (Plan 04-03):
  - async def evaluate(req, *, sqlite_path, config, gas_cache, w3) -> EvaluateOutput
  - GasHistoryCache class

Breakers (Plans 04-04 / 04-05): 10 modules each exporting a class subclassing Breaker.

State writers (Plan 04-02):
  - insert_breaker_event(conn, *, kind, breaker_name, reason, chain_ts, run_id, payload_json) -> None
  - insert_predeploy_gate_record(conn, *, gate_passed, git_sha, git_dirty, config_hash, wiki_page_path, run_id, chain_ts) -> None
  - get_latest_predeploy_gate_record(sqlite_path) -> dict | None

Screener (existing — Phase 1):
  - brain.screener.economics_gate.run_screener(config) -> ShortlistResult  (verify exact module path)

NEW interfaces created in this plan:

  class BreakerCoordinator:
    def __init__(self, *, cmd_bus, config, run_id, gas_cache, breakers: list[Breaker]):
        self._tripped: dict[str, int] = {}  # breaker.name -> first_tripped_chain_ts
    async def tick(self, *, sqlite_path, w3, parquet_root, current_chain_ts) -> dict[str, BreakerSignal]
    async def gate(self, decisions: list[EvaluateOutput], *, current_chain_ts: int) -> None
    async def halt_via_chain_time(self, reason: str, payload: dict) -> None  (replaces ChainTimeCache._default_halt_callback)

  def run_predeploy_gate(config: BotConfig, *, sqlite_path: Path, run_id: str) -> int  (CLI subcommand body)

  Module python/src/boros_brain/decision/cli.py:
    def build_parser() -> argparse.ArgumentParser
    def main(argv: list[str] | None = None) -> int  (manifest-first preamble + subcommand dispatch)

  Module python/src/boros_brain/decision/__main__.py:
    sys.exit(main())  (5-line passthrough)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: BreakerCoordinator (SAFE-10)</name>
  <files>
    python/src/boros_brain/decision/breaker_coordinator.py,
    python/tests/test_breaker_coordinator_exclusive.py
  </files>
  <read_first>
    - python/src/boros_brain/bus/cmd.py (CmdBus.send_cmd / send_kill — invocation pattern)
    - python/src/boros_brain/bus/messages.py (KillCmd, PlaceCmd, CancelCmd)
    - python/src/boros_brain/decision/breakers/base.py (Breaker ABC, BreakerSignal — coordinator iterates over a list[Breaker])
    - python/src/boros_brain/state/writers/breaker_events.py (insert_breaker_event signature)
    - python/src/boros_brain/decision/gas_history.py (GasHistoryCache injected into MaturityBreaker.gas_cache)
    - python/src/boros_brain/data/chain_time.py (ChainTimeCache.halt_callback replacement seam)
    - python/tests/test_zmq_kill_priority.py (CmdBus + ipc_dir end-to-end pattern — verbatim test scaffold)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (SAFE-10 §, lines 768-846; Pitfall #1 timeout, Pitfall #2 no in-memory log, Pitfall #6 hysteresis, Pitfall #9 LINGER)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (breaker_coordinator.py pattern lines 470-575)
    - python/tests/test_breaker_coordinator_exclusive.py (RED tests — must turn GREEN)
  </read_first>
  <behavior>
    BreakerCoordinator class:
      __init__(self, *, cmd_bus, config, run_id, gas_cache, breakers: list[Breaker]):
          self._cmd_bus = cmd_bus
          self._config = config
          self._run_id = run_id
          self._gas_cache = gas_cache
          self._breakers = breakers
          self._tripped: dict[str, int] = {}  # name -> first_tripped_chain_ts (rising-edge tracking)
          self._last_check_ts: dict[str, int] = {}

      async def tick(self, *, sqlite_path, w3, parquet_root, current_chain_ts) -> dict[str, BreakerSignal]:
          """Sweep all breakers; emit KillCmd on RISING edge only (Pitfall #6 hysteresis)."""
          signals: dict[str, BreakerSignal] = {}
          for b in self._breakers:
              try:
                  sig = await asyncio.wait_for(
                      b.check(sqlite_path=sqlite_path, w3=w3, parquet_root=parquet_root,
                              config=self._config, current_chain_ts=current_chain_ts),
                      timeout=0.2,  # Pitfall #1: 200ms per breaker
                  )
              except asyncio.TimeoutError:
                  log.warning("breaker.timeout", name=b.name, current_chain_ts=current_chain_ts)
                  sig = BreakerSignal(tripped=False, reason="timeout")
              except Exception as exc:
                  log.error("breaker.error", name=b.name, err=str(exc))
                  sig = BreakerSignal(tripped=False, reason="error")
              signals[b.name] = sig

              # Hysteresis: rising edge on transition False -> True; un-trip after min_re_arm_s
              was_tripped = b.name in self._tripped
              if sig.tripped and not was_tripped:
                  # RISING EDGE — fire KillCmd ONCE
                  self._tripped[b.name] = current_chain_ts
                  await self._cmd_bus.send_kill(KillCmd(reason=f"{b.name}:{sig.reason}", run_id=self._run_id))
                  log.error("breaker_tripped", breaker=b.name, reason=sig.reason, payload=sig.payload)
                  with open_connection(Path(self._config.infra.sqlite_path)) as conn:
                      insert_breaker_event(
                          conn, kind="kill_emitted", breaker_name=b.name,
                          reason=sig.reason, chain_ts=current_chain_ts, run_id=self._run_id,
                          payload_json=sig.model_dump_json(),
                      )
                      conn.commit()
              elif not sig.tripped and was_tripped:
                  # Hysteresis: only un-trip after min_re_arm_s
                  re_arm_cfg = getattr(self._config.decision.breakers, b.name, None)
                  re_arm_s = getattr(re_arm_cfg, "min_re_arm_s", 60.0) if re_arm_cfg else 60.0
                  if current_chain_ts - self._tripped[b.name] >= re_arm_s:
                      del self._tripped[b.name]
                      with open_connection(Path(self._config.infra.sqlite_path)) as conn:
                          insert_breaker_event(
                              conn, kind="rearmed", breaker_name=b.name,
                              reason="auto_rearm", chain_ts=current_chain_ts, run_id=self._run_id,
                          )
                          conn.commit()
          return signals

      async def gate(self, decisions, *, current_chain_ts: int) -> None:
          """Suppress all PLACE/CANCEL while any breaker active. SAFE-10 exclusivity."""
          if not self._tripped:
              # Forward decisions through cmd_bus (engine emits PLACE / CANCEL only)
              for d in decisions:
                  if d.decision_kind == "PLACE":
                      await self._cmd_bus.send_cmd(self._build_place_cmd(d))
                  elif d.decision_kind == "CANCEL":
                      await self._cmd_bus.send_cmd(self._build_cancel_cmd(d))
                  # HOLD / HOLD_NO_REPLACE -> no cmd
              return
          # Suppression path
          with open_connection(Path(self._config.infra.sqlite_path)) as conn:
              for d in decisions:
                  if d.decision_kind in ("PLACE", "CANCEL"):
                      insert_breaker_event(
                          conn, kind="suppression", breaker_name=",".join(self._tripped.keys()),
                          reason=f"active_breaker_blocked_{d.decision_kind}",
                          chain_ts=current_chain_ts, run_id=self._run_id,
                          payload_json=d.model_dump_json(),
                      )
                      log.warning("breaker_coordinator.suppressed", decision_kind=d.decision_kind,
                                  active_breakers=list(self._tripped.keys()))
              conn.commit()

      def _build_place_cmd(self, d) -> PlaceCmd: ...  (concrete construction; v0.5 minimal — engine reasoning carries the order params)
      def _build_cancel_cmd(self, d) -> CancelCmd: ...  (concrete construction)

      async def halt_via_chain_time(self, reason: str, payload: dict) -> None:
          """Replaces ChainTimeCache._default_halt_callback. Routes chain_drift halt through KILL lane."""
          await self._cmd_bus.send_kill(KillCmd(reason=f"chain_time_halt:{reason}", run_id=self._run_id))
          log.error("chain_time_halt_via_coordinator", reason=reason, payload=payload)

    Tests:
    - test_kill_fires_once: real CmdBus over ipc_dir; AlwaysTrippedBreaker fakes a tripped=True signal; coord.tick once -> assert KillCmd received on kill socket; coord.tick again -> assert NO new KillCmd (Pitfall #6 hysteresis).
    - test_suppression: trip a breaker; call coord.gate([place_decision]); assert no msg on cmd socket; assert state.breaker_events row with kind='suppression'.
    - test_suppression_logged: same as above but inspect breaker_events row payload_json contains the order_id from the suppressed decision.
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/breaker_coordinator.py per the body in <behavior>. Imports include:
   - asyncio
   - from pathlib import Path
   - structlog
   - from ..bus.cmd import CmdBus
   - from ..bus.messages import KillCmd, PlaceCmd, CancelCmd
   - from ..config.schema import BotConfig
   - from ..state.db import open_connection
   - from ..state.writers.breaker_events import insert_breaker_event
   - from .breakers.base import Breaker, BreakerSignal
   - from .gas_history import GasHistoryCache
   - log = structlog.get_logger(__name__)

   The class body matches <behavior>. The _build_place_cmd / _build_cancel_cmd helpers construct minimal PlaceCmd / CancelCmd objects from EvaluateOutput.reasoning fields (order_id, market_id, side); the full hot-path cmd construction lands in Phase 6 hands so v0.5 keeps it simple. Document this with a code comment "v0.5 minimal cmd shape; Phase 6 hands extends with calldata".

   Pitfall #6 hysteresis: the elif branch handles auto-rearm after min_re_arm_s elapsed and the breaker un-trips itself.

   Pitfall #2: NEVER use an in-memory list — every suppression goes to state.breaker_events.

2. Update python/tests/test_breaker_coordinator_exclusive.py — remove importorskip; implement three tests:
   - test_kill_fires_once: build real CmdBus over ipc_dir/cmd + ipc_dir/cmd.kill; bind a zmq.PULL socket on kill_endpoint; sleep 0.05 for slow-joiner. Define `class _AlwaysTrippedBreaker(Breaker): name = "test_always"; async def check(...): return BreakerSignal(tripped=True, reason="test", kill_command_kind="CANCEL_ALL")`. Build coord with breakers=[_AlwaysTrippedBreaker()]. Call coord.tick() once; assert kill_pull.recv_json() returns a msg with kind="kill". Call coord.tick(current_chain_ts=t+1) again; assert pytest.raises(asyncio.TimeoutError) on kill_pull.recv_json(timeout=0.1).

   - test_suppression: with same coord (still tripped), build a fake EvaluateOutput with decision_kind="PLACE"; call coord.gate([fake]); bind a zmq.PULL on cmd_endpoint; assert pytest.raises(asyncio.TimeoutError) on cmd_pull.recv_json(timeout=0.1) (no PLACE arrives).

   - test_suppression_logged: after test_suppression, query state.breaker_events; assert at least one row with kind='suppression', breaker_name contains "test_always", payload_json contains the order_id.

   Use the ipc_dir fixture from conftest. Apply migrations to the test DB (the breaker_events table needs to exist — use the apply_migrations helper from conftest).

Self-verification: cd python ; uv run pytest tests/test_breaker_coordinator_exclusive.py -x exits 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_coordinator_exclusive.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "class BreakerCoordinator"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "async def tick"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "async def gate"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "halt_via_chain_time"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "asyncio.wait_for"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "min_re_arm_s"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "insert_breaker_event"
    - File python/src/boros_brain/decision/breaker_coordinator.py contains "kind=\"suppression\""
    - cd python ; uv run pytest tests/test_breaker_coordinator_exclusive.py -x exits 0
    - python3 scripts/no_threshold_dials_lint.py exits 0
    - python3 scripts/no_time_time_lint.py exits 0
  </acceptance_criteria>
  <done>SAFE-10 implemented; rising-edge KillCmd fires once; suppression of PLACE/CANCEL persisted; tests GREEN.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: predeploy_gate + decision CLI (A5 absorbed)</name>
  <files>
    python/src/boros_brain/decision/predeploy_gate.py,
    python/src/boros_brain/decision/cli.py,
    python/src/boros_brain/decision/__main__.py,
    python/tests/test_predeploy_gate_cli.py
  </files>
  <read_first>
    - python/src/boros_brain/screener/economics_gate.py (verify exact module path and run_screener signature)
    - python/src/boros_brain/state/writers/predeploy_gate_records.py (insert_predeploy_gate_record + get_latest signatures)
    - python/src/boros_brain/manifest/writer.py (build_run_manifest pattern + git_sha + git_dirty extraction)
    - python/src/boros_brain/fill_model/cli.py (verbatim model for argparse + manifest-first preamble + subcommand dispatch)
    - python/src/boros_brain/fill_model/__main__.py (5-line passthrough)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (Pre-deployment re-screen gate § lines 870-887; Pitfall #8 git_sha + config_hash mismatch lines 1314-1317)
  </read_first>
  <behavior>
    predeploy_gate.py:
      def run_predeploy_gate(config: BotConfig, *, sqlite_path: Path, run_id: str,
                              wiki_dir: Path | None = None) -> int:
          """A5 absorbed — re-runs economics gate; writes a state.predeploy_gate_records row with
          git_sha + config_hash; writes a wiki page; exits 0 on pass and 1 on fail."""
          # 1. Re-run economics gate
          try:
              shortlist = run_screener(config)  # returns list[str] of market_ids that pass
          except Exception as exc:
              log.error("predeploy_gate.screener_failed", err=str(exc))
              return 1
          # 2. Verify configured market is in the shortlist
          configured_market = config.markets[0].market_id if config.markets else None
          gate_passed = configured_market in shortlist if configured_market else False
          # 3. Compute git_sha + git_dirty + config_hash
          git_sha, git_dirty = _read_git_sha()
          config_json = config.model_dump_json()
          config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:16]
          # 4. Write wiki page
          wiki_dir = wiki_dir or Path("/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki")
          wiki_filename = f"predeploy-gate-pass-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.md"
          wiki_path = wiki_dir / wiki_filename
          wiki_path.write_text(f"""---
title: Pre-deployment Gate Result
status: Current — pre-deployment validation
phase: 4
plan: 04-06
date: {datetime.now(UTC).isoformat()}
---

# Pre-deployment Gate

**Status:** Current — pre-deployment validation
**Result:** {'PASS' if gate_passed else 'FAIL'}
**Configured market:** {configured_market}
**Shortlist:** {shortlist}
**git_sha:** {git_sha}
**git_dirty:** {git_dirty}
**config_hash:** {config_hash}

[[predeploy-gate-cli]]
""")
          # 5. Persist record
          chain_ts = int(datetime.now(UTC).timestamp())
          with open_connection(sqlite_path) as conn:
              insert_predeploy_gate_record(
                  conn, gate_passed=gate_passed, git_sha=git_sha, git_dirty=git_dirty,
                  config_hash=config_hash, wiki_page_path=str(wiki_path),
                  run_id=run_id, chain_ts=chain_ts,
              )
              conn.commit()
          return 0 if gate_passed else 1

      def _read_git_sha() -> tuple[str, bool]:
          import subprocess
          try:
              sha = subprocess.check_output(["git","rev-parse","HEAD"], text=True).strip()
              dirty = bool(subprocess.check_output(["git","status","--porcelain"], text=True).strip())
              return sha, dirty
          except Exception:
              return "unknown", True

    cli.py mirrors fill_model/cli.py:
      def build_parser() -> argparse.ArgumentParser:
          p = argparse.ArgumentParser(prog="python -m boros_brain.decision",
                                       description="Decision engine CLI (predeploy_gate, reset_breaker)")
          p.add_argument("--config", default="strategy/v0.5-default.yaml")
          sub = p.add_subparsers(dest="cmd", required=True)
          sub.add_parser("predeploy-gate", help="Re-run economics gate; write predeploy_gate_records row + wiki page")
          rst = sub.add_parser("reset-breaker", help="Manually clear a tripped breaker")
          rst.add_argument("--name", required=True,
                            choices=["margin_trajectory","oracle_stale","clo_removal","clo_shift",
                                     "fill_rate","competition","maturity","side_budget",
                                     "underlying_stale","loss_fit_degraded"])
          return p

      def main(argv=None) -> int:
          args = build_parser().parse_args(argv)
          config = load_config(Path(args.config))
          manifest = build_run_manifest(config)
          configure_logging(run_id=manifest.run_id, tier="decision-cli",
                            logs_dir=Path(config.infra.logs_dir))
          write_manifest(manifest, logs_dir=Path(config.infra.logs_dir),
                         sqlite_path=Path(config.infra.sqlite_path))
          log = structlog.get_logger("decision.cli")
          log.info("RUN_MANIFEST", **manifest.model_dump(mode="json"))
          if args.cmd == "predeploy-gate":
              return run_predeploy_gate(config, sqlite_path=Path(config.infra.sqlite_path),
                                         run_id=manifest.run_id)
          if args.cmd == "reset-breaker":
              # Manually delete the tripped row from state.breaker_events of kind='kill_emitted'
              # AND insert a kind='rearmed' row for the named breaker. v0.5 minimal — Plan 6+ extends.
              return _reset_breaker(config, args.name, manifest.run_id)
          return 2

    __main__.py: 5-line passthrough (mirrors fill_model/__main__.py).

    Tests:
    - test_gate_passes_on_clean_run: monkeypatch screener.run_screener to return [config.markets[0].market_id]; call run_predeploy_gate; assert exit 0; assert state.predeploy_gate_records row with gate_passed=True.
    - test_gate_fails_when_market_dropped: monkeypatch run_screener to return []; assert exit 1; assert row gate_passed=False.
    - test_gate_records_git_sha_and_config_hash: assert the row has non-empty git_sha and config_hash strings.
  </behavior>
  <action>
1. Create python/src/boros_brain/decision/predeploy_gate.py per <behavior>. Imports include hashlib, datetime, subprocess, the screener module (verify path: most likely `from ..screener.economics_gate import run_screener` — read the screener module first to confirm).

2. Create python/src/boros_brain/decision/cli.py per <behavior>. Copy structure verbatim from fill_model/cli.py. The reset-breaker subcommand body for v0.5 is minimal (insert a kind='rearmed' row in breaker_events and log).

3. Create python/src/boros_brain/decision/__main__.py — verbatim copy of fill_model/__main__.py with one import swap:
```python
"""Enables python -m boros_brain.decision."""
import sys
from .cli import main
if __name__ == "__main__":
    sys.exit(main())
```

4. Update python/tests/test_predeploy_gate_cli.py — remove importorskip; implement three tests using monkeypatch on the screener and a tmp wiki_dir to avoid polluting the real wiki.

Self-verification: cd python ; uv run python -m boros_brain.decision predeploy-gate --config strategy/v0.5-default.yaml exits 0 or 1 (depending on whether the configured market is in the shortlist).
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_predeploy_gate_cli.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/decision/predeploy_gate.py contains "def run_predeploy_gate"
    - File python/src/boros_brain/decision/predeploy_gate.py contains "config_hash"
    - File python/src/boros_brain/decision/predeploy_gate.py contains "_read_git_sha"
    - File python/src/boros_brain/decision/predeploy_gate.py contains "insert_predeploy_gate_record"
    - File python/src/boros_brain/decision/cli.py contains "predeploy-gate"
    - File python/src/boros_brain/decision/cli.py contains "reset-breaker"
    - File python/src/boros_brain/decision/__main__.py contains "from .cli import main"
    - cd python ; uv run pytest tests/test_predeploy_gate_cli.py -x exits 0
    - cd python ; uv run python -m boros_brain.decision --help 2>&1 | grep -q "predeploy-gate"
  </acceptance_criteria>
  <done>predeploy_gate + cli + __main__ implemented; CLI subcommands accessible via python -m; tests GREEN.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: main.py spawn block — 1 Hz _decision_loop</name>
  <files>
    python/src/boros_brain/main.py,
    python/tests/test_main_decision_loop_spawn.py
  </files>
  <read_first>
    - python/src/boros_brain/main.py (lines 144-220 — Phase 3 spawn pattern; we APPEND the Phase 4 spawn before stop.wait())
    - python/src/boros_brain/data/chain_time.py (ChainTimeCache.halt_callback seam)
    - python/src/boros_brain/decision/breaker_coordinator.py (just landed in Task 1)
    - python/src/boros_brain/decision/engine.py (engine.evaluate signature; what it needs from main)
    - python/src/boros_brain/state/writers/decisions.py (insert_decision signature for persisting EvaluateOutput)
    - python/src/boros_brain/state/writers/open_orders.py (read_open_orders helper for the 1 Hz loop body — verify name; if absent, use a SELECT pattern)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (main.py spawn block §, lines 1441-1483)
  </read_first>
  <behavior>
    main.py modifications (append to existing run() between competition_tracker spawn and stop.wait()):

    1. Imports at top of file (add to existing imports):
       from .decision.breaker_coordinator import BreakerCoordinator
       from .decision.gas_history import GasHistoryCache
       from .decision.engine import evaluate as evaluate_decision
       from .decision.breakers.margin_trajectory import MarginTrajectoryBreaker
       from .decision.breakers.oracle_stale import OracleStaleBreaker
       from .decision.breakers.clo_removal import CloRemovalBreaker
       from .decision.breakers.clo_shift import CloShiftBreaker
       from .decision.breakers.fill_rate import FillRateBreaker
       from .decision.breakers.competition import CompetitionBreaker
       from .decision.breakers.maturity import MaturityBreaker
       from .decision.breakers.side_budget import SideBudgetBreaker
       from .decision.breakers.underlying_stale import UnderlyingStaleBreaker
       from .decision.breakers.loss_fit_degraded import LossFitDegradedBreaker
       from .state.writers.decisions import insert_decision
       from .fill_model.schemas import FillModelStaleFeatureError, FillModelNoFreshFitError
       from .loss_model.schemas import LossModelNoFreshGridError

    2. After the existing comp_task spawn (around line 195), add:
       gas_cache = GasHistoryCache()
       breakers = [
           MarginTrajectoryBreaker(),
           OracleStaleBreaker(),
           CloRemovalBreaker(),
           CloShiftBreaker(),
           FillRateBreaker(),
           CompetitionBreaker(),
           MaturityBreaker(gas_cache=gas_cache),
           SideBudgetBreaker(),
           UnderlyingStaleBreaker(),
           LossFitDegradedBreaker(),
       ]
       coord = BreakerCoordinator(
           cmd_bus=cmd_bus, config=cfg, run_id=manifest.run_id,
           gas_cache=gas_cache, breakers=breakers,
       )
       # Wire ChainTimeCache.halt_callback to coord.halt_via_chain_time (replaces log-only default)
       chain_cache.halt_callback = coord.halt_via_chain_time
       log.info("decision.coordinator_wired", n_breakers=len(breakers))

       async def _decision_loop():
           sqlite_path = Path(cfg.infra.sqlite_path)
           parquet_root = Path("data/parquet")
           while not stop.is_set():
               current_chain_ts = await chain_cache.now_cached()
               try:
                   await coord.tick(sqlite_path=sqlite_path, w3=w3,
                                    parquet_root=parquet_root, current_chain_ts=current_chain_ts)
               except Exception as exc:
                   log.error("decision.tick_failed", err=str(exc))
               # Per-in-flight-order EV evaluation (v0.5 single-market simplification:
               # the open_orders read is a thin SELECT; full hot-path lives in TS hands)
               # For Phase-4 dryrun the loop simply ticks coord; engine.evaluate is invoked
               # only when an open order exists (which v0.5 does not until Phase 6 wires hands).
               # The shape below is the WIRING contract — Phase 6 populates open_orders.
               try:
                   from .state.writers.open_orders import read_open_orders_for_market
                   orders = read_open_orders_for_market(sqlite_path, market_id=cfg.market_id)
               except Exception:
                   orders = []
               decisions = []
               for order in orders:
                   req = _build_evaluate_input(order, cfg, current_chain_ts)
                   try:
                       out = await evaluate_decision(req, sqlite_path=sqlite_path, config=cfg,
                                                      gas_cache=gas_cache, w3=w3)
                       decisions.append(out)
                       with open_connection(sqlite_path) as conn:
                           insert_decision(conn, out, run_id=manifest.run_id, chain_ts=current_chain_ts)
                           conn.commit()
                   except (FillModelStaleFeatureError, FillModelNoFreshFitError,
                           LossModelNoFreshGridError) as exc:
                       log.warning("decision_engine.skipped_on_stale_input",
                                   order_id=order.get("order_id"), error_class=type(exc).__name__)
                       continue
               try:
                   await coord.gate(decisions, current_chain_ts=current_chain_ts)
               except Exception as exc:
                   log.error("decision.gate_failed", err=str(exc))
               await asyncio.sleep(cfg.decision.decision_loop_interval_s)

       decision_task = asyncio.create_task(_decision_loop())

    3. Extend the cancellation tuple at lines ~200:
       for t in (
           send_task, monitor_task, ingest_task,
           fill_refit_task, loss_refit_task, comp_task,
           decision_task,   # NEW
       ):
           t.cancel()
           with contextlib.suppress(asyncio.CancelledError):
               await t

    Helpers to add in main.py (private):
       def _build_evaluate_input(order: dict, cfg: BotConfig, current_chain_ts: int) -> EvaluateInput:
           """Assemble the EV inputs from open_orders + market_reward_calibration + competition_history.
           v0.5 minimal — Phase 6 hands populates open_orders with full schema."""
           # Stub implementation — fields populated as available; defaults safe for v0.5
           ...

    NEW read helper to add to state/writers/open_orders.py:
       def read_open_orders_for_market(sqlite_path: Path, *, market_id: str) -> list[dict]:
           """Read ACTIVE open_orders for the configured market. v0.5 reads what hands writes (TS owns the writer)."""
           with open_connection(sqlite_path) as conn:
               rows = conn.execute(
                   "SELECT order_id, market_id, side, depth_from_mark_ticks, "
                   "size_pendle, status FROM open_orders "
                   "WHERE market_id = ? AND status = 'active'",
                   (market_id,),
               ).fetchall()
           return [dict(zip(["order_id","market_id","side","depth_from_mark_ticks",
                              "size_pendle","status"], r)) for r in rows]

    Tests:
    - test_decision_loop_task_created: monkeypatch refit-once helpers to be no-ops; call run() with --dry-run=True or use a sentinel; assert that asyncio.all_tasks() includes a task whose name or coroutine name contains "_decision_loop". Use brief await asyncio.sleep(0) and immediately stop.set().
    - test_chain_cache_halt_callback_wired: after run() boot (with stub heavy paths), assert chain_cache.halt_callback is coord.halt_via_chain_time (i.e., not the default).

    Implementation note: the dry-run path returns early; the test must NOT use dry_run=True. Instead, monkeypatch fill_refit_once and loss_refit_once to be no-op coroutines; pre-set stop.set() shortly after task creation; and inspect the task list before cancel.
  </behavior>
  <action>
1. Read python/src/boros_brain/main.py lines 144-220 to see the exact spawn pattern and indentation conventions.

2. Add the new imports at the top of main.py (after the existing imports). Place the decision package imports near the loss_model and fill_model imports for grouping.

3. Insert the spawn block per <behavior> just before the existing `try: await stop.wait()` line. Construct gas_cache, breakers list, coord, wire chain_cache.halt_callback, define _decision_loop async function, create the task.

4. Extend the cancellation tuple to include decision_task.

5. Add the _build_evaluate_input helper in main.py — minimal v0.5 implementation that constructs an EvaluateInput from an order dict using safe defaults for fields that Phase 6 hands will populate later (e.g. queue_ahead_wei=0, current_features={}, p_purge=0.0, r_me_per_epoch_pendle_accumulated_so_far=0.0). The competition_history and market_reward_calibration values come from the latest rows in those tables (or 0.0 fallback).

6. Add the read_open_orders_for_market helper to python/src/boros_brain/state/writers/open_orders.py (the file already has TEST_ONLY=True for hands-owned table; adding a read helper is fine — sqlite_writer_lint only checks WRITES).

7. Update python/tests/test_main_decision_loop_spawn.py — remove importorskip; implement two tests:
   - test_decision_loop_task_created: monkeypatch fill_refit_once and loss_refit_once to async no-ops; monkeypatch CompetitionTracker run_one_cycle to no-op; await run() in a task, after 100ms set stop, then inspect asyncio.all_tasks() before await; assert at least one task's coroutine name contains "_decision_loop".
   - test_chain_cache_halt_callback_wired: similar setup; after stop, assert that the coord.halt_via_chain_time is bound to chain_cache.halt_callback during the run window.

   These tests are intentionally light-touch (they verify wiring, not behavior). Heavy behavior tests live in test_breaker_coordinator_exclusive.

Self-verification: cd python ; uv run pytest tests/test_main_decision_loop_spawn.py -x exits 0; existing tests still pass (test_competition_tracker, test_zmq_kill_priority etc.).
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_main_decision_loop_spawn.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/src/boros_brain/main.py contains "from .decision.breaker_coordinator import BreakerCoordinator"
    - File python/src/boros_brain/main.py contains "from .decision.engine import evaluate"
    - File python/src/boros_brain/main.py contains "_decision_loop"
    - File python/src/boros_brain/main.py contains "MarginTrajectoryBreaker"
    - File python/src/boros_brain/main.py contains "LossFitDegradedBreaker"
    - File python/src/boros_brain/main.py contains "chain_cache.halt_callback = coord.halt_via_chain_time"
    - File python/src/boros_brain/main.py contains "decision_task"
    - grep -q "read_open_orders_for_market" python/src/boros_brain/state/writers/open_orders.py
    - cd python ; uv run pytest tests/test_main_decision_loop_spawn.py -x exits 0
    - cd python ; uv run pytest tests/test_zmq_kill_priority.py tests/test_competition_tracker.py -x exits 0 (existing tests still pass)
    - python3 scripts/no_time_time_lint.py exits 0
    - python3 scripts/architecture_lint.py exits 0
  </acceptance_criteria>
  <done>main.py spawns 1 Hz _decision_loop; chain_cache.halt_callback wired through coordinator; cancellation discipline preserved; tests GREEN.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Final architecture delta — coordinator + cli + predeploy_gate + main.py edits + manifest leaf test</name>
  <files>
    docs/architecture.yml,
    docs/ARCHITECTURE.md,
    python/tests/test_phase4_manifest_leaves.py
  </files>
  <read_first>
    - docs/architecture.yml (current Phase 4 Wave 2A/2B/2C state)
    - docs/ARCHITECTURE.md (current Phase 4 Mermaid)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (Architecture Manifest Delta lines 957-1090)
    - python/tests/test_manifest_contains_all_knobs.py (lines 137-200 — test_phase3_leaves_surfaced; mirror line-for-line)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-PATTERNS.md (lines 1182-1208 — manifest leaf-count pattern)
    - python/src/boros_brain/decision/config.py (final BotConfig delta, count of decision.* leaves)
  </read_first>
  <behavior>
    Append the FULL Phase 4 architecture delta — this task is the single atomic point where ALL Phase-4 nodes/edges land. Plans 04-04 and 04-05 deferred their arch edits here to avoid Wave-2 parallel-execution merge conflicts on docs/architecture.yml + docs/ARCHITECTURE.md.

    Module nodes (15 total — 13 deferred from 04-04/05 + 3 native to 04-06):
      Deferred from 04-04 (6 breakers):
        - brain.decision.breakers.margin_trajectory
        - brain.decision.breakers.oracle_stale
        - brain.decision.breakers.clo_removal
        - brain.decision.breakers.clo_shift
        - brain.decision.breakers.fill_rate
        - brain.decision.breakers.loss_fit_degraded
      Deferred from 04-05 (4 breakers + 1 helper):
        - brain.decision.breakers.competition
        - brain.decision.breakers.maturity
        - brain.decision.breakers.side_budget
        - brain.decision.breakers.underlying_stale
        - brain.data.underlying_apr_reader
      Native to 04-06:
        - brain.decision.breaker_coordinator
        - brain.decision.predeploy_gate
        - brain.decision.cli

    Edges (atomic, ~50 total):
      Deferred from 04-04 (13 edges — see step 1b in <action>): margin_trajectory reads/depends-on-config, oracle_stale calls/depends-on-config, clo_removal/clo_shift reads/depends-on-config (incl. voluntary_cancel_forfeits_accumulated), fill_rate reads/depends-on-config, loss_fit_degraded reads.
      Deferred from 04-05 (11 edges — see step 1d in <action>): competition reads/depends-on-config, maturity calls/reads/depends-on-config, side_budget reads/depends-on-config, underlying_stale calls/depends-on-config, underlying_apr_reader reads parquet.underlying_apr, and the new competition_tracker -> state.competition_history WRITES edge.
      Native 04-06 (~24 edges — see step 1f in <action>):
        - brain.main -> brain.decision.breaker_coordinator (calls)
        - brain.main -> brain.decision.engine (calls)
        - brain.main -> brain.decision.gas_history (calls)
        - brain.main -> brain.decision.breakers.* (10 calls — one per breaker class instantiation)
        - brain.decision.breaker_coordinator -> brain.bus.cmd (calls — send_kill, send_cmd)
        - brain.decision.breaker_coordinator -> state.breaker_events (writes via state.writers.breaker_events)
        - brain.decision.breaker_coordinator -> brain.data.chain_time (subscribes-to — halt_callback target)
        - brain.decision.engine -> brain.decision.breaker_coordinator (emits-event — engine emits decisions to coord.gate)
        - brain.decision.breaker_coordinator -> brain.decision.engine (subscribes-to — coord gates engine output)
        - brain.decision.predeploy_gate -> brain.screener.economics_gate (calls)
        - brain.decision.predeploy_gate -> state.predeploy_gate_records (writes via state.writers)
        - brain.decision.cli -> brain.decision.predeploy_gate (calls)
        - brain.decision.cli -> brain.manifest.writer (calls)
        - brain.main -> state.decisions (writes via insert_decision)
        - brain.main -> state.open_orders (reads via read_open_orders_for_market)

    Mermaid: full Phase 4 sub-graph showing the data flow:
      [DataSources] -> [Per-cycle breaker sweep] -> [BreakerCoordinator]
      [In-flight orders] -> [DecisionEngine] -> [BreakerCoordinator gate]
      [BreakerCoordinator] -> [CmdBus cmd PUSH] / [CmdBus kill PUSH (priority lane)]

    test_phase4_manifest_leaves.py: assert >=25 decision.* leaves; spot-check the 10 specific leaves listed in Plan 04-01 Task 2.
  </behavior>
  <action>
1. Append to docs/architecture.yml the FULL Phase 4 atomic delta. This is the SINGLE place where ALL Phase-4 architecture nodes/edges land — plans 04-04 and 04-05 deliberately deferred their arch edits here to avoid Wave-2 parallel-execution merge conflicts on docs/architecture.yml + docs/ARCHITECTURE.md. Plan 04-03's arch delta is already in place from its own task.

   ### Step 1a: Append the 04-04 breaker module nodes (deferred from plan 04-04 Task 6):

   ```yaml
   # ── Phase 4 Wave 2B breakers SAFE-01..05 + B5 — deferred from Plan 04-04 ─
   - id: brain.decision.breakers.margin_trajectory
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/margin_trajectory.py
     public_functions: [MarginTrajectoryBreaker]

   - id: brain.decision.breakers.oracle_stale
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/oracle_stale.py
     public_functions: [OracleStaleBreaker]

   - id: brain.decision.breakers.clo_removal
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/clo_removal.py
     public_functions: [CloRemovalBreaker]

   - id: brain.decision.breakers.clo_shift
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/clo_shift.py
     public_functions: [CloShiftBreaker]

   - id: brain.decision.breakers.fill_rate
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/fill_rate.py
     public_functions: [FillRateBreaker]

   - id: brain.decision.breakers.loss_fit_degraded
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/loss_fit_degraded.py
     public_functions: [LossFitDegradedBreaker]
   ```

   ### Step 1b: Append the 04-04 breaker edges (deferred from plan 04-04 Task 6):

   ```yaml
   # ── Phase 4 Wave 2B breaker edges — deferred from Plan 04-04 ─────
   - {from: brain.decision.breakers.margin_trajectory, to: state.margin_history, type: reads}
   - {from: brain.decision.breakers.margin_trajectory, to: config.decision.breakers.margin.window_s, type: depends-on-config}
   - {from: brain.decision.breakers.margin_trajectory, to: config.decision.breakers.margin.min_samples, type: depends-on-config}
   - {from: brain.decision.breakers.margin_trajectory, to: config.decision.breakers.margin.time_to_mm_threshold_s, type: depends-on-config}
   - {from: brain.decision.breakers.oracle_stale, to: brain.data.findex_reader, type: calls}
   - {from: brain.decision.breakers.oracle_stale, to: config.decision.breakers.oracle_stale.fraction_of_max, type: depends-on-config}
   - {from: brain.decision.breakers.clo_removal, to: state.clo_history, type: reads}
   - {from: brain.decision.breakers.clo_shift, to: state.clo_history, type: reads}
   - {from: brain.decision.breakers.clo_shift, to: config.decision.breakers.clo_shift.n_ticks, type: depends-on-config}
   - {from: brain.decision.breakers.clo_shift, to: config.strategy.voluntary_cancel_forfeits_accumulated, type: depends-on-config}
   - {from: brain.decision.breakers.fill_rate, to: state.tx_receipts, type: reads}
   - {from: brain.decision.breakers.fill_rate, to: config.decision.breakers.fill_rate.k_fills_per_hour, type: depends-on-config}
   - {from: brain.decision.breakers.loss_fit_degraded, to: state.loss_grid_artifacts, type: reads}
   ```

   ### Step 1c: Append the 04-05 breaker module nodes + helper module (deferred from plan 04-05 Task 5):

   ```yaml
   # ── Phase 4 Wave 2C breakers SAFE-06..09 — deferred from Plan 04-05 ──
   - id: brain.decision.breakers.competition
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/competition.py
     public_functions: [CompetitionBreaker]

   - id: brain.decision.breakers.maturity
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/maturity.py
     public_functions: [MaturityBreaker]

   - id: brain.decision.breakers.side_budget
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/side_budget.py
     public_functions: [SideBudgetBreaker]

   - id: brain.decision.breakers.underlying_stale
     type: module
     process: brain
     path: python/src/boros_brain/decision/breakers/underlying_stale.py
     public_functions: [UnderlyingStaleBreaker]

   - id: brain.data.underlying_apr_reader
     type: module
     process: brain
     path: python/src/boros_brain/data/underlying_apr_reader.py
     public_functions: [read_underlying_apr_max_ts]
   ```

   ### Step 1d: Append the 04-05 breaker edges + new competition_tracker write edge (deferred from plan 04-05 Task 5):

   ```yaml
   # ── Phase 4 Wave 2C breaker edges — deferred from Plan 04-05 ─────
   - {from: brain.decision.breakers.competition, to: state.competition_history, type: reads}
   - {from: brain.decision.breakers.competition, to: config.decision.breakers.competition.drop_threshold, type: depends-on-config}
   - {from: brain.decision.breakers.maturity, to: brain.decision.gas_history, type: calls}
   - {from: brain.decision.breakers.maturity, to: state.decisions, type: reads}
   - {from: brain.decision.breakers.maturity, to: config.execution.entrance_fee_pendle, type: depends-on-config}
   - {from: brain.decision.breakers.side_budget, to: state.market_reward_calibration, type: reads}
   - {from: brain.decision.breakers.side_budget, to: config.decision.breakers.side_budget.drift_threshold, type: depends-on-config}
   - {from: brain.decision.breakers.underlying_stale, to: brain.data.underlying_apr_reader, type: calls}
   - {from: brain.decision.breakers.underlying_stale, to: config.decision.breakers.underlying_stale.expected_cadence_s_per_exchange, type: depends-on-config}
   - {from: brain.data.underlying_apr_reader, to: parquet.underlying_apr, type: reads}
   - {from: brain.reward_model.competition_tracker, to: state.competition_history, type: writes}
   ```

   If `parquet.underlying_apr` is not yet declared as a storage node, add it in the storage section. If `state.competition_history` is not yet declared, ensure it is (Plan 03-02 / 04-02 should have registered it).

   ### Step 1e: Append the 04-06 native nodes (BreakerCoordinator, predeploy_gate, cli):

   ```yaml
   # ── Phase 4 Wave 3 final — Plan 04-06 ──────────────────────────
   - id: brain.decision.breaker_coordinator
     type: module
     process: brain
     path: python/src/boros_brain/decision/breaker_coordinator.py
     public_functions: [BreakerCoordinator]

   - id: brain.decision.predeploy_gate
     type: module
     process: brain
     path: python/src/boros_brain/decision/predeploy_gate.py
     public_functions: [run_predeploy_gate]

   - id: brain.decision.cli
     type: module
     process: brain
     path: python/src/boros_brain/decision/cli.py
     public_functions: [main, build_parser]
   ```

   ### Step 1f: Append the 04-06 native edges (coordinator wiring, main.py spawn, decision.engine subscribes-to / emits-event relationships):

   ```yaml
   # ── Phase 4 Wave 3 final edges — Plan 04-06 ─────────────────────
   - {from: brain.main, to: brain.decision.breaker_coordinator, type: calls}
   - {from: brain.main, to: brain.decision.engine, type: calls}
   - {from: brain.main, to: brain.decision.gas_history, type: calls}
   - {from: brain.main, to: brain.decision.breakers.margin_trajectory, type: calls}
   - {from: brain.main, to: brain.decision.breakers.oracle_stale, type: calls}
   - {from: brain.main, to: brain.decision.breakers.clo_removal, type: calls}
   - {from: brain.main, to: brain.decision.breakers.clo_shift, type: calls}
   - {from: brain.main, to: brain.decision.breakers.fill_rate, type: calls}
   - {from: brain.main, to: brain.decision.breakers.competition, type: calls}
   - {from: brain.main, to: brain.decision.breakers.maturity, type: calls}
   - {from: brain.main, to: brain.decision.breakers.side_budget, type: calls}
   - {from: brain.main, to: brain.decision.breakers.underlying_stale, type: calls}
   - {from: brain.main, to: brain.decision.breakers.loss_fit_degraded, type: calls}
   - {from: brain.decision.breaker_coordinator, to: brain.bus.cmd, type: calls}
   - {from: brain.decision.breaker_coordinator, to: state.breaker_events, type: writes}
   - {from: brain.decision.breaker_coordinator, to: brain.data.chain_time, type: subscribes-to}
   - {from: brain.decision.engine, to: brain.decision.breaker_coordinator, type: emits-event}
   - {from: brain.decision.breaker_coordinator, to: brain.decision.engine, type: subscribes-to}
   - {from: brain.decision.predeploy_gate, to: brain.screener.economics_gate, type: calls}
   - {from: brain.decision.predeploy_gate, to: state.predeploy_gate_records, type: writes}
   - {from: brain.decision.cli, to: brain.decision.predeploy_gate, type: calls}
   - {from: brain.decision.cli, to: brain.manifest.writer, type: calls}
   - {from: brain.main, to: state.decisions, type: writes}
   - {from: brain.main, to: state.open_orders, type: reads}
   ```

2. Update docs/ARCHITECTURE.md — replace the Phase 4 Mermaid section with the full picture per RESEARCH §System Architecture Diagram (lines 177-249). The diagram must show:
   - 1 Hz Decision Loop subgraph (chain_time -> open_orders read -> per-order EV evaluation -> Engine -> Coordinator -> writer)
   - Per-Cycle Breaker Sweep subgraph (10 breaker boxes)
   - EV Inputs subgraph (predict, expected_loss, r_capped_curve, gas_history)
   - Already-Polled State subgraph (chain_time, REST, SQLite, parquet)
   - Hands-bound Commands subgraph (CmdBus -> ipc cmd PUSH / ipc kill PUSH PRIORITY LANE)

3. Update python/tests/test_phase4_manifest_leaves.py — remove importorskip / xfail; implement test_phase4_leaves_surfaced. Use _collect_leaf_paths from test_manifest_contains_all_knobs.py:

   ```python
   from .test_manifest_contains_all_knobs import _collect_leaf_paths
   ```

   (or duplicate the helper inline if importing across test files is cleaner.)

   Body:
   ```python
   def test_phase4_leaves_surfaced(default_config: BotConfig) -> None:
       leaves = _collect_leaf_paths(BotConfig)
       leaf_strs = [".".join(leaf) for leaf in leaves]
       decision_leaves = [s for s in leaf_strs if s.startswith("decision.")]
       assert len(decision_leaves) >= 25, (
           f"expected >=25 decision leaves, got {len(decision_leaves)}: {decision_leaves}"
       )
       # Spot-check 10 critical leaves
       for must in [
           "decision.cancel_cost_ewma_alpha",
           "decision.cancel_cost_ttl_s",
           "decision.cancel_cost_block_window",
           "decision.decision_loop_interval_s",
           "decision.breakers.margin.window_s",
           "decision.breakers.oracle_stale.fraction_of_max",
           "decision.breakers.clo_shift.n_ticks",
           "decision.breakers.fill_rate.k_fills_per_hour",
           "decision.breakers.competition.drop_threshold",
           "decision.breakers.side_budget.drift_threshold",
       ]:
           assert must in decision_leaves, f"{must} missing from manifest reflection"
   ```

4. Run python3 scripts/architecture_lint.py — must exit 0.

Self-verification: full test suite passes; architecture lint clean.
  </action>
  <verify>
    <automated>python3 scripts/architecture_lint.py ; cd python ; uv run pytest tests/test_phase4_manifest_leaves.py -x</automated>
  </verify>
  <acceptance_criteria>
    - grep -q "brain.decision.breaker_coordinator" docs/architecture.yml
    - grep -q "brain.decision.predeploy_gate" docs/architecture.yml
    - grep -q "brain.decision.cli" docs/architecture.yml
    - grep -q "brain.decision.breakers.margin_trajectory" docs/architecture.yml
    - grep -q "brain.decision.breakers.oracle_stale" docs/architecture.yml
    - grep -q "brain.decision.breakers.clo_removal" docs/architecture.yml
    - grep -q "brain.decision.breakers.clo_shift" docs/architecture.yml
    - grep -q "brain.decision.breakers.fill_rate" docs/architecture.yml
    - grep -q "brain.decision.breakers.loss_fit_degraded" docs/architecture.yml
    - grep -q "brain.decision.breakers.competition" docs/architecture.yml
    - grep -q "brain.decision.breakers.maturity" docs/architecture.yml
    - grep -q "brain.decision.breakers.side_budget" docs/architecture.yml
    - grep -q "brain.decision.breakers.underlying_stale" docs/architecture.yml
    - grep -q "brain.data.underlying_apr_reader" docs/architecture.yml
    - grep -q "brain.main, to: brain.decision.breaker_coordinator" docs/architecture.yml
    - grep -q "breaker_coordinator, to: state.breaker_events" docs/architecture.yml
    - grep -q "brain.decision.engine, to: brain.decision.breaker_coordinator" docs/architecture.yml
    - grep -q "breaker_coordinator, to: brain.decision.engine" docs/architecture.yml
    - grep -q "brain.main, to: state.decisions" docs/architecture.yml
    - grep -q "competition_tracker, to: state.competition_history" docs/architecture.yml
    - grep -q "underlying_apr_reader, to: parquet.underlying_apr" docs/architecture.yml
    - grep -q "1 Hz Decision Loop\|Decision Loop" docs/ARCHITECTURE.md
    - grep -q "PRIORITY LANE\|kill PUSH" docs/ARCHITECTURE.md
    - python3 scripts/architecture_lint.py exits 0
    - cd python ; uv run pytest tests/test_phase4_manifest_leaves.py -x exits 0
  </acceptance_criteria>
  <done>Final Phase-4 architecture delta atomic — ALL Phase-4 nodes/edges land in this single task: 6 breakers from 04-04, 4 breakers + underlying_apr_reader from 04-05, BreakerCoordinator + predeploy_gate + cli from 04-06, plus all corresponding edges (reads, writes, calls, depends-on-config, subscribes-to, emits-event); manifest leaf-count test PASSES with >=25 decision.* leaves.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Phase 4 ship-gate — full test suite GREEN + lint clean + final wiki</name>
  <files>
    python/tests/test_phase4_manifest_leaves.py
  </files>
  <read_first>
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md (Validation Sign-Off checklist line 99-112)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (LLM Wiki Pages to Write-Back lines 1532-1557)
  </read_first>
  <behavior>
    Final gate: run the full test suite, run all 5 lint scripts, file the remaining wiki pages (decision-engine-ev-rule-implementation-v05 was filed in 04-03; now file breaker-coordinator-kill-mutex.md and predeploy-gate-cli.md). Touch test_phase4_manifest_leaves.py docstring with cross-references to all Phase 4 wiki pages.

    Verification commands MUST exit 0:
      cd python ; uv run pytest -x
      python3 scripts/architecture_lint.py
      python3 scripts/sqlite_writer_lint.py --root .
      python3 scripts/no_time_time_lint.py
      python3 scripts/no_hardcoded_cancel_cost_lint.py
      python3 scripts/no_threshold_dials_lint.py
      python3 scripts/wiki_cite_lint.py
  </behavior>
  <action>
1. Update .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md frontmatter:
   - Flip `nyquist_compliant: false` -> `nyquist_compliant: true`
   - Flip `wave_0_complete: false` -> `wave_0_complete: true`
   - Update `Approval: pending` -> `Approval: signed-off (plan 04-06 ship-gate)`
   This is the validation-checkpoint flip required by the Wave 0 contract — only flip after all Phase-4 tests are GREEN and all 6 lint scripts pass.

2. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-coordinator-kill-mutex.md with content:
   - Status: Current
   - SAFE-10 spec; the brain-side mutex; rising-edge KillCmd discipline; Pitfall #6 hysteresis (min_re_arm_s); Pitfall #2 no in-memory log (every suppression to state.breaker_events); Pitfall #1 200ms per-breaker timeout; Pitfall #9 ZMQ LINGER notes.
   - Cross-references: [[zmq-bus-topology-v05]], [[circuit-breakers-v05]]

3. File /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/predeploy-gate-cli.md with content:
   - Status: Current
   - A5 absorbed; CLI subcommand python -m boros_brain.decision predeploy-gate
   - Pitfall #8: git_sha + config_hash stamped in state.predeploy_gate_records; Phase 7 boot reads latest record
   - Cross-references: [[economics-kill-switch-v05]], [[circuit-breakers-v05]]

4. Update [[circuit-breakers-v05]] index page: add a section "## Coordinator + Predeploy Gate" linking to [[breaker-coordinator-kill-mutex]] and [[predeploy-gate-cli]].

5. Touch python/tests/test_phase4_manifest_leaves.py module docstring: add a cross-reference list of all Phase 4 wiki pages filed in plans 04-01..04-06.

6. Run the final gate sequence:
   - cd python ; uv run pytest -x  (FULL test suite GREEN — must include the new test_breaker_coordinator_publishes_kill_lane_per_safe.py)
   - python3 scripts/architecture_lint.py
   - python3 scripts/sqlite_writer_lint.py --root .
   - python3 scripts/no_time_time_lint.py
   - python3 scripts/no_hardcoded_cancel_cost_lint.py
   - python3 scripts/no_threshold_dials_lint.py
   - python3 scripts/wiki_cite_lint.py  (every research/decision/postmortem markdown cites a wiki page)

7. If any test or lint fails, fix BEFORE declaring this task done. Phase 4 is the kill-authority component — its ship gate is non-negotiable. ONLY after step 6 passes do you flip the 04-VALIDATION.md frontmatter flags in step 1 — verify the flip is the LAST git-tracked change in this plan's commit.

Self-verification: All 6 verification commands exit 0.
  </action>
  <verify>
    <automated>cd python ; uv run pytest -x</automated>
  </verify>
  <acceptance_criteria>
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-coordinator-kill-mutex.md" exists
    - File "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/predeploy-gate-cli.md" exists
    - grep -q "Status: Current" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-coordinator-kill-mutex.md"
    - grep -q "SAFE-10\|exclusive kill authority" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/breaker-coordinator-kill-mutex.md"
    - grep -q "Pitfall #8\|config_hash" "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/predeploy-gate-cli.md"
    - cd python ; uv run pytest -x exits 0
    - python3 scripts/architecture_lint.py exits 0
    - python3 scripts/sqlite_writer_lint.py --root . exits 0
    - python3 scripts/no_time_time_lint.py exits 0
    - python3 scripts/no_hardcoded_cancel_cost_lint.py exits 0
    - python3 scripts/no_threshold_dials_lint.py exits 0
    - python3 scripts/wiki_cite_lint.py exits 0
    - grep -q "^nyquist_compliant: true" .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md
    - grep -q "^wave_0_complete: true" .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md
  </acceptance_criteria>
  <done>Phase 4 ship-gate: full test suite GREEN; all 6 lint scripts pass; final wiki pages filed; 04-VALIDATION.md frontmatter flipped (nyquist_compliant=true, wave_0_complete=true); ready for /gsd-verify-work 4.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 6: SAFE composition end-to-end test (parametrized over SAFE-01..09 + B5)</name>
  <files>
    python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
  </files>
  <read_first>
    - python/tests/test_breaker_coordinator_exclusive.py (Task 1 — pattern for real CmdBus + ipc_dir + zmq.PULL pattern; copy verbatim)
    - python/tests/test_zmq_kill_priority.py (priority-lane PUSH/PULL HWM contract)
    - python/tests/test_breaker_margin_trajectory.py through test_breaker_loss_fit_degraded.py (each has a tripping fixture this task reuses)
    - python/src/boros_brain/decision/breaker_coordinator.py (just landed in Task 1)
    - python/src/boros_brain/decision/breakers/{margin_trajectory,oracle_stale,clo_removal,clo_shift,fill_rate,competition,maturity,side_budget,underlying_stale,loss_fit_degraded}.py (all 10 breakers from plans 04-04 / 04-05)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-VALIDATION.md (Validation Sign-Off bullet about every SAFE having a trigger-fixture asserting the correct ZMQ KILL-lane message)
    - .planning/phases/04-decision-engine-predictive-circuit-breakers/04-RESEARCH.md (per-SAFE kill_command_kind table)
  </read_first>
  <behavior>
    The test is a parametrized end-to-end composition test. The Wave-0 RED stub (added by plan 04-01 Task 3) is a `pytest.importorskip` skeleton; this task turns it GREEN by:
      1. For each parameter (one per SAFE-01..09 + B5 loss_fit_degraded — 10 cases), construct a real instance of the matching breaker (MarginTrajectoryBreaker, OracleStaleBreaker, etc.) with a tripping fixture (reuse the trigger fixtures already built in plan 04-04/05 unit tests — e.g. seed_margin_history(slope=-1.0), monkeypatch findex_reader to return stale, seed_clo_history with clo_lower=0, etc.).
      2. Build a real CmdBus over the ipc_dir fixture (cmd_endpoint = ipc://{ipc_dir}/cmd; kill_endpoint = ipc://{ipc_dir}/cmd.kill).
      3. Bind a zmq.PULL socket on the kill_endpoint BEFORE creating the CmdBus (slow-joiner protection — sleep 0.05).
      4. Build a BreakerCoordinator with breakers=[<the_one_breaker>] and run coord.tick() once.
      5. Receive on the kill_pull socket with timeout 0.5s; assert the message has kind="kill" and the `payload.kind` (or equivalent kill_command_kind field) matches the expected ZMQ message kind for that SAFE per the table below:

      | SAFE | Breaker class | Expected kill_command_kind |
      |------|---------------|------------------------------|
      | SAFE-01 | MarginTrajectoryBreaker | EMERGENCY_CLOSE |
      | SAFE-02 | OracleStaleBreaker | CANCEL_ALL |
      | SAFE-03 | CloRemovalBreaker | CANCEL_ALL_AND_ALERT |
      | SAFE-04 | CloShiftBreaker | CANCEL_ALL_AND_RECALIBRATE |
      | SAFE-05 | FillRateBreaker | PAUSE_AND_ALERT |
      | SAFE-06 | CompetitionBreaker | PAUSE_AND_ALERT |
      | SAFE-07 | MaturityBreaker | ROLL_POSITION |
      | SAFE-08 | SideBudgetBreaker | HALVE_POSITION_AND_ALERT |
      | SAFE-09 | UnderlyingStaleBreaker | HALT_AND_ALERT |
      | B5 (loss_fit_degraded) | LossFitDegradedBreaker | SHRINK_TO_Q_MIN |

      Note: SAFE-10 is the BreakerCoordinator itself (kill-authority exclusivity). It is NOT in this parametrized set — it is covered by `test_breaker_coordinator_exclusive.py` (Task 1).

      6. Each parameter passes its OWN tripping fixture builder (a callable receiving the test fixtures and returning the configured breaker + sqlite_path/parquet_root state). Use pytest.mark.parametrize with `ids=["SAFE-01","SAFE-02",...]` so failures are easy to locate.

      7. For the SAFE-04 (CloShiftBreaker) parameter, the default config has `voluntary_cancel_forfeits_accumulated=False` so the expected kill_command_kind is `CANCEL_ALL_AND_RECALIBRATE`. The punitive-branch variant `CANCEL_ALL_HOLD_NO_REPLACE` is covered by the unit test in plan 04-04 — not duplicated here.
  </behavior>
  <action>
1. Open python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py (lands as a RED stub from plan 04-01 Task 3 with `pytest.importorskip` at module top). Remove the importorskip guard now that BreakerCoordinator + all 10 breaker modules exist.

2. Replace the stub with the real parametrized test. Structure:

```python
"""SAFE-01..09 + B5 composition end-to-end test (Plan 04-06 Task 6).

Per Phase 4 success criterion #2: each of SAFE-01..09 must cause the ZMQ CANCEL_ALL or
EMERGENCY_CLOSE (or equivalent kill_command_kind) message to be published on the priority
KILL lane. SAFE-10 is the coordinator itself — covered by test_breaker_coordinator_exclusive.

See [[circuit-breakers-v05]] and [[breaker-coordinator-kill-mutex]].
"""
from __future__ import annotations
import asyncio
from pathlib import Path
import pytest
import zmq
import zmq.asyncio
from boros_brain.bus.cmd import CmdBus
from boros_brain.config.schema import BotConfig
from boros_brain.decision.breaker_coordinator import BreakerCoordinator
# imports for all 10 breakers …

# Define one fixture-builder per SAFE — each returns (breaker_instance, sqlite_path, parquet_root, current_chain_ts)
# (use the seed-helpers from conftest.py; reuse the trigger fixtures from plan 04-04/05 unit tests)

SAFE_CASES = [
    ("SAFE-01", _build_safe_01_fixture, "EMERGENCY_CLOSE"),
    ("SAFE-02", _build_safe_02_fixture, "CANCEL_ALL"),
    # … all 10 cases per the table in <behavior>
]

@pytest.mark.asyncio
@pytest.mark.parametrize("safe_id,build_fixture,expected_kind", SAFE_CASES,
                         ids=[c[0] for c in SAFE_CASES])
async def test_safe_publishes_kill_lane(safe_id, build_fixture, expected_kind,
                                          tmp_path: Path, default_config: BotConfig,
                                          ipc_dir: Path, monkeypatch,
                                          # the seed-helper fixtures it needs:
                                          seed_margin_history, seed_clo_history,
                                          seed_competition_history,
                                          seed_market_reward_calibration,
                                          seed_loss_grid_artifact,
                                          seed_tx_receipts_fills,
                                          seed_underlying_apr_parquet) -> None:
    breaker, sqlite_path, parquet_root, current_chain_ts = await build_fixture(
        tmp_path, default_config, monkeypatch,
        seed_margin_history=seed_margin_history,
        seed_clo_history=seed_clo_history,
        seed_competition_history=seed_competition_history,
        seed_market_reward_calibration=seed_market_reward_calibration,
        seed_loss_grid_artifact=seed_loss_grid_artifact,
        seed_tx_receipts_fills=seed_tx_receipts_fills,
        seed_underlying_apr_parquet=seed_underlying_apr_parquet,
    )

    # Bind PULL on kill endpoint BEFORE building CmdBus (slow-joiner protection)
    ctx = zmq.asyncio.Context.instance()
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.bind(f"ipc://{ipc_dir}/cmd.kill")
    await asyncio.sleep(0.05)
    cmd_bus = CmdBus(cmd_endpoint=f"ipc://{ipc_dir}/cmd",
                     kill_endpoint=f"ipc://{ipc_dir}/cmd.kill")

    coord = BreakerCoordinator(cmd_bus=cmd_bus, config=default_config,
                                run_id="test-safe-composition",
                                gas_cache=None, breakers=[breaker])

    await coord.tick(sqlite_path=sqlite_path, w3=None,
                     parquet_root=parquet_root,
                     current_chain_ts=current_chain_ts)

    msg = await asyncio.wait_for(kill_pull.recv_json(), timeout=0.5)
    assert msg["kind"] == "kill", f"{safe_id} did not produce a kill message; got {msg!r}"
    # Coordinator wraps kill_command_kind into the KillCmd payload — check it surfaces.
    # Exact field name depends on KillCmd schema; assert the expected_kind appears in
    # either msg['payload']['kill_command_kind'] OR msg['reason']:
    payload = msg.get("payload", {})
    found = (payload.get("kill_command_kind") == expected_kind
             or expected_kind in str(msg.get("reason", "")))
    assert found, f"{safe_id}: expected kill_command_kind={expected_kind}; msg={msg!r}"

    kill_pull.close()
```

3. Implement the 10 fixture-builders (one per SAFE) as module-level async helpers. Each builds the appropriate seeded state and returns the configured breaker. Reuse seed-helpers from conftest.py; for SAFE-02 (oracle_stale) and SAFE-04 (clo_shift) use monkeypatch to stub the chain-state reads; for SAFE-09 (underlying_stale) use the seed_underlying_apr_parquet fixture to write a stale parquet row; for B5 (loss_fit_degraded) use seed_loss_grid_artifact(fit_status="degraded").

4. The 6 lint scripts in Task 5 step 6 run AFTER this task lands so any new SQL or hardcoded threshold introduced by the fixture-builders will be caught. Keep fixture-builders in this single test file — do NOT add helper code to production source modules.

Self-verification: cd python ; uv run pytest tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py -x exits 0 with all 10 parametrized cases PASSING.
  </action>
  <verify>
    <automated>cd python ; uv run pytest tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py -x</automated>
  </verify>
  <acceptance_criteria>
    - File python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py exists and contains "@pytest.mark.parametrize"
    - grep -q "SAFE-01" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "SAFE-09" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "loss_fit_degraded\|B5" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "EMERGENCY_CLOSE" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "SHRINK_TO_Q_MIN" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "ROLL_POSITION" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "HALT_AND_ALERT" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - grep -q "ipc_dir" python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py
    - cd python ; uv run pytest tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py -x exits 0
    - cd python ; uv run pytest tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py --collect-only 2>&1 | grep -E "10 tests collected"
  </acceptance_criteria>
  <done>SAFE composition test parametrized over 10 cases (SAFE-01..09 + B5); each tripping fixture produces the correct ZMQ kill_command_kind on the priority KILL lane; success criterion #2 verified end-to-end.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| BreakerCoordinator -> CmdBus.send_kill | The coordinator OWNS the brain-side kill mutex. No other component is authorized to call send_kill (architecturally enforced; lint can grep for direct send_kill calls outside the coordinator). |
| BreakerCoordinator -> CmdBus.send_cmd | Decisions only enter cmd_bus through coord.gate. Engine never calls send_cmd directly (architecturally enforced). |
| ChainTimeCache.halt_callback -> coord.halt_via_chain_time | Replaces the log-only default; chain_drift halt routes through KILL lane. |
| predeploy_gate.run_screener -> screener.economics_gate | Single entry point for re-screen; the gate's exit code (0/1) is the mechanical Phase 6->7 transition guard. |
| state.predeploy_gate_records.config_hash -> Phase 7 boot | Phase 7 startup reads the latest record and refuses to start on hash mismatch. Config drift between gate-time and run-time is mechanically blocked. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-06-01 | E (Elevation of privilege) | Bypass of breaker coordinator | mitigate | The architecture invariant is: "every PLACE / CANCEL command enters CmdBus.send_cmd ONLY through BreakerCoordinator.gate." Tests in test_breaker_coordinator_exclusive verify this end-to-end with real ZMQ over ipc://. A future contributor wiring a direct CmdBus.send_cmd from engine or a breaker would be caught by code review (no automatic lint exists yet — could be added in Phase 6 if regressions appear). |
| T-04-06-02 | T (Tampering) | ZMQ KILL message reordering / dropping | mitigate | Kill is a separate PUSH/PULL socket from cmd (Plan 01-03). The hands-side cmd_listener.ts drains the kill socket FIRST on every iteration. test_zmq_kill_priority.py verifies preemption end-to-end. Pitfall #9 LINGER=100ms is acceptable because hands' own watchdog (lost-sibling, 15s) cancels orders independently. |
| T-04-06-03 | T (Tampering) | Stale gas history fed to cancel_cost | mitigate | gas_history TTL=60s (Plan 04-03). On RPC failure the cache returns last_value_pendle (stale-but-known). The daily-rescreen workflow (PITFALLS Phase-4 #5) verifies eth_price_usd / pendle_price_usd freshness. Stale config knobs ARE a residual risk — mitigated by RUN_MANIFEST stamping (operator sees calibration timestamps in the manifest at boot). |
| T-04-06-04 | I (Information disclosure) | LossModel fit-degraded signal getting lost | mitigate | The signal flows: Phase 3 LossGridArtifact.fit_status='degraded' (persisted) -> Plan 04-04 LossFitDegradedBreaker reads -> Plan 04-06 BreakerCoordinator -> SHRINK_TO_Q_MIN. Every step is auditable via state.loss_grid_artifacts and state.breaker_events. The architecture.yml edge brain.decision.breakers.loss_fit_degraded -> state.loss_grid_artifacts (reads) is in place from Plan 04-04. |
| T-04-06-05 | T (Tampering) | voluntary_cancel_forfeits_accumulated flag flip | mitigate | Default = False per P0-01 LOCKED in BotConfig schema. Any change to the flag's runtime value would require a YAML edit + new RUN_MANIFEST + new run_id (knobs are frozen=True post-load — no in-process mutation). Operator sees the flag in every manifest line. Phase 5 backtest sweeps both branches as sanity check. |
| T-04-06-06 | T (Tampering) | Predeploy-gate hash mismatch silently passing | mitigate | Pitfall #8 — predeploy_gate writes the config_hash AND git_sha; Phase 7 boot reads get_latest_predeploy_gate_record and refuses to start on hash mismatch. The hash is sha256(config.model_dump_json())[:16] — collision-resistant for our scale. |
| T-04-06-07 | D (Denial of service) | Coordinator deadlock on slow breaker | mitigate | Pitfall #1 — every breaker.check is wrapped in asyncio.wait_for(timeout=0.2). On timeout the breaker returns BreakerSignal(tripped=False, reason="timeout") and the loop continues. Operator sees breaker.timeout log lines if they accumulate. |
| T-04-06-08 | R (Repudiation) | Suppression event chain | mitigate | Every kill_emitted, suppression, and rearmed event is persisted to state.breaker_events with run_id + chain_ts. Forensic replay is grep + SQL. Pitfall #2 — no in-memory log; every event durable. |
| T-04-06-09 | E (Elevation of privilege) | predeploy_gate runs against wrong config | mitigate | The gate writes config_hash + git_sha + git_dirty into the record. Phase 7 boot's hash-mismatch refusal is the second-line-of-defense. The CLI itself takes --config arg; the operator could pass a wrong file, but the manifest-first preamble logs the resolved config path so operator audit catches it. |
| T-04-06-10 | I (Information disclosure) | RUN_MANIFEST after Phase 4 | accept | Phase 4 adds ~25 new manifest leaves (decision.* + decision.breakers.*). All are bounded numerics or per-exchange dicts. No secrets, no PII. The leaf count >=25 is asserted by test_phase4_manifest_leaves. |
</threat_model>

<verification>
After all tasks complete, run:

```
cd python ; uv run pytest -x

python3 scripts/architecture_lint.py
python3 scripts/sqlite_writer_lint.py --root .
python3 scripts/no_time_time_lint.py
python3 scripts/no_hardcoded_cancel_cost_lint.py
python3 scripts/no_threshold_dials_lint.py
python3 scripts/wiki_cite_lint.py
```

All commands MUST exit 0. The full Phase 4 RED test set from Plan 04-01 (17 files) is GREEN. The Phase 4 ship-gate is satisfied; ready for /gsd-verify-work 4.
</verification>

<success_criteria>
- [ ] BreakerCoordinator owns the brain-side kill mutex; rising-edge KillCmd fires exactly once per Pitfall #6.
- [ ] coord.gate suppresses ALL PLACE/CANCEL while any breaker active; suppression events durable in state.breaker_events.
- [ ] main.py spawns 1 Hz _decision_loop; chain_cache.halt_callback wired through coord.
- [ ] predeploy_gate CLI exits 0/1 and persists git_sha + config_hash.
- [ ] Final architecture.yml + Mermaid Phase-4 delta atomic; architecture_lint clean.
- [ ] Phase 4 manifest leaf-count >=25 verified.
- [ ] FULL Phase 4 RED test suite (18 files from 04-01) is GREEN — including the new test_breaker_coordinator_publishes_kill_lane_per_safe.py parametrized over SAFE-01..09 + B5 (10 cases).
- [ ] All 6 lint scripts exit 0.
- [ ] All Phase 4 wiki pages filed with Status: Current.
- [ ] 04-VALIDATION.md frontmatter flipped: nyquist_compliant=true, wave_0_complete=true.
</success_criteria>

<output>
After completion, create `.planning/phases/04-decision-engine-predictive-circuit-breakers/04-06-SUMMARY.md` documenting:
- BreakerCoordinator (SAFE-10 exclusive kill authority + hysteresis)
- predeploy_gate CLI (A5 absorbed)
- decision/cli.py + __main__.py (manifest-first + subcommand dispatch)
- main.py 1 Hz _decision_loop spawn + chain_cache.halt_callback wire-up
- Atomic Phase 4 architecture delta (final coordinator + cli + predeploy_gate nodes + ~22 edges)
- Manifest leaf-count test PASSES (>=25 decision.* leaves)
- Final Phase 4 ship-gate: full test suite GREEN; 6 lint scripts pass
- Wiki pages filed: breaker-coordinator-kill-mutex.md, predeploy-gate-cli.md
</output>
