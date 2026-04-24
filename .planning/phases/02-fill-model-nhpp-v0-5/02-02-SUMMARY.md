---
phase: 02-fill-model-nhpp-v0-5
plan: "02"
subsystem: fill_model
tags: [fill_model, queue_tracker, amm_consumption, schemas, event_index_replay, bias_diagnostic, nhpp]
dependency_graph:
  requires:
    - 02-01 (FillModelConfig, fill_model package scaffold, wave-0 test stubs)
    - 01-foundation (parquet.market_trades, parquet.order_book_raw, parquet.order_book_combined)
  provides:
    - QueueTracker (tri-track replay + drift diagnostic)
    - compute_drift_diagnostic (free function)
    - compute_amm_share_timeseries (FILL-04 per-tick amm_share)
    - assert_epoch_conservation (per-epoch flow identity)
    - AMMConsumptionIdentityError (exception, re-exported from amm_consumption)
    - ReplayResult + EpochFlowSnapshot dataclasses (partial schemas.py)
  affects:
    - docs/architecture.yml (3 new module nodes + 9 new edges)
    - docs/ARCHITECTURE.md (Mermaid fill_model subgraph extended)
    - Wave-0 test stubs (test_fill_model_queue_tracker + test_fill_model_amm_consumption: 0 skipped → 12 passing)
tech_stack:
  added: []
  patterns:
    - Tri-track replay (pessimistic/realized/optimistic) with bracket invariant: pess >= real >= opt
    - eventIndex-ordered sort (blockTimestamp, eventIndex) with null-fill degrade path
    - max(combined - raw, 0.0) for amm_share by construction — matches Phase 1 DATA-05 pattern
    - Distinct exception names per phase: AMMConservationError (ingest) vs AMMConsumptionIdentityError (runtime)
    - Log-before-raise pattern: structured event emitted with run_id BEFORE raising exception
key_files:
  created:
    - python/src/boros_brain/fill_model/schemas.py
    - python/src/boros_brain/fill_model/amm_consumption.py
    - python/src/boros_brain/fill_model/queue_tracker.py
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/queue-tracker-algorithm-v05.md
    - /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/amm-consumption-model-v05.md
  modified:
    - python/tests/test_fill_model_amm_consumption.py (0 skipped → 5 passing)
    - python/tests/test_fill_model_queue_tracker.py (0 skipped → 7 passing)
    - docs/architecture.yml (3 new nodes + 9 new edges)
    - docs/ARCHITECTURE.md (Mermaid extended + Phase 2 paragraph updated)
decisions:
  - "Tri-track bracket vs point-estimate: bracket approach chosen because it produces directly observable uncertainty bounds and matches PITFALLS §B1 (queue-drift direction blindness) — the pessimistic bound is the default for the EV rule"
  - "AMMConsumptionIdentityError named distinctly from Phase-1 AMMConservationError — they guard different invariants at different times (runtime per-epoch vs ingest per-snapshot); sharing the exception class would lie in the architecture graph"
  - "eventIndex-null degrade-not-crash policy: fills fill_null(0) and marks event_index_coverage='degraded' — v0.5 stays shippable if a later re-screened market lacks eventIndex coverage"
  - "Log-before-raise in assert_epoch_conservation: structured log event emitted with epoch context BEFORE raise so operator has grep-joinable record by run_id even if exception is caught upstream"
metrics:
  duration: ~6 min
  completed_date: "2026-04-24"
  tasks: 3
  files: 7
---

# Phase 02 Plan 02: Queue Tracker + AMM Consumption + Schemas Summary

**One-liner:** QueueTracker tri-track (pessimistic/realized/optimistic) eventIndex-ordered tape replay with drift diagnostic; AMMConsumption runtime per-tick and per-epoch flow-identity assertion; both PITFALLS §B1 and §B3 defused.

## What Was Built

### Task 1: schemas.py (partial) + amm_consumption.py + AMM tests

**`python/src/boros_brain/fill_model/schemas.py`** (new, partial — Plan 02-03 appends more):
- `ReplayResult(frozen=True)` dataclass: tri-track anchor dicts + drift_diagnostics_per_hour + event_index_coverage literal
- `EpochFlowSnapshot(frozen=True)` dataclass: epoch flow audit trail
- `AMMConsumptionIdentityError(RuntimeError)`: runtime per-epoch violation (distinct from Phase-1 `AMMConservationError`)

**`python/src/boros_brain/fill_model/amm_consumption.py`** (new):
- `compute_amm_share_timeseries(raw, combined, epoch_start_ts, epoch_end_ts)`: joins on (snapshot_ts, tick), computes `amm_share = max(combined - raw, 0.0)`. Raises `AMMConsumptionIdentityError` with offending rows if `combined - raw < -1e-9`.
- `assert_epoch_conservation(book_ahead_start, book_ahead_end, taker, amm, net_placements, epoch_start_ts, epoch_end_ts, tolerance=1e-6)`: logs `fill_model.amm_conservation_violation` (error) BEFORE raising on violation.
- Re-exports `AMMConsumptionIdentityError` so `from boros_brain.fill_model.amm_consumption import AMMConsumptionIdentityError` works.

**Tests (5 passing):**

| Test | Coverage |
|------|---------|
| `test_amm_share_non_negative_basic` | Happy path: 2 snapshots, sum = 80.0 |
| `test_amm_share_non_negative` (Hypothesis) | Property: combined>=raw always yields amm_share>=0 |
| `test_amm_share_raises_on_combined_less_than_raw` | Combined<raw → AMMConsumptionIdentityError with "combined < raw" in message |
| `test_epoch_conservation_balanced` | Balanced 100-30-20+0=50 → None |
| `test_epoch_conservation_raises_on_imbalance` | Imbalanced → raises with "delta=" in message |

### Task 2: queue_tracker.py + queue tests

**`python/src/boros_brain/fill_model/queue_tracker.py`** (new):

`compute_drift_diagnostic(replay_queue, snapshot_queue) -> dict[str, float]`:
- Returns `drift_signed_mean`, `drift_magnitude_mean`, `drift_std`, `n_ticks_compared`
- Empty inputs → zeros (no crash)
- Uses numpy ddof=1 std for >1 tick

`QueueTracker(config, market_id, side)` with:
- `_load_trades()`: scans `data/parquet/market_trades/**/*.parquet`, logs `fill_model.eventindex_coverage_degraded` on null eventIndex rows, sorts by `["blockTimestamp", "eventIndex"]`
- `_replay_realized()`: consume queue by visible takers only
- `_replay_pessimistic()`: realized + bump UP to snapshot_next where snapshot_next > realized
- `_replay_optimistic()`: realized + cap DOWN to snapshot_next where snapshot_next < realized
- `replay_window()`: orchestrates tri-track for each adjacent anchor pair; logs `fill_model.queue_drift_reconciliation` (info) per hour; logs `fill_model.bracket_width_warn` (warning) when max bracket width exceeds `config.fill_model.bracket_width_warn_multiplier × mean_queue`

**Tests (7 passing):**

| Test | Coverage |
|------|---------|
| `test_compute_drift_diagnostic_empty` | Degenerate empty inputs → zeros |
| `test_compute_drift_diagnostic_signed` | -50 signed mean when snapshot > replay by 50 |
| `test_drift_bias_detected` | Non-zero signed mean on biased pair |
| `test_bracket_invariant` (Hypothesis, 50 examples) | T-02-Q-01: pess>=real>=opt for all inputs |
| `test_replay_on_fixture` | T-02-Q-02: realized=60, pess=70, opt=60 for hand-constructed case |
| `test_bracket_width_warn` | T-02-Q-04: log event fires when snap_next=500 vs start=100 |
| `test_eventindex_null_degraded_flag` | ReplayResult supports 'degraded' literal |

### Task 3: Architecture + Wiki

**`docs/architecture.yml`** additions:
- 3 new module nodes: `brain.fill_model.{schemas,queue_tracker,amm_consumption}`
- 9 new edges (6 from queue_tracker, 3 from amm_consumption)
- `architecture_lint.py` exits 0 (no drift)

**`docs/ARCHITECTURE.md`**:
- Mermaid fill_model subgraph extended with 3 new nodes + 4 data-flow edges
- Phase 2 description paragraph updated with Plan 02-02 details
- Links added: `[[queue-tracker-algorithm-v05]]`, `[[amm-consumption-model-v05]]`

**LLM Wiki pages filed:**

| Page | Status |
|------|--------|
| `queue-tracker-algorithm-v05.md` | Current — v0.5 regime (NEW) |
| `amm-consumption-model-v05.md` | Current — v0.5 regime (NEW) |

## Key Decisions Made

1. **Tri-track bracket vs point-estimate** — the bracket (pessimistic/realized/optimistic) directly encodes uncertainty from invisible inter-snapshot events. PITFALLS §B1 (queue-drift direction blindness) is defused by making both directions explicit. Default `queue_tracker_bias_mode="pessimistic"` for conservative EV rule input.

2. **`AMMConsumptionIdentityError` distinct from `AMMConservationError`** — these guard different invariants at different points in the pipeline. Sharing the class would make the architecture graph misleading. Filed in `[[amm-consumption-model-v05]]`.

3. **eventIndex-null degrade-not-crash** — `fill_null(0)` + `event_index_coverage="degraded"` + log event preserves v0.5 shippability if a later re-screened market lacks eventIndex coverage. The plan RESEARCH §Assumption A3 explicitly permits this degradation path. Filed in `[[queue-tracker-algorithm-v05]]`.

4. **Log-before-raise pattern** — `fill_model.amm_conservation_violation` is emitted at error level BEFORE raising `AMMConsumptionIdentityError`, ensuring the operator has a grep-joinable record by `run_id` even if the exception is caught at a higher layer.

## Deviations from Plan

None — plan executed exactly as written. The TDD RED→GREEN cycle was followed for both tasks.

## Test Pass Map

| File | Before (02-01 wave-0) | After (02-02) |
|------|-----------------------|---------------|
| `test_fill_model_amm_consumption.py` | 2 SKIPPED | 5 PASSED |
| `test_fill_model_queue_tracker.py` | 4 SKIPPED | 7 PASSED |
| `test_fill_model_features.py` | 5 PASSED | 5 PASSED |
| `test_architecture_lint.py` | 1 PASSED | 1 PASSED |
| `test_manifest_contains_all_knobs.py` | 5 PASSED | 5 PASSED |
| **Total** | 11 passed, 6 skipped | **23 passed, 0 skipped (plan scope)** |

## Architecture Delta Summary

New nodes in `docs/architecture.yml`:
- `brain.fill_model.schemas` (module: ReplayResult, EpochFlowSnapshot, AMMConsumptionIdentityError)
- `brain.fill_model.queue_tracker` (module: QueueTracker class + compute_drift_diagnostic)
- `brain.fill_model.amm_consumption` (module: compute_amm_share_timeseries + assert_epoch_conservation)

New edges (9 total):
- queue_tracker → {parquet.market_trades, parquet.order_book_raw, brain.fill_model.amm_consumption, brain.fill_model.schemas, config.fill_model.bracket_width_warn_multiplier, config.fill_model.queue_tracker_bias_mode}
- amm_consumption → {parquet.order_book_raw, parquet.order_book_combined, brain.fill_model.schemas}

## Known Stubs

None. All interfaces are fully implemented. Plan 02-03 will extend `schemas.py` with `FitArtifact`, `PredictInput`, `PredictOutput`.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the `<threat_model>` in the plan enumerates. All T-02-02-0x mitigations are implemented:
- T-02-02-01 (pathological negative sizes): `compute_amm_share_timeseries` raises `AMMConsumptionIdentityError`
- T-02-02-05 (eventIndex coverage silently assumed full): explicit `event_index_coverage` field in `ReplayResult`

## Self-Check: PASSED

Files exist:
- python/src/boros_brain/fill_model/schemas.py — FOUND
- python/src/boros_brain/fill_model/amm_consumption.py — FOUND
- python/src/boros_brain/fill_model/queue_tracker.py — FOUND
- /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/queue-tracker-algorithm-v05.md — FOUND
- /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/amm-consumption-model-v05.md — FOUND

Commits present: 8b61512 (Task 1), dd014cd (Task 2), faf7027 (Task 3)
