---
phase: 05
slug: event-driven-backtest-ship-gate
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-26
---

# Phase 05 Security Audit Report

**Phase:** 05 — event-driven-backtest-ship-gate
**Date:** 2026-04-26
**ASVS Level:** L1
**Auditor:** gsd-security-auditor (claude-sonnet-4-6)
**block_on:** HIGH

---

## Summary

**Threats Closed:** 26/26
**Threats Open:** 0/26
**Unregistered Flags:** 0

All 26 (plan, threat_id, component) threat tuples verified CLOSED. Several threat
IDs are legitimately reused across plans for different components — each was
verified independently. Both accepted threats have sound rationale. No unregistered
threat flags surfaced in SUMMARY.md files that lack a registered threat mapping.

---

## Threat Verification

| Plan | Threat ID | Category | Disposition | Status | Evidence |
|------|-----------|----------|-------------|--------|----------|
| 05-01 | T-05-01 | D (DoS) | mitigate | CLOSED | `test_breaker_coordinator_publishes_kill_lane_per_safe.py:103` — `ctx = zmq.asyncio.Context()` (NOT `Context.instance()`); `ctx.term()` in `finally` at line 146. `pyproject.toml:27,47` — `pytest-timeout>=2.3,<3` and `timeout = 30` in pytest config. |
| 05-01 | T-05-02 | T (Tampering) | mitigate | CLOSED | `backtest/config.py:19` — `ConfigDict(extra="forbid", frozen=True)` on `StrictBase`; `class BacktestConfig(StrictBase)` at line 22. Schema enforcement prevents out-of-schema knobs mechanically. |
| 05-01 | T-05-03 [P01] | T (Tampering) | mitigate | CLOSED | `backtest/config.py:29-35` — `@field_validator("cancel_latency_grid")` / `_validate_latency_grid` clamps to `[0.001, 60.0]` and `len in [1, 20]`. |
| 05-01 | T-05-04 [P01] | I (Information disclosure) | accept | CLOSED | Rationale: `manifest/writer.py:60-62` — `_wallet_address_hash` uses `sha256(lower(addr))[:16]`; raw secrets never appear in manifests or subprocess captures. Accept rationale is sound and the implementation pre-dates Phase 5. |
| 05-02 | T-05-03 [P02] | T (Tampering) | mitigate | CLOSED | `backtest/replay.py:177` — `.sort(["blockTimestamp", pl.col("eventIndex").fill_null(0)])` before yield. Coverage flag set at line 185 when nulls observed. |
| 05-02 | T-05-04 [P02] | T (Tampering) | mitigate | CLOSED | `backtest/replay.py:38` — `AMMConsumptionIdentityError` imported; lines 501, 519 — explicit NEVER-catch comment; line 563 — `assert_epoch_conservation` delegated to `amm_consumption.py`. `amm_consumption.py:80,125` — raises `AMMConsumptionIdentityError` on violation. |
| 05-02 | T-05-05 | I (Information disclosure) | mitigate | CLOSED | `backtest/replay.py:52-55` — `class LookAheadError(RuntimeError)`; lines 418-422 — `_test_marker_future` guard raises `LookAheadError`; line 455 — `current_chain_ts=current_ts` bound to `evt['blockTimestamp']` in all model calls. |
| 05-02 | T-05-06 | T (Tampering) | mitigate | CLOSED | `backtest/replay.py:344` — SQL CTE literal `WHERE data_source = 'operator'`; line 323 — `log.warning("lineage_filter.synthetic_current_rejected", ...)` with `n_rejected_rows` count when synthetic_current rows are present. |
| 05-03 | T-05-09 [P03] | T (Tampering) | mitigate | CLOSED | `backtest/cancel_latency.py:58-61` — `LatencyScheduler.__init__` raises `ValueError` on `L_seconds < 0` and `decision_period_s <= 0`. |
| 05-03 | T-05-10 [P03] | I (Information disclosure) | mitigate | CLOSED | `backtest/replay.py:611-622` — `_fire_scheduled_closes` calls `self._underlying_at(sc.close_at_ts)`, NOT `sc.fill_ts`; docstring at lines 613-615 explicitly states the invariant. |
| 05-04 | T-05-11 [P04] | T (Tampering) | mitigate | CLOSED | `sweeps/cancel_latency.py:41` — `build_run_manifest(config, parent_run_id=parent_manifest.run_id)` per child run; `sweeps/competition.py:40` — same pattern. |
| 05-04 | T-05-12 | I (Information disclosure) | mitigate | CLOSED | `sweeps/cancel_latency.py:107-118` — `_check_monotonicity` emits `log.warning("backtest.sweep.cancel_latency.unexpected_monotonicity", ...)` on any P&L reversal. |
| 05-05 | T-05-07 [P05] | T (Tampering) | mitigate | CLOSED | `backtest/report.py:158-164` — `_ensure_under_root` checks `out_dir.is_relative_to(parquet_root_resolved)` and raises `ValueError` on escape. `contour_2d.py:164-168` — same guard implemented independently for the contour writer. |
| 05-05 | T-05-13 | I (Information disclosure) | accept | CLOSED | Rationale: `report.py:119,122,141,144,163,166` — all matplotlib imports are lazy (inside function bodies); `cli.py` has no matplotlib import; `replay.py` has no matplotlib import. Replay engine determinism is structurally isolated from matplotlib version. Accept rationale is sound. |
| 05-06 | T-05-14 | T (Tampering) | mitigate | CLOSED | `config/schema.py:42` — `voluntary_cancel_forfeits_accumulated: bool = False` (LOCKED P0-01); `sweeps/forfeit_branch.py:48-52` — uses `model_copy(update={...})` to create a new frozen instance; no in-place mutation. |
| 05-06 | T-05-15 | I (Information disclosure) | mitigate | CLOSED | `sweeps/forfeit_branch.py:106-107` — `log.warning("forfeit_branch_load_bearing", ...)` surfaces material divergence. |
| 05-07 | T-05-08 [P07] | R (Repudiation) | mitigate | CLOSED | `backtest/bootstrap.py:24-31` — `seed_from_manifest` derives seed deterministically from ULID bytes; same manifest always yields same seed and same p5. |
| 05-07 | T-05-16 | T (Tampering) | mitigate | CLOSED | `backtest/bootstrap.py:39-42` — `block_bootstrap_pnl(daily_pnl, *, rng: np.random.Generator, ...)` requires explicit rng; no `numpy.random.choice` or global state calls in module. |
| 05-07 | T-05-17 | I (Information disclosure) | mitigate | CLOSED | `backtest/ship_gate.py:32-77` — `ShipGateHalt(SystemExit)` defined; `evaluate_ship_gate` returns `ShipGateVerdict` with `passed` bool; `write_ship_gate_report` called on both branches. `backtest/cli.py:176` — `raise ShipGateHalt(1)` when `passed=False`. |
| 05-08 | T-05-08 [P08] | T (Tampering) | mitigate | CLOSED | `backtest/perturbation.py:97,126` — `enumerate_perturbable_leaves` calls `config.model_dump(mode='json')` fresh on every invocation (not cached); `extra='forbid'` on `StrictBase` makes adding a knob outside the schema mechanically impossible. |
| 05-08 | T-05-07 [P08] | T (Tampering) | mitigate | CLOSED | `backtest/contour_2d.py:164-168` — `contour_grid_to_parquet` resolves output path and asserts `is_relative_to(parquet_root_resolved)`; raises `ValueError` on escape. |
| 05-08 | T-05-09 [P08] | I (Information disclosure) | mitigate | CLOSED | `backtest/perturbation.py:61-62,130-138,186-192` — sign-flip is recorded in `PerturbationRow.fragile` field; no auto-fail logic; `run_perturbation_grid` returns rows normally whether `fragile=True` or not. |
| 05-09 | T-05-09 [P09] | R (Repudiation) | mitigate | CLOSED | `backtest/cli.py:5,225-244` — MANIFEST-FIRST 4-step preamble present; `log.info("RUN_MANIFEST", ...)` is first log call after `configure_logging`. |
| 05-09 | T-05-07 [P09] | T (Tampering) | mitigate | CLOSED | `backtest/run_manifest.py:37-57` — `_ensure_under_root` raises `ValueError` with "backtest manifest sidecar path traversal blocked"; `var_root = Path("var/backtest").resolve()` as anchor. |
| 05-09 | T-05-10 [P09] | I (Information disclosure) | mitigate | CLOSED | `python/tests/test_backtest_architecture_yaml_drift.py:27-38` — test runs `scripts/architecture_lint.py` as subprocess and asserts exit 0. `scripts/architecture_lint.py` and `docs/architecture.yml` both present. |
| 05-09 | T-05-11 [P09] | T (Tampering) | mitigate | CLOSED | `backtest/run_manifest.py:81-100` — `assert_manifest_contains_all_botconfig_leaves` calls `enumerate_perturbable_leaves(config, exclude_prefixes=())` to include ALL leaves; cross-checks manifest dict against full leaf set. |

---

## Accepted Risks Log

### T-05-04 [P01] — RED-scaffold tests leaking secrets via subprocess capture

**Date accepted:** 2026-04-26
**Category:** I (Information disclosure)
**Component:** Test CLI invocation via subprocess (Plan 05-01 Task 5 / 05-09 Task 1)
**Rationale:** The manifest emitted during test subprocess calls contains `wallet_address_hash`, which is `sha256(lower(addr))[:16]` (16 hex chars, non-reversible). Raw wallet addresses and private keys never appear in manifests, log lines, or subprocess captures. The hashing discipline is enforced in `manifest/writer.py:60-62` and predates Phase 5. No secret material is disclosed.
**Residual risk:** Negligible — hash prefix is a one-way function; collisions do not reveal the address.

### T-05-13 — matplotlib version drift affects replay determinism

**Date accepted:** 2026-04-26
**Category:** I (Information disclosure)
**Component:** Plot generation (report.py)
**Rationale:** Structural decoupling: matplotlib is imported lazily inside each plot function body in `report.py` only. The replay engine (`replay.py`), bootstrap (`bootstrap.py`), ship gate (`ship_gate.py`), perturbation (`perturbation.py`), and sweeps have no matplotlib imports. Plot generation is invoked as a separate CLI subcommand (`python -m boros_brain.backtest plot`), not during the replay run. Matplotlib version changes cannot affect replay, bootstrap, or ship-gate outputs.
**Residual risk:** None to replay determinism. Plot visual output may differ across matplotlib versions, which is acceptable for a diagnostic tool.

---

## Unregistered Threat Flags

None. All SUMMARY.md `## Threat Flags` sections either:
- Map directly to a registered threat ID in the register, OR
- Explicitly state no new attack surface was introduced (05-01 has no flag section; 05-02, 05-03 have no flag section; 05-04, 05-05, 05-06, 05-07, 05-08, 05-09 all confirm no new endpoints/auth paths beyond what their plan's threat model covers).

No unregistered flags require escalation.

---

## Files Verified (Read-Only)

- `python/src/boros_brain/backtest/config.py`
- `python/src/boros_brain/backtest/replay.py`
- `python/src/boros_brain/backtest/cancel_latency.py`
- `python/src/boros_brain/backtest/sweeps/cancel_latency.py`
- `python/src/boros_brain/backtest/sweeps/competition.py`
- `python/src/boros_brain/backtest/sweeps/forfeit_branch.py`
- `python/src/boros_brain/backtest/report.py`
- `python/src/boros_brain/backtest/contour_2d.py`
- `python/src/boros_brain/backtest/perturbation.py`
- `python/src/boros_brain/backtest/bootstrap.py`
- `python/src/boros_brain/backtest/ship_gate.py`
- `python/src/boros_brain/backtest/cli.py`
- `python/src/boros_brain/backtest/run_manifest.py`
- `python/src/boros_brain/config/schema.py`
- `python/src/boros_brain/manifest/writer.py`
- `python/src/boros_brain/fill_model/amm_consumption.py`
- `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py`
- `python/tests/test_backtest_architecture_yaml_drift.py`
- `python/pyproject.toml`
- `scripts/architecture_lint.py`
- `docs/architecture.yml`

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-26 | 26 | 26 | 0 | gsd-security-auditor (claude-sonnet-4-6) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-26
