---
phase: 2
slug: fill-model-nhpp-v0-5
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `02-RESEARCH.md` § Validation Architecture (lines 696–765).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + hypothesis 6.x + pytest-asyncio 0.24 (already in `python/pyproject.toml` dev deps) |
| **Config file** | `python/pyproject.toml` `[tool.pytest.ini_options]`; `python/tests/conftest.py` |
| **Quick run command** | `cd python && uv run pytest tests/test_fill_model_* -x` |
| **Full suite command** | `cd python && uv run pytest -x` |
| **Estimated runtime** | ~10s quick · ~120s full |

---

## Sampling Rate

- **After every task commit:** Run `cd python && uv run pytest tests/test_fill_model_* -x` (<10s)
- **After every plan wave:** Run `cd python && uv run pytest -x` (<120s)
- **Before `/gsd-verify-work`:** Full suite green; calibration-plot artifact committed (plot is an artifact, not a test); GoF threshold bootstrap-calibrated on real 14-day history of the confirmed shortlist market from Phase 1.
- **Max feedback latency:** 10s per commit; 120s per wave.

---

## Per-Task Verification Map

> Task IDs (`02-PP-TT`) use `PP = plan number`, `TT = task index` per the planner's 4-sub-plan decomposition recommendation. Actual task IDs finalized in PLAN.md; this map is the **test inventory the planner must honor** — every test-type row below MUST map to at least one `<automated>` entry in a task's `<acceptance_criteria>`.

| Test ID | Target Plan (recommended) | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|---------------------------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T-02-F-01 | 02-01 feature-pipeline | 1 | FILL-02 | V5 Input Validation | Covariate whitelist enforced (non-whitelisted covariate → `ConfigError`) | unit | `uv run pytest tests/test_fill_model_fit_basic.py::test_covariate_whitelist -x` | ❌ W0 | ⬜ pending |
| T-02-F-02 | 02-01 feature-pipeline | 1 | FILL-02 | V7 Error Handling | Left-closed EWMA (no look-ahead): last-bin trade does not affect its own `ewma_vol` | unit | `uv run pytest tests/test_fill_model_features.py::test_ewma_no_lookahead -x` | ❌ W0 | ⬜ pending |
| T-02-Q-01 | 02-02 queue-tracker | 1 | FILL-03 | V7 Error Handling | Pessimistic ≥ realized ≥ optimistic for every tick | property | `uv run pytest tests/test_fill_model_queue_tracker.py::test_bracket_invariant -x` | ❌ W0 | ⬜ pending |
| T-02-Q-02 | 02-02 queue-tracker | 1 | FILL-03 | — | `eventIndex`-ordered replay matches hand-computed expectation on tiny tape fixture | unit | `uv run pytest tests/test_fill_model_queue_tracker.py::test_replay_on_fixture -x` | ❌ W0 | ⬜ pending |
| T-02-Q-03 | 02-02 queue-tracker | 1 | FILL-03 | — | Drift diagnostic reports non-zero signed mean on synthetic biased tape | unit | `uv run pytest tests/test_fill_model_queue_tracker.py::test_drift_bias_detected -x` | ❌ W0 | ⬜ pending |
| T-02-Q-04 | 02-02 queue-tracker | 1 | FILL-06 | — | `bracket_width_warn` log emitted on synthetic widening bracket | unit | `uv run pytest tests/test_fill_model_queue_tracker.py::test_bracket_width_warn -x` | ❌ W0 | ⬜ pending |
| T-02-A-01 | 02-02 amm-consumption | 1 | FILL-04 | V5 Input Validation | `amm_share(δ, t) ≥ 0` at every (δ, t) on fixture | property | `uv run pytest tests/test_fill_model_amm_consumption.py::test_amm_share_non_negative -x` | ❌ W0 | ⬜ pending |
| T-02-A-02 | 02-02 amm-consumption | 1 | FILL-04 | — | Per-epoch runtime conservation identity holds on synthetic epoch | unit | `uv run pytest tests/test_fill_model_amm_consumption.py::test_epoch_conservation -x` | ❌ W0 | ⬜ pending |
| T-02-M-01 | 02-03 fit-predict | 2 | FILL-01 | — | Log-linear Poisson GLM fit on 5 covariates converges with finite β | unit | `uv run pytest tests/test_fill_model_fit_basic.py::test_fit_converges_on_synthetic_poisson -x` | ❌ W0 | ⬜ pending |
| T-02-M-02 | 02-03 fit-predict | 2 | FILL-01 | V7 Error Handling | Fit on empty / rank-deficient data marks `fit_status=degraded` and does not crash | unit | `uv run pytest tests/test_fill_model_fit_basic.py::test_fit_degrades_on_sparse -x` | ❌ W0 | ⬜ pending |
| T-02-P-01 | 02-03 fit-predict | 2 | FILL-05 | — | `predict()` returns `p ∈ [0,1]` on happy path | unit | `uv run pytest tests/test_fill_model_predict_contract.py::test_predict_in_unit_interval -x` | ❌ W0 | ⬜ pending |
| T-02-P-02 | 02-03 fit-predict | 2 | FILL-05 | V7 Error Handling | `predict()` raises `FillModelStaleFeatureError` on NaN covariate (no silent exp(β₀) fallback) | unit | `uv run pytest tests/test_fill_model_predict_contract.py::test_predict_raises_on_nan -x` | ❌ W0 | ⬜ pending |
| T-02-P-03 | 02-03 fit-predict | 2 | FILL-05 | — | `predict()` monotone-decreasing in δ (ceteris paribus) | property | `uv run pytest tests/test_fill_model_predict_contract.py::test_predict_monotone_in_depth -x` | ❌ W0 | ⬜ pending |
| T-02-P-04 | 02-03 fit-predict | 2 | FILL-05 | — | `predict()` monotone-decreasing in queue_ahead | property | `uv run pytest tests/test_fill_model_predict_contract.py::test_predict_monotone_in_queue -x` | ❌ W0 | ⬜ pending |
| T-02-C-01 | 02-04 calibration | 3 | FILL-05 | — | Calibration-plot predicted P(fill) matches realized within ±5pp per decile on hold-out | integration | `uv run pytest tests/test_fill_model_calibration_gof.py::test_calibration_on_holdout -x` | ❌ W0 | ⬜ pending |
| T-02-C-02 | 02-04 calibration | 3 | FILL-06 | — | Rolling 14-day refit loop produces a new fit artifact each cadence | integration | `uv run pytest tests/test_fill_model_calibration_gof.py::test_refit_loop_writes_artifact -x` | ❌ W0 | ⬜ pending |
| T-02-C-03 | 02-04 calibration | 3 | FILL-06 | — | GoF (Rosenblatt-KS) below bootstrap threshold triggers `fit_degraded` log line grep-able by `run_id` | unit | `uv run pytest tests/test_fill_model_calibration_gof.py::test_degraded_warning_on_regime_shift -x` | ❌ W0 | ⬜ pending |
| T-02-R-01 | 02-01 feature-pipeline | 1 | PROTO-04 (RUN_MANIFEST) | V14 Configuration | All `fill_model` knobs appear in RUN_MANIFEST (reflection-driven) | integration | `uv run pytest tests/test_manifest_reflection.py::test_manifest_contains_fill_model_knobs -x` | ❌ W0 | ⬜ pending |
| T-02-L-01 | 02-04 calibration | 3 | PROTO-02 (architecture.yml) | — | `architecture.yml` contains every new node + edge declared by Phase 2 | lint | `uv run pytest tests/test_architecture_lint.py -x` | ❌ W0 (hook exists, test stub new) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Wave 0 is a prerequisite feature — before any FILL-XX code is written, these test files and fixtures must exist as failing/stub tests so every downstream task has an `<automated>` target:

- [ ] `python/tests/test_fill_model_features.py` — FILL-02 feature pipeline (EWMA left-closed, standardization, sin/cos funding-cycle)
- [ ] `python/tests/test_fill_model_queue_tracker.py` — FILL-03 tri-track replay (pessimistic / realized / optimistic) + drift diagnostic
- [ ] `python/tests/test_fill_model_amm_consumption.py` — FILL-04 amm_share subtraction + runtime conservation identity
- [ ] `python/tests/test_fill_model_fit_basic.py` — FILL-01 GLM convergence + degraded-fit handling
- [ ] `python/tests/test_fill_model_predict_contract.py` — FILL-05 predict contract (unit interval, NaN raise, monotonicity)
- [ ] `python/tests/test_fill_model_calibration_gof.py` — FILL-06 Rosenblatt-KS GoF + refit loop
- [ ] `python/tests/test_manifest_reflection.py` — PROTO-04 (add fill_model knob assertion to existing manifest tests)
- [ ] `python/tests/test_architecture_lint.py` — PROTO-02 (stub test invoking `scripts/architecture_lint.py` as a subprocess)
- [ ] `python/tests/fixtures/fill_model_tiny_tape.ndjson` — synthetic 100-trade tape for queue replay (hand-verifiable)
- [ ] `python/tests/fixtures/fill_model_synthetic_poisson.parquet` — known-β Poisson realization for fit regression
- [ ] `python/tests/fixtures/fill_model_regime_shift.parquet` — regime-change fixture for GoF degradation
- [ ] Dependency install: `uv add statsmodels>=0.14.6` + verify `tick==0.8.0.1` installs on macOS arm64; if `tick` wheel fails, downgrade to `tick==0.7.x` and file `[[python-stack-v05]]` supersedence.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Calibration plot visual inspection (predicted P(fill) vs realized, per decile) | FILL-05 success criterion — "matches realized within calibration-test tolerance" | Visual shape (S-curve, flat tails, miscalibration direction) carries information that a ±5pp KS band does not; human eye catches systematic over/under-prediction bands. | 1. Run `uv run python -m boros_brain.fill_model.calibration_report --phase 2 --market <confirmed_id>`. 2. Open produced PNG in `python/docs/fill_model/calibration-<date>.png`. 3. Check: (a) each decile dot within its CI bar, (b) no monotone bias across deciles, (c) tail deciles (D1, D10) populated ≥ 30 events. |
| Log-grep check: `run_id` → `fit_degraded` → calibration report surface | Success Criterion #4 | Cross-cutting: involves structlog JSON output + periodic report generation + grep pipeline. End-to-end smoke is quicker to eyeball than to encode. | 1. Force a degraded fit: `uv run python -m boros_brain.fill_model.refit --force-degrade`. 2. `grep -E '"event":"fit_degraded"' var/logs/brain-*.jsonl`. 3. Confirm run_id matches the degrading run's manifest. 4. Confirm the next `calibration_report` rollup lists the degraded fit with `Status: degraded`. |
| `docs/architecture.yml` review — new nodes `FillModel`, `QueueTracker`, `AMMConsumption`, `CalibrationReport` + edges | PROTO-02 | Topology review belongs to a human — the lint catches missing entries but doesn't check semantic correctness (edge type, direction, dependency granularity). | 1. `git diff HEAD~1 -- docs/architecture.yml docs/ARCHITECTURE.md`. 2. Confirm each new node has its `calls`/`reads`/`writes`/`emits-event`/`depends-on-config` edges filled. 3. Open `docs/ARCHITECTURE.md` and confirm the Mermaid diagram renders and matches yml. |

---

## Nyquist-Rate Sampling Implication (from RESEARCH.md § Validation Architecture)

- 14-day fit window at 60s bins → **20,160 bins per market-side**.
- Hold-out: **last 20% ≈ 2,880 bins ≈ 2.8 days**.
- At ~1 event/bin on a typical confirmed shortlist market → ~2,880 events → 95% CI on realized frequency ≈ ±1.8% — **tighter than the ±5pp calibration tolerance** required by FILL-05.
- If we dropped to a 1-day (200-bin) hold-out we would **lose discriminative power** on calibration-plot extremes (D1, D10). Do not shorten.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify command, or `blocked_by: wave-0-fixtures`
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING entries in per-task map (see checklist above)
- [ ] No watch-mode flags (`--watch`, `-f`) — all commands must terminate
- [ ] Feedback latency < 10s per task, < 120s per wave
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 fixtures committed
- [ ] Calibration plot artifact committed to `python/docs/fill_model/` at phase gate

**Approval:** pending
