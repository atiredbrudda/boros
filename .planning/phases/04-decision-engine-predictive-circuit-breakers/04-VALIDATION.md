---
phase: 4
slug: decision-engine-predictive-circuit-breakers
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-25
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `04-RESEARCH.md` § Validation Architecture (line 1154+).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (Python brain) |
| **Config file** | `python/pyproject.toml` (already configured by Phase 1) |
| **Quick run command** | `cd python && uv run pytest tests/ -k decision -x` (or the explicit list under "Full suite command") |
| **Full suite command** | `cd python && uv run pytest tests/test_decision_*.py tests/test_breaker_*.py tests/test_gas_history_ewma.py tests/test_no_threshold_dials_lint.py tests/test_predeploy_gate_cli.py tests/test_main_decision_loop_spawn.py tests/test_phase4_manifest_leaves.py` |
| **Estimated runtime** | ~30 seconds (target; deterministic fixtures, no live RPC) |

> Authoritative path layout: flat `python/tests/` directory with the
> `test_decision_*` / `test_breaker_*` / `test_gas_history_ewma.py` /
> `test_no_threshold_dials_lint.py` / `test_predeploy_gate_cli.py` /
> `test_main_decision_loop_spawn.py` / `test_phase4_manifest_leaves.py`
> filenames declared in plan 04-01's `files_modified` frontmatter
> (the canonical `test_breaker_*.py` glob covers `test_breaker_coordinator_exclusive.py`,
> `test_breaker_coordinator_publishes_kill_lane_per_safe.py`, and the per-SAFE breaker tests).
> There is NO `tests/decision/` subdirectory.

---

## Sampling Rate

- **After every task commit:** Run `cd python && uv run pytest tests/ -k decision -x` (fail-fast)
- **After every plan wave:** Run the full suite command above
- **Before `/gsd-verify-work`:** Full suite must be green AND `scripts/no_hardcoded_cancel_cost_lint.py` AND `scripts/no_threshold_dials_lint.py` must pass
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Filled in during planning by `gsd-planner` from RESEARCH.md Validation Architecture section. Each of the enumerated test files maps to one task; each task gets an `<automated>` verify command. Plan-checker validates the map is complete before approving plans.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _populated by planner_ | _ | _ | _ | _ | _ | _ | _ | _ | _ |

---

## Wave 0 Requirements

> Test scaffolding that must land BEFORE engine/breaker code is written. Per RESEARCH.md, all test files are net-new (no existing test stubs cover Phase 4). Paths below match plan 04-01's `files_modified` frontmatter EXACTLY (flat `python/tests/` layout — no subdirectory).

- [ ] `python/tests/conftest.py` — extended with shared fixtures (deterministic clock, BotConfig builder, simulated book/feature stream, ZMQ mock socket pair, 7 breaker-history seed-helper fixtures)
- [ ] `python/tests/test_decision_engine_ev_equation.py` — DECIDE-01 EV-sign line-by-line stubs
- [ ] `python/tests/test_decision_engine_voluntary_branch.py` — DECIDE-02 dual-branch divergence stub
- [ ] `python/tests/test_gas_history_ewma.py` — DECIDE-03 EWMA + linter sentinel stubs
- [ ] `python/tests/test_no_threshold_dials_lint.py` — DECIDE-04 audit stub
- [ ] `python/tests/test_breaker_margin_trajectory.py` — SAFE-01
- [ ] `python/tests/test_breaker_oracle_stale.py` — SAFE-02
- [ ] `python/tests/test_breaker_clo_removal.py` — SAFE-03
- [ ] `python/tests/test_breaker_clo_shift.py` — SAFE-04
- [ ] `python/tests/test_breaker_fill_rate.py` — SAFE-05
- [ ] `python/tests/test_breaker_competition.py` — SAFE-06
- [ ] `python/tests/test_breaker_maturity.py` — SAFE-07
- [ ] `python/tests/test_breaker_side_budget.py` — SAFE-08
- [ ] `python/tests/test_breaker_underlying_stale.py` — SAFE-09
- [ ] `python/tests/test_breaker_loss_fit_degraded.py` — B5 absorption (file path uses `test_breaker_loss_fit_degraded.py`; the alias `test_loss_fit_degraded_breaker.py` is referenced in some commands for backward-compat; plan 04-01 declares the canonical name in its frontmatter)
- [ ] `python/tests/test_breaker_coordinator_exclusive.py` — SAFE-10 kill-authority exclusivity
- [ ] `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py` — SAFE-01..09 + B5 end-to-end ZMQ KILL-lane composition test (parametrized; lands as a Wave-0 RED stub guarded by `pytest.importorskip` on coordinator import; turns GREEN in plan 04-06 Task 6)
- [ ] `python/tests/test_predeploy_gate_cli.py` — A5 absorption (Phase 6→7 gate)
- [ ] `python/tests/test_main_decision_loop_spawn.py` — main.py spawn-block integration RED test
- [ ] `python/tests/test_phase4_manifest_leaves.py` — PROTO-04 leaf-count assertion (>=25 decision.* leaves)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Phase 6→7 transition gate fires on stale economics-gate hash | A5 absorption | Crosses phase boundary; depends on Phase 6 ship state | After Phase 6 lands, run `python -m brain.decision.predeploy_gate verify` and confirm exit code 1 with stale hash, exit code 0 after re-running economics gate |

---

## Nyquist Sampling Notes

| Primitive | Sampling Source | Min Cadence | Test Pattern |
|-----------|----------------|-------------|--------------|
| `DecisionEngine.evaluate()` | 1 Hz brain loop | 1 Hz | Deterministic stream of 60+ snapshot fixtures (>=60s of simulated wall time per test); EV-sign matched line-by-line against equation in `04-RESEARCH.md` § DECIDE-01 |
| Margin trajectory (SAFE-01) | `dNetBalance/dt` over sliding window | sliding window of 10 samples (10s @ 1Hz) | Synthetic descent fixture: net margin decreasing s.t. time-to-maintenance < 30s — assert breaker fires within one cycle |
| Oracle staleness (SAFE-02) | `now − fTime > 0.7 × maxUpdateDelay` | per-cycle (1 Hz) | Frozen clock + injected fTime; sweep boundary at 0.69× / 0.70× / 0.71× |
| CLO removal/shift (SAFE-03/04) | Per-cycle book snapshot | per-cycle | Fixture stream with thresholds flipping to 0 / drifting > N ticks |
| Fill-rate runaway (SAFE-05) | Sliding 1h count of fill events | per-cycle, window=1h | Inject K+1 synthetic fills at K threshold (K=3); assert pause |
| Competition collapse (SAFE-06) | `Q_total_in_range` snapshots per epoch | per-epoch | Two-snapshot fixture with 51% drop |
| Maturity migration (SAFE-07) | `time_to_maturity × R_me_per_epoch < migration_cost` | per-cycle | Edge fixture at the inequality boundary |
| Per-side budget (SAFE-08) | `E_liq_per_epoch` split delta per epoch | per-epoch | Two-snapshot fixture with 31% shift |
| Underlying-feed stale (SAFE-09) | CEX funding feed last-update timestamp | per-cycle | Stale-clock fixture at 2× expected cadence boundary |
| Loss-fit degraded (B5) | `LossGridArtifact.fit_status` event | event-driven | Mock LossModel emitting `degraded` status; assert SHRINK_TO_Q_MIN action propagated through coordinator |
| Kill-authority exclusivity (SAFE-10) | Coordinator mutex flag | per-decision-cycle | Trip any breaker; verify subsequent `DecisionEngine.PLACE` is suppressed and logged with `run_id` |
| `cancel_cost` measurement (DECIDE-03) | `w3.eth.fee_history(100, ...)` | 60s TTL cache | Mock RPC returning known fee history; assert EWMA(α=0.1) matches expected; assert linter flags any commit with hardcoded scalar in `cancel_cost` field |

---

## Validation Sign-Off

- [ ] All 14 phase requirements (DECIDE-01..04, SAFE-01..10) have at least one `<automated>` verification command
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify in the per-task map
- [ ] Wave 0 test scaffolding files land before any engine/breaker source file
- [ ] No `pytest --watch` or other watch-mode flags in any task command
- [ ] Feedback latency for the quick run < 30s on a clean checkout
- [ ] EV-sign line-by-line test (DECIDE-01 success criterion #1) covers both `voluntary_cancel_forfeits_accumulated` branches with distinguishable traces
- [ ] Each of SAFE-01..10 has at least one trigger-fixture test asserting the correct ZMQ KILL-lane message (`CANCEL_ALL` or `EMERGENCY_CLOSE`) is published (covered by `test_breaker_coordinator_publishes_kill_lane_per_safe.py` parametrized test in plan 04-06 Task 6)
- [ ] `test_breaker_coordinator_exclusive.py` proves no other component can submit orders while any breaker is tripped (success criterion #3)
- [ ] `scripts/no_hardcoded_cancel_cost_lint.py` AND `scripts/no_threshold_dials_lint.py` are wired into the test suite (DECIDE-03 success criterion #4 + DECIDE-04 enforcement)
- [ ] `nyquist_compliant: true` set in frontmatter (flipped by plan 04-06 Task 5 ship-gate)
- [ ] `wave_0_complete: true` set in frontmatter (flipped by plan 04-06 Task 5 ship-gate)

**Approval:** pending
