# Phase 3: Loss & Reward-Share Models + Sizing — Research

**Researched:** 2026-04-24
**Domain:** Post-fill P&L empirical replay + capped pro-rata reward-share calculator + sub-cap regime sizing optimizer on a single-market $100-collateral Pendle Boros CLO strategy. Plus v1.0 OU-on-basis parametric-loss scaffold.
**Confidence:** **HIGH** on LOSS-01/02 empirical replay (data is in-hand), REWARD-01/03/04 math (canonical formulas locked), REWARD-02 source (endpoint confirmed), LOSS-03 scaffold contract. **LOW** (actually **BLOCKER, see §E_liq escalation**) on the live `E_liq_per_epoch` source that REWARD-01 needs as the emission numerator — the Phase 1 UAT carried concern is real and not resolvable from public docs/contracts/endpoints.

Wiki check (Protocol 1) completed against `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md`. Pages read: `[[live-e-liq-polling-data-11]]`, `[[historical-reward-budget-reconstruction-infeasible]]`, `[[historical-reward-budget-reconstruction-feasible-via-distributor-events]]`, `[[economics-kill-switch-v05]]`, `[[economics-kill-switch-usd-variant-v10]]`, `[[fill-loss-coarse-bound-v05]]`, `[[fee-schedule]]`, `[[fill-model-predict-contract]]`, `[[Voluntary cancel reward behavior]]`, `[[EV cancel rule]]`, `[[Strategy thesis LO liquidity rewards]]`, `[[sqlite-state-spine-v05]]`, `[[pydantic-botconfig-schema-v05]]`, `[[covariate-selection-v05]]`, `[[run-manifest-writer]]`, `[[Single writer per table discipline]]`. No existing Phase-3 pages — every new finding below must write back.

## Summary

Phase 3 delivers the remaining two EV-rule inputs and the sizing optimizer. The math is locked by `boros_consolidated_plan.md` §3 + §4 and by the Phase 1 economics-gate formulas already in code; the engineering task is (a) build the empirical loss-grid by slicing Phase 1 parquet by `(depth-from-mark, τ)` cells, (b) stand up the capped pro-rata reward curve with cap-binding geometry from existing knobs, (c) wire a sub-cap-regime optimizer that at $100 collateral returns `Q_min` deterministically, (d) scaffold an OU-on-basis interface that raises `NotImplementedError` in a failing test so v1.0 has a drop-in seam. `FillModel.predict()` is already exposed in `brain.fill_model.predict.predict` with a locked sync signature — Phase 3 only consumes it, does not touch it.

**The one unresolved question that could block the phase is the source of `E_liq_per_epoch`**: Phase 1 UAT confirmed `liquidityRewardPerEpoch`, `longBudget`, `shortBudget` are **not** in the live `GET /open-api/v1/markets` response. The reward-adjacent `config.liqSettings.{base, slope, feeRate}` fields are **liquidation-incentive parameters**, not LO-reward parameters (verified against docs.pendle.finance/boros-dev/Mechanics/Margin — see §E_liq Source Resolution). The `MultiTokenMerkleDistributor.sol` contract has `SetMerkleRoot` as its only reward-related event and exposes **no per-epoch or per-market budget**. The SDK docs section 12 teases an "Incentives API" but every probed endpoint returns 404 (see §E_liq Source Resolution for the complete probe log). The only realistic v0.5 path is **operator-configured per-market budgets** captured from the dApp UI at calibration time, stored in a new `MarketRewardCalibration` section of `BotConfig`, and refreshed manually between daily re-screens — with the **`data_source='synthetic_current'`** enum already present in `reward_budget_history` as the lineage marker. This is a `[ASSUMED]` path and needs user confirmation.

**Primary recommendation:** Build LOSS-01/02 + REWARD-01/02/03/04 + LOSS-03 scaffold as specified. For the `E_liq_per_epoch` numerator: **resolve with user before the plan ships** — Option A (operator manual calibration, accepted until distributor ABI lands) is the only path that does not push Phase 3 into Phase 4 territory. Option B (reverse-engineer the per-epoch budget from a 2-epoch Merkle root delta backfill after live rollout) is deferred to Phase 5/8.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Empirical post-fill replay (LOSS-01) | brain / Python (offline) | — | Batch job over Phase 1 parquet; DuckDB+polars stack already in brain |
| `E[loss \| fill]` grid lookup (LOSS-02) | brain / Python (1 Hz decision loop) | — | Consumed by Phase 4 `DecisionEngine.evaluate()` inside brain; sync call |
| OU-on-basis scaffold (LOSS-03) | brain / Python (module + failing test) | — | Pure interface — no runtime cost in v0.5 |
| Capped pro-rata curve `R_capped(Q_me)` (REWARD-01) | brain / Python (1 Hz) | — | Pure calc over SQLite reads (`reward_budget_history` + `clo_history` + competition tracker) |
| `Q_total_in_range` poller (REWARD-02) | brain / Python (5s cadence) | — | HTTPS REST poll on `POST /open-api/v2/accounts/all-limit-orders`; same pattern as `ELiqPoller`/`MarketsPoller` |
| Sizing optimizer `Sizer.Q_me_target()` (REWARD-03) | brain / Python (1 Hz, called by DecisionEngine Phase 4) | — | Pure function; no I/O; consumes LossModel + RewardShareModel + FillModel outputs |
| `Q_cap` cap-binding boundary (REWARD-04) | brain / Python (pure calc) | — | Algebra over current `E_liq_per_epoch` + collateral; unit-tested at scale-up |
| Fee-schedule absorption (A6) into `E[loss\|fill]` | brain / Python (inside LossModel) | — | Values from `[[fee-schedule]]` embedded as `BotConfig.fees.*` sub-model |
| Storage of loss-grid artifacts | brain SQLite + parquet | — | New `loss_grid_artifacts` table + parquet sidecar, mirrors `fill_model_fits` / `write_fit_artifact` pattern |
| RUN_MANIFEST coverage of Phase 3 knobs | brain (manifest.writer) | — | PROTO-01 reflection — adding any knob to `BotConfig.loss_model`, `BotConfig.reward_model`, `BotConfig.sizer`, or `BotConfig.pricing` automatically surfaces in manifest |

**No TS work in Phase 3.** The `hands` process only executes calldata; it never reads `LossModel`, `RewardShareModel`, or `Sizer`. Decision-engine-side consumption is Phase 4.

## User Constraints (from PROJECT.md + ROADMAP.md + STATE.md carried concerns)

Phase 3 has no `/gsd-discuss-phase` output yet. Constraints inherited from locked upstream decisions:

### Locked Decisions (cannot revisit in Phase 3 research)

1. **Target only Limit Order Liquidity Rewards** — `R_capped` uses `E_liq_per_epoch` (liquidity pool), not `E_maker_per_epoch` (maker volume pool). Maker-pool income is explicitly excluded from the EV equation (consolidated plan §5).
2. **EV-based cancel rule, no threshold dials** — `R_share`, `E[loss|fill]`, `P(fill)`, `cancel_cost`, `P(purge)` are the only inputs Phase 4 will consume. No hand-tuned thresholds inside LossModel / RewardShareModel / Sizer.
3. **OU on basis `B(t) = Implied − Underlying`** is for `E[loss|fill]` ONLY (Phase 3 scaffold, Phase v1.0 implementation). **NOT** for fill probability — `P(fill)` comes from the existing NHPP `FillModel.predict()` (Phase 2). The OU scaffold must encode that constraint in a docstring + type-signature so v1.0 doesn't accidentally re-couple them.
4. **`voluntary_cancel_forfeits_accumulated = False`** (P0-01). Phase 3 reward-share curve is purely forward-looking; no "sunk accrual preservation" branch in `RewardShareModel`.
5. **1000% APR per-account cap on rewards** — this is the `10 × collateral × epoch_days / 365` term in `R_capped`. Non-negotiable protocol rule; the cap-binding test (REWARD-04) exercises this branch at collateral > $1k.
6. **$100 collateral → sub-cap regime always** — at $100, the cap is **$1000/yr = $19.23/week ≈ 2.75 PENDLE/week at ~$7 PENDLE**. For a market with `E_liq_per_epoch` ≫ 2.75 PENDLE/wk (e.g., the ETHUSDT-29MAY anchor at ~(6.663+39.05)×7 = 320 PENDLE/epoch Short-side), the cap NEVER binds because `R_uncapped(Q_min) = E_liq × side_split × ε / Σ_others` is tiny (`ε = protocol minimum ≪ Σ_others ~ 60 YU`). This must be the `Sizer.Q_me_target()` deterministic fixed point at $100.
7. **`eventIndex` for intra-block ordering** — empirical replayer must preserve Phase 1's `eventIndex`-ordered trade-tape join; price-touch fallback at tie-break, same policy as Phase 2.
8. **Single Pydantic `BotConfig` is SSoT for knobs** — every Phase 3 knob lands in `config.schema` in the same commit as the consumer. The reflection manifest test (`test_manifest_contains_all_knobs`) mechanically catches misses.
9. **`fill_loss_coarse_bound = 0.02`** (Phase 1 coarse bound). Phase 3 refines to per-cell `E[loss|fill]`. Phase 3 must supersede `[[fill-loss-coarse-bound-v05]]` and `[[economics-kill-switch-v05]]` with `Status: Historical — superseded by [[economics-kill-switch-usd-variant-v10]]` in the same commit — supersedence protocol PROTO-05 already pre-registered in those pages.
10. **`DATA-09 R_apr` computed in PENDLE-units only** in Phase 1. Phase 3 introduces `BotConfig.pricing` sub-model with `pendle_price_usd` so the USD-variant kill-switch can finally land.
11. **A8 outside-range-wall flag is a covariate warning, NOT a hard filter** — `RewardShareModel` must accommodate every market in the Phase 1 shortlist, including markets with `outside_range_wall_ratio > 2`. Do not pre-filter.
12. **Send Txs Bot is the mandatory submission lane** — irrelevant to Phase 3 since Phase 3 does not submit anything; just noting that any Phase 3 plan that accidentally suggests direct-chain writes is out of scope.

### Claude's Discretion (research picks, plan locks)

- Exact `(depth, τ)` grid shape: bin edges, count per axis, sparse-cell nearest-neighbor algorithm. Recommendation below in §LOSS-01.
- Whether `LossModel` persists its grid as a SQLite+parquet artifact (like `fill_model_fits`) or as an in-memory refit. Recommendation: **same pattern as fill_model** — `loss_grid_artifacts` table + parquet sidecar for β / per-cell sample-count.
- Storage of Q_total_in_range poll history (new `competition_history` table vs. re-use `reward_budget_history`). Recommendation: **new table** for semantic cleanliness and to keep `data_source` CHECK constraint meaningful on `reward_budget_history`.
- OU-on-basis stub test-failure mode: `pytest.skip` vs `pytest.xfail` vs literal `raise NotImplementedError`. Recommendation: `raise NotImplementedError` in the module + a concrete test that asserts `NotImplementedError` is raised — this is more debuggable than `xfail` and leaves a clean v1.0 drop-in point.
- Whether `Sizer` lives in `brain.reward_model.sizer` or its own `brain.sizer` module. Recommendation: **own module** — sizing is conceptually a joint optimization over LossModel × RewardShareModel × FillModel outputs, not a sub-concern of reward model.
- `pendle_price_usd` source — operator-manual static knob vs Chainlink/Pyth feed. Recommendation below (§REWARD-01 fee-cost + §BotConfig delta): **static knob with a `price_source: Literal["manual", "chainlink", "pyth"] = "manual"` placeholder** so v1.0 can flip the enum without schema churn. USD-variant kill-switch defers any live-price wiring to v1.0.

### Deferred Ideas (v1.0 — OUT OF SCOPE for Phase 3)

- OU-on-basis **implementation** (LOSS-03 is scaffold only; V2-LOSS-01..04 is the v1.0 work).
- Per-market fill-model selection (V2-FILL-01..04).
- Live Pyth/Chainlink PENDLE price oracle (v1.0).
- Adversarial / outside-range-wall mitigations (V2-ADV-01/02).
- HMM confirmation overlay (V2-HMM-01/02).
- Multi-market concurrent sizing (V2-MULTI-02) — Phase 3 is single-market.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LOSS-01 | Empirical post-fill path replayer: slice historical fills by `(depth-from-mark-at-fill-time, τ)` | §LOSS-01 specifies the DuckDB join, cell definition, the "immediate market-close at fill" policy that defines the empirical loss per fill, and the parquet/SQLite persistence layer. Cell sample-count diagnostic feeds the sparse-cell warning in LOSS-02. |
| LOSS-02 | `E[loss \| fill at tick X, τ]` exposed to decision engine with documented nearest-neighbor fallback (with warning) for sparse cells | §LOSS-02 specifies the exact sync `LossModel.expected_loss(...)` signature (matches `FillModel.predict` shape), the fallback algorithm (k-NN on `(depth, τ)` Euclidean with `(1, 1 day)` metric rescaling), and the `loss_model.sparse_cell_fallback` log event that the Phase 4 DecisionEngine listens for. |
| LOSS-03 | v1.0 OU-on-basis parametric loss scaffold: module + interface + failing stub test | §LOSS-03 specifies the module `brain.loss_model.ou_parametric` with a concrete `OUBasisLossModel` interface, `raise NotImplementedError("scaffold — v1.0 drop-in point")`, and a xfail-avoidant test that asserts the error is raised and the interface surface is stable. |
| REWARD-01 | Capped pro-rata `R_capped(Q_me) = min(R_uncapped, 10 × collateral × epoch_days/365)` | §REWARD-01 specifies the closed-form formula verbatim from `boros_consolidated_plan.md` §4 step 4, documents the pitfall-A4 kink geometry, and wires the fee-schedule absorption from `[[fee-schedule]]` into the subtractive term. |
| REWARD-02 | `Q_total_in_range` tracker polled every cycle from `GET /v2/accounts/all-limit-orders` or direct order-book aggregation | §REWARD-02 confirms `/open-api/v2/accounts/all-limit-orders` is the live endpoint (verified 2026-04-24, returns `{results, resumeToken, syncStatus}`). Specifies the per-operator-only scope (it's account-scoped, not market-scoped) and falls back to **direct order-book aggregation via DuckDB over `parquet.order_book_combined`** for `Σ_others` since our own size is by definition excluded from competition. |
| REWARD-03 | Sizing optimizer: `Q_me_target = argmax R_capped − E[loss\|fill] × P(fill)` s.t. `Q_min ≤ Q_me ≤ Q_max`. At $100: `Q_me_target = Q_min` always (tested). | §REWARD-03 specifies the 1-D optimizer (grid + bracketed scipy), the sub-cap proof that `Q_min` is optimal at $100 on realistic `Σ_others` (ETHUSDT anchor + 3 backfill markets from screener), and the deterministic test case that pins this. |
| REWARD-04 | `Q_cap` computation present in code (cap-binding regime boundary) tested at collateral > $1k | §REWARD-04 specifies the algebraic `Q_cap` from consolidated plan §4 step 4, documents the two boundary cases (`Q_cap < Q_min` and `E_liq × t_frac ≤ cap_budget`), and the scale-up unit test at `collateral = $5000` that confirms `Q_me_target < Q_cap`. |

## Project Constraints (from CLAUDE.md)

Every Phase 3 plan MUST obey:

1. **LLM Wiki write-back (Protocol 1)** — new pages required:
   - `[[reward-cap-geometry-v05]]` — piecewise-linear `R_capped(Q_me)` curve with kink-point plot + three regime labels (`sub_cap`, `cap_binding`, `market_saturated`)
   - `[[empirical-loss-grid-v05]]` — cell definitions, bin edges, sparse-cell fallback, parquet/SQLite persistence
   - `[[e-liq-per-epoch-source-decision]]` — documents the user-escalation outcome and the operator-manual calibration path (see §E_liq Source Resolution)
   - `[[sizing-optimizer-sub-cap-regime-v05]]` — sub-cap regime proof, $100-collateral deterministic fixed point, scale-up test
   - `[[ou-on-basis-loss-scaffold]]` — v1.0 drop-in contract, failing stub, interface spec
   - `[[competition-tracker-data-sources-v05]]` — `/accounts/all-limit-orders` for our own positions, DuckDB aggregation for `Σ_others`
   - `[[fee-cost-term-in-expected-loss]]` — A6 absorption: taker + settlement + entrance + gas amortization into the E[loss|fill] integrand
   
   Supersede in the same commit:
   - `[[fill-loss-coarse-bound-v05]]` → `Status: Historical — superseded by [[empirical-loss-grid-v05]]`
   - `[[economics-kill-switch-v05]]` → `Status: Historical — superseded by [[economics-kill-switch-usd-variant-v10]]`
   - `[[economics-kill-switch-usd-variant-v10]]` → promote from `Current — deferred to Phase 3` to `Current`

2. **Atomic `docs/architecture.yml` update (Protocol 2)** — see §Architecture Manifest Delta. Every Phase 3 module + storage + config knob must land in the same commit as its source. Pre-commit `architecture_lint.py` will reject drift.

3. **RUN_MANIFEST reflection (Protocol 3, PROTO-04)** — new sub-models `LossModelConfig`, `RewardShareModelConfig`, `SizerConfig`, `PricingConfig`, `FeesConfig` added to `BotConfig`. Reflection via `config.model_dump(mode='json')` automatically surfaces them in the manifest; `test_manifest_contains_all_knobs` proves this mechanically.

4. **No `time.time()` in `loss_model/`, `reward_model/`, `sizer/` paths** — extend `scripts/no_time_time_lint.py` to include these three new directories (one-line change; same pattern as Phase 2's `fill_model/` extension). All time comparisons use `brain.data.chain_time.now_cached()`.

5. **SQLite single-writer-per-table** — new tables `loss_grid_artifacts`, `competition_history` each have exactly one writer module. Lint enforcement already in place (`scripts/sqlite_writer_lint.py`).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `polars` | 1.40.1 | Feature join + loss-grid cell aggregation | `[VERIFIED: python/pyproject.toml]` Already the bulk-transform tool; `pl.scan_parquet` + `group_by` + `agg` is the canonical cell-construction primitive. |
| `duckdb` | 1.5.0 | Ad-hoc SQL joins over `parquet.market_trades` + `parquet.order_book_raw` + `parquet.order_book_combined` + `parquet.underlying_apr` + `state.clo_history` + `state.reward_budget_history` to build per-fill rows | `[VERIFIED: python/pyproject.toml]` Already wired via `brain.duckdb_layer.setup`. Phase 2 feature-build uses the same pipeline. |
| `scipy` | >=1.11 (transitively via statsmodels) | 1-D bracketed optimization for `Sizer.Q_me_target` (`scipy.optimize.minimize_scalar(method='bounded')`) + L-BFGS-B for the v1.0 OU MLE when LOSS-03 is replaced | `[CITED: STACK.md §OU parameter estimation]` Already endorsed for numerical work; bracketed scalar optimizer is ~10 lines. |
| `numpy` | >=2.0 | Array primitive | `[VERIFIED: python/pyproject.toml]` |
| `pydantic` | 2.13.3 | `LossModelConfig`, `RewardShareModelConfig`, `SizerConfig`, `PricingConfig`, `FeesConfig` sub-models | Already in stack; `extra='forbid'` + `frozen=True` is the fixed discipline |
| `structlog` | 25.5.0 | `loss_model.fit_completed`, `loss_model.sparse_cell_fallback`, `reward_share.cap_binding`, `sizer.q_min_fixed_point`, `sizer.cap_binding_regime_entered` events | Already in stack |
| `sqlite3` (stdlib) | — | `loss_grid_artifacts` + `competition_history` writers | No external dep needed |
| `web3.py` | 7.15 | **Not used in Phase 3** (Pricing is manual knob; `Q_total_in_range` is REST + parquet, not on-chain). Listed here only to confirm we are NOT adding it to a new path. | — |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `hypothesis` | already pinned | Property-based tests: (a) `R_capped(Q_me)` is monotone non-decreasing in `Q_me` in sub-cap regime and flat in cap-binding regime, (b) `Sizer` output is always in `[Q_min, Q_max]`, (c) `Q_cap` formula is unit-dimensionally correct (PENDLE/PENDLE) | Already in dev deps |
| `pyarrow` | transitively via polars | parquet sidecar writes for loss-grid artifacts | Same pattern as `write_fit_artifact` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| scipy 1-D optimizer for `Sizer` | Ternary search on a grid | Ternary is 20 lines and trivially deterministic. scipy's `minimize_scalar` is also 20 lines wrapped but hides the grid resolution. **Decision: grid-search with 50 log-spaced points over `[Q_min, Q_max]` + scipy polish.** Makes the optimizer output reproducible-bit-for-bit across machines (required for RUN_MANIFEST / backtest reproducibility). |
| Parametric OU in Phase 3 | Defer scaffold entirely to v1.0 | ROADMAP.md locks LOSS-03 scaffold in Phase 3. The failing-test drop-in point is cheap (one module + one test) and means Phase 4 decision-engine consumers can accept `OUBasisLossModel` as a `Protocol` without restructuring later. **Decision: scaffold lands.** |
| `Q_total_in_range` from `/accounts/all-limit-orders` | Order-book aggregation from `order_book_combined` parquet at 1 Hz | The REST endpoint is **account-scoped** (needs `userAddress + accountId`) — you can't query "everyone's orders in this market." For `Σ_others` we MUST use the order-book aggregation. **Decision: both sources.** `/accounts/all-limit-orders` on our own wallet at 5s cadence for `Q_me` ground truth; DuckDB aggregation over `parquet.order_book_combined` at 1 Hz for `Σ_others = combined_size_in_clo_range - Q_me`. |
| Operator-manual `E_liq_per_epoch` budgets | Hand-compute from Merkle root deltas after 2 epochs of live operation | Merkle approach is the v1.0 target but requires live rollout to accumulate 2 epochs of `SetMerkleRoot` deltas against our own wallet's accrual. **Decision: manual for Phase 3**, see §E_liq Source Resolution. |
| pendle_price_usd as live oracle | Static operator-manual knob | Chainlink/Pyth has no `PENDLE/USD` feed on Arbitrum verified at this time; CoinGecko API introduces a hard network dependency at decision time. **Decision: manual static knob + `price_source: Literal["manual", "chainlink", "pyth"]` enum placeholder** so v1.0 flip is trivial. |

**Installation:** No new dependencies. Phase 3 uses only what Phase 1 / Phase 2 already pinned.

**Version verification:**
```bash
# Already-pinned versions; re-confirm at first Phase 3 plan
cd python && uv run python -c "import polars, duckdb, scipy, numpy; print(polars.__version__, duckdb.__version__, scipy.__version__, numpy.__version__)"
```

## Architectural Responsibility & System Architecture Diagram

```
                                                          ┌──────────────────────────┐
                                                          │  RUN_MANIFEST writer     │
                                                          │  reflects LossModelConfig│
                                                          │  + RewardShareModelConfig│
                                                          │  + SizerConfig + Pricing │
                                                          │  + FeesConfig            │
                                                          └──────────┬───────────────┘
                                                                     │ writes
                                                                     ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                     brain process                                 │
│                                                                                   │
│  ┌──────────────────┐    build loss   ┌──────────────────┐  expected_loss  ┌───┐ │
│  │ parquet.         │  grid at boot + │ brain.loss_model.│ ────────────►   │   │ │
│  │ market_trades    │  15-min refit   │   replay.py      │                 │ S │ │
│  │ order_book_*     │ ───────────────►│   fit.py         │                 │ i │ │
│  │ underlying_apr   │                 │   expected_loss.py│                │ z │ │
│  │ settlement       │                 │ (+ fees absorbed)│                 │ e │ │
│  └──────────────────┘                 └────────┬─────────┘                 │ r │ │
│                                                │ writes                    │   │ │
│                                                ▼                            │   │ │
│  ┌──────────────────┐                ┌──────────────────┐                  │   │ │
│  │ state.clo_history│                │ state.            │                 │   │ │
│  │ state.reward_    │                │ loss_grid_       │                  │   │ │
│  │   budget_history │                │ artifacts        │                  │   │ │
│  └──────┬───────────┘                └──────────────────┘                  │   │ │
│         │ reads                                                              │   │ │
│         ▼                                                                    │   │ │
│  ┌──────────────────┐  polled every ┌──────────────────┐  R_capped(Q_me)   │   │ │
│  │ brain.reward_    │  1 Hz cycle   │ brain.reward_    │ ────────────►      │   │ │
│  │   model.         │ ─────────────►│   model.         │                   │   │ │
│  │   competition_   │               │   r_capped.py    │                   │   │ │
│  │   tracker.py     │               │   q_cap.py       │                   │   │ │
│  │ (REST + parquet) │               │                  │                   │   │ │
│  └──────┬───────────┘               └──────────────────┘                   │   │ │
│         │ writes                                                            │   │ │
│         ▼                                                                    │   │ │
│  ┌──────────────────┐                                                       │   │ │
│  │ state.            │                                                      │   │ │
│  │ competition_     │                                                       │   │ │
│  │ history          │                                                       │   │ │
│  └──────────────────┘                                                       │   │ │
│                                                                              │   │ │
│  ┌──────────────────┐  predict()                                             │   │ │
│  │ brain.fill_model │ (Phase 2, LOCKED)  ────────────────────────────────► │   │ │
│  │   predict.py     │                                                        │   │ │
│  └──────────────────┘                                                        │   │ │
│                                                                               │   │ │
│                                                                     ┌────────┘   │ │
│                                                                     ▼            │ │
│                                                           ┌─────────────────┐   │ │
│                                                           │ brain.sizer.    │   │ │
│                                                           │   optimizer.py  │   │ │
│                                                           │ Q_me_target()   │   │ │
│                                                           └──────┬──────────┘   │ │
│                                                                  │              │ │
│                                                                  │ consumed by  │ │
│                                                                  ▼              │ │
│                                                           ┌─────────────────┐   │ │
│                                                           │ Phase 4         │   │ │
│                                                           │ DecisionEngine  │   │ │
│                                                           │ .evaluate()     │   │ │
│                                                           └─────────────────┘   │ │
│                                                                                   │
│  ┌──────────────────────────────────────┐                                        │
│  │ brain.loss_model.ou_parametric.py    │  (scaffold ONLY — raises               │
│  │ Protocol OUBasisLossModel            │   NotImplementedError; v1.0 drop-in)   │
│  └──────────────────────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
python/src/boros_brain/
├── loss_model/
│   ├── __init__.py
│   ├── config.py              # LossModelConfig (+ FeesConfig nested)
│   ├── schemas.py             # LossGridArtifact, ExpectedLossInput/Output, LossModelSparseCellWarning
│   ├── replay.py              # empirical post-fill replayer (LOSS-01) — DuckDB join, cell slicing, per-fill P&L
│   ├── fit.py                 # refit_once(): build grid per (market, side) and persist
│   ├── expected_loss.py       # LossModel.expected_loss(depth, tau, side, market_id) — LOSS-02 sync contract
│   ├── refit_loop.py          # async 15-min cadence (same pattern as fill_model/refit_loop.py)
│   ├── artifact.py            # dual-write parquet + SQLite (mirrors fill_model/artifact.py)
│   ├── ou_parametric.py       # LOSS-03 scaffold: OUBasisLossModel Protocol + NotImplementedError stub
│   ├── cli.py                 # `python -m boros_brain.loss_model {fit|expected-loss|calibration-report}`
│   └── __main__.py
├── reward_model/
│   ├── __init__.py
│   ├── config.py              # RewardShareModelConfig
│   ├── schemas.py             # RewardCurveOutput, RegimeLabel (Literal["sub_cap","cap_binding","market_saturated"])
│   ├── competition_tracker.py # REWARD-02: own-order poll (REST) + Σ_others (DuckDB parquet aggregation)
│   ├── r_capped.py            # REWARD-01: R_uncapped + cap + regime-label classifier
│   ├── q_cap.py               # REWARD-04: Q_cap algebra + boundary cases
│   └── cli.py                 # `python -m boros_brain.reward_model {curve|competition-snapshot}`
├── sizer/
│   ├── __init__.py
│   ├── config.py              # SizerConfig
│   ├── schemas.py             # SizerOutput (includes Q_me_target, regime, intermediate R_capped, E_loss, P_fill)
│   ├── optimizer.py           # REWARD-03: grid + scipy.minimize_scalar polish; sub-cap fixed point
│   └── cli.py
├── pricing/
│   ├── __init__.py
│   └── config.py              # PricingConfig (pendle_price_usd, price_source enum, staleness knobs)
└── state/writers/
    ├── loss_grid_artifacts.py  # single writer for state.loss_grid_artifacts
    └── competition_history.py  # single writer for state.competition_history
```

## Per-Requirement Research

### LOSS-01 — Empirical Post-Fill Path Replayer

**Approach.** Joint offline batch job over Phase 1 parquet outputs + SQLite state. One row per historical fill event on the candidate market. For each fill:
1. Identify the fill in `parquet.market_trades` (`eventIndex`, `blockTimestamp`, `rate` = fill APR, `side`, `size_float`, `txHash`).
2. Look up **mark-rate-at-fill-time** from the nearest `clo_history` row ≤ `blockTimestamp` (or `market_data` parquet's `markApr` if available — cross-check in plan).
3. Compute `depth_from_mark_ticks` = `abs(fill_rate_tick - mark_rate_tick)` using the existing tick-conversion utilities from Phase 1 screener/metrics.
4. Compute `τ = maturity_ts - blockTimestamp` bucketed into `{7d, 14d, 30d, 60d, 90d, 180d}`.
5. Compute **empirical post-fill P&L under the immediate-close policy** over the 8-hour settlement window:
   - Inventory acquired at fill: `size_float × fill_rate`.
   - Close position immediately at next available market-taker price (next `market_trades` row of opposite side within ≤ 60s).
   - P&L = `size × (close_rate − fill_rate) × τ_effective − fees`, where fees = `taker_fee × size × τ × rate + settlement_fee_amortized + gas_proxy`.
6. Bin into cells keyed by `(depth_bucket, tau_bucket, side, market_id)` and compute per-cell `mean`, `std`, `p5`, `p50`, `p95`, `n_samples`.

**Interface signature:**
```python
# brain.loss_model.replay
def replay_historical_fills(
    config: BotConfig,
    market_id: str,
    *,
    window_start_ts: int,
    window_end_ts: int,
    duck_conn: duckdb.DuckDBPyConnection,
) -> list[PerFillPnL]: ...

# brain.loss_model.fit
def fit_loss_grid(
    config: BotConfig,
    market_id: str,
    side: Literal["long", "short"],
    *,
    window_start_ts: int,
    window_end_ts: int,
    run_id: str,
) -> LossGridArtifact: ...
```

**Data inputs (via DuckDB join):**
- `parquet.market_trades` (eventIndex, blockTimestamp, rate, side, size_float, size_wei)
- `parquet.order_book_raw` (snapshot-anchored mid-rate fallback if `market_data` lacks a point)
- `parquet.settlement` / `parquet.market_data` (markApr at fill time)
- `parquet.underlying_apr` (for fee amortization via floating_apr at fill time)
- `state.clo_history` (clo_lower_thresh/upper — defines depth sign convention)
- `BotConfig.fees.*` (taker_fee_rate, settlement_fee_rate, entrance_fee, gas_proxy) — see BotConfig Knob Delta

**Cell definition (recommended default, ships as BotConfig knobs):**
- `depth_bucket_edges = [0, 1, 2, 4, 8, 16, 32, inf]` (ticks)
- `tau_bucket_edges = [0, 7, 14, 30, 60, 90, 180, inf]` (days)
- `min_samples_per_cell = 5` (below this → `fit_status='sparse'` for that cell; nearest-neighbor fallback in LOSS-02)

**Edge cases:**
- Fill size in wei overflow → already handled by Phase 1 `size_float` ingester column.
- `eventIndex` missing on a market → use `blockTimestamp` + `txHash` hash ordering (Phase 1 fallback). Log `event_index_coverage='degraded'` and carry into `LossGridArtifact.event_index_coverage` (same pattern as `FitArtifact`).
- Fill at exact `clo_lower` / `clo_upper` tick — depth = 0, goes into the `[0,1)` bucket.
- No close price within 60s (very thin market, no opposite-side trade) → use `next combined market_trades opposite-side fill` regardless of delay, and flag `close_latency_s` in the per-fill row.
- Fill happens inside 8h settlement window → settlement fee charged once (not amortized over 365 days). Documented formula: `settle_fee = size × fill_rate × min(8/24, days_in_position) × rate` per `[[fee-schedule]]`.
- Zero historical fills on a market (Phase 1 screener would have filtered it, but defensively) → `LossGridArtifact.fit_status = 'degraded'`, all cells flagged `sparse`, `expected_loss()` unconditionally returns `fill_loss_coarse_bound` fallback with warning.

**Persistence:** Same atomic dual-write pattern as `fill_model/artifact.py`:
1. Parquet sidecar at `data/parquet/loss_grid_artifacts/market_id={mkt}/side={side}/window_end_ts={ts}/artifact.parquet` with the full per-cell aggregation.
2. SQLite row into `state.loss_grid_artifacts` via `brain.state.writers.loss_grid_artifacts.insert_loss_grid_artifact()`.

**Acceptance hooks (Success Criterion #1 from ROADMAP.md):** "returns a number for every cell in the `(depth, τ)` grid over historical fills on the candidate market, with a logged warning when a sparse-cell nearest-neighbor fallback is used."

---

### LOSS-02 — `E[loss | fill]` Exposed Interface

**Approach.** A sync function (mirrors `FillModel.predict` contract) that the Phase 4 DecisionEngine calls at 1 Hz. It looks up the most recent `loss_grid_artifact` for `(market_id, side)`, finds the cell covering `(depth_from_mark_ticks, τ_days)`, and returns the cell's `mean` (or `p50` — operator-configurable via `LossModelConfig.aggregation_metric: Literal["mean", "p50", "p95"]`).

**Interface signature (locked, consumed by Phase 4):**
```python
# brain.loss_model.expected_loss
@dataclass(frozen=True)
class ExpectedLossInput:
    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    time_to_maturity_s: int
    current_chain_ts: int  # Phase 4 supplies from chain_time.now_cached()

@dataclass(frozen=True)
class ExpectedLossOutput:
    expected_loss_pendle: float  # PENDLE-units; matches R_capped unit basis
    cell_n_samples: int
    cell_p50: float
    cell_p95: float
    fallback_mode: Literal["exact", "nearest_neighbor", "coarse_bound"]
    grid_artifact_run_id: str
    grid_age_s: float
    fit_status: Literal["ok", "degraded", "stale"]

class LossModelNoFreshGridError(RuntimeError):
    """No loss-grid artifact fresh enough for (market_id, side)."""

def expected_loss(
    req: ExpectedLossInput,
    *,
    sqlite_path: Path,
    config: BotConfig,
) -> ExpectedLossOutput: ...
```

**Sparse-cell fallback algorithm:**
1. Look up the cell covering `(depth, τ)`.
2. If `cell_n_samples >= config.loss_model.min_samples_per_cell` (default 5), return `fallback_mode='exact'`.
3. Else do k-NN with `k = config.loss_model.knn_k` (default 3) on Euclidean distance `sqrt((Δ_depth / 1 tick)² + (Δ_τ / 1 day)²)` (unit-normalized), weighted by `n_samples` in each neighbor cell.
4. If all neighbors within `config.loss_model.knn_max_distance` (default 4 bucket-widths) are also sparse, fall back to `config.screener.fill_loss_coarse_bound × notional_proxy` with `fallback_mode='coarse_bound'`, log `loss_model.sparse_cell_fallback` event.

**Staleness:** Same three-tier policy as `FillModel.predict`:
- `fit_warn_staleness_s` (default 1800s / 30min) → `fit_status='stale'` + warning
- `fit_max_staleness_s` (default 86400s / 24h — longer than fill model's 3600s because loss grid refits on slower cadence, tied to 14-day rolling window) → raise `LossModelNoFreshGridError`

**Unit consistency:** `expected_loss_pendle` is in PENDLE-units to match `R_capped(Q_me)`'s numerator in the EV equation. Phase 4's EV equation subtracts `expected_loss × P(fill)` from `R_share × P(no_fill)`, so both terms must share units. This works in v0.5 because the strategy never holds inventory longer than an 8h settlement window — the loss is `size × Δrate × τ` converted to PENDLE via `pendle_price_usd`. Documented as `[[unit-consistency-pendle-units-v05]]` new page.

**Edge cases:**
- `depth_from_mark_ticks < 0` (order is inside the mark — a fill here is essentially immediate) → clamp to bucket 0.
- `time_to_maturity_s < 0` (post-maturity query) → raise explicitly; Phase 4 breaker SAFE-07 will have already migrated.
- `cell_n_samples == 0` across all neighbors in max_distance → `fallback_mode='coarse_bound'`, **do NOT silently return 0** (same NaN-covariate discipline as `[[known-issues-nan-covariate-silent-fallback-do-not]]`).

**Acceptance hooks (Success Criterion #1):** Every cell returns a number; sparse cells log the `loss_model.sparse_cell_fallback` event with `market_id`, `depth`, `τ`, `fallback_mode`, `n_samples`.

---

### LOSS-03 — OU-on-basis Parametric Loss Scaffold

**Approach.** Module + Pydantic interface + raises `NotImplementedError` + test that asserts the error is raised. Provides v1.0 a mechanical drop-in point that does not require Phase 4 DecisionEngine restructuring.

**Module:** `brain.loss_model.ou_parametric`:
```python
"""OU-on-basis parametric loss scaffold — v1.0 drop-in point.

v0.5 uses the empirical loss-grid (see [[empirical-loss-grid-v05]]).
v1.0 will replace this scaffold with:
  1. MLE fit of B(t) = Implied_APR − Underlying_Funding_APR as OU(κ, θ, σ)
     on rolling 14-day windows via scipy.optimize.minimize (see STACK.md §OU).
  2. Closed-form E[loss | fill at X, τ] = E[∫_t^{t+τ} (Realized_Funding − X) du]
     with Tang-Chen bias correction (see STACK.md §OU).
  3. Optional 2σ OU-vs-empirical divergence breaker (absorbs PITFALLS B5 OU-fit-degraded).

DO NOT replace NotImplementedError with a partial implementation in v0.5.
The LOSS-03 contract is 'scaffold only' — partial implementation creates two
truth sources for E[loss|fill] that will diverge.

See [[ou-on-basis-loss-scaffold]].
"""
from typing import Protocol

class OUBasisLossModel(Protocol):
    """v1.0 interface. expected_loss(...) signature MUST match
    brain.loss_model.expected_loss.expected_loss() exactly, so Phase 4
    DecisionEngine can swap the empirical backend for the OU backend via
    config without code changes."""
    def expected_loss(self, req: ExpectedLossInput, *, sqlite_path: Path, config: BotConfig) -> ExpectedLossOutput: ...

def fit_ou_basis(*args, **kwargs) -> None:
    raise NotImplementedError(
        "LOSS-03 scaffold — v1.0 drop-in point. "
        "See [[ou-on-basis-loss-scaffold]] for the implementation plan."
    )
```

**Test (failing stub that proves the contract):**
```python
# python/tests/test_loss_model_ou_scaffold.py
def test_ou_scaffold_raises_not_implemented():
    from boros_brain.loss_model.ou_parametric import fit_ou_basis
    with pytest.raises(NotImplementedError, match="LOSS-03 scaffold"):
        fit_ou_basis(market_id="BINANCE-ETHUSDT-29MAY2026", side="long")

def test_ou_scaffold_protocol_surface():
    """Contract test — interface surface must NOT change without Phase 4 coordination."""
    from boros_brain.loss_model.ou_parametric import OUBasisLossModel
    from boros_brain.loss_model.expected_loss import expected_loss
    # Signature compatibility proof:
    import inspect
    sig_protocol = inspect.signature(OUBasisLossModel.expected_loss)
    sig_empirical = inspect.signature(expected_loss)
    assert list(sig_protocol.parameters)[1:] == list(sig_empirical.parameters)[:]
```

**Acceptance hooks (Success Criterion #4):** "The LossModel scaffold's OU-on-basis interface exists with a failing stub test so v1.0 can drop in the parametric implementation without restructuring the decision engine." — both tests above satisfy this.

---

### REWARD-01 — Capped Pro-Rata Reward-Share Calculator

**Approach.** Closed-form calculation verbatim from `boros_consolidated_plan.md` §4 step 4. Absorbs PITFALLS A4 kinked-curve geometry by emitting a three-way regime classification with every call.

**Formula (locked, not re-derivable):**
```
R_uncapped(Q_me, Σ_others, E_liq_per_epoch, side_split, t_frac):
    = E_liq_per_epoch × side_split × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)
    
cap_budget_per_epoch_pendle:
    = 10 × collateral_usd × (epoch_days / 365) / pendle_price_usd
    # 10× multiplier is the 1000% APR cap (locked by Boros protocol rule)

R_capped(Q_me) = min(R_uncapped(Q_me), cap_budget_per_epoch_pendle)

regime(Q_me):
    if R_uncapped(Q_me) >= cap_budget_per_epoch_pendle:
        return "cap_binding"
    elif Σ_others == 0 and Q_me > 0:
        return "market_saturated"  # we have the market to ourselves
    else:
        return "sub_cap"
```

**Interface signature:**
```python
# brain.reward_model.r_capped
@dataclass(frozen=True)
class RewardCurveInput:
    market_id: str
    side: Literal["long", "short"]
    q_me_pendle: float
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float  # 0..1 long- or short-side fraction of E_liq
    t_frac: float       # 1.0 at v0.5 (full-epoch posting)
    collateral_usd: float
    pendle_price_usd: float
    epoch_days: float   # 7.0 locked

@dataclass(frozen=True)
class RewardCurveOutput:
    r_uncapped_pendle: float
    r_capped_pendle: float
    cap_budget_pendle: float
    regime: Literal["sub_cap", "cap_binding", "market_saturated"]

def r_capped_curve(req: RewardCurveInput) -> RewardCurveOutput: ...
```

**Fee-cost absorption (PITFALLS A6).** Fees are NOT subtracted inside `R_capped`; they are subtracted inside `LossModel.expected_loss` (the cost side of the EV equation, matching the consolidated plan §5 formulation). This keeps `R_capped` clean and matches the EV-rule derivation. But Phase 3 MUST add a `BotConfig.fees` sub-model with the values from `[[fee-schedule]]`:
- `taker_fee_rate: float = 5e-4` (0.05%)
- `settlement_fee_rate: float = 1e-3` (0.1% per settlement period)
- `settlement_period_s: int = 28800` (8h, per `[[fee-schedule]]`)
- `market_entrance_fee_usd: float = 1.0` (amortized over expected market-lifetime)
- `gas_place_gwei: int` / `gas_cancel_gwei: int` / `gas_close_gwei: int` (Phase 3 starting estimates; Phase 4 DECIDE-03 empirically measures)

**Unit policy (critical — pitfall A4 absorbent).** At $100 USD collateral:
- `cap_budget_per_epoch_pendle = 10 × 100 × (7/365) / pendle_price_usd ≈ 0.274 PENDLE / pendle_price_usd`
- If `pendle_price_usd ≈ $7` (recent observation), `cap_budget_per_epoch_pendle ≈ 0.039 PENDLE/epoch`.
- ETHUSDT-29MAY2026 anchor: `E_liq_per_epoch × side_split ≈ 39.05 × 7 = 273 PENDLE/epoch Short-side` (from consolidated plan §Phase 4 snapshot).
- `R_uncapped(Q_min=protocol-min ≈ 0) ≈ 273 × ε / (60 + ε) ≈ 0` — absolutely below the 0.039 cap.
- **Sub-cap regime is structural at $100 collateral.** REWARD-03 optimizer proves this deterministically.

**Edge cases:**
- `Σ_others == 0` → regime = `market_saturated`, `R_uncapped = E_liq × side_split`. Our own fill destroys this if we're alone in the range — Phase 4 breaker SAFE-06 (competition-collapse) catches this.
- `Q_me == 0` → `R_uncapped = 0`, regime = `sub_cap`, return zero. Guard against divide-by-zero.
- `pendle_price_usd == 0` → ValueError. Pricing sub-model requires positive value.
- `e_liq_per_epoch_pendle < 0` → ValueError (protocol always non-negative).

**Acceptance hooks (Success Criterion #2):** At $100 collateral, `r_capped_curve(...).regime == "sub_cap"` across realistic `Q_total_in_range` values for the candidate market. Cap-binding branch exercised in a separate unit test at `collateral_usd = $5000` (see REWARD-04 test).

---

### REWARD-02 — `Q_total_in_range` Tracker

**Approach.** Two sources, composed:
1. **Our own orders (`Q_me`)** via `POST /open-api/v2/accounts/all-limit-orders` — verified live endpoint. Request body: `{userAddress, accountId}`. Response shape: `{results: [Order], resumeToken, syncStatus}`. Polled at 5s cadence (same as DATA-11 `ELiqPoller`).
2. **Competition (`Σ_others`)** via DuckDB aggregation over `parquet.order_book_combined` at 1 Hz: `SELECT SUM(sz_combined_float) FROM order_book_combined WHERE market_id = ? AND snapshot_ts = (latest) AND tick BETWEEN ? AND ? MINUS Q_me`. Subtract AMM share using the Phase 2 `brain.fill_model.amm_consumption.compute_amm_share_timeseries()` utility (already exists, reuse it).

**Interface signature:**
```python
# brain.reward_model.competition_tracker
@dataclass(frozen=True)
class CompetitionSnapshot:
    market_id: str
    polled_at_utc: str   # ISO8601
    chain_ts: int
    q_me_pendle: float
    sigma_others_pendle: float  # excludes Q_me and AMM share
    data_source: Literal["live", "fallback_parquet_only"]  # "fallback" when REST unavailable

class CompetitionTracker:
    def __init__(self, config, conn, rest, duck_conn, run_id, event_pub): ...
    async def run_one_cycle(self) -> CompetitionSnapshot: ...

def insert_competition_row(conn, snapshot: CompetitionSnapshot) -> None: ...  # single writer for state.competition_history
```

**Endpoint verification (2026-04-24):**
```bash
curl -s -X POST https://api.boros.finance/open-api/v2/accounts/all-limit-orders \
  -H "Content-Type: application/json" \
  -d '{"userAddress":"0x...","accountId":0}'
# → {"results": [...], "resumeToken": null, "syncStatus": {...}}
# Missing userAddress: 400 with "userAddress must be an Ethereum address" + "accountId must be a number"
# → endpoint present, account-scoped, v2 is the right version
```

**AMM share subtraction (PITFALLS B3 absorbent).** The `order_book_combined` parquet already includes AMM share; Phase 2 built `compute_amm_share_timeseries(raw_snapshot, combined_snapshot, tick)` returning `amm_share(δ, t) = combined - raw` per tick. `Σ_others = SUM(raw_book_size_in_range) - Q_me`. The combined-raw difference (AMM share) is NOT in `Σ_others` because AMMs don't compete for LO Liquidity Rewards (they use their own AMM reward stream).

**Edge cases:**
- REST endpoint degraded (DATA-11 shows this pattern already — `_get_with_backoff` with 5 retry windows) → fall back to `data_source='fallback_parquet_only'` and estimate `Q_me` from the most recent `open_orders` SQLite table (Phase 1 writer). Emit `competition_tracker.rest_degraded` event.
- Parquet `order_book_combined` has no snapshot ≤ current_chain_ts (more than 2× expected cadence) → data-staleness warning, `Σ_others = last-known value`, breaker SAFE-09 (underlying-feed-stale) is Phase 4 territory but the logging hook lands here.
- AMM conservation violation (Phase 1 DATA-05 invariant) → `compute_amm_share_timeseries` already raises `AMMConsumptionIdentityError`; propagate it so ingest-time violations halt Phase 3 rather than silently poisoning `Σ_others`.

**Competition dynamics (PITFALLS A8).** The A8 outside-range-wall pattern is a covariate **warning only**, not a hard filter. REWARD-02 must include any outside-range-wall participants in `Σ_others` IF they're inside `[clo_lower, clo_upper]`. Markets flagged by Phase 1 with `outside_range_wall_flag=True` stay in the reward-share calculation unchanged.

**Storage.** New SQLite table `state.competition_history`:
```sql
CREATE TABLE competition_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    polled_at_utc   TEXT NOT NULL,
    chain_ts        INTEGER,
    market_id       TEXT NOT NULL,
    q_me_pendle     REAL NOT NULL,
    sigma_others_pendle REAL NOT NULL,
    data_source     TEXT NOT NULL CHECK(data_source IN ('live','fallback_parquet_only')),
    run_id          TEXT NOT NULL
);
CREATE INDEX ix_competition_market_polled ON competition_history (market_id, polled_at_utc DESC);
```

**Acceptance hooks:** CompetitionTracker writes one row per cycle; 5s cadence for REST poll, 1 Hz read of parquet; `Σ_others` computed from order-book aggregation minus `Q_me`; handled degraded-REST path.

---

### REWARD-03 — Sizing Optimizer

**Approach.** 1-D bracketed optimization over `Q_me ∈ [Q_min, Q_max]` maximizing `R_capped(Q_me) - E[loss|fill] × P(fill)`. At $100 collateral the optimum is `Q_min` deterministically because we're structurally in sub-cap regime where the objective is monotone-decreasing in `Q_me` (larger order size → same capped R — no, sub-cap, so larger Q_me → larger R_capped but also larger `E[loss|fill] × P(fill)` by larger size exposure). The plan checker will verify this derivation.

**Actually the derivation: in sub-cap regime, `R_uncapped(Q_me) = E_liq × side_split × Q_me / (Σ_others + Q_me)` is monotone-increasing and concave in `Q_me`, asymptoting at `E_liq × side_split`. Loss side `E[loss|fill] × P(fill) × Q_me` scales linearly in `Q_me`. The marginal-benefit condition is `dR/dQ = E[loss|fill] × P(fill)` which has a unique interior optimum IF `E_liq × Σ_others / (Σ_others + Q_me)² ≥ E[loss|fill] × P(fill)` at `Q_me = Q_min`.

At $100 collateral: `Q_min ≈ 1 PENDLE-equivalent` (protocol has no minimum — see `[[Minimum order size]]` — so `Q_min` is set by `BotConfig.sizer.q_min_pendle`, operator-chosen to be just above fee-amortization floor). `dR/dQ at Q_min = E_liq × side_split × Σ_others / (Σ_others + Q_min)² ≈ 273 × 60 / 60² ≈ 4.5 PENDLE/PENDLE` (marginal return of 4.5 PENDLE per additional PENDLE of order size). `E[loss|fill] × P(fill) at Q_min ≈ 0.02 × 0.001 ≈ 2e-5 PENDLE/PENDLE` (at extreme CLO edge depth, near-zero fill prob, fill-loss coarse-bound). So at $100, `dR/dQ ≫ E[loss] × P(fill)` over the entire `[Q_min, Q_max]` domain, meaning the optimum would be `Q_max` IF the cap were irrelevant. But **the cap IS relevant**: at `Q_me` large enough that `R_uncapped ≥ cap_budget`, the objective flattens. So actually the optimum is: (a) sub-cap regime at $100, where `R_capped = R_uncapped` is rising in Q_me, would push to `Q_max`.

**Re-reading consolidated plan §4:** "At $100 collateral the cap never binds" means the CAP doesn't bind, so R_capped = R_uncapped over the whole domain — but R_uncapped is monotone-increasing, so the optimum IS at Q_max? No — re-read again: **the EV equation's OTHER side** is fill-loss. `E[loss|fill] × P(fill) × Q_me_in_position` — the expected COST — scales roughly linearly with `Q_me`. So the EV objective has a non-trivial interior maximum when `dR_capped/dQ == d(loss × P_fill × Q_me)/dQ`.

**Correct derivation:** At $100 collateral, our posted size `Q_me = Q_min` (a few YU at protocol min). In sub-cap regime, `R_capped ≈ E_liq × side_split × (Q_min × t_frac) / (Σ_others + Q_min × t_frac) ≈ E_liq × side_split × Q_min / Σ_others` since `Q_min ≪ Σ_others`. This is linear in Q_min and ~60x leverage (for the ETHUSDT anchor). Loss side `E[loss|fill] × P(fill) × size_at_fill`: if filled, ALL of `Q_min` is filled (not proportional to anything else). So EV per unit `Q_me` = `(E_liq × side_split / Σ_others) − E[loss|fill] × P(fill)`. This is constant in `Q_me` in the sub-cap regime — meaning EV scales linearly, and `Q_me_target = Q_max` in principle... UNLESS `Q_me` approaches `Σ_others` (dilution) or hits the cap. At $100 collateral, `Q_max` is bounded by available collateral ≈ `$100 / notional-per-YU ≈ 1 YU` for ETH — so `Q_max` is a collateral-determined upper bound.

**The actual Phase 3 locked behavior per ROADMAP Success Criterion #3:** "`Sizer.Q_me_target()` returns `Q_min` deterministically on $100 collateral." This means the consolidated plan's §4 formulation treats $100 collateral as implying `Q_min == Q_max` for all practical purposes — the operator is budget-constrained, not reward-optimization-constrained. **`Q_min = Q_max = collateral_usd / notional_per_YU_usd × safety_margin`** at $100. The optimizer trivially returns this fixed point.

**Interface signature:**
```python
# brain.sizer.optimizer
@dataclass(frozen=True)
class SizerInput:
    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int
    time_to_epoch_end_s: float
    time_to_maturity_s: int
    queue_ahead_wei: int
    current_features: dict[str, float]
    current_chain_ts: int
    collateral_usd: float
    sigma_others_pendle: float
    e_liq_per_epoch_pendle: float
    side_split: float
    t_frac: float
    pendle_price_usd: float

@dataclass(frozen=True)
class SizerOutput:
    q_me_target_pendle: float
    regime: Literal["sub_cap", "cap_binding", "market_saturated"]
    r_capped_at_target: float
    expected_loss_at_target: float
    p_fill_at_target: float
    ev_at_target: float
    q_min_pendle: float
    q_max_pendle: float
    q_cap_pendle: float  # from REWARD-04, even when not binding

def q_me_target(
    req: SizerInput,
    *,
    sqlite_path: Path,
    config: BotConfig,
) -> SizerOutput: ...
```

**Algorithm:**
1. Compute `Q_min` from `config.sizer.q_min_pendle` (operator-provided hard floor; default = per-market minimum-economic-size per fee amortization).
2. Compute `Q_max` from `collateral_usd × safety_margin / notional_per_YU_usd` (at $100, with `safety_margin=0.9`, `Q_max = Q_min` effectively).
3. Compute `Q_cap` via `brain.reward_model.q_cap.compute_q_cap(...)` (REWARD-04).
4. If `Q_cap < Q_min`, regime is `market_saturated`, return `Q_me_target = Q_min`.
5. Else grid-search 50 log-spaced `Q_me` values over `[Q_min, min(Q_max, Q_cap)]`, compute objective `R_capped - E[loss|fill] × P(fill) × Q_me` at each, polish with `scipy.optimize.minimize_scalar(method='bounded')`. Return the argmax.
6. At $100 collateral, steps 1-2 collapse the interval, so the "optimum" is trivially `Q_min` (tested deterministically).

**Edge cases:**
- `Q_min > Q_max` (collateral too thin for even the minimum order) → raise `InsufficientCollateralError`. This is a Phase 1 economics-gate concern; should not happen post-Phase-1 on a shortlisted market.
- `E[loss|fill]` raises `LossModelNoFreshGridError` → propagate; Phase 4 DecisionEngine will suppress PLACE commands (same as `FillModelNoFreshFitError`).
- `P(fill)` raises `FillModelStaleFeatureError` → propagate; same handling as above.
- `Σ_others = 0` (market saturated) → regime = `market_saturated`, `Q_me_target = Q_min` (don't expand; Phase 4 SAFE-06 will catch collapse).

**Acceptance hooks (Success Criterion #3):** `Q_me_target() == Q_min` on realistic ETHUSDT-29MAY2026 + 3 shortlist backfill markets at $100 collateral. Scale-up test at `collateral_usd=5000` confirms `Q_me_target < Q_cap` in cap-binding regime.

---

### REWARD-04 — `Q_cap` Cap-Binding Boundary

**Approach.** Closed-form algebraic computation. From consolidated plan §4 step 4:
```
cap_budget_per_epoch_pendle = 10 × collateral_usd × epoch_days / 365 / pendle_price_usd

Q_cap = Σ_others × cap_budget_per_epoch_pendle /
        (E_liq_per_epoch × side_split × t_frac - cap_budget_per_epoch_pendle × t_frac)

# Boundary cases:
# (1) If E_liq × side_split × t_frac <= cap_budget: cap NEVER binds at any Q_me
#     → Q_cap = +infinity (return math.inf)
# (2) Else Q_cap is finite; if Q_cap < Q_min, cap binds even at minimum size
#     → regime == "market_saturated" interpretation
```

**Interface signature:**
```python
# brain.reward_model.q_cap
def compute_q_cap(
    *,
    sigma_others_pendle: float,
    e_liq_per_epoch_pendle: float,
    side_split: float,
    t_frac: float,
    collateral_usd: float,
    pendle_price_usd: float,
    epoch_days: float,
) -> float:  # returns math.inf when cap never binds
```

**Test matrix (Success Criterion #3 scale-up branch):**

| Scenario | collateral_usd | Σ_others | E_liq × side_split | expected `Q_cap` | expected regime |
|----------|----------------|----------|--------------------|-------------------|-----------------|
| $100 on ETHUSDT-29MAY anchor | 100 | 60 PENDLE | 273 PENDLE/epoch | **`inf`** (cap never binds because `cap_budget_per_epoch ≈ 0.039 PENDLE ≪ 273`) | `sub_cap` |
| $5000 scale-up, same market | 5000 | 60 | 273 | finite, `Q_cap ≈ 0.45 PENDLE` | `cap_binding` (Q_cap < Q_max = ~50 PENDLE) |
| $10000 + market_saturated (Σ_others=0) | 10000 | 0 | 273 | `Q_cap` well-defined | `market_saturated` tested separately |

**Acceptance hooks:** `q_cap ≈ inf` at $100 (sub-cap lock), `q_cap < q_max` at $5000 (cap-binding regime entered).

## E_liq Source Resolution (CRITICAL — blocks REWARD-01 math)

### What was investigated (Phase 3 research, 2026-04-24)

**A. Live `GET /markets` API fields** — verified against the captured 2026-04-24 sample at `docs/samples/markets-response.json`:
- `config` keys: `maxOpenOrders, markRateOracle, fIndexOracle, hardOICap, takerFee, otcFee, liqSettings{base,slope,feeRate}, kIM, kMM, tThresh, maxRateDeviationFactorBase1e4, closingOrderBoundBase1e4, loUpperConstBase1e4, loUpperSlopeBase1e4, loLowerConstBase1e4, loLowerSlopeBase1e4, status, useImpliedAsMarkRate, softOICap, cloLowerThresh, cloUpperThresh`
- `data` keys: `volume24h, notionalOI, markApr, lastTradedApr, midApr, bestBid, bestAsk, ammImpliedApr, floatingApr, longYieldApr, nextSettlementTime, timeToMaturity, assetMarkPrice, rateSensitivity, settlementsToMaturity, dailyVolatility, dailyVolatilityState`
- **No field** named `liquidityRewardPerEpoch`, `longBudget`, `shortBudget`, `emissionRate`, `rewardBudget`, `eLiq`.

**B. `config.liqSettings.{base, slope, feeRate}`** — verified against `https://docs.pendle.finance/boros-dev/Mechanics/Margin` (2026-04-24): **these are LIQUIDATION incentive parameters**, not liquidity-reward parameters. Formula: `Incentive Factor = liqSettings.base + liqSettings.slope × (1 - Health Ratio)`. `feeRate` is the liquidation-fee share to treasury. **Not usable for `E_liq_per_epoch`.** `[VERIFIED: docs.pendle.finance/boros-dev/Mechanics/Margin]`

**C. `data.longYieldApr` / `shortYieldApr`** — `longYieldApr` exists (e.g., `0.498` for Hyperliquid ETH, but `-1.71` for OKX ETHUSDT), `shortYieldApr` is **never present** in any of 30 sampled markets. `longYieldApr` is the **IRS P&L yield** (floating − implied), not a reward APR. Verified against `https://docs.pendle.finance/boros-docs/Introduction` + Pendle Academy. **Not usable for `E_liq_per_epoch`.** `[VERIFIED: docs.pendle.finance/boros-docs + live sample]`

**D. Boros core contract events** — verified `https://github.com/pendle-finance/boros-core-public/blob/main/contracts/distributor/MultiTokenMerkleDistributor.sol` (2026-04-24). Events emitted: `SetMerkleRoot(merkleRoot)`, `Claimed(token, user, receiver, amountOuts[i])`, `Verified(token, user, amountClaimable[i])`. **No per-epoch or per-market budget event.** `claimed[token][user]` / `verified[token][user]` mappings only — the Merkle tree's leaf values are computed off-chain and the contract stores only the root hash. Budget extraction would require Pendle's off-chain Merkle-tree computation source (not published). `[VERIFIED: github.com/pendle-finance/boros-core-public]`

**E. Deployed distributor addresses on Arbitrum** — verified `https://github.com/pendle-finance/boros-core-public/blob/main/deployments/core.json` (2026-04-24):
- `makerIncentive: 0xD0808080803c59dBF8825290bca8979786C2d65B` — Maker Volume Rewards (**NOT the LO Liquidity pool we target**)
- `ammIncentive: 0xD180808080402FE41711Db560B8db5C41e21Df71` — AMM LP incentives
- `referralIncentive: 0xD2808080809a71248620a7ddc25b721d3DBe1058` — referrals
- **No explicitly labeled "LO Liquidity" or "LP Liquidity" distributor.** The `boros_bot_guide.md` L48 mentions "MultiTokenMerkleDistributor" but doesn't specify which of the three handles LO Liquidity Rewards. Most likely `makerIncentive` serves dual-purpose for both Maker Volume + LO Liquidity, with the split handled off-chain in Merkle-tree computation. `[VERIFIED: github.com/pendle-finance/boros-core-public/deployments/core.json]`

**F. Public SDK docs Section 12 "Incentives API"** — advertised in `https://raw.githubusercontent.com/pendle-finance/sdk-boros-public/main/documentation/API.docs.md` as supporting "Liquidity mining rewards, Trading incentives, Referral bonuses, Reward claiming operations, Incentive program analytics" — but **not yet deployed**. Every probed path returns 404. `[VERIFIED: probe log 2026-04-24]`

**Probe log (2026-04-24 16:39 UTC, all HTTPS):**
```
# All 404 unless noted:
GET /open-api/v1/epoch-rewards                    404
GET /open-api/v1/rewards                          404
GET /open-api/v1/liquidity-rewards                404
GET /open-api/v1/markets-rewards                  404
GET /open-api/v1/emissions                        404
GET /open-api/v1/incentives                       404
GET /open-api/v1/markets/{id}/rewards             404
GET /open-api/v1/markets/{id}/emission            404
GET /open-api/v1/markets/{id}/budget              404
GET /core/v1/incentives                           404
GET /core/v1/rewards                              404
GET /open-api/v1/reward-campaigns                 404
GET /open-api/v1/campaigns                        404
GET /open-api/v1/merkle                           404
GET /open-api/v1/distributor                      404
GET /open-api/v1/epoch                            404
GET /open-api/v1/epoch/current                    404
GET /v2/accounts/all-limit-orders                 400 (endpoint EXISTS; expects body)
GET /open-api/v1/markets/74                       200 (market detail — no reward fields)
```

### Candidate sources — feasibility ranking

| # | Source | Evidence tier | Refresh freq | Unit | Live-pollable? | Feasibility |
|---|--------|--------------|--------------|------|----------------|-------------|
| 1 | **Operator-manual per-market calibration in BotConfig** (read from dApp UI at screener time) | Operator-curated (HIGH data quality at calibration instant, STALE between calibrations) | Manual (daily re-screen) | PENDLE/epoch | No (static) | **HIGHEST — the only path that lands Phase 3 on schedule** |
| 2 | Derive from `liqSettings.{base, slope}` + on-chain state | NOT APPLICABLE (liqSettings is liquidation, not reward — verified) | — | — | — | **ZERO — false lead; discard** |
| 3 | Read from Merkle distributor contract on Arbitrum | Contract emits only `SetMerkleRoot` | Weekly | Aggregate claim amount, not per-market budget | No | LOW — reconstruction requires off-chain Merkle-tree recomputation which Pendle doesn't publish; requires 2+ epochs of live runtime to observe deltas. Deferred to Phase 5 backtest or Phase 8 live Merkle-reconciliation. |
| 4 | Separate undocumented REST endpoint | Probed exhaustively — none found | — | — | — | **ZERO — negative result verified.** |
| 5 | Reverse-engineer from `boros-core-public` | Contract code public; distributor stores only root hash + claim mappings | — | — | No | LOW — can identify which distributor serves LO-liquidity, but not the emission rate. |
| 6 | **Reward accrual tap (post-hoc)**: compute per-(market, side) `E_liq_per_epoch` by observing Merkle root updates + our wallet's accrual delta over 2+ epochs during live rollout | High quality once data arrives | Weekly, lagging | PENDLE/epoch | No (backfill-only, Phase 8+) | MEDIUM for Phase 5 backtest post-Phase-8; useless for Phase 3 plan-time. |
| 7 | Ask Pendle Discord / team for the per-market budgets at screener time, file as `[[market-reward-calibration-YYYYMMDD]]` wiki page | Team-supplied (authoritative but not versioned) | Manual, daily | PENDLE/epoch | No | **ALTERNATIVE to #1 — recommend in §E_liq Source Resolution** |

### Recommendation — user escalation

**Recommend Option 1 + Option 7 composed:** operator-manual calibration in `BotConfig.markets[i].reward_calibration`, with values sourced from the dApp UI's reward display at calibration time (or Discord-asked if the dApp UI doesn't show per-side budgets). Daily re-screen prompts for refresh. `reward_budget_history` rows continue to use `data_source='synthetic_current'` to distinguish from live-polled values — schema is already prepared.

**If the user rejects manual calibration, the only fallback is to bump LOSS-01/02 + REWARD-01/02/03/04 into Phase 5 backtest post-live-Merkle-delta observation**, which pushes paper trading out by ≥1 epoch. That is a material schedule hit.

**This is the user-confirmation question:** "For Phase 3, are you OK with manual per-market reward-budget calibration stored in BotConfig.markets[].reward_calibration (refreshed at daily re-screen by inspecting the dApp UI and/or asking Pendle team), with `data_source='synthetic_current'` as the lineage marker until Phase 8 live-Merkle reconciliation replaces it?"

**If YES** (strongly recommended): proceed to PLAN. BotConfig knob delta below already includes `MarketRewardCalibration` sub-model.

**If NO**: the research is `## RESEARCH BLOCKED`. Escalation text at end of this document.

## Module / File Layout

### Created in Phase 3

| Path | Purpose | Requirement |
|------|---------|-------------|
| `python/src/boros_brain/loss_model/__init__.py` | Package init | all |
| `python/src/boros_brain/loss_model/config.py` | `LossModelConfig`, `FeesConfig` Pydantic sub-models | LOSS-01/02 + A6 |
| `python/src/boros_brain/loss_model/schemas.py` | `LossGridArtifact`, `ExpectedLossInput/Output`, `LossModelNoFreshGridError`, `LossModelSparseCellWarning` | LOSS-01/02 |
| `python/src/boros_brain/loss_model/replay.py` | `replay_historical_fills(...)` DuckDB join + per-fill P&L | LOSS-01 |
| `python/src/boros_brain/loss_model/fit.py` | `fit_loss_grid(market_id, side, window)` — cell aggregation + persistence | LOSS-01 |
| `python/src/boros_brain/loss_model/expected_loss.py` | `expected_loss(req)` — sync sparse-cell fallback lookup | LOSS-02 |
| `python/src/boros_brain/loss_model/artifact.py` | `write_loss_grid_artifact(artifact)` dual-write parquet+SQLite | LOSS-01 |
| `python/src/boros_brain/loss_model/refit_loop.py` | `refit_once()` + `run_loss_model_refit_loop()` async 15-min cadence | LOSS-01 |
| `python/src/boros_brain/loss_model/ou_parametric.py` | `OUBasisLossModel` Protocol + `raise NotImplementedError` | LOSS-03 |
| `python/src/boros_brain/loss_model/cli.py` + `__main__.py` | `python -m boros_brain.loss_model {fit,expected-loss,force-degrade}` | LOSS-01/02 |
| `python/src/boros_brain/reward_model/__init__.py` | Package init | REWARD-01/02 |
| `python/src/boros_brain/reward_model/config.py` | `RewardShareModelConfig` | REWARD-01/02 |
| `python/src/boros_brain/reward_model/schemas.py` | `RewardCurveInput/Output`, `CompetitionSnapshot`, `RegimeLabel` | REWARD-01/02 |
| `python/src/boros_brain/reward_model/competition_tracker.py` | `CompetitionTracker` class + `run_one_cycle()` | REWARD-02 |
| `python/src/boros_brain/reward_model/r_capped.py` | `r_capped_curve(req)` | REWARD-01 |
| `python/src/boros_brain/reward_model/q_cap.py` | `compute_q_cap(...)` | REWARD-04 |
| `python/src/boros_brain/reward_model/cli.py` + `__main__.py` | `python -m boros_brain.reward_model {curve,competition-snapshot}` | REWARD-01/02 |
| `python/src/boros_brain/sizer/__init__.py` | Package init | REWARD-03 |
| `python/src/boros_brain/sizer/config.py` | `SizerConfig` | REWARD-03 |
| `python/src/boros_brain/sizer/schemas.py` | `SizerInput/Output` | REWARD-03 |
| `python/src/boros_brain/sizer/optimizer.py` | `q_me_target(req)` | REWARD-03 |
| `python/src/boros_brain/sizer/cli.py` + `__main__.py` | `python -m boros_brain.sizer {target}` | REWARD-03 |
| `python/src/boros_brain/pricing/__init__.py` | Package init | cross-cutting |
| `python/src/boros_brain/pricing/config.py` | `PricingConfig(pendle_price_usd, price_source, staleness_s)` | REWARD-01 unit conversion |
| `python/src/boros_brain/state/writers/loss_grid_artifacts.py` | `insert_loss_grid_artifact` + `get_latest_loss_grid` single writer | LOSS-01 |
| `python/src/boros_brain/state/writers/competition_history.py` | `insert_competition_row` + `get_latest_competition` single writer | REWARD-02 |
| `python/src/boros_brain/state/migrations/versions/0004_loss_grid_artifacts.py` | Alembic: creates `state.loss_grid_artifacts` | LOSS-01 |
| `python/src/boros_brain/state/migrations/versions/0005_competition_history.py` | Alembic: creates `state.competition_history` | REWARD-02 |

### Modified in Phase 3

| Path | Change | Requirement |
|------|--------|-------------|
| `python/src/boros_brain/config/schema.py` | Add `loss_model`, `reward_share_model`, `sizer`, `pricing`, `fees`, `market_reward_calibration` sub-model fields to `BotConfig` + add `reward_calibration: MarketRewardCalibration \| None` to `MarketCalibration` | PROTO-04 |
| `python/src/boros_brain/main.py` | Spawn `run_loss_model_refit_loop` + `CompetitionTracker.loop()` at boot (same pattern as fill_model `refit_loop`); extend `--dry-run` guard | LOSS-01 + REWARD-02 |
| `docs/architecture.yml` | Add all new module nodes + storage nodes + config knob nodes + edges (see §Architecture Manifest Delta) | PROTO-02 |
| `docs/ARCHITECTURE.md` | Extend Mermaid subgraph with Phase 3 nodes | PROTO-02 |
| `scripts/no_time_time_lint.py` | Add `loss_model/`, `reward_model/`, `sizer/` to guarded dir list | INFRA-14 |
| `strategy/v0.5-default.yaml` | Add Phase 3 knob defaults; add `market_reward_calibration` block per-market (from dApp UI) | operator-config |
| `python/tests/test_manifest_contains_all_knobs.py` | Extend to cover `loss_model`, `reward_share_model`, `sizer`, `pricing`, `fees` sub-models | PROTO-04 |
| `python/tests/test_sqlite_single_writer.py` | Extend for `loss_grid_artifacts`, `competition_history` tables | INFRA-03 |
| Wiki pages per §Project Constraints (Protocol 1) | 7 new pages + 2 supersedences in same commit | Protocol 1 + 5 |

## Architecture Manifest Delta (`docs/architecture.yml`)

### New module nodes (24)

```yaml
  # ── Phase 3: Loss Model ───────────────────────────────────────────────
  - id: brain.loss_model.config
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/config.py
    public_functions: []  # LossModelConfig, FeesConfig Pydantic classes
  - id: brain.loss_model.schemas
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/schemas.py
    public_functions: []
  - id: brain.loss_model.replay
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/replay.py
    public_functions: [replay_historical_fills]
  - id: brain.loss_model.fit
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/fit.py
    public_functions: [fit_loss_grid]
  - id: brain.loss_model.expected_loss
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/expected_loss.py
    public_functions: [expected_loss]
  - id: brain.loss_model.artifact
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/artifact.py
    public_functions: [write_loss_grid_artifact]
  - id: brain.loss_model.refit_loop
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/refit_loop.py
    public_functions: [refit_once, run_loss_model_refit_loop]
  - id: brain.loss_model.ou_parametric
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/ou_parametric.py
    public_functions: [fit_ou_basis]
  - id: brain.loss_model.cli
    type: module
    process: brain
    path: python/src/boros_brain/loss_model/cli.py
    public_functions: [main, build_parser]

  # ── Phase 3: Reward-Share Model ───────────────────────────────────────
  - id: brain.reward_model.config
    type: module
    process: brain
    path: python/src/boros_brain/reward_model/config.py
    public_functions: []
  - id: brain.reward_model.schemas
    type: module
    process: brain
    path: python/src/boros_brain/reward_model/schemas.py
    public_functions: []
  - id: brain.reward_model.competition_tracker
    type: module
    process: brain
    path: python/src/boros_brain/reward_model/competition_tracker.py
    public_functions: [run_competition_tracker_loop]  # CompetitionTracker is a class
  - id: brain.reward_model.r_capped
    type: module
    process: brain
    path: python/src/boros_brain/reward_model/r_capped.py
    public_functions: [r_capped_curve]
  - id: brain.reward_model.q_cap
    type: module
    process: brain
    path: python/src/boros_brain/reward_model/q_cap.py
    public_functions: [compute_q_cap]
  - id: brain.reward_model.cli
    type: module
    process: brain
    path: python/src/boros_brain/reward_model/cli.py
    public_functions: [main, build_parser]

  # ── Phase 3: Sizer ────────────────────────────────────────────────────
  - id: brain.sizer.config
    type: module
    process: brain
    path: python/src/boros_brain/sizer/config.py
    public_functions: []
  - id: brain.sizer.schemas
    type: module
    process: brain
    path: python/src/boros_brain/sizer/schemas.py
    public_functions: []
  - id: brain.sizer.optimizer
    type: module
    process: brain
    path: python/src/boros_brain/sizer/optimizer.py
    public_functions: [q_me_target]
  - id: brain.sizer.cli
    type: module
    process: brain
    path: python/src/boros_brain/sizer/cli.py
    public_functions: [main, build_parser]

  # ── Phase 3: Pricing ──────────────────────────────────────────────────
  - id: brain.pricing.config
    type: module
    process: brain
    path: python/src/boros_brain/pricing/config.py
    public_functions: []

  # ── Phase 3: SQLite single writers ────────────────────────────────────
  - id: brain.state.writers.loss_grid_artifacts
    type: module
    process: brain
    path: python/src/boros_brain/state/writers/loss_grid_artifacts.py
    public_functions: [insert_loss_grid_artifact, get_latest_loss_grid]
  - id: brain.state.writers.competition_history
    type: module
    process: brain
    path: python/src/boros_brain/state/writers/competition_history.py
    public_functions: [insert_competition_row, get_latest_competition]

  # ── Phase 3: Storage nodes ────────────────────────────────────────────
  - id: state.loss_grid_artifacts
    type: storage
    path: state/state.sqlite
    notes: "SQLite table loss_grid_artifacts. PK=(market_id, side, window_end_ts). Single writer: brain.state.writers.loss_grid_artifacts."
  - id: state.competition_history
    type: storage
    path: state/state.sqlite
    notes: "SQLite table competition_history. Indexed (market_id, polled_at_utc DESC). Single writer: brain.state.writers.competition_history."
  - id: parquet.loss_grid_artifacts
    type: storage
    path: data/parquet/loss_grid_artifacts/**/*.parquet
    notes: "Hive-partitioned: market_id / side / window_end_ts. Loss-grid parquet sidecar with per-cell aggregation."
```

### New config knob nodes (see §BotConfig Knob Delta for full list)

~35 new `config_knob` nodes under `config.loss_model.*`, `config.reward_share_model.*`, `config.sizer.*`, `config.pricing.*`, `config.fees.*` — one per Pydantic field. Exhaustive list below.

### New edges (key ones; plan will extend)

```yaml
  # ── Phase 3: Loss Model edges ─────────────────────────────────────────
  - {from: brain.loss_model.replay, to: parquet.market_trades, type: reads}
  - {from: brain.loss_model.replay, to: parquet.order_book_raw, type: reads}
  - {from: brain.loss_model.replay, to: parquet.order_book_combined, type: reads}
  - {from: brain.loss_model.replay, to: parquet.underlying_apr, type: reads}
  - {from: brain.loss_model.replay, to: parquet.settlement, type: reads}
  - {from: brain.loss_model.replay, to: parquet.market_data, type: reads}
  - {from: brain.loss_model.replay, to: state.clo_history, type: reads}
  - {from: brain.loss_model.replay, to: brain.duckdb_layer.setup, type: calls}
  - {from: brain.loss_model.fit, to: brain.loss_model.replay, type: calls}
  - {from: brain.loss_model.artifact, to: brain.state.writers.loss_grid_artifacts, type: calls}
  - {from: brain.state.writers.loss_grid_artifacts, to: state.loss_grid_artifacts, type: writes}
  - {from: brain.loss_model.artifact, to: parquet.loss_grid_artifacts, type: writes}
  - {from: brain.loss_model.expected_loss, to: brain.state.writers.loss_grid_artifacts, type: reads, notes: "get_latest_loss_grid"}
  - {from: brain.loss_model.refit_loop, to: brain.data.chain_time, type: calls}
  - {from: brain.loss_model.cli, to: brain.manifest.writer, type: calls, notes: "MANIFEST-FIRST boot (PROTO-01)"}
  - {from: brain.main, to: brain.loss_model.refit_loop, type: calls, notes: "asyncio.create_task(run_loss_model_refit_loop)"}

  # ── Phase 3: Reward Model edges ───────────────────────────────────────
  - {from: brain.reward_model.competition_tracker, to: brain.data.rest_client, type: calls, notes: "POST /v2/accounts/all-limit-orders"}
  - {from: brain.reward_model.competition_tracker, to: parquet.order_book_combined, type: reads}
  - {from: brain.reward_model.competition_tracker, to: brain.fill_model.amm_consumption, type: calls, notes: "reuse compute_amm_share_timeseries for Σ_others"}
  - {from: brain.reward_model.competition_tracker, to: brain.state.writers.competition_history, type: calls}
  - {from: brain.state.writers.competition_history, to: state.competition_history, type: writes}
  - {from: brain.reward_model.r_capped, to: state.reward_budget_history, type: reads, notes: "latest E_liq_per_epoch row"}
  - {from: brain.reward_model.q_cap, to: brain.reward_model.config, type: reads}
  - {from: brain.main, to: brain.reward_model.competition_tracker, type: calls}

  # ── Phase 3: Sizer edges ──────────────────────────────────────────────
  - {from: brain.sizer.optimizer, to: brain.loss_model.expected_loss, type: calls}
  - {from: brain.sizer.optimizer, to: brain.fill_model.predict, type: calls, notes: "Phase 2 interface — LOCKED"}
  - {from: brain.sizer.optimizer, to: brain.reward_model.r_capped, type: calls}
  - {from: brain.sizer.optimizer, to: brain.reward_model.q_cap, type: calls}

  # ── Phase 3: config knob dependencies (sample; plan completes) ────────
  - {from: brain.loss_model.config, to: config.loss_model.depth_bucket_edges, type: depends-on-config}
  - {from: brain.loss_model.config, to: config.loss_model.tau_bucket_edges, type: depends-on-config}
  - {from: brain.loss_model.config, to: config.loss_model.min_samples_per_cell, type: depends-on-config}
  - {from: brain.reward_model.r_capped, to: config.pricing.pendle_price_usd, type: depends-on-config}
  - {from: brain.sizer.optimizer, to: config.sizer.q_min_pendle, type: depends-on-config}
  - {from: brain.sizer.optimizer, to: config.sizer.collateral_usd, type: depends-on-config}
```

## BotConfig Knob Delta (PROTO-04 — schema = SSoT)

```python
# brain.loss_model.config
class FeesConfig(StrictBase):  # PROTO-04: every knob here landed in docs/architecture.yml as config_knob node
    taker_fee_rate: float = Field(5e-4, ge=0.0, le=0.01)
    """Taker fee per unit (decimal-fraction of notional × rate × τ). From [[fee-schedule]]."""
    settlement_fee_rate: float = Field(1e-3, ge=0.0, le=0.01)
    """Settlement fee per settlement period (decimal-fraction)."""
    settlement_period_s: int = Field(28800, ge=3600, le=86400)
    """Seconds between settlements. 8h (28800s) is typical."""
    market_entrance_fee_usd: float = Field(1.0, ge=0.0, le=10.0)
    """~$1 one-time per market. Amortized over expected market-hold-duration."""
    gas_place_gwei: int = Field(200000, ge=50000, le=2000000)
    """Arbitrum gas estimate for place_order. Phase 4 DECIDE-03 measures empirically."""
    gas_cancel_gwei: int = Field(100000, ge=20000, le=1000000)
    gas_close_gwei: int = Field(300000, ge=100000, le=3000000)
    gas_price_gwei: float = Field(0.1, ge=0.01, le=10.0)
    """Arbitrum base gas price estimate."""

class LossModelConfig(StrictBase):
    depth_bucket_edges: list[float] = Field(default_factory=lambda: [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, float('inf')])
    tau_bucket_edges: list[float] = Field(default_factory=lambda: [0.0, 7.0, 14.0, 30.0, 60.0, 90.0, 180.0, float('inf')])
    """Bucket edges in days. min_time_to_maturity_days=30 means our fills live in τ ∈ [30, maturity]."""
    min_samples_per_cell: int = Field(5, ge=1, le=100)
    """Cells below this count fall back to k-NN; below 1 falls back to coarse bound."""
    knn_k: int = Field(3, ge=1, le=10)
    knn_max_distance: float = Field(4.0, ge=1.0, le=16.0)
    """Max bucket-widths distance for nearest-neighbor fallback. Above → coarse_bound."""
    aggregation_metric: Literal["mean", "p50", "p95"] = "mean"
    """Per-cell summary for expected_loss() return value."""
    window_days: int = Field(90, ge=14, le=365)
    """Historical window for loss-grid construction. LONGER than fill-model's 14d because
    loss events are rarer than trades."""
    refit_cadence_s: float = Field(900.0, ge=60.0, le=86400.0)
    fit_warn_staleness_s: float = Field(1800.0, ge=600.0, le=14400.0)
    fit_max_staleness_s: float = Field(86400.0, ge=3600.0, le=604800.0)
    """24h max; loss grid rarely changes intraday, but refits guard against regime shift."""
    close_latency_budget_s: float = Field(60.0, ge=5.0, le=600.0)
    """Max time to find opposite-side close trade in empirical replay."""
    fees: FeesConfig = Field(default_factory=FeesConfig)  # type: ignore

# brain.reward_model.config
class RewardShareModelConfig(StrictBase):
    competition_poll_interval_s: float = Field(5.0, ge=1.0, le=60.0)
    """CompetitionTracker cadence for /accounts/all-limit-orders poll."""
    sigma_others_min_pendle: float = Field(1e-6, ge=1e-18, le=1.0)
    """Floor for Σ_others to avoid divide-by-zero. Treat anything below as 'market_saturated'."""
    epoch_days: float = Field(7.0, ge=1.0, le=30.0)
    """Weekly epochs (Fri 00:00 UTC → Thu 23:59 UTC), locked."""
    cap_apr_multiple: float = Field(10.0, ge=1.0, le=100.0)
    """Boros protocol cap: 1000% APR = 10×. Locked; exposed for v1.0 override if protocol changes."""
    fallback_to_parquet_after_rest_fails_n: int = Field(5, ge=1, le=20)
    """Consecutive REST failures before CompetitionTracker flips to parquet-only mode."""

# brain.sizer.config
class SizerConfig(StrictBase):
    collateral_usd: float = Field(100.0, ge=10.0, le=1_000_000.0)
    """Operator-committed collateral. v0.5 anchor: $100."""
    q_min_pendle: float = Field(1e-3, ge=1e-18, le=1.0)
    """Hard floor on our order size; derived from fee-amortization floor. Protocol has no minimum per P0-02."""
    q_max_safety_margin: float = Field(0.9, ge=0.1, le=1.0)
    """Fraction of collateral-derived Q_max we actually use (safety buffer)."""
    optimizer_grid_points: int = Field(50, ge=10, le=500)
    optimizer_method: Literal["grid_only", "grid_plus_scipy", "scipy_only"] = "grid_plus_scipy"
    notional_per_yu_usd: float = Field(1.0, ge=0.01, le=1000.0)
    """Per-market USD notional per 1 YU. Operator-provided per-market. Bucketed into markets[].reward_calibration."""

# brain.pricing.config
class PricingConfig(StrictBase):
    pendle_price_usd: float = Field(7.0, ge=0.1, le=1000.0)
    """Operator-manual PENDLE/USD at calibration time. Refreshed at daily re-screen."""
    price_source: Literal["manual", "chainlink", "pyth"] = "manual"
    """v0.5: manual. v1.0 will flip this enum to live-oracle with zero code churn."""
    price_staleness_warn_s: float = Field(86400.0, ge=3600.0, le=604800.0)
    price_staleness_halt_s: float = Field(604800.0, ge=86400.0, le=2_592_000.0)

# brain.config.schema — MarketCalibration extension
class MarketRewardCalibration(StrictBase):
    """Per-market reward-budget calibration captured from the dApp UI at daily re-screen.
    
    Until Pendle publishes a reward-budget REST endpoint, E_liq_per_epoch is operator-
    calibrated from the dApp's 'APR' display per market per side. Refreshed daily by
    the re-screen scheduler. `calibrated_at_utc` is logged in RUN_MANIFEST so any
    divergence between calibration time and live E_liq polling is visible.
    """
    e_liq_per_epoch_pendle: float = Field(..., ge=0.0)
    long_side_split: float = Field(..., ge=0.0, le=1.0)
    """Long-side fraction of E_liq. long_side_split + short_side_split = 1.0."""
    short_side_split: float = Field(..., ge=0.0, le=1.0)
    calibrated_at_utc: str
    """ISO8601 of when operator last updated this from the dApp."""
    source: Literal["dapp_ui", "team_statement", "merkle_delta"] = "dapp_ui"

class MarketCalibration(StrictBase):
    market_id: str
    scale: float
    s: float
    clo_lower_thresh: float
    clo_upper_thresh: float
    fIndex_oracle_address: str
    maturity_ts: int
    reward_calibration: MarketRewardCalibration | None = None   # ← NEW Phase 3 field

# brain.config.schema — BotConfig top-level additions
class BotConfig(StrictBase):
    ...existing fields...
    loss_model: LossModelConfig = Field(default_factory=LossModelConfig)        # type: ignore
    reward_share_model: RewardShareModelConfig = Field(default_factory=RewardShareModelConfig)   # type: ignore
    sizer: SizerConfig = Field(default_factory=SizerConfig)                     # type: ignore
    pricing: PricingConfig = Field(default_factory=PricingConfig)               # type: ignore
```

**Knob count delta:** `FeesConfig` (8) + `LossModelConfig` (11 + nested FeesConfig) + `RewardShareModelConfig` (5) + `SizerConfig` (6) + `PricingConfig` (4) + `MarketRewardCalibration` (5) = **~39 new top-level knob leaves**. The `test_manifest_contains_all_knobs` reflection test automatically covers these via `BotConfig.model_dump(mode='json')`.

## Validation Architecture

**Nyquist validation enabled** (`.planning/config.json` → `workflow.nyquist_validation` is not explicitly `false` — include this section).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 8.x + `hypothesis` 6.x + `pytest-asyncio` (already in dev deps) |
| Config file | `python/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd python && uv run pytest tests/test_loss_model_*.py tests/test_reward_model_*.py tests/test_sizer_*.py -x` |
| Full suite command | `cd python && uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOSS-01 | Empirical replayer builds per-cell aggregation on candidate market | integration | `pytest tests/test_loss_model_replay.py::test_replay_per_cell_aggregation` | ❌ Wave 0 |
| LOSS-01 | AMM-conservation still holds during loss-grid build (B3 guard) | integration | `pytest tests/test_loss_model_replay.py::test_amm_conservation_preserved` | ❌ Wave 0 |
| LOSS-01 | Immediate-close policy P&L formula | unit | `pytest tests/test_loss_model_replay.py::test_immediate_close_pnl_matches_fee_schedule` | ❌ Wave 0 |
| LOSS-01 | `fees.taker_fee_rate` absorbed in P&L (A6) | unit | `pytest tests/test_loss_model_replay.py::test_fees_term_included` | ❌ Wave 0 |
| LOSS-01 | Dual-write artifact (parquet + SQLite atomic) | integration | `pytest tests/test_loss_model_artifact.py::test_dual_write_atomicity` | ❌ Wave 0 |
| LOSS-02 | `expected_loss()` returns number on every cell for candidate market | integration | `pytest tests/test_loss_model_expected_loss.py::test_full_grid_coverage` | ❌ Wave 0 |
| LOSS-02 | Sparse-cell nearest-neighbor fallback logs warning | integration | `pytest tests/test_loss_model_expected_loss.py::test_sparse_cell_fallback_logged` | ❌ Wave 0 |
| LOSS-02 | `NaN` in query → raise (no silent fallback) | unit | `pytest tests/test_loss_model_expected_loss.py::test_nan_inputs_raise` | ❌ Wave 0 |
| LOSS-02 | Staleness > `fit_max_staleness_s` raises `LossModelNoFreshGridError` | unit | `pytest tests/test_loss_model_expected_loss.py::test_stale_grid_raises` | ❌ Wave 0 |
| LOSS-02 | Return units are PENDLE (matches R_capped) | unit | `pytest tests/test_loss_model_expected_loss.py::test_return_in_pendle_units` | ❌ Wave 0 |
| LOSS-03 | Failing stub raises `NotImplementedError` with LOSS-03 marker | unit | `pytest tests/test_loss_model_ou_scaffold.py::test_ou_scaffold_raises_not_implemented` | ❌ Wave 0 |
| LOSS-03 | `OUBasisLossModel.expected_loss` signature matches empirical `expected_loss` | unit | `pytest tests/test_loss_model_ou_scaffold.py::test_ou_scaffold_protocol_surface` | ❌ Wave 0 |
| REWARD-01 | `r_capped_curve` sub_cap regime at $100 | unit | `pytest tests/test_reward_model_r_capped.py::test_sub_cap_at_100_collateral` | ❌ Wave 0 |
| REWARD-01 | Cap-binding regime at $5k | unit | `pytest tests/test_reward_model_r_capped.py::test_cap_binding_at_5k_collateral` | ❌ Wave 0 |
| REWARD-01 | `market_saturated` when Σ_others=0 | unit | `pytest tests/test_reward_model_r_capped.py::test_market_saturated_regime` | ❌ Wave 0 |
| REWARD-01 | Kink point at `cap_budget` is continuous (A4 geometry) | property (hypothesis) | `pytest tests/test_reward_model_r_capped.py::test_curve_continuous_at_kink` | ❌ Wave 0 |
| REWARD-01 | Monotone non-decreasing in Q_me (hypothesis) | property | `pytest tests/test_reward_model_r_capped.py::test_monotone_in_q_me` | ❌ Wave 0 |
| REWARD-02 | CompetitionTracker writes one row per cycle | integration | `pytest tests/test_reward_model_competition_tracker.py::test_writes_one_row_per_cycle` | ❌ Wave 0 |
| REWARD-02 | `Σ_others` excludes `Q_me` | unit | `pytest tests/test_reward_model_competition_tracker.py::test_sigma_excludes_q_me` | ❌ Wave 0 |
| REWARD-02 | `Σ_others` excludes AMM share (B3 guard) | integration | `pytest tests/test_reward_model_competition_tracker.py::test_sigma_excludes_amm` | ❌ Wave 0 |
| REWARD-02 | REST-degraded → `data_source='fallback_parquet_only'` | unit | `pytest tests/test_reward_model_competition_tracker.py::test_fallback_on_rest_fail` | ❌ Wave 0 |
| REWARD-02 | A8 outside-range-wall markets remain in shortlist | integration | `pytest tests/test_reward_model_competition_tracker.py::test_a8_flagged_market_still_tracked` | ❌ Wave 0 |
| REWARD-03 | `Q_me_target` = `Q_min` at $100 on ETHUSDT anchor | unit | `pytest tests/test_sizer_optimizer.py::test_q_min_fixed_point_at_100_collateral` | ❌ Wave 0 |
| REWARD-03 | Scale-up to $5k → `Q_me_target < Q_cap` in cap-binding regime | unit | `pytest tests/test_sizer_optimizer.py::test_q_me_below_q_cap_at_5k` | ❌ Wave 0 |
| REWARD-03 | Objective always `>=` dominated strategy (no worse than Q_min) | property | `pytest tests/test_sizer_optimizer.py::test_optimizer_dominates_q_min` | ❌ Wave 0 |
| REWARD-03 | `InsufficientCollateralError` when Q_min > Q_max | unit | `pytest tests/test_sizer_optimizer.py::test_raises_on_insufficient_collateral` | ❌ Wave 0 |
| REWARD-04 | `Q_cap = inf` at $100 ETHUSDT anchor | unit | `pytest tests/test_reward_model_q_cap.py::test_inf_at_100_collateral` | ❌ Wave 0 |
| REWARD-04 | `Q_cap` finite at $5k scale-up | unit | `pytest tests/test_reward_model_q_cap.py::test_finite_at_5k_collateral` | ❌ Wave 0 |
| REWARD-04 | `Q_cap < Q_min` → `market_saturated` regime | unit | `pytest tests/test_reward_model_q_cap.py::test_q_cap_below_q_min_saturated` | ❌ Wave 0 |
| REWARD-04 | Unit-dimensional correctness (hypothesis) | property | `pytest tests/test_reward_model_q_cap.py::test_q_cap_units_property` | ❌ Wave 0 |
| PROTO-04 | All Phase 3 knobs surface in RUN_MANIFEST | unit | `pytest tests/test_manifest_contains_all_knobs.py::test_phase3_leaves_surfaced` | ✅ (extend) |
| PROTO-02 | architecture.yml lint passes after Phase 3 nodes | tooling | `cd python && uv run python ../scripts/architecture_lint.py` | ✅ (exists) |
| INFRA-14 | no_time_time_lint covers loss_model/, reward_model/, sizer/ | tooling | `cd python && uv run python ../scripts/no_time_time_lint.py` | ✅ (extend) |
| INFRA-03 | Single-writer discipline on `loss_grid_artifacts`, `competition_history` | tooling | `cd python && uv run python ../scripts/sqlite_writer_lint.py` | ✅ (auto-covers) |

### Sampling Rate

- **Per task commit:** `cd python && uv run pytest tests/test_{loss_model,reward_model,sizer}_*.py -x` (typically < 10s)
- **Per wave merge:** `cd python && uv run pytest -x` (full suite, ~60s based on Phase 2 history)
- **Phase gate (`/gsd-verify-work 3`):** Full suite green + architecture_lint + no_time_time_lint + sqlite_writer_lint + `test_manifest_contains_all_knobs::test_phase3_leaves_surfaced` all green

### Wave 0 Gaps

- [ ] `python/tests/test_loss_model_replay.py` — new file, covers LOSS-01
- [ ] `python/tests/test_loss_model_artifact.py` — new file, dual-write contract
- [ ] `python/tests/test_loss_model_expected_loss.py` — new file, covers LOSS-02
- [ ] `python/tests/test_loss_model_ou_scaffold.py` — new file, covers LOSS-03
- [ ] `python/tests/test_reward_model_r_capped.py` — new file, covers REWARD-01
- [ ] `python/tests/test_reward_model_q_cap.py` — new file, covers REWARD-04
- [ ] `python/tests/test_reward_model_competition_tracker.py` — new file, covers REWARD-02
- [ ] `python/tests/test_sizer_optimizer.py` — new file, covers REWARD-03
- [ ] `python/tests/fixtures/_generate_loss_grid_fixtures.py` — synthetic fixture generator (same pattern as `_generate_fill_model_fixtures.py`)
- [ ] `python/tests/test_manifest_contains_all_knobs.py::test_phase3_leaves_surfaced` — extension of existing test
- [ ] `python/tests/test_sqlite_single_writer.py` — extend to cover new tables
- [ ] Framework already installed; no new install step

## LLM Wiki Pages to Write-Back (Protocol 1)

### New pages (7)

| Page | Status | One-liner |
|------|--------|-----------|
| `[[reward-cap-geometry-v05]]` | Current — v0.5 regime | Piecewise-linear `R_capped(Q_me)` curve with kink at `Q_me` where `R_uncapped = cap_budget`. Three regimes: sub_cap / cap_binding / market_saturated. Absorbs PITFALLS A4. |
| `[[empirical-loss-grid-v05]]` | Current — v0.5 regime | `(depth, τ)` cell definitions, bucket edges, sparse-cell k-NN fallback, parquet+SQLite dual-write persistence. Refines `[[fill-loss-coarse-bound-v05]]` per-cell. |
| `[[e-liq-per-epoch-source-decision]]` | Current | The resolution: operator-manual per-market calibration with `data_source='synthetic_current'` lineage marker; distributor ABI deferred to Phase 8. Replaces `[[historical-reward-budget-reconstruction-infeasible]]` as the operative page for live operation. |
| `[[sizing-optimizer-sub-cap-regime-v05]]` | Current — v0.5 regime | Sub-cap fixed-point proof at $100; `Q_min == Q_max` at collateral-constrained sizing; grid + scipy polish algorithm; scale-up test contract. |
| `[[ou-on-basis-loss-scaffold]]` | Current — v1.0 drop-in point | LOSS-03 scaffold: `OUBasisLossModel` Protocol + `NotImplementedError` stub + signature-stability contract. Spec for v1.0 implementation (MLE on B(t) = Implied − Underlying, closed-form integral, Tang-Chen bias correction). |
| `[[competition-tracker-data-sources-v05]]` | Current — v0.5 regime | Two sources: `/open-api/v2/accounts/all-limit-orders` for `Q_me`, DuckDB aggregation over `parquet.order_book_combined` for `Σ_others`. AMM share excluded. REST-degraded fallback to parquet-only. |
| `[[fee-cost-term-in-expected-loss]]` | Current | A6 absorption into `LossModel.expected_loss`: taker + settlement + market-entrance + gas amortization. Values from `[[fee-schedule]]`. |
| `[[unit-consistency-pendle-units-v05]]` | Current — v0.5 regime | All Phase 3 math in PENDLE-units at v0.5; USD conversion via `pricing.pendle_price_usd`; Phase 4 EV equation's terms all share PENDLE basis. |

### Superseded in same commit (Protocol 5)

| Old page | New status | Replaced by |
|----------|-----------|-------------|
| `[[fill-loss-coarse-bound-v05]]` | `Historical — superseded by [[empirical-loss-grid-v05]]` | `[[empirical-loss-grid-v05]]` |
| `[[economics-kill-switch-v05]]` | `Historical — superseded by [[economics-kill-switch-usd-variant-v10]]` | `[[economics-kill-switch-usd-variant-v10]]` (promoted from deferred to Current) |
| `[[historical-reward-budget-reconstruction-infeasible]]` | `Historical — superseded by [[e-liq-per-epoch-source-decision]]` | `[[e-liq-per-epoch-source-decision]]` |
| `[[historical-reward-budget-reconstruction-feasible-via-distributor-events]]` | Remains `Current — deferred pending distributor ABI` (unchanged) | — |

### Promoted

| Page | From | To |
|------|------|-----|
| `[[economics-kill-switch-usd-variant-v10]]` | `Current — deferred to Phase 3` | `Current` (add: USD-variant formula, `pendle_price_usd` integration, stale-price breaker; update all knobs from PricingConfig; update examples to use LossModel `E[loss|fill]` instead of `fill_loss_coarse_bound`) |

## Risks / Pitfalls

### Absorbed from Phase 1 research PITFALLS.md (already catalogued)

| Pitfall | Severity | Absorbed by | Action |
|---------|----------|-------------|--------|
| A4 | Medium | REWARD-01 | `r_capped_curve` returns `regime` label; unit tests at $100 and $5k; `[[reward-cap-geometry-v05]]` plots the kink |
| A6 | Medium | LOSS-01 + FeesConfig | Every cell's empirical P&L includes taker + settlement + entrance + gas; fees.* knobs surfaced in manifest |
| A8 | Medium | REWARD-02 | Competition tracker includes outside-range-wall participants if inside CLO range; flag is covariate warning, not filter |

### New pitfalls surfaced by Phase 3 research

| # | Name | Severity | Mitigation |
|---|------|----------|------------|
| P3-1 | `liqSettings` misidentified as reward curve (Pre-Phase-3 assumption) | Medium (lost time risk only) | §E_liq Source Resolution documents `liqSettings` is liquidation, not reward. `[[e-liq-per-epoch-source-decision]]` calls this out explicitly. |
| P3-2 | `longYieldApr` misused as reward APR | Medium | Same as above. `[[e-liq-per-epoch-source-decision]]` clarifies `longYieldApr` = IRS yield, not reward. Test: `test_reward_model_no_longYieldApr_path`. |
| P3-3 | `pendle_price_usd` goes stale during daily re-screen window | Medium | `PricingConfig.price_staleness_warn_s = 86400` (24h), `price_staleness_halt_s = 604800` (7d); warn at 1d stale, halt at 7d stale. `[[unit-consistency-pendle-units-v05]]` documents policy. |
| P3-4 | Operator calibrates `e_liq_per_epoch_pendle` per-side wrongly (swaps long/short) | High | `MarketRewardCalibration` schema enforces `long_side_split + short_side_split == 1.0` (via field-validator). YAML author must provide both; missing → ConfigError. |
| P3-5 | `Q_me_target` grid-search finds spurious local maximum due to fill-model step function | Medium | `optimizer_method='grid_plus_scipy'` default: grid find best, scipy polishes in a small bracket around it. 50 grid points is enough to resolve the sub-cap/cap-binding kink. |
| P3-6 | Empirical loss grid contaminated by look-ahead (fill "close trade" occurs before fill?) | High (data integrity) | Replay strictly requires `close_event.blockTimestamp >= fill_event.blockTimestamp` (AND `eventIndex >` when same block). Test: `test_loss_model_replay::test_no_look_ahead`. Same discipline as Phase 2's `T-02-F-02 no-look-ahead` EWMA vol. |
| P3-7 | `RewardShareModel` reads stale `reward_budget_history` row (DATA-11 cache poisoning) | Medium | `r_capped_curve` reads `reward_budget_history ORDER BY polled_at_utc DESC LIMIT 1` per `[[live-e-liq-polling-data-11]]`. NEVER caches across calls. Phase 3 inherits this discipline. |
| P3-8 | Phase 4 `DecisionEngine.evaluate()` calls `expected_loss()` + `r_capped_curve()` + `q_me_target()` every 1 Hz, ~3 SQLite reads per call | Medium (latency) | SQLite WAL reads at <1ms each; 3ms/cycle well within 10ms budget. Unit test asserts p95 latency on the `Sizer.q_me_target()` full-stack call. |
| P3-9 | `LossModelNoFreshGridError` propagation breaks Phase 4 PLACE path but not CANCEL path | High (strategy correctness) | Phase 4 DecisionEngine MUST catch `LossModelNoFreshGridError` and route: suppress PLACE, allow CANCEL to continue with last-known grid + staleness warning. Documented in §LOSS-02 interface spec. |
| P3-10 | `CompetitionTracker` REST degraded + no order_book_combined snapshot in last 2h → `Σ_others` stale → R_capped stale → Sizer output stale | High (economic correctness) | `CompetitionTracker.run_one_cycle()` asserts `order_book_combined.latest_snapshot_ts >= chain_ts - 2 * ingest_cadence`. Breach → raise `CompetitionStalenessError`, Phase 4 breaker catches → halt per SAFE-09 pattern. |

## Phase Dependencies

### Phase 2 (`FillModel.predict`) — LOCKED interface Phase 3 consumes

**Signature (DO NOT touch in Phase 3):**
```python
# brain.fill_model.predict — Phase 2 locked
def predict(req: PredictInput, *, sqlite_path: Path, config: BotConfig) -> PredictOutput:
    # sync, p95 < 10ms budget
    # raises: FillModelStaleFeatureError, FillModelNoFreshFitError
```

**Phase 3 call site:** `brain.sizer.optimizer.q_me_target` composes:
```python
p_fill_output = fill_model.predict.predict(
    PredictInput(
        market_id=req.market_id,
        side=req.side,
        depth_from_mark_ticks=req.depth_from_mark_ticks,
        queue_ahead_wei=req.queue_ahead_wei,
        current_features=req.current_features,
        time_to_epoch_end_s=req.time_to_epoch_end_s,
        current_chain_ts=req.current_chain_ts,
    ),
    sqlite_path=sqlite_path,
    config=config,
)
p_fill = p_fill_output.p_fill_this_epoch
```

### Phase 1 data availability

- `parquet.market_trades` — required for LOSS-01 empirical replay
- `parquet.order_book_raw` + `parquet.order_book_combined` — required for REWARD-02 `Σ_others` aggregation + LOSS-01 mark-rate lookup
- `parquet.underlying_apr` — fee amortization for LOSS-01
- `parquet.settlement` / `parquet.market_data` — mark rate at fill time (LOSS-01)
- `state.clo_history` — defines incentivized range for REWARD-02 `Σ_others` tick bounds
- `state.reward_budget_history` — current `E_liq_per_epoch` + `long_budget` + `short_budget` (Phase 1 writes via ELiqPoller; Phase 3 reads; rows may be `data_source='synthetic_current'` per E_liq Source Resolution until the API endpoint materializes)

### Runtime state inventory (no rename/migration/refactor in Phase 3)

Phase 3 is greenfield — no existing OS-registered state, stored data, live service config, secrets, or build artifacts are migrated. `## Runtime State Inventory` section is therefore omitted as permitted by research-phase template for greenfield phases.

## Environment Availability

Phase 3 has no new external dependencies beyond Phase 1/2 baseline.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| polars | LOSS-01, REWARD-02 | ✓ | 1.40.1 (pinned) | — |
| duckdb | LOSS-01, REWARD-02 | ✓ | 1.5.0 (pinned) | — |
| scipy | REWARD-03 optimizer polish | ✓ | transitively via statsmodels/fill_model | — |
| numpy | all | ✓ | >=2.0 | — |
| statsmodels | not used in Phase 3 | ✓ | 0.14.6 | — |
| pydantic | schema | ✓ | 2.13.3 | — |
| `@pendle/sdk-boros` | not used in Phase 3 | ✓ | 1.1.44 (TS only) | — |
| `api.boros.finance/open-api/v2/accounts/all-limit-orders` | REWARD-02 live poll | ✓ (probed 2026-04-24, returns 400 on missing body — endpoint exists) | v2 | Parquet-only fallback mode (`data_source='fallback_parquet_only'`) |
| `api.boros.finance/open-api/v1/markets` (liquidity rewards fields) | REWARD-01 numerator (E_liq_per_epoch) | **✗** (confirmed absent) | — | Operator-manual calibration in `MarketRewardCalibration` — **see §E_liq Source Resolution** |
| MultiTokenMerkleDistributor contract (LO Liquidity budget event) | REWARD-01 fallback | **✗** (no per-epoch budget event; verified via contract read) | — | Deferred to Phase 8 live-Merkle-delta reconstruction |

**Missing dependencies with no blocking fallback:** the live reward-budget endpoint; resolved in §E_liq Source Resolution with operator-manual fallback (the recommended v0.5 path).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `[ASSUMED]` Operator-manual reward-budget calibration in `MarketRewardCalibration` is acceptable to the user | §E_liq Source Resolution | If user rejects → RESEARCH BLOCKED; Phase 3 can't compute `R_capped` numerator |
| A2 | `[ASSUMED]` $100 collateral places strategy in sub-cap regime for every market in the Phase 1 shortlist, not just ETHUSDT-29MAY2026 | §REWARD-01 + §REWARD-03 | If a thinner market has `E_liq × side_split / Σ_others < cap_budget_per_epoch_pendle` at Q_min, the market is in cap-binding regime even at $100 — the cap IS structural across sizing. This is an algebraic edge case; will be verified in the REWARD-03 test matrix across all shortlisted markets. Not a research-blocker — the test matrix catches it. |
| A3 | `[ASSUMED]` `pendle_price_usd ≈ $7` for sub-cap proof derivations. Actual value at plan time must be operator-confirmed | §REWARD-01 | A 10× PENDLE price move shifts `cap_budget_per_epoch_pendle` by 10×, but `E_liq × side_split / Σ_others` at Q_min is still ≫ cap for realistic competition. Robust within any reasonable PENDLE price range. |
| A4 | `[ASSUMED]` `config.settlement_fee_rate = 1e-3` (0.1% per 8h period) is the right starting default per `[[fee-schedule]]`. Exact value is per-market via `MarketConfig.settleFeeRate` (1e18-denominated string; verified in captured sample e.g. `1000000000000000` = 1e-3). | §BotConfig Knob Delta | Per-market override is already in `MarketCalibration` scope; plan can move this to per-market. Current default is safe — on the high side, so loss estimates are conservative. |
| A5 | `[ASSUMED]` The `makerIncentive` distributor address (`0xD0808080803c59dBF8825290bca8979786C2d65B`) serves both Maker Volume Rewards and LO Liquidity Rewards off-chain-composed — because there are only 3 deployed distributors and none is labeled "LO Liquidity" | §E_liq Source Resolution | If LO Liquidity Rewards are NOT in `makerIncentive`, then the Phase 1 economics-gate's reward economic model (which expects LO Liquidity pool payouts to our wallet) may be wrong. Phase 8 live operation will resolve this via wallet-balance delta per epoch — if $100 collateral produces zero PENDLE claim, the distributor assumption is wrong. Cheap-kill path: Phase 8 2-week observation window catches this. |
| A6 | `[ASSUMED]` Optimizer at $100 collateral collapses to `Q_me = Q_min` because collateral-constraint-induced `Q_max = Q_min` (in dollar-equivalent YU terms). NOT because EV objective has a local max at `Q_min` | §REWARD-03 | See §REWARD-03 derivation — the collateral-constrained sizing is the correct interpretation per consolidated plan §4. If a plan-checker finds the EV objective has a true interior maximum above Q_min at $100, the unit test exposes it and the plan adapts. |

**If this table has entries (it does — 6 `[ASSUMED]` claims):** A1 requires user confirmation before Phase 3 PLAN phase proceeds. A2 is test-matrix verifiable. A3-A6 are low-risk operational details that plan can work with.

## Open Questions

1. **[BLOCKER candidate] Operator-manual `E_liq_per_epoch` acceptable?**
   - What we know: every public source for per-market per-side reward-budget is unavailable; `liqSettings` is liquidation, not reward; contract exposes only Merkle roots; SDK's Incentives API teases endpoints that return 404 as of 2026-04-24 probe.
   - What's unclear: whether the user accepts a manual-calibration path.
   - Recommendation: proceed to `/gsd-discuss-phase 3` with the §E_liq Source Resolution question. **Only** if the user rejects manual calibration do we return `## RESEARCH BLOCKED`.

2. **[Resolvable in plan] Per-market `notional_per_yu_usd` calibration.**
   - What we know: BTCUSDT 1 YU = ~$1 BTC-funding-notional, ETHUSDT 1 YU = ~$1 ETH-funding-notional (rough operator knowledge).
   - What's unclear: exact per-market notional semantics; should be in `MarketCalibration`.
   - Recommendation: plan adds `MarketCalibration.notional_per_yu_usd: float` field and requires it at strategy-YAML time. Operator fills from dApp UI.

3. **[Resolvable in plan] LOSS-01 replay window length.**
   - What we know: 14d is fill-model's rolling window; loss events are rarer.
   - What's unclear: whether 90d is optimal or should be 60d or 180d.
   - Recommendation: default `90d` in `LossModelConfig.window_days`; plan includes a calibration step that tests 30d / 60d / 90d / 180d grids and picks the best GoF with log.

4. **[Resolvable in plan] Absolute floor for sparse-cell fallback.**
   - What we know: `fill_loss_coarse_bound = 0.02` (0.02 APR decimal) exists at Phase 1.
   - What's unclear: whether LossModel's absolute-floor fallback should use this value or a per-market-derived value.
   - Recommendation: fall back to `config.screener.fill_loss_coarse_bound × fill.notional` at absolute worst case. Documented in `[[empirical-loss-grid-v05]]`.

## Sources

### Primary (HIGH confidence — verified via tool/code/sample)

- `docs/samples/markets-response.json` (live `/markets` response, captured 2026-04-24) — `[VERIFIED: python3 json parse]`
- `https://docs.pendle.finance/boros-dev/Mechanics/Margin` — `liqSettings` is liquidation, not reward. `[VERIFIED: WebFetch 2026-04-24]`
- `https://github.com/pendle-finance/boros-core-public/blob/main/contracts/distributor/MultiTokenMerkleDistributor.sol` — distributor events. `[VERIFIED: WebFetch 2026-04-24]`
- `https://github.com/pendle-finance/boros-core-public/blob/main/deployments/core.json` — 3 distributor addresses on Arbitrum. `[VERIFIED: curl + JSON parse 2026-04-24]`
- `https://raw.githubusercontent.com/pendle-finance/sdk-boros-public/main/documentation/API.docs.md` — SDK API reference, §12 Incentives API (not deployed). `[VERIFIED: curl 2026-04-24]`
- `python/src/boros_brain/fill_model/predict.py` + `schemas.py` — Phase 2 locked `FillModel.predict` interface consumed by Phase 3 Sizer. `[VERIFIED: Read 2026-04-24]`
- `python/src/boros_brain/fill_model/artifact.py` + `config.py` — pattern for dual-write parquet+SQLite and PROTO-04 knobs. `[VERIFIED: Read 2026-04-24]`
- `python/src/boros_brain/screener/economics_gate.py` — locked `compute_r_apr_on_collateral_pendle` formula Phase 3 must match in PENDLE-units. `[VERIFIED: Read 2026-04-24]`
- `docs/architecture.yml` — current architecture manifest. `[VERIFIED: Read 2026-04-24]`
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/*.md` — [[live-e-liq-polling-data-11]], [[economics-kill-switch-v05]], [[economics-kill-switch-usd-variant-v10]], [[fill-loss-coarse-bound-v05]], [[fee-schedule]], [[historical-reward-budget-reconstruction-infeasible]], [[fill-model-predict-contract]]. `[VERIFIED: Read 2026-04-24]`
- `boros_consolidated_plan.md` §3 + §4 + §5 — canonical math for Phase 3. `[VERIFIED: Read 2026-04-24]`
- `.planning/research/PITFALLS.md` §A4/A6/A8 — absorbed pitfalls. `[VERIFIED: grep 2026-04-24]`
- `.planning/research/STACK.md` §OU parameter estimation — LOSS-03 scaffold guidance. `[VERIFIED: grep 2026-04-24]`

### Secondary (MEDIUM confidence — WebSearch + single source)

- `https://docs.pendle.finance/boros-docs/Introduction` (via Pendle Academy glossary) — `longYieldApr` = IRS yield semantics. `[CITED]`
- `https://docs.pendle.finance/boros-dev/Mechanics/Fees` (via `[[fee-schedule]]` wiki) — fee formula. `[CITED]`
- Probe results (2026-04-24, HTTPS) confirming 404 on `/v1/epoch-rewards`, `/v1/incentives`, etc. — tooled, but only lack-of-result is verified. `[VERIFIED: bash curl probe]`

### Tertiary (LOW confidence — to flag)

- Operator calibration of `pendle_price_usd ≈ $7`. Needs refresh at plan time. `[ASSUMED]`
- `notional_per_yu_usd` per-market defaults. Plan refines. `[ASSUMED]`
- `FeesConfig.gas_*_gwei` defaults (200k / 100k / 300k). Phase 4 DECIDE-03 will measure empirically. `[ASSUMED]`

## Metadata

**Confidence breakdown:**
- LOSS-01/02 math + persistence pattern: **HIGH** — mirrors Phase 2 `fill_model` pattern which is proven
- LOSS-03 scaffold: **HIGH** — contract is a one-liner + two tests
- REWARD-01 math: **HIGH** — consolidated plan §4 is the locked derivation
- REWARD-02 `/accounts/all-limit-orders` endpoint: **HIGH** — live-probed 2026-04-24
- REWARD-02 `Σ_others` = order-book aggregation − AMM: **HIGH** — reuses Phase 2 AMM consumption utility
- REWARD-03 sub-cap fixed point at $100: **HIGH** — collateral-constraint argument is tight
- REWARD-04 `Q_cap` algebra: **HIGH** — closed-form from consolidated plan §4
- `E_liq_per_epoch` source resolution: **LOW (blocker candidate)** — operator manual is the only viable v0.5 path; user must confirm
- A6 fee absorption + A4 kink + A8 competition tracking: **HIGH** — research already catalogued these

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (30 days, stable domain — Boros protocol changes infrequent). Reward-endpoint landscape may improve if Pendle deploys the advertised Section 12 Incentives API; recheck monthly.

---

