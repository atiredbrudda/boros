---
phase: 5
slug: event-driven-backtest-ship-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-26
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `05-RESEARCH.md` § Validation Architecture (line 1206+).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24 + hypothesis 6.x + pytest-timeout >=2.3,<3 (NEW Wave 0) |
| **Config file** | `python/pyproject.toml` `[tool.pytest.ini_options]` (Phase 1 baseline; `timeout = 30` added in Wave 0) |
| **Quick run command** | `cd python && uv run pytest -q tests/test_backtest_*.py -x` |
| **Full suite command** | `cd python && uv run pytest -q` |
| **Estimated runtime** | quick ~30s, full ~3 min (target — BACK-07 success criterion #6 mandates 0 hangs / 0 timeouts) |

> Authoritative path layout: flat `python/tests/` directory. Every Phase 5 test file
> begins `test_backtest_*.py` so the quick run glob captures it. The Wave-0 ZMQ fix
> lives in the existing `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py`
> (no new file). The new lint guard is `python/scripts/no_zmq_singleton_in_tests_lint.py`.

---

## Sampling Rate

- **After every task commit:** `cd python && uv run pytest -q tests/test_backtest_<task>*.py -x` (fail-fast, <30s)
- **After every plan wave:** `cd python && uv run pytest -q tests/test_backtest_*.py` (<2 min)
- **Before `/gsd-verify-work`:** Full suite must be green AND `python scripts/no_zmq_singleton_in_tests_lint.py` AND `python scripts/no_threshold_dials_lint.py` (carried from Phase 4) must pass
- **Max feedback latency:** 30 seconds (quick), 3 minutes (full suite — BACK-07 ship-gate forces this)

---

## Per-Task Verification Map

> Filled in during planning by `gsd-planner` from `05-RESEARCH.md` § Validation Architecture (line 1217+ Phase Requirements → Test Map). Each enumerated test file maps to one task; each task gets an `<automated>` verify command. Plan-checker validates the map is complete before approving plans.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _populated by planner_ | _ | _ | _ | _ | _ | _ | _ | _ | _ |

---

## Wave 0 Requirements

> Wave-0 prerequisite forced by BACK-07 success criterion #6 (full-suite green, no `--ignore`). All paths flat `python/tests/` — no subdirectories.

- [ ] Fix `python/tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py:99` — replace `zmq.asyncio.Context.instance()` with a per-test `zmq.asyncio.Context()` plus `try/finally: ctx.term()`
- [ ] Add `pytest-timeout >=2.3,<3` to `python/pyproject.toml` `[dependency-groups].dev`
- [ ] Add `timeout = 30` to `python/pyproject.toml` `[tool.pytest.ini_options]`
- [ ] Add `python/scripts/no_zmq_singleton_in_tests_lint.py` (regression guard) + wire into pre-commit
- [ ] Capture `var/phase5-wave0-greenrun-<git-sha>.log` proving full pytest run is green with exit_code=0 and no `[pytest-timeout]` lines
- [ ] Create `BotConfig.backtest` Pydantic sub-model exposing: `bootstrap_n_resamples` (default 2000), `bootstrap_block_seconds` (default 86400), `cancel_latency_grid` (default `[0.5, 1, 2, 3, 5, 10]`), `competition_multipliers` (default `[0.5, 0.75, 1.0, 1.5, 2.0, 3.0]`), `all_fees_threshold` (default 0.01), `budget_haircut_pessimistic` (default 0.5), `perturbation_pct` (default 0.20), `contour_2d_knobs` (default `["latency_default_seconds", "p_purge"]`), `output_parquet_root` (default `var/backtest`)
- [ ] Extend `python/tests/conftest.py` with backtest fixtures: `seed_market_trades_parquet`, `seed_order_book_raw_parquet`, `seed_order_book_combined_parquet` (`seed_underlying_apr_parquet` reused from Phase 4)
- [ ] Wave-0 RED stubs for every BACK-* test file (one per row of the Phase Requirements → Test Map)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Ship-gate kill-report human readability | BACK-07 | Markdown layout / prose quality not unit-testable | After a synthetic-fail backtest run, open the generated `var/backtest/<run_id>/ship-gate-report.md` and confirm: (a) RUN_MANIFEST excerpt at top, (b) component breakdown of `alt_yield + all_fees` threshold, (c) bootstrap distribution chart linked, (d) recommended kill or proceed verdict |
| Phase 5 → Phase 7 transition gate | BACK-07 | Crosses phase boundary into paper trading | After ship-gate `passed=True`, run `python -m brain.decision.predeploy_gate verify` and confirm `phase=5_ship_gate` artefact present and hash matches |

---

## Nyquist Sampling Notes

| Primitive | Sampling Source | Min Cadence | Test Pattern |
|-----------|----------------|-------------|--------------|
| Replay event ordering (BACK-01) | `(blockTimestamp, eventIndex)` per trade | per-event | Hypothesis property test: shuffled tape input → identical output state vs canonical-ordered input |
| AMM conservation during replay (BACK-01) | `combined − raw` per snapshot anchor | per-hourly snapshot | Re-use Phase 1 `assert_epoch_conservation` against replayed state; integration test on a 30-day fixture |
| Look-ahead prevention (BACK-01) | DecisionEngine.evaluate() arguments | per-tick | Lint test: assert engine call site only sees events with `(t_event ≤ t_decision)` |
| Decision log fidelity (BACK-01) | Per-tick decision log line | 1 Hz simulated | Replay 60s of fixture; assert one decision row per in-flight order per tick |
| Cancel latency two-axis (BACK-02) | Synthetic fill at known `(t, eventIndex)` with L=2s | per-fill | Two-axis fixture asserting `close_at_ts = fill_ts + L` AND order-of-event = next-tick |
| Cancel-latency sweep (BACK-03) | 6 latency rows per backtest run | per-run | Property test: row count exactly 6, monotone-decreasing sign on synthetic always-fill scenario |
| Competition sweep (BACK-04) | 6 multiplier rows per backtest run | per-run | Property test: row count exactly 6, monotone-decreasing sign on synthetic high-fill scenario |
| Output schema round-trip (BACK-05) | Parquet partitioned by `run_id` | per-run | DuckDB query against synthetic backtest run; assert all columns present, types match Pydantic model |
| Plot artifact existence (BACK-05) | Files on disk in `var/backtest/<run_id>/plots/` | per-run | Smoke test: assert `calibration.png`, `dpnl_dl.png`, `dpnl_dq.png` exist after a backtest run |
| Voluntary-cancel sensitivity row (BACK-06) | Two-row A/B summary in ship-gate report | per-run | Both branches produced; absolute P&L divergence <10% → sanity-check pass logged; ≥10% → follow-up flag emitted (no auto-fail) |
| Bootstrap idempotence (BACK-07) | RNG seed derived from `RUN_MANIFEST.run_id` | per-run | Property: rerun with same manifest → bit-for-bit identical bootstrap distribution |
| Ship-gate threshold assembly (BACK-07) | `alt_yield + all_fees_threshold` from `BotConfig` | per-run | Unit test: synthetic config → expected sum; mutation test: bumping either knob shifts threshold by the right delta |
| Ship-gate verdict (BACK-07) | 5th-percentile annualized P&L vs threshold | per-run | Synthetic positive-P&L fixture → `passed=True`; synthetic negative-P&L → `passed=False` AND `var/backtest/<run_id>/ship-gate-report.md` written |
| Full-suite green forcing function (BACK-07 #6) | `cd python && uv run pytest -q` exit code | per-phase-gate | Phase-gate smoke: must exit 0 with NO `--ignore` flags AND NO `[pytest-timeout]` log lines |
| Perturbation grid enumeration (BACK-08) | `BotConfig.model_dump(mode='json')` numeric leaves | per-run | Property test: count of perturbed knobs equals count of numeric leaves found via reflection |
| Sign-flip detection (BACK-08) | Per-knob ±20% perturbation P&L delta | per-knob, per-run | Synthetic fragile-knob fixture → flag fires; non-fragile → no flag; flag is reported but does NOT auto-fail the gate (operator decides) |
| 2D contour (BACK-08) | 5×5 grid on two operator-chosen knobs | per-run | Property: grid is 5×5, no NaN cells, `(L, p_purge)` default knobs both in grid |
| RUN_MANIFEST emission (Protocol 3) | First log line + sidecar `<run_id>.manifest.json` | per-run | Smoke test: launch a backtest, assert manifest JSON contains all `BotConfig` leaves AND first stdout line is the manifest record |
| Architecture diagram drift (Protocol 2) | `docs/architecture.yml` BacktestEngine node | per-commit | Pre-commit `scripts/architecture_lint.py` blocks commits that touch `python/brain/backtest/` without updating yaml |
| Reward-budget lineage filter (BACK-01 absorbing B6) | SQL `WHERE data_source = 'operator'` | per-replay-window | Unit test: inject `synthetic_current` row → assert it's filtered AND a warning is logged |

---

## Validation Sign-Off

- [ ] All 8 phase requirements (BACK-01..BACK-08) plus Wave-0 prerequisite have at least one `<automated>` verification command
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify in the per-task map
- [ ] Wave 0 test scaffolding files land before any backtest engine source file
- [ ] No `pytest --watch` or other watch-mode flags in any task command
- [ ] Feedback latency for the quick run < 30s on a clean checkout
- [ ] Bootstrap idempotence test (BACK-07) covers the manifest → RNG seed derivation
- [ ] Ship-gate fail-path test asserts `var/backtest/<run_id>/ship-gate-report.md` exists AND a non-zero exit code is returned
- [ ] Perturbation grid test enumerates leaves via `BotConfig.model_dump` reflection (NOT a hardcoded list — adding a knob to `BotConfig` must auto-extend the grid)
- [ ] Reward-budget lineage filter test proves `synthetic_current` rows are excluded from ship-gate calculations
- [ ] `nyquist_compliant: true` set in frontmatter after planner populates the per-task map and plan-checker approves

**Approval:** pending
