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
| **Quick run command** | `cd python && uv run pytest tests/decision/ -x` |
| **Full suite command** | `cd python && uv run pytest tests/decision/` |
| **Estimated runtime** | ~30 seconds (target; deterministic fixtures, no live RPC) |

---

## Sampling Rate

- **After every task commit:** Run `cd python && uv run pytest tests/decision/ -x` (fail-fast)
- **After every plan wave:** Run `cd python && uv run pytest tests/decision/` (full)
- **Before `/gsd-verify-work`:** Full suite must be green AND `scripts/no_hardcoded_cancel_cost_lint.py` AND `scripts/no_threshold_dials_lint.py` must pass
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Filled in during planning by `gsd-planner` from RESEARCH.md Validation Architecture section. Each of the 17 enumerated test files maps to one task; each task gets an `<automated>` verify command. Plan-checker validates the map is complete before approving plans.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _populated by planner_ | _ | _ | _ | _ | _ | _ | _ | _ | _ |

---

## Wave 0 Requirements

> Test scaffolding that must land BEFORE engine/breaker code is written. Per RESEARCH.md, all 17 test files are net-new (no existing test stubs cover Phase 4).

- [ ] `python/tests/decision/conftest.py` — shared fixtures (deterministic clock, BotConfig builder, simulated book/feature stream, ZMQ mock socket pair)
- [ ] `python/tests/decision/test_engine_ev.py` — DECIDE-01 EV-sign line-by-line stubs
- [ ] `python/tests/decision/test_engine_voluntary_cancel.py` — DECIDE-02 dual-branch divergence stub
- [ ] `python/tests/decision/test_gas_history.py` — DECIDE-03 EWMA + linter sentinel stubs
- [ ] `python/tests/decision/test_no_threshold_dials.py` — DECIDE-04 audit stub
- [ ] `python/tests/decision/test_safe_01_margin_trajectory.py`
- [ ] `python/tests/decision/test_safe_02_oracle_stale.py`
- [ ] `python/tests/decision/test_safe_03_clo_removal.py`
- [ ] `python/tests/decision/test_safe_04_clo_shift.py`
- [ ] `python/tests/decision/test_safe_05_fill_runaway.py`
- [ ] `python/tests/decision/test_safe_06_competition_collapse.py`
- [ ] `python/tests/decision/test_safe_07_maturity_migration.py`
- [ ] `python/tests/decision/test_safe_08_side_budget.py`
- [ ] `python/tests/decision/test_safe_09_underlying_stale.py`
- [ ] `python/tests/decision/test_loss_fit_degraded_breaker.py` — B5 absorption
- [ ] `python/tests/decision/test_breaker_coordinator_exclusive.py` — SAFE-10 kill-authority exclusivity
- [ ] `python/tests/decision/test_predeploy_gate.py` — A5 absorption (Phase 6→7 gate)

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
- [ ] Wave 0 (17 test scaffolding files) lands before any engine/breaker source file
- [ ] No `pytest --watch` or other watch-mode flags in any task command
- [ ] Feedback latency for the quick run < 30s on a clean checkout
- [ ] EV-sign line-by-line test (DECIDE-01 success criterion #1) covers both `voluntary_cancel_forfeits_accumulated` branches with distinguishable traces
- [ ] Each of SAFE-01..10 has at least one trigger-fixture test asserting the correct ZMQ KILL-lane message (`CANCEL_ALL` or `EMERGENCY_CLOSE`) is published
- [ ] `test_breaker_coordinator_exclusive.py` proves no other component can submit orders while any breaker is tripped (success criterion #3)
- [ ] `scripts/no_hardcoded_cancel_cost_lint.py` AND `scripts/no_threshold_dials_lint.py` are wired into the test suite (DECIDE-03 success criterion #4 + DECIDE-04 enforcement)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
