---
phase: 05-event-driven-backtest-ship-gate
verified: 2026-04-26T19:30:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 5: Event-Driven Backtest + Ship-Gate Verification Report

**Phase Goal:** Build the event-driven backtest + ship-gate verdict that proves the strategy earns positive risk-adjusted P&L before any live capital is deployed. All 8 BACK-* requirements must be satisfied. Ship-gate PASS → proceed to Phase 6+7. FAIL → project halts with written report.
**Verified:** 2026-04-26T19:30:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Replay engine processes trade tape in `(blockTimestamp, eventIndex)` order — no out-of-order events | VERIFIED | `replay.py:717 lines`, `fill_null(0)` + polars sort present; 5 BACK-01 tests GREEN |
| 2 | AMM conservation asserted at every replay-window boundary; `AMMConsumptionIdentityError` propagates and is never swallowed | VERIFIED | `assert_epoch_conservation` called in `_maybe_anchor_snapshot`; no try/except around it in engine |
| 3 | Replay never reads future events; `LookAheadError` defined and raised on `_test_marker_future` | VERIFIED | `LookAheadError` class present (5 occurrences); `current_chain_ts = evt['blockTimestamp']` pattern enforced |
| 4 | Reward-budget lineage filter `WHERE data_source = 'operator'` is in SQL (5 occurrences), not Python; warning logged for synthetic_current rows | VERIFIED | `lineage_filter.synthetic_current_rejected` log key present; 5 SQL filter occurrences in relay.py |
| 5 | One decision log row per in-flight synthetic order per 1 Hz tick | VERIFIED | `decision_log.append` (2 occurrences); 1 Hz cadence guard in `_maybe_emit_tick`; BACK-01 decision log test GREEN |
| 6 | Cancel latency has two compounding axes (order-of-event + time-since-event); `LatencyScheduler` never calls `time.time()`; close P&L uses `close_at_ts` basis not `fill_ts` | VERIFIED | `cancel_latency.py:109 lines`; `FILL_REALIZED` path in replay.py; `_underlying_at(sc.close_at_ts)` confirmed; BACK-02 tests GREEN |
| 7 | Cancel-latency sweep (L∈{0.5…10}s, 6 rows) and competition sweep (m∈{0.5…3.0}, 6 rows) with `dP&L/dL < 0` and `dP&L/dQ < 0` on synthetic always-fills; each child run gets a fresh `RUN_MANIFEST` with `parent_run_id` | VERIFIED | `sweeps/cancel_latency.py` + `sweeps/competition.py` exist; `build_run_manifest(config, parent_run_id=` confirmed; BACK-03/04 tests GREEN |
| 8 | Backtest output is Hive-partitioned parquet; path-traversal guard fires; ShipGateVerdict JSON sidecar written; bootstrap ship-gate: 5th-pct bootstrapped P&L > alt_yield + all_fees; voluntary-cancel sensitivity 2-row sweep; perturbation grid reflection-driven ±20%; 2D contour 5×5; CLI emits RUN_MANIFEST first; architecture diagram in sync | VERIFIED | All files exist and substantive; 412 passed / 2 skipped; architecture lint exits 0 |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Status | Lines | Key Evidence |
|----------|--------|-------|--------------|
| `python/src/boros_brain/backtest/replay.py` | VERIFIED | 717 | `class ReplayEngine`, `LookAheadError`, SQL lineage filter, AMM conservation, decision_log.append, FILL_REALIZED |
| `python/src/boros_brain/backtest/schemas.py` | VERIFIED | 143 | `BacktestRunOutput`, `ReplayConfig`, `ReplayOutput`, `ShipGateVerdict`, `ThresholdComponents` |
| `python/src/boros_brain/backtest/synthetic_orders.py` | VERIFIED | 84 | `SyntheticOrder`, `SyntheticOrderLedger`, `in_flight()` |
| `python/src/boros_brain/backtest/cancel_latency.py` | VERIFIED | 109 | `ScheduledClose`, `LatencyScheduler`, `math.ceil`, `decision_ts + self.L`, no `time.time()` |
| `python/src/boros_brain/backtest/sweeps/cancel_latency.py` | VERIFIED | ~120 | `run_cancel_latency_sweep`, `compute_dpnl_dl`, `unexpected_monotonicity`, `parent_run_id=` |
| `python/src/boros_brain/backtest/sweeps/competition.py` | VERIFIED | ~110 | `run_competition_sweep`, `compute_dpnl_dq`, `sigma_others_multiplier` |
| `python/src/boros_brain/backtest/sweeps/forfeit_branch.py` | VERIFIED | ~115 | `run_forfeit_branch_sweep`, `forfeit_branch.sanity_check_pass`, `forfeit_branch_load_bearing` |
| `python/src/boros_brain/backtest/report.py` | VERIFIED | 244 | `write_backtest_row`, `write_ship_gate_verdict_json`, `_ensure_under_root`, `is_relative_to`, plot generators, `append_perturbation_section_to_ship_gate_report` |
| `python/src/boros_brain/backtest/bootstrap.py` | VERIFIED | 62 | `seed_from_manifest`, `make_rng`, `block_bootstrap_pnl`, `int.from_bytes` |
| `python/src/boros_brain/backtest/ship_gate.py` | VERIFIED | 161 | `ShipGateHalt`, `assemble_threshold`, `evaluate_ship_gate`, `write_ship_gate_report`, `alt_yield +` |
| `python/src/boros_brain/backtest/perturbation.py` | VERIFIED | 346 | `enumerate_perturbable_leaves`, `detect_sign_flip`, `run_perturbation_grid`, `model_dump(mode='json')`, `_set_leaf_by_path` |
| `python/src/boros_brain/backtest/contour_2d.py` | VERIFIED | 168 | `run_2d_contour_grid`, `ContourCell`, `contour_grid_to_parquet`, `contour_2d_knobs` (4 occurrences) |
| `python/src/boros_brain/backtest/cli.py` | VERIFIED | 251 | `def main`, `ShipGateHalt`, MANIFEST-FIRST preamble, `ReplayEngine(replay_config=` or flat kwargs |
| `python/src/boros_brain/backtest/run_manifest.py` | VERIFIED | 127 | `emit_backtest_manifest` (2 occurrences), PROTO-04 reflection lockstep |
| `python/src/boros_brain/backtest/__main__.py` | VERIFIED | 8 | `from .cli import main` shim |
| `docs/architecture.yml` | VERIFIED | — | All 13 Phase-5 module nodes present; architecture lint exits 0 |
| `docs/ARCHITECTURE.md` | VERIFIED | — | `phase5_wave3_cli` subgraph present |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `replay.py` | `fill_model.queue_tracker` | `from ..fill_model.queue_tracker import QueueTracker` | VERIFIED |
| `replay.py` | `fill_model.amm_consumption` | `assert_epoch_conservation` called | VERIFIED |
| `replay.py` | `decision.engine` | `evaluate as evaluate_decision` | VERIFIED |
| `replay.py` | `state.market_reward_calibration` | `WHERE data_source = 'operator'` SQL CTE | VERIFIED |
| `replay.py` | `backtest.cancel_latency` | `from .cancel_latency import LatencyScheduler` | VERIFIED |
| `sweeps/cancel_latency.py` | `replay.py` | `ReplayEngine(` instantiation | VERIFIED |
| `sweeps/competition.py` | `ReplayConfig.sigma_others_multiplier` | `replace(base_run, sigma_others_multiplier=m)` pattern | VERIFIED |
| `bootstrap.py` | `python-ulid` | `int.from_bytes(ULID bytes...)` | VERIFIED |
| `ship_gate.py` | `config.screener.alt_yield + config.backtest.all_fees_threshold` | `assemble_threshold` (6 occurrences) | VERIFIED |
| `report.py` | `data/parquet/backtest_results/` | `write_parquet` via polars + `is_relative_to` guard | VERIFIED |
| `cli.py` | `ship_gate.ShipGateHalt` | `ShipGateHalt` (2 occurrences) | VERIFIED |
| `cli.py` | `run_manifest.emit_backtest_manifest` | `emit_backtest_manifest` in cli.py | VERIFIED |
| `perturbation.py` | `BotConfig.model_dump(mode='json')` | `model_dump(mode='json')` (4 occurrences) | VERIFIED |

### Requirements Coverage

| Requirement | Source Plan | Description | Status |
|-------------|-------------|-------------|--------|
| BACK-01 | 05-02 | Event-driven replay engine, eventIndex order, AMM conservation, look-ahead prevention | SATISFIED — `replay.py` 717 lines; 5 tests GREEN |
| BACK-02 | 05-03 | Cancel latency simulation, two-axis compound, close P&L at close_at_ts | SATISFIED — `cancel_latency.py` + wired into replay.py; BACK-02 tests GREEN |
| BACK-03 | 05-04 | Cancel-latency sweep L∈{0.5…10}s; dP&L/dL curve | SATISFIED — `sweeps/cancel_latency.py`; 3 tests GREEN |
| BACK-04 | 05-04 | Competition sweep m∈{0.5…3.0}; dP&L/dQ curve | SATISFIED — `sweeps/competition.py`; 3 tests GREEN |
| BACK-05 | 05-05 | Backtest outputs: Hive-partitioned parquet, plots, ship_gate_verdict.json | SATISFIED — `report.py`; 7 tests GREEN |
| BACK-06 | 05-06 | Voluntary-cancel sensitivity 2-row sweep; divergence sanity check | SATISFIED — `sweeps/forfeit_branch.py`; 3 tests GREEN |
| BACK-07 | 05-07 | Bootstrap ship-gate: 5th-pct > alt_yield + all_fees; fail path writes report + halts | SATISFIED — `bootstrap.py` + `ship_gate.py`; 4 tests GREEN |
| BACK-08 | 05-08 | Perturbation grid ±20% Pydantic-reflection; sign-flip detection; 2D contour 5×5 | SATISFIED — `perturbation.py` + `contour_2d.py`; 21 tests GREEN |

All 8 BACK-* requirements satisfied. No orphaned requirements detected.

### Anti-Patterns Found

No blocking anti-patterns found. The following intentional stubs are present and documented:

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| `test_backtest_plot_generation.py:101` | `pytest.skip("Plan 05-09 implements the plot subcommand")` | INFO | Intentional — plot CLI subcommand is out-of-scope stub per Plan 05-09 SUMMARY ("full `plot_dpnl_dl` / `plot_dpnl_dq` reconstruction from sweep-axis-filtered rows is out-of-scope for this phase") |
| `test_loss_model_replay.py:228` | `pytest.skip("integration test requires Phase-1 parquet fixture")` | INFO | Intentional carry-forward from Phase 5 backtest; unrelated to BACK-* requirements |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite passes | `uv run pytest -q` | 412 passed, 2 skipped, 2 warnings in 68.40s | PASS |
| Architecture lint passes | `python3 scripts/architecture_lint.py` | exit 0 | PASS |
| All 13 Phase-5 nodes in architecture.yml | grep for each id | All 13 confirmed present | PASS |

### Human Verification Required

None. All must-haves verified programmatically.

### Gaps Summary

No gaps. All 8 BACK-* requirements are satisfied by substantive, wired, data-flowing implementations. The full pytest suite passes at 412/2 with zero regressions. Architecture diagram is in sync (lint exit 0).

---

_Verified: 2026-04-26T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
