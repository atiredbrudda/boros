---
phase: 3
slug: loss-reward-share-models-sizing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-24
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (existing from Phase 1/2) |
| **Config file** | `python/pyproject.toml` (pytest section) |
| **Quick run command** | `cd python && uv run pytest tests/test_phase_03_*.py -x --tb=short` |
| **Full suite command** | `cd python && uv run pytest -x --tb=short` |
| **Estimated runtime** | ~60 seconds (quick), ~3 min (full) |

---

## Sampling Rate

- **After every task commit:** Run quick command (matching phase-03 test files).
- **After every plan wave:** Run full suite.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds (quick), 180 seconds (full).

---

## Per-Task Verification Map

*Populated by `gsd-planner` from RESEARCH.md `## Validation Architecture` section.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | LOSS-01 | — | empirical replay produces per-cell PnL distribution | unit | `cd python && uv run pytest tests/test_loss_replay.py::test_empirical_grid -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 2 | LOSS-02 | — | nearest-neighbor fallback logs warning on sparse cells | unit | `cd python && uv run pytest tests/test_loss_expected.py::test_sparse_cell_warning -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 2 | LOSS-03 | — | OU scaffold raises NotImplementedError with v1.0 interface locked | unit | `cd python && uv run pytest tests/test_loss_ou_scaffold.py -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 1 | REWARD-01 | — | `R_capped(Q_me)` returns `sub_cap`-labeled curve at $100 | unit | `cd python && uv run pytest tests/test_reward_share.py::test_sub_cap_regime -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 1 | REWARD-01 | — | cap-binding branch returns `cap_binding` label at $5000 collateral | unit | `cd python && uv run pytest tests/test_reward_share.py::test_cap_binding_branch -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 1 | REWARD-02 | — | `Q_total_in_range` tracker returns number from all-limit-orders + parquet aggregation | unit + integration | `cd python && uv run pytest tests/test_competition_tracker.py -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 3 | REWARD-03 | — | `Sizer.Q_me_target()` returns `Q_min` deterministically on $100 across shortlist | unit | `cd python && uv run pytest tests/test_sizer.py::test_q_min_at_100_collateral -x` | ❌ W0 | ⬜ pending |
| 03-03-02 | 03 | 3 | REWARD-04 | — | `Q_cap` computed in code; scale-up > $1k collateral yields `Q_me_target < Q_cap` | unit | `cd python && uv run pytest tests/test_sizer.py::test_scale_up_cap_binding -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 4 | PROTO-02 | — | `docs/architecture.yml` contains `LossModel`, `RewardShareModel`, `Sizer` nodes with typed edges | lint | `python scripts/architecture_lint.py` | ✅ | ⬜ pending |
| 03-04-02 | 04 | 4 | PROTO-04 | — | `BotConfig` exposes new Phase 3 knobs (pendle_price_usd, depth_bucket_edges, tau_bucket_edges, reward_cap_apr_annual, epoch_days, q_min, q_max, market_reward_calibration) | unit | `cd python && uv run pytest tests/test_config_schema.py::test_phase_03_knobs -x` | ❌ W0 | ⬜ pending |
| 03-04-03 | 04 | 4 | PROTO-01 | — | calibration CLI emits RUN_MANIFEST with Phase 3 knob tree | integration | `cd python && uv run pytest tests/test_manifest_phase_03.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Planner will refine task IDs / commands / coverage to match actual plan decomposition.*

---

## Wave 0 Requirements

- [ ] `python/tests/test_loss_replay.py` — LOSS-01 empirical replay stubs
- [ ] `python/tests/test_loss_expected.py` — LOSS-02 expected_loss interface stubs
- [ ] `python/tests/test_loss_ou_scaffold.py` — LOSS-03 OU interface + failing stub
- [ ] `python/tests/test_reward_share.py` — REWARD-01 sub-cap + cap-binding branch stubs
- [ ] `python/tests/test_competition_tracker.py` — REWARD-02 `Q_total_in_range` stubs
- [ ] `python/tests/test_sizer.py` — REWARD-03/04 sizer + cap-regime stubs
- [ ] `python/tests/test_config_schema.py` — Phase 3 knob delta coverage (extends existing file)
- [ ] `python/tests/test_manifest_phase_03.py` — RUN_MANIFEST shape after Phase 3 knob add
- [ ] `python/tests/conftest.py` — shared `chain_time_fixture`, parquet temp-dir (already exists; extend for Phase 3 fixtures)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `MarketRewardCalibration` operator-refresh workflow at daily re-screen | REWARD-01 | Requires operator to paste values from Pendle announcements (no live API source) | Run `cd python && uv run python -m boros_brain.reward.calibrate --market ETHUSDT-29MAY2026 --e-liq-pendle <N> --long-split <f> --short-split <f>`; verify row in `market_reward_calibration` table; verify `data_source='operator'` stamped |
| Fill-loss coarse-bound vs per-cell `E[loss|fill]` comparison vs Phase 1 `fill_loss_coarse_bound=0.02` | LOSS-02 | Sanity check on calibration output before Phase 5 backtest | Run `cd python && uv run python -m boros_brain.loss.compare_bound --market <M>`; verify per-cell mean `E[loss|fill]` sits within ±50% of coarse bound or raises investigation-flag log |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 180s (full suite)
- [ ] `nyquist_compliant: true` set in frontmatter (flip after plans lock per-task map)

**Approval:** pending
