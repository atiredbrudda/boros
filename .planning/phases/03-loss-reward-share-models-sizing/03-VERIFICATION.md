---
phase: 03-loss-reward-share-models-sizing
verified: 2026-04-25T00:00:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
---

# Phase 3: Loss & Reward-Share Models + Sizing Verification Report

**Phase Goal:** Deliver the other two EV-rule inputs — empirical E[loss|fill] and capped pro-rata reward-share R_capped(Q_me) — plus the sizing optimizer. At $100 collateral the cap never binds (sub-cap regime), but cap-binding code must exist so scale-up doesn't silently oversize. OU-on-basis parametric loss is scaffolded as a v1.0 interface-only stub so the decision engine doesn't need restructuring later.
**Verified:** 2026-04-25T00:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LossModel.expected_loss covers grid with sparse-cell fallback (ROADMAP SC #1) | VERIFIED | `expected_loss.py` implements exact→nearest_neighbor→coarse_bound three-tier fallback; `test_loss_model_fit_and_expected_loss.py` 9 tests all pass; structured `loss_model.sparse_cell_fallback` warning with market_id/depth/tau/n_samples confirmed in code |
| 2 | RewardShareModel.R_capped produces sub_cap regime at $100 and cap_binding at scale-up (ROADMAP SC #2) | VERIFIED | `r_capped_curve` returns `RewardCurveOutput.regime` field with correct labels; `test_reward_curve.py` 12 tests pass including `test_sub_cap_regime`, `test_cap_binding_regime`, `test_market_saturated_regime` |
| 3 | Sizer.Q_me_target() returns Q_min deterministically at $100 and Q_me<Q_cap at $5k scale-up (ROADMAP SC #3) | VERIFIED | `test_sizer.py::test_q_min_fixed_point_at_100_collateral` PASS (`q_me_target_pendle == approx(0.001)`); `test_sizer.py::test_scale_up_to_5k_cap_binding` PASS; 9/9 sizer tests pass |
| 4 | OU-on-basis scaffold with failing stub (ROADMAP SC #4) | VERIFIED | `ou_parametric.py` exports `OUBasisLossModel` Protocol + `fit_ou_basis` raising `NotImplementedError('LOSS-03 scaffold')`; `test_loss_model_ou_scaffold.py` 3 tests pass (including signature-equality check) |
| 5 | brain.main.run() spawns loss_model refit loop + competition_tracker loop; both join cancel-on-shutdown tuple | VERIFIED | `main.py` lines 161-165 spawn `run_loss_model_refit_loop`; lines 175-183 spawn `run_competition_tracker_loop`; cancel tuple at lines 194-201 includes `loss_refit_task` + `comp_task` alongside 4 existing tasks |
| 6 | loss_model/replay.py wires pendle_price_usd from config.pricing (resolves Plan 03-01 TODO) | VERIFIED | `replay.py` contains 3 occurrences of `config.pricing.pendle_price_usd`; grep for `pendle_price_usd: float = 1.0` returns 0 |
| 7 | architecture.yml + ARCHITECTURE.md carry full Phase-3 delta; architecture_lint and no_time_time_lint pass clean | VERIFIED | `test_architecture_lint_clean` PASS; `scripts/no_time_time_lint.py` exits 0; `_BANNED_DIRS` includes all 3 new entries; architecture.yml has 35 `brain.loss_model.` refs, 33 `brain.reward_model.` refs, 20 `brain.sizer.` refs |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `python/src/boros_brain/loss_model/config.py` | LossModelConfig + FeesConfig Pydantic sub-models | VERIFIED | `class LossModelConfig(StrictBase)` exists; 12 knobs + 8 FeesConfig knobs confirmed |
| `python/src/boros_brain/loss_model/schemas.py` | LossGridArtifact, ExpectedLossInput/Output, LossModelNoFreshGridError | VERIFIED | All 4 classes present |
| `python/src/boros_brain/loss_model/expected_loss.py` | expected_loss sync sub-10ms with 3-tier fallback | VERIFIED | `def expected_loss` at line 73; three fallback modes confirmed |
| `python/src/boros_brain/loss_model/ou_parametric.py` | OUBasisLossModel Protocol + fit_ou_basis NotImplementedError stub | VERIFIED | Protocol at line 31; `raise NotImplementedError` at line 48 |
| `python/src/boros_brain/reward_model/r_capped.py` | r_capped_curve closed-form | VERIFIED | `def r_capped_curve` at line 27; 12 tests pass |
| `python/src/boros_brain/reward_model/q_cap.py` | compute_q_cap algebra | VERIFIED | `def compute_q_cap` at line 26 |
| `python/src/boros_brain/reward_model/competition_tracker.py` | CompetitionTracker + run_competition_tracker_loop | VERIFIED | `class CompetitionTracker` at line 41; reads `order_book_raw` (NOT combined) per T-03-06 |
| `python/src/boros_brain/sizer/config.py` | SizerConfig with 6 knobs | VERIFIED | `class SizerConfig(StrictBase)` at line 30; all 6 knobs present (`collateral_usd`, `q_min_pendle`, `q_max_safety_margin`, `optimizer_grid_points`, `optimizer_method`, `notional_per_yu_usd`) |
| `python/src/boros_brain/sizer/schemas.py` | SizerInput, SizerOutput, InsufficientCollateralError | VERIFIED | All 3 classes present at lines 28, 51, 70 |
| `python/src/boros_brain/sizer/optimizer.py` | q_me_target sync optimizer composing fill/loss/reward models | VERIFIED | `def q_me_target` at line 64; all 4 imports confirmed; `scipy.optimize.minimize_scalar` at lines 226 and 244 |
| `python/src/boros_brain/sizer/cli.py` | `target` subcommand with MANIFEST-FIRST boot | VERIFIED | `def build_parser` at line 30; `def main` at line 104 |
| `python/src/boros_brain/config/schema.py` | BotConfig.sizer attached | VERIFIED | `sizer: SizerConfig = Field(default_factory=SizerConfig)` at line 189; import at line 23 |
| `python/src/boros_brain/pricing/config.py` | PricingConfig with pendle_price_usd | VERIFIED | `class PricingConfig(StrictBase)` at line 23 |
| `python/src/boros_brain/main.py` | Spawns 3 Phase-3 async tasks | VERIFIED | 3 new spawns + cancel tuple confirmed |
| `python/src/boros_brain/loss_model/replay.py` | pendle_price_usd wired from config.pricing | VERIFIED | 3 occurrences of `config.pricing.pendle_price_usd` |
| `scripts/no_time_time_lint.py` | _BANNED_DIRS extended with 3 new entries | VERIFIED | `loss_model/`, `reward_model/`, `sizer/` all present at lines 44-46 |
| `docs/architecture.yml` | All Phase-3 module/storage/config_knob/edge rows | VERIFIED | 24+ module nodes; 4 storage nodes; ~34 config_knob nodes; ~40 edges; architecture_lint exits 0 |
| `docs/ARCHITECTURE.md` | Phase-3 Mermaid subgraph | VERIFIED | `Phase 3` appears 5 times; `subgraph phase3` block present |
| `python/tests/test_sizer.py` | 7 core sizer tests | VERIFIED | 9 tests collected (7 named + 2 parametrized variants of optimizer_dominates); all pass |
| `python/tests/test_manifest_contains_all_knobs.py` | test_phase3_leaves_surfaced (>=34 leaves) | VERIFIED | Test passes; 34 Phase-3 leaves confirmed |
| `python/tests/test_sqlite_single_writer.py` | test_phase3_tables_have_single_writer | VERIFIED | Test passes; 3 Phase-3 tables each have single writer confirmed |
| `state.loss_grid_artifacts` SQLite table | Alembic 0004 | VERIFIED | `test_all_8_tables_exist_after_migration` passes; table in expected set |
| `state.competition_history` SQLite table | Alembic 0005 | VERIFIED | Table in migration test expected set |
| `state.market_reward_calibration` SQLite table | Alembic 0006 with LOCKED D-01 | VERIFIED | Table in migration test expected set; `data_source='operator'` CHECK constraint |
| `strategy/v0.5-default.yaml` | `sizer:` block with `notional_per_yu_usd: 90000.0` | VERIFIED | `sizer:` at line 123; `notional_per_yu_usd: 90000.0` at line 129 |
| 9 Phase-3 LLM Wiki pages | Filed with Status + wiki-links | VERIFIED | All 9 pages confirmed: empirical-loss-grid-v05, ou-on-basis-loss-scaffold, fee-cost-term-in-expected-loss, reward-cap-geometry-v05, competition-tracker-data-sources-v05, market-reward-calibration-operator-workflow, e-liq-per-epoch-source-decision, sizing-optimizer-sub-cap-regime-v05, unit-consistency-pendle-units-v05 |
| Protocol-5 supersedences (5 wiki operations) | 3 Historical flips + 1 promotion + 1 narrowing | VERIFIED | fill-loss-coarse-bound-v05 → Historical; economics-kill-switch-v05 → Historical; economics-kill-switch-usd-variant-v10 → Current (promoted); historical-reward-budget-reconstruction-infeasible → Historical; live-e-liq-polling-data-11 → narrowed with SCOPE NARROWING banner |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `sizer/optimizer.py` | `fill_model/predict.py` | `from ..fill_model.predict import predict` | WIRED | Line 29 in optimizer.py; `predict(PredictInput(...))` called at line 119 |
| `sizer/optimizer.py` | `loss_model/expected_loss.py` | `from ..loss_model.expected_loss import expected_loss` | WIRED | Line 31 in optimizer.py; `expected_loss(ExpectedLossInput(...))` called inside q_me_target |
| `sizer/optimizer.py` | `reward_model/r_capped.py` | `from ..reward_model.r_capped import r_capped_curve` | WIRED | Line 34 in optimizer.py; `r_capped_curve(RewardCurveInput(...))` called in grid loop and shortcuts |
| `sizer/optimizer.py` | `reward_model/q_cap.py` | `from ..reward_model.q_cap import compute_q_cap` | WIRED | Line 33 in optimizer.py; `compute_q_cap(...)` called at step 2 of q_me_target |
| `config/schema.py` | `sizer/config.py` | `from ..sizer.config import SizerConfig` | WIRED | Line 23 in schema.py; `sizer: SizerConfig = Field(default_factory=SizerConfig)` at line 189 |
| `main.py` | `loss_model/refit_loop.py` | `run_loss_model_refit_loop(cfg, manifest.run_id)` | WIRED | Lines 161-165 in main.py; cancel tuple at line 199 |
| `main.py` | `reward_model/competition_tracker.py` | `run_competition_tracker_loop(cfg, manifest.run_id, ...)` | WIRED | Lines 175-183 in main.py; cancel tuple at line 200 |
| `loss_model/replay.py` | `pricing/config.py` | `config.pricing.pendle_price_usd` | WIRED | 3 occurrences in replay.py; `pendle_price_usd: float = 1.0` default removed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `sizer/optimizer.py` | `p_fill_output` | `fill_model.predict()` — reads `fill_model_fits` SQLite table | Yes — tested with seeded real fit artifacts in `test_propagates_fill_model_errors` (raises when no artifact) | FLOWING |
| `sizer/optimizer.py` | `e_loss_output` | `loss_model.expected_loss()` — reads `loss_grid_artifacts` SQLite table | Yes — tested with seeded real grid artifacts in `test_propagates_loss_model_errors` (raises when no artifact) | FLOWING |
| `sizer/optimizer.py` | `r_out` | `reward_model.r_capped_curve()` — pure closed-form computation | Yes — deterministic formula with real inputs from SizerInput | FLOWING |
| `sizer/optimizer.py` | `q_cap` | `reward_model.compute_q_cap()` — pure closed-form computation | Yes — deterministic formula | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All sizer tests pass (9 tests) | `uv run python -m pytest tests/test_sizer.py -v` | 9 passed in 1.10s | PASS |
| All Phase-3 tests pass (50 tests) | `uv run python -m pytest tests/test_loss_model_*.py tests/test_reward_curve.py tests/test_competition_tracker.py tests/test_market_reward_calibration.py tests/test_manifest_contains_all_knobs.py` | 50 passed, 1 skipped | PASS |
| Full test suite (excluding pre-existing screener_filter) | `uv run python -m pytest tests/ -x -q` | 253 passed, 1 skipped | PASS |
| architecture_lint.py exits 0 | `python scripts/architecture_lint.py` | exit=0 (clean) | PASS |
| no_time_time_lint.py exits 0 | `uv run python scripts/no_time_time_lint.py` | exit=0 (clean) | PASS |
| sqlite_writer_lint.py exits 0 | `python scripts/sqlite_writer_lint.py` | exit=0 (clean) | PASS |
| BotConfig.sizer attached with 6 knobs | `python -c "from boros_brain.config.schema import BotConfig; bc = BotConfig(...); print(bc.sizer)"` | sizer field present with all 6 defaults | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| LOSS-01 | 03-01 | Empirical post-fill path replayer over historical fills | SATISFIED | `replay_historical_fills` in `loss_model/replay.py`; DuckDB CTE join with no-look-ahead invariant; `test_loss_model_replay.py` 3 pass + 1 skip (Phase-5 integration) |
| LOSS-02 | 03-01 | E[loss\|fill] exposed with sparse-cell nearest-neighbor fallback | SATISFIED | `expected_loss()` three-tier fallback (exact→nearest_neighbor→coarse_bound); structured warn log confirmed; `test_loss_model_fit_and_expected_loss.py` covers all fallback tiers |
| LOSS-03 | 03-01 | OU-on-basis scaffold with failing stub test | SATISFIED | `ou_parametric.py` exports `OUBasisLossModel` Protocol + `fit_ou_basis` NotImplementedError; signature-equality test passes |
| REWARD-01 | 03-02 | Capped pro-rata reward-share calculator | SATISFIED | `r_capped_curve` implements `R_uncapped = E_liq×side_split×(Q_me×t_frac)/(Σ_others+Q_me×t_frac)`; `R_capped = min(R_uncapped, cap_budget)`; 12 tests pass |
| REWARD-02 | 03-02 | Q_total_in_range tracker polled every cycle | SATISFIED | `CompetitionTracker.run_one_cycle()` polls `POST /v2/accounts/all-limit-orders` + reads `parquet.order_book_raw`; 5 tracker tests pass |
| REWARD-03 | 03-03 | Sizing optimizer Q_me_target | SATISFIED | `q_me_target()` in `sizer/optimizer.py`; returns Q_min at $100 (test passes); $5k scale-up cap_binding test passes |
| REWARD-04 | 03-03 | Q_cap computation present in code | SATISFIED | `compute_q_cap()` in `reward_model/q_cap.py`; wired into sizer optimizer step 2; cap-binding architecture.yml edge declared |

All 7 requirement IDs from phase plans (LOSS-01, LOSS-02, LOSS-03, REWARD-01, REWARD-02, REWARD-03, REWARD-04) are accounted for. No orphaned requirements detected — all 7 are mapped to Phase 3 in REQUIREMENTS.md traceability table.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `loss_model/replay.py` | formerly had `pendle_price_usd: float = 1.0` default | TODO placeholder resolved in Plan 03-04 | INFO | Not a stub — resolved. `build_per_fill_pnl_from_frame` retains `pendle_price_usd: float | None = None` with config fallback (test injection seam, not a stub) |
| `loss_model/ou_parametric.py` | `raise NotImplementedError` | Intentional scaffold | INFO | Documented LOSS-03 stub; `OUBasisLossModel` Protocol exists; v1.0 drop-in point. Tests assert this behavior. Not a blocker. |

No blocker or warning-severity anti-patterns found. The NotImplementedError in `ou_parametric.py` is the required Phase 3 LOSS-03 scaffold behavior, not an accidental stub.

### Human Verification Required

None. All Phase-3 behaviors are verified programmatically:
- Math correctness verified via unit tests with known-input/known-output assertions
- Architecture wiring verified via architecture_lint.py
- Time-clock discipline verified via no_time_time_lint.py
- SQLite single-writer discipline verified via sqlite_writer_lint.py

### Gaps Summary

No gaps found. All 7 observable truths verified. All required artifacts exist, are substantive, and are wired. All key links confirmed. All 7 requirement IDs satisfied. Full test suite: 253 pass, 1 skip (intentional Phase-5 integration placeholder), 0 fail.

**Note on pre-existing screener_filter failures:** These were documented in Plans 03-01/02/03 SUMMARY files as pre-existing, but at verification time `tests/test_screener_filter.py` actually passes (6/6 tests green). The pre-existing bug was resolved between plan execution and verification — likely by the same Plan 03-04 wiring work that fixed the underlying `size_float` DuckDB issue. This is a positive finding, not a concern.

---

_Verified: 2026-04-25T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
