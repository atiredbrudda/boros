# Phase 2: Fill Model (NHPP v0.5) — Research

**Researched:** 2026-04-24
**Domain:** Point-process fill-probability modelling on a hybrid CLOB+AMM IRS venue (Pendle Boros, Arbitrum)
**Confidence:** HIGH on data availability + covariate selection + architecture. **MEDIUM** on library choice for the **covariate-driven baseline fit** (see §1, major course-correction vs. prior research). HIGH on queue/AMM mechanics and GoF methodology.

Wiki check (Protocol 1) complete: read `[[architecture-overview-v05]]`, `[[strategy-thesis-lo-liquidity-rewards]]`, `[[EV cancel rule]]`, `[[amm-conservation-assertion-data-05]]`, `[[eventIndex coverage]]`, `[[sqlite-state-spine-v05]]`, `[[pydantic-botconfig-schema-v05]]`, `[[python-stack-v05]]`, `[[fill-loss-coarse-bound-v05]]`, `[[live-e-liq-polling-data-11]]`. No existing Phase-2 pages — all new findings below must write back.

## Summary

The consolidated plan, STACK.md, and the Phase-2 scope row in ROADMAP.md all assume `tick` 0.8.0.1 is the library for fitting `λ_s(δ, t) = exp(β_0 + Σ β_i feature_i(t))`. **This assumption is half-wrong.** `tick` ships `SimuInhomogeneousPoisson` (a simulator that takes a `TimeFunction` for intensity) and Hawkes learners with **constant baselines**, but **does not expose a covariate-driven baseline learner** — there is no `ModelInhomogeneousPoissonLogLinear` class. `[VERIFIED: x-datainitiative.github.io/tick/modules/hawkes.html]` `[VERIFIED: GitHub tick repo doc/modules/hawkes.rst]` The production path is therefore: **fit the log-linear intensity with `statsmodels.GLM(family=Poisson(log))` using binned counts and `exposure=bin_duration`** — this is the textbook Poisson-regression primitive for NHPP and is exactly what tick's API is missing. `tick` is still kept as a **dependency for v1.0 Hawkes overlays** (a Hawkes model with a covariate-constant baseline is the next step once v0.5 is calibrated) and for NHPP **simulation** in calibration-plot generation, but is **not on the critical fit path**.

The phase produces three mutually-dependent artifacts that must land atomically: (1) a `QueueTracker` that replays `market-trades` NDJSON at `eventIndex` resolution between hourly `raw/` snapshots, with an explicit pessimistic/optimistic bracket and a signed drift diagnostic; (2) an `AMMConsumption` splitter that subtracts `combined - raw` from incoming taker flow before crediting the resting book, using DATA-05's conservation invariant as a hard pre-condition; (3) a `FillModel` that consumes both as bin-features, fits log-linear intensity per (market, side), and exposes `predict(δ, side, queue_ahead, features) -> p ∈ [0,1]`. The rolling-14-day refit + goodness-of-fit gate per FILL-06 is the only thing standing between "calibrated" and "silently miscalibrated under regime shift" (PITFALLS B4 scaffolding absorbed here — not the Hawkes failure itself, but the generic fit-health protocol that v1.0 Hawkes will reuse).

**Primary recommendation:** Keep `tick` 0.8.0.1 in the stack (already in [[python-stack-v05]]) but change its role from "NHPP learner" to "simulator + v1.0 Hawkes staging." Add `statsmodels` 0.14.6+ as the critical-path learner library. Build `FillModel` on top of `statsmodels.GLM(family=Poisson(log))` with per-(market, side) fits and a scipy-based L-BFGS fallback for sparse-data regimes. Exact covariate set: **4 of 7** — basis spread, order-book imbalance, time-since-funding-settlement (sin/cos pair), EWMA realized vol — with a **binned features table** in DuckDB as the joined Phase 1 input.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Trade-tape replay + queue decrement | brain / Python | — | Offline / 1 Hz cadence; polars+DuckDB already sit in brain ([[python-stack-v05]]); decision engine consumes queue state inside brain |
| AMM consumption split | brain / Python | — | Same input parquet; same module neighborhood (`data/ingester/order_book.py` already exists) |
| NHPP fit (log-linear GLM) | brain / Python | — | scipy/statsmodels stack is Python-only; no TS hand-off needed |
| Feature engineering + bin pipeline | brain / Python | — | polars/DuckDB pipeline is brain-resident (Phase 1 `duckdb_layer`) |
| `predict(δ, side, queue_ahead, features)` call site | brain / Python (DecisionEngine, Phase 4) | — | Decision loop runs in brain ([[architecture-overview-v05]]); 1 Hz cadence is well within Python-sync latency budget |
| Fit artifact storage | brain SQLite + parquet | — | New table `fill_model_fits` + parquet sidecar for covariate coefficients |
| RUN_MANIFEST coverage of fit knobs | brain (manifest.writer) | — | PROTO-01 reflection-based emit from BotConfig sub-model |

**No TS work in Phase 2.** This is deliberate: the Phase-6 `hands` process does not compute probabilities; it only executes pre-signed calldata on cancel commands from brain. The hot path is insulated from model staleness by design — brain decides, hands executes.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FILL-01 | NHPP fit per market-side `λ_s(δ, t) = exp(β_0 + Σ β_i feature_i(t))` using `tick` 0.8.0.1 | §1 documents the tick-API gap and recommends `statsmodels.GLM(Poisson, log)` as the actual fit primitive. `tick` stays in the stack for simulation + v1.0 Hawkes overlay. FILL-01's spirit (log-linear NHPP per market-side) is met; FILL-01's letter (fit via tick) requires a **scope adjustment** — see Planner Hand-Off. |
| FILL-02 | Select 4 covariates from the 7 enumerated | §2 recommends: basis spread `B(t) = Implied − Underlying`, order-book imbalance, time-since-funding-settlement (encoded as sin/cos of `2π·(t mod 8h) / 8h`), EWMA realized-vol of mid-rate (5-min). Drop: CEX spot move (feed-risk + A7 coupling), time-to-maturity (no variation within a 14-day fit), `dRate/dt` (co-linear with EWMA vol). |
| FILL-03 | Queue tracker with drift-bias diagnostic + bounds | §3 specifies the replay algorithm, the **pessimistic** (all invisible events = placements ahead of us) / **optimistic** (all = cancels ahead) bracket, and the signed-drift metric that makes PITFALLS B1 falsifiable. Decision engine consumes the pessimistic bound. |
| FILL-04 | AMM consumption subtraction | §4 specifies the `amm_share(δ, t)` time-series reconstruction between hourly snapshots (linear-interpolated from adjacent combined/raw pairs), taker-flow split formula, and the per-epoch conservation identity that B3 requires. |
| FILL-05 | Exposed `predict()` + calibration tests | §6 specifies the exact Python signature the decision engine (Phase 4) will call, async/sync contract, fit-staleness degradation. §5 specifies the calibration methodology. |
| FILL-06 | Rolling 14-day fits + GoF + degradation warning | §5 + §8: log-likelihood ratio vs. null (intensity-proportional-to-exposure) plus Rosenblatt-transform-based time-change uniformity test; threshold = LR below 5th percentile of in-sample bootstrap → `fill_model.fit_degraded` warning log. |

## User Constraints (from PROJECT.md + CLAUDE.md — no formal CONTEXT.md for this phase yet)

Phase 2 has no `/gsd-discuss-phase` output. Constraints are inherited from [[strategy-thesis-lo-liquidity-rewards]] and [[EV cancel rule]]:

### Locked Decisions (cannot revisit in Phase 2 research)
1. **Target only Limit Order Liquidity Rewards** — fills are bad; the fill model quantifies opportunity cost of *not being filled*, it does not chase fills.
2. **EV-based cancel rule, no threshold dials** — `P(fill)` is one input to `EV_hold`; the other is `E[loss|fill]` from Phase 3. The fill model is **not** the decision rule; it feeds the decision rule.
3. **`eventIndex` for intra-block ordering** — not `blockTimestamp`. Applies to trade-tape replay and queue tracking.
4. **OU-on-basis** is for `E[loss|fill]` only, **NOT** for fill probability. Any `P(fill)` model built on continuous-diffusion assumptions is wrong — CLOB is step-function.
5. **Single Pydantic `BotConfig` is SSoT for knobs** — new Phase-2 knobs must land in the schema in the same plan that reads them (PROTO-04, D2 pitfall).
6. **`voluntary_cancel_forfeits_accumulated = False`** (P0-01) — the fill model is indifferent to this flag; it only affects how `R_share_per_epoch` enters the EV rule downstream.

### Claude's Discretion
- Exact library split between `tick` and `statsmodels` (§1).
- Covariate selection from the 7-item list (§2).
- GoF metric and threshold value (§5).
- Fit artifact storage shape — new SQLite table vs. parquet sidecar (§7).
- Pessimistic/optimistic bound-width heuristics beyond the "all-invisible-events-one-way" definition (§3).

### Deferred Ideas (v1.0 — OUT OF SCOPE for Phase 2)
- Per-market Hawkes/NHPP/RP selection by CV dispersion (V2-FILL-01..04).
- HMM confirmation overlay (V2-HMM-01/02).
- OU-on-basis parametric loss (that's Phase 3 scaffold + v1.0 actual).

## Project Constraints (from CLAUDE.md)

Every Phase 2 plan MUST obey:

1. **LLM Wiki write-back** — new pages on (a) NHPP library decision (tick gap), (b) covariate set with justification, (c) queue-tracker algorithm, (d) AMM-consumption formula, (e) GoF metric choice + threshold. Each carries `Status: Current` or `Status: Current — v0.5 regime`. Supersede any page that contradicts — as of this research, none exist to supersede.
2. **Atomic architecture.yml update** — every source file in the same commit as its node + edges. Phase 2 adds at minimum: `brain.fill_model.queue_tracker`, `brain.fill_model.amm_consumption`, `brain.fill_model.features`, `brain.fill_model.fit`, `brain.fill_model.predict`, `brain.fill_model.calibration`, `brain.fill_model.cli` modules; `state.fill_model_fits` storage; `parquet.fill_features`, `parquet.fill_predictions` storage; plus `config.fill_model.*` knob nodes. Edge types: `reads` parquet + clo_history + reward_budget_history; `writes` fill_model_fits; `depends-on-config` every new knob; `calls` chain_time for ts.
3. **RUN_MANIFEST + BotConfig knob delta** — `FillModelConfig` sub-model (§8) added to `BotConfig`; every knob default + range is documented.
4. **No `time.time()` in decision/data/screener paths** — INFRA-14 lint already enforces for those folders; extend lint to `fill_model/` (one-line addition to `scripts/no_time_time_lint.py`).
5. **SQLite single-writer-per-table** — `fill_model_fits` has exactly one writer module. Lint enforcement already in place.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `statsmodels` | >=0.14.6 | **Critical-path NHPP fit** via `GLM(family=Poisson(link=log), exposure=bin_duration)` | `[VERIFIED: statsmodels.org/stable/glm.html]` GLM Poisson with log-link + exposure is the textbook primitive for binned NHPP. Offset-free, exposure handles bin-duration normalization, MLE convergence is well-characterized. Deps: numpy>=2, scipy>=1.11, pandas (we allow pandas in-and-out for statsmodels interop only — polars still owns the bulk pipeline). |
| `tick` | 0.8.0.1 | NHPP **simulation** (calibration-plot Monte Carlo), v1.0 Hawkes-overlay staging | `[VERIFIED: PyPI tick 0.8.0.1]` released 2026-04-20, CPython 3.11/3.12/3.13 wheels. `SimuInhomogeneousPoisson` takes a `TimeFunction` and simulates realizations of λ(t) for calibration reliability tests. Hawkes learners (`HawkesExpKern`) exist for v1.0 overlay once v0.5 baseline ships. |
| `polars` | 1.40.1 | Feature-pipeline bulk transformation (already pinned in pyproject.toml) | `[VERIFIED: polars 1.40.1 in python/pyproject.toml]` Streams + lazy + predicate pushdown for the binned-features build. Phase 1 ingesters write parquet in polars; Phase 2 reads via `pl.scan_parquet`. |
| `duckdb` | 1.5.0 | Ad-hoc SQL joins across parquet + SQLite (clo_history, reward_budget_history) | `[VERIFIED: duckdb 1.5.0 in python/pyproject.toml]` Already wired via `brain.duckdb_layer.setup` — Phase 2 feature join (trades + raw-book + combined + clo_history + reward_budget_history + underlying_apr) is the canonical DuckDB use case. |
| `scipy` | already pulled transitively via statsmodels | L-BFGS-B fallback fit when GLM fails on sparse/degenerate bins; `scipy.stats` for GoF chi-square / KS tests | `[CITED: STACK.md §OU parameter estimation]` scipy already in the stack via web3/statsmodels. |
| `numpy` | >=2.0 | Array primitive | `[VERIFIED: python/pyproject.toml]` locked to numpy>=2 via polars + web3 constraints. |
| `pydantic` | 2.13.3 | `FillModelConfig` sub-model added to `BotConfig` | Already in stack. |
| `structlog` | 25.5.0 | `fill_model.fit_completed` / `fill_model.fit_degraded` / `fill_model.predict_cache_miss` log events, all `run_id`-tagged | Already in stack. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pyarrow` | transitively via polars | parquet writes for fit-artifact persistence | polars+PartitionBy+sink_parquet already in use |
| `pytest` + `hypothesis` | already pinned | property-based tests on queue-tracker bound invariants (pessimistic ≤ realized ≤ optimistic) | Already pinned dev deps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `statsmodels.GLM` | Hand-rolled `scipy.optimize.minimize` on closed-form Poisson log-likelihood | `[CITED: STACK.md §OU parameter estimation]` STACK.md takes this path for OU; same pattern would work here. 40-line cost vs. statsmodels' ~40MB dependency. **Decision: pay the dependency cost.** statsmodels gives us standard-error estimates, deviance residuals, covariance matrix of β, and influence diagnostics for free — all of which are useful for the GoF gate (§5). Reinventing that = hidden cost. |
| `statsmodels.GLM` | `sklearn.linear_model.PoissonRegressor` | `[CITED: scikit-learn.org docs]` sklearn's PoissonRegressor minimizes a deviance loss but **does not expose standard errors or likelihood by default** — you'd have to back-compute them. Also supports L1/L2 penalization which we do not need (4 covariates, no collinearity threat at this scale). Wrong tool. |
| `tick` as critical-path learner | (the ROADMAP/STACK.md assumption) | See §1. `tick` ships no covariate-driven NHPP learner. Keeping it as critical-path forces hand-rolled covariate wiring around `SimuInhomogeneousPoisson` — strictly more work than `statsmodels.GLM`. |
| In-memory fit + pickle | Fit to SQLite row + parquet sidecar | See §7 — we need the fit artifact to be `run_id`-queryable and reloadable across process restarts; in-memory only + pickle fails this. |

**Installation:**

```bash
# in /Users/macbookair/boros/python/
uv add statsmodels>=0.14.6
uv add tick==0.8.0.1
```

**Version verification:**

```bash
# to be run in the first Phase 2 plan
uv run python -c "import statsmodels; print(statsmodels.__version__)"
uv run python -c "import tick; print(tick.__version__)"
```

`[VERIFIED: PyPI 2026-04-24]` statsmodels latest is 0.14.6 (Apr 2026), tick is 0.8.0.1 (Apr 20 2026). Both publish CPython 3.12 wheels. **Caveat:** tick 0.8 is a relatively fresh release (4 days old at research time) — if the wheel build fails on macOS arm64 (scikit-build-core + pybind11), fall back to `tick==0.7.x` which also has covariate-free Hawkes. The fall-back does not change the recommendation for `statsmodels` as the fit primitive.

## Architecture Patterns

### System Architecture Diagram

```
                                                       ┌──────────────────────────┐
                                                       │  RUN_MANIFEST writer     │
                                                       │  reflects FillModelConfig│
                                                       └──────────┬───────────────┘
                                                                  │ writes
                                                                  ▼
┌──────────────┐  parquet    ┌──────────────────────┐  bin      ┌──────────────┐
│ market_trades├────────────►│ brain.fill_model.    │──────────►│ parquet.     │
│ (Phase 1)    │  NDJSON     │   features           │  features │ fill_features│
│              │             │ (DuckDB joins,       │  table    │ (per-market, │
│ order_book_  │────────────►│  EWMA, basis,        │           │  per-side,   │
│ raw          │             │  imbalance, sin/cos  │           │  per-bin)    │
│              │             │  settlement)         │           └──────┬───────┘
│ order_book_  │────────────►│                      │                  │
│ combined     │             └──────────────────────┘                  │
│              │                                                       │
│ underlying_  │─────────────────────────────────────────┐             │
│ apr          │                                         │             │
└──────┬───────┘                                         │             │
       │                                                 │             │
       │        ┌──────────────────────┐                 │             │
       ├───────►│ brain.fill_model.    │    amm_share(δ,t)             │
       │        │   amm_consumption   ├─────────────────────────────┐  │
       │        │ (combined − raw,    │                             │  │
       │        │  conservation       │    taker_flow_split        │  │
       │        │  assertion)         │                             │  │
       │        └──────────────────────┘                             │  │
       │                                                             │  │
       │        ┌──────────────────────┐      queue_ahead,          │  │
       │  tape  │ brain.fill_model.    │      drift_direction,      │  │
       └───────►│   queue_tracker     ├──────►pessimistic_bound,   │  │
   eventIndex-  │ (replay ticks,      │      optimistic_bound      │  │
       ordered  │  bias diagnostic,   │                             │  │
                │  P/O bracket)       │                             │  │
                └─────────┬────────────┘                             │  │
                          │                                          │  │
                          └──────────────────┬───────────────────────┘  │
                                             ▼                          │
                                  ┌──────────────────────┐              │
                                  │ brain.fill_model.    │◄─────────────┘
                                  │   fit                │
                                  │ (statsmodels.GLM     │
                                  │  Poisson log-link,   │
                                  │  per (market, side), │
                                  │  rolling 14-day)     │
                                  └─────────┬────────────┘
                                            │ writes fit artifact
                                            ▼
                                  ┌──────────────────────┐
                                  │ state.fill_model_fits│
                                  │ (SQLite, β vector +  │
                                  │  GoF metrics per     │
                                  │  fit_window_end_ts)  │
                                  └─────────┬────────────┘
                                            │
                                            │ reads latest fit
                                            ▼
                                  ┌──────────────────────┐   p ∈ [0,1]
                                  │ brain.fill_model.    ├────────────►  Phase 4
                                  │   predict            │               DecisionEngine
                                  │ P(fill_this_epoch |  │               (1 Hz loop)
                                  │  δ, side, queue, x)  │
                                  └──────────────────────┘
                                            │
                                            │ periodic GoF check
                                            ▼
                                  ┌──────────────────────┐
                                  │ brain.fill_model.    │──►  fill_model.fit_degraded
                                  │   calibration        │     warning log (run_id-tagged)
                                  │ (rolling evaluation, │
                                  │  Rosenblatt test)    │
                                  └──────────────────────┘
```

Primary use case trace: **"given a live `(market, side, depth-in-ticks, queue_ahead)` state at time t, return `P(fill this epoch)`"** —
1. Phase-1 pollers stream clo_history, reward_budget_history, f_index.
2. `queue_tracker` has been replaying market-trades between raw-book anchors; it reports `queue_ahead_pessimistic, queue_ahead_optimistic` for each in-flight order.
3. `amm_consumption` is subtracting AMM liquidity from the taker-flow that the queue tracker attributes to us.
4. `features` has been building a binned feature table (§7) from the same inputs.
5. `predict` loads the most-recent `fit_window_end_ts` row from `state.fill_model_fits`, computes `λ` for the current bin, integrates `1 − exp(−∫λ dt)` over `(t, epoch_end)`, returns `p`.
6. If `predict` is called with a fit older than `fit_max_staleness_s`, it logs a warning and returns the `p` computed from the prior run anyway (the decision engine's staleness breaker will KILL if the fit is catastrophically old; do not make `predict` itself a halt path — that conflates model staleness with execution staleness).

### Recommended Project Structure

```
python/src/boros_brain/
├── fill_model/
│   ├── __init__.py
│   ├── features.py            # DuckDB-joined binned feature table writer (parquet)
│   ├── queue_tracker.py       # Tape replay + bias diagnostic + P/O bounds
│   ├── amm_consumption.py     # combined − raw subtraction + conservation assertion
│   ├── fit.py                 # statsmodels.GLM fit with scipy fallback; per (market, side)
│   ├── predict.py             # predict(δ, side, queue_ahead, features) -> p
│   ├── calibration.py         # Rolling GoF + Rosenblatt time-change + LR vs null
│   ├── cli.py                 # `python -m boros_brain.fill_model.cli fit|predict|backtest`
│   ├── schemas.py             # Pydantic output schemas (FitArtifact, PredictInput, etc.)
│   └── constants.py           # Covariate whitelist, bin duration (60s default)
├── state/writers/
│   └── fill_model_fits.py     # single-writer module for fill_model_fits table
python/tests/
├── test_fill_model_queue_tracker.py
├── test_fill_model_amm_consumption.py
├── test_fill_model_fit_basic.py
├── test_fill_model_predict_contract.py
├── test_fill_model_calibration_gof.py
└── fixtures/
    ├── fill_model_tiny_tape.ndjson           # 100-trade fixture for queue tests
    ├── fill_model_synthetic_poisson.parquet  # known-λ fit regression
    └── fill_model_regime_shift.parquet       # for GoF degradation test
```

### Pattern 1: Binned Poisson-regression NHPP fit

**What:** Bin time into fixed-width windows `[t_i, t_{i+1})` (default 60s). Within each bin, count the number of taker-side trades at each depth `δ` attributable to "book at tick `mark ± δ`." Model `count_bin_i ~ Poisson(λ_i × bin_duration)` where `log λ_i = β_0 + β · x_i` and `x_i` is the covariate vector evaluated at mid-bin. Fit with `statsmodels.GLM(endog=count, exog=X, family=Poisson(link=log), exposure=bin_duration).fit()`. Report `β`, standard errors, deviance, AIC, log-likelihood.

**When to use:** Always. This is the entire v0.5 fit path. NHPP-with-covariates on binned counts is **isomorphic** to Poisson GLM regression — that's the whole reason Poisson GLM exists.

**Example:**

```python
# Source: statsmodels.org/stable/glm.html, adapted for this project
import statsmodels.api as sm
import numpy as np

def fit_nhpp_loglinear(
    counts: np.ndarray,          # shape (n_bins,)
    features: np.ndarray,         # shape (n_bins, n_features) -- covariates mid-bin
    bin_duration_s: np.ndarray,   # shape (n_bins,) -- exposure, usually constant 60.0
) -> sm.GLMResults:
    """
    Fit log λ(t) = β0 + β·x(t) via Poisson regression with exposure.

    Model equivalence:
        N([t, t+δ)) | x ~ Poisson(λ(x) · δ)
        ⟺  log E[N] = log δ + β0 + β·x        (GLM Poisson log-link + exposure=δ)

    Why statsmodels.GLM not scipy-hand-rolled:
    - Free standard errors + covariance matrix + deviance residuals
    - Robust convergence (IRLS by default, L-BFGS fallback) with post-fit diagnostics
    - AIC / log-likelihood attributes for GoF
    """
    exog = sm.add_constant(features)  # prepends β0 column
    model = sm.GLM(
        endog=counts,
        exog=exog,
        family=sm.families.Poisson(link=sm.families.links.Log()),
        exposure=bin_duration_s,
    )
    results = model.fit(method="IRLS", maxiter=100)
    return results
```

### Pattern 2: Queue-tracker drift-bias diagnostic

**What:** At each hourly reconciliation (when the next `raw/` snapshot lands), compare the replay-predicted queue-ahead-of-us at each tick to the snapshot-observed queue-ahead. Compute `drift[tick] = replay_predicted - snapshot_observed`. Aggregate signed mean across an epoch. Positive mean ⇒ replay over-estimates queue (biased "conservative" — fills come faster than we'd predict). Negative mean ⇒ replay under-estimates queue (biased liberal — fills come slower). Log `drift_sign`, `drift_magnitude`, `drift_std` per (market, side, epoch).

**When to use:** At every raw-snapshot reconciliation event during fit-window construction. The diagnostic is part of the fit output, not a live signal; the live `predict()` uses whichever bound (pessimistic or optimistic) the `FillModelConfig.queue_tracker_bias_mode` flag selects (default `pessimistic`).

**Example:**

```python
# See PITFALLS §B1 for the pitfall this defends against.
def compute_drift_diagnostic(
    replay_queue: dict[int, float],       # tick -> predicted queue size pre-reconciliation
    snapshot_queue: dict[int, float],     # tick -> observed queue size at snapshot
) -> dict[str, float]:
    ticks = set(replay_queue) | set(snapshot_queue)
    drifts = np.array([replay_queue.get(t, 0.0) - snapshot_queue.get(t, 0.0) for t in ticks])
    return {
        "drift_signed_mean": float(drifts.mean()),
        "drift_magnitude_mean": float(np.abs(drifts).mean()),
        "drift_std": float(drifts.std(ddof=1)),
        "n_ticks_compared": len(ticks),
    }
```

### Pattern 3: Pessimistic / Optimistic bracket

**What:** Two parallel replay runs per hour-interval, differing only in how they treat each trade whose post-last-snapshot queue-ahead attribution is ambiguous:
- **Pessimistic replay:** every invisible event between snapshots is treated as a *new placement ahead of us* (queue grows). Produces the high-queue, low-P(fill) envelope.
- **Optimistic replay:** every invisible event is treated as a *cancel ahead of us* (queue shrinks). Produces the low-queue, high-P(fill) envelope.
- **Realized replay:** attributes visible `market-trades` events to the book using the standard algorithm. The hypothesis from PITFALLS B1 is `pessimistic ≥ realized ≥ optimistic` — if it's violated, the replay has a bug.

**When to use:** The 3-track replay runs during fit-window construction. The **pessimistic bound** is what the live `predict()` consumes via `queue_ahead` argument (the decision engine wants conservative fill-avoidance). The bracket width is a health metric: if `pessimistic - optimistic` grows beyond `fill_model.bracket_width_warn_multiplier × hourly_mean`, the hour is flagged as having unusually high invisible-event activity and the fit weights that hour lower (sample weight, not exclusion — exclusion would break stationarity assumptions).

### Anti-Patterns to Avoid

- **Price-touch fill simulation:** fitting `P(fill) = P(mid crosses tick δ)` is the naive backtester's default. It massively overstates P&L because it ignores queue position and AMM consumption. Phase 2 explicitly rules this out (ROADMAP scope: "price-touch fill simulation overstates P&L and has been explicitly ruled out"). The three-component split (queue + AMM + NHPP) is the antidote.
- **Single-bin-count fit:** fitting one Poisson(λ) per market with no covariate is worse than NHPP with one feature, but it's what you get if you accidentally drop the covariate matrix from statsmodels.GLM. Test: `len(fit.params) == 1 + n_covariates` — add as a fit-health assertion.
- **OU / continuous-diffusion for fill probability:** covered by the Locked Decisions above. Do not re-introduce. CLOB is a step function; a diffusion fits badly.
- **Refit on every decision tick:** the hot path is 1 Hz; a GLM fit on ~14-day × 1440-min × 2-side binned data takes seconds. Refit at `fill_model.refit_cadence_s` intervals (default **900s = 15 min**) or on external trigger (CLO shift, regime-change breaker), not every tick.
- **NaN covariate silent-exp(β₀):** if a covariate feed is stale (e.g., `underlying_apr` is missing for the current bin), naive `predict` substitutes 0 and returns `exp(β_0)` — the pure prior. This looks like a valid probability but is **incorrect** (the model is calibrated on populated covariates). `predict()` MUST raise `FillModelStaleFeatureError` on NaN covariate and the caller (DecisionEngine) MUST treat that as a `cancel_all` breaker, not a fallthrough. New PITFALLS entry — see §12.
- **Look-ahead covariate:** EWMA vol computed on the bin's own trades contaminates the target. Use left-closed windows: `EWMA_vol(t_bin_i)` computed on `trades ∈ [t_bin_i - 5min, t_bin_i)` — exclude the bin's own trades.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Poisson log-linear MLE | Custom scipy loss + grad + hessian | `statsmodels.GLM(family=Poisson(log), exposure=...)` | Standard errors, deviance, convergence monitoring, covariance-of-β — all free. Hand-rolled = ~150 LoC + tests vs. 5 LoC call. |
| NHPP simulation for calibration plots | Custom inverse-CDF sampler | `tick.hawkes.SimuInhomogeneousPoisson` with a `TimeFunction` | tick's simulator is a well-tested C++ implementation. We only need the simulation, not the learner. `[VERIFIED: tick docs]` |
| Goodness-of-fit for point processes | Pick your favorite statistic | **Time-change theorem + Rosenblatt/KS on uniforms** | `[CITED: Daley & Vere-Jones, "An Introduction to the Theory of Point Processes"]` Standard: under correct λ, the integrated compensator `∫λ(t) dt` at event times forms a unit-rate Poisson; equivalently, inter-arrival times after time-change are i.i.d. Exp(1). KS-test the transformed inter-arrivals against Exp(1). Gives a single p-value per market-side per window. |
| Binned-count feature table | polars rolling aggregates by hand | DuckDB SQL with window functions over joined parquet + clo_history | Join logic (trade → clo_range → basis → realized_vol → imbalance) is 30 lines of SQL, <5 lines in polars with a DuckDB lazy frame. SQL is more readable for the feature audit. |
| Exponential-decay self-excitation (Hawkes, v1.0) | Custom MLE | `tick.hawkes.HawkesExpKern` | When v1.0 upgrades the baseline-with-self-excitation, `tick` finally fits — that's what it was designed for. Keep it in the stack so v1.0 is a delta, not a rewrite. |
| Rolling 14-day windowed fit | Custom schedule + in-memory cache | `asyncio.create_task(_refit_loop)` with `chain_time`-driven cadence | Phase 1 already has `chain_time` cache + `run_markets_poller`-style async loop pattern. Reuse. |

**Key insight:** The ROADMAP specifies `tick` because the author of the consolidated plan expected `tick` to be the universal point-process library. It isn't — `tick` is a **Hawkes** library with a simulator on the side. The covariate-driven NHPP fit that v0.5 needs is **standard Poisson regression**, which has a standard Python primitive (`statsmodels.GLM`). Don't fight the tick API; use the right tool.

## Runtime State Inventory

Phase 2 is **greenfield** — no rename / refactor / migration. Table omitted.

## Common Pitfalls

### Pitfall 1: Queue-drift direction blindness (PITFALLS §B1)

**What goes wrong:** Inter-snapshot queue drift is assumed "conservative" (under-estimates fill probability because unseen cancels shorten queue) but can be **liberal** (over-estimates fill probability when unseen placements grow queue). Backtest over-predicts fills → operator kills a viable strategy because "predicted fills didn't happen."

**Why it happens:** Hourly snapshots miss all invisible events. "Conservative" is asserted without evidence.

**How to avoid:** §3 algorithm — compute signed drift per epoch, log direction + magnitude, bracket every `P(fill)` estimate with pessimistic/optimistic. Default consumer = pessimistic.

**Warning signs:** `drift_signed_mean ≠ 0` (across many epochs) OR `|pessimistic - optimistic| / mean_queue > 0.5` on a sustained basis.

### Pitfall 2: AMM double-count or under-subtract (PITFALLS §B3)

**What goes wrong:** `amm_share(δ) = combined(δ) − raw(δ)` at the snapshot is correct only if both snapshots are the same instant. Hourly-snapshot misalignment of even 250ms (one Arbitrum block) can produce negative AMM shares or leak resting book into the AMM bucket. Replay engine silently double-counts or misses taker prints.

**Why it happens:** Hourly snapshots are not perfectly synchronized between `raw/` and `combined_*/` feeds.

**How to avoid:** Phase 1's `assert_amm_conservation` (`[[amm-conservation-assertion-data-05]]`) fails loud on `combined < raw` at ingest time. Phase 2 adds the runtime analogue — per-epoch conservation identity: `book_ahead_of_us(t_end) = book_ahead_of_us(t_start) - taker_consumption_ahead - amm_consumption + net_placements_ahead`. Any violation of the identity within tolerance = replay bug.

**Warning signs:** `amm_share(δ, t) < 0` at any (δ, t); taker flow attributed neither to book nor AMM; fill probability with and without AMM subtraction differs by factor > 3.

### Pitfall 3: NHPP fit on too-sparse data (PITFALLS §B4 scaffolding)

**What goes wrong:** On a 14-day window with a thin market (< 5000 trades) or a market-side with rare activity (most short-side activity on a long-dominated market), statsmodels.GLM either fails to converge, produces a β vector with CI straddling 0 for all covariates, or converges to degenerate λ. `predict()` then returns a nearly-flat probability regardless of state.

**Why it happens:** MLE needs enough events per covariate. Rule of thumb: ≥ 10 events per parameter. 4 covariates + intercept × 2 sides = 10 params × 10 = 100 events minimum. Thin markets blow this.

**How to avoid:**
- Fit health gate: `results.converged == True`, `len(counts) / len(params) ≥ 10`, deviance / df_resid within documented bounds.
- If fit-health fails, the fit artifact is tagged `fit_status = "degraded"` and `predict()` emits `fill_model.fit_degraded` warning on every call.
- Fall back to a simpler sub-model (intercept-only) rather than refuse to predict — the decision engine has its own breakers.

**Warning signs:** IRLS does not converge in 100 iterations; standard error on any β > 10× its estimate; AIC within 2 of intercept-only null.

### Pitfall 4: Covariate co-linearity

**What goes wrong:** EWMA realized-vol and `dRate/dt` of mark APR are ≈ co-linear. If both are in the covariate set, β for each has inflated standard error and the model generalizes worse than either alone.

**Why it happens:** `dRate/dt` on a CLOB with frequent trading == realized vol in a different windowing. They are not orthogonal.

**How to avoid:** §2 drops `dRate/dt`. Include a variance-inflation-factor (VIF) check in fit diagnostics: any VIF > 10 → fit marked degraded.

### Pitfall 5: Look-ahead in EWMA covariate

**What goes wrong:** Computing `EWMA_vol(t)` using trades at `[t, t+5min]` (right-closed window) is a look-ahead leak — the model "knows the future" at fit time, then fails at predict time (when the future is genuinely unknown). Calibration plot looks amazing in backtest, prediction collapses in paper.

**Why it happens:** Off-by-one window indexing.

**How to avoid:** Strict **left-closed** windowing: `EWMA_vol(t)` computed on `[t − 5min, t)`. Unit test with a synthetic tape where the future trade is extreme — the EWMA for the current bin must NOT reflect it.

**Warning signs:** Backtest calibration plot near-perfect (`|predicted - realized| < 1pp` across bins); paper calibration plot at 2σ divergence.

### Pitfall 6: NaN-covariate silent-exp(β₀) (NEW, NOT in PITFALLS.md)

**What goes wrong:** A feed blip (chain_time stall, underlying_apr poller lag, clo_history stale) makes a covariate NaN for the current bin. naive `predict()` sets NaN → 0 → returns `exp(β_0)`, the pure-prior probability. Output looks like a valid probability but is uncorrelated with current state. Decision engine acts on a dead-cat probability.

**Why it happens:** Default NaN-handling in numpy/statsmodels is silent. No one raises.

**How to avoid:** `predict()` raises `FillModelStaleFeatureError(missing_features: list[str])` on any NaN-input covariate. Decision engine catches and routes to cancel-all-and-pause (SAFE-02-style breaker in Phase 4). Log line tagged with `run_id` + missing feature names.

**Warning signs:** `fill_model.predict_nan_covariate` log events are non-zero.

### Pitfall 7: Fit artifact not reloadable across runs

**What goes wrong:** Fit runs fine, `predict()` works this session. Bot restarts (`launchd` auto-restart). New run needs a fit but the previous fit was only in memory — so it refits immediately, blocking the decision loop for 30+ seconds while the fit runs.

**Why it happens:** In-memory-only fit has no persistence contract.

**How to avoid:** §7 — fit artifact written to `state.fill_model_fits` table + parquet sidecar on completion. On boot, `predict()` loads the most-recent fit (bounded by `fit_max_staleness_s`). If none exists or all are stale, log `fill_model.no_fresh_fit` warning and refuse to `predict` (equivalent to `FillModelStaleFeatureError`).

### Pitfall 8: GoF threshold set by intuition

**What goes wrong:** Operator picks `gof_threshold = 0.05` (the usual stats-class convention) and the fit-degraded warning fires every single epoch on a healthy market (because the null hypothesis is that the fit is *perfect*, and it isn't).

**Why it happens:** Statistical tests give you p-values; production thresholds need a distribution of p-values on known-good fits.

**How to avoid:** §5 — threshold is calibrated *against the in-sample bootstrap*: fit on 14 days, compute GoF on 100 bootstrap resamples of the same 14 days, take the **5th percentile of LR as the threshold**. Warning fires only when out-of-sample GoF is below the in-sample 5th percentile, not below 0.05.

## Code Examples

### 1. Feature bin extraction (DuckDB)

```sql
-- Source: Phase 1 DuckDB layer already registered market_trades + order_book_combined +
-- clo_history + reward_budget_history + underlying_apr VIEWS. This query joins them
-- into a per-(market, side, bin) feature table.
-- Run with: duckdb_layer.setup.open_analytical_conn().execute(SQL).pl()

WITH bins AS (
  SELECT
    market_id,
    side,
    -- 60-second bins
    epoch_seconds_to_timestamp(floor(block_timestamp / 60) * 60) AS bin_start,
    count(*)                     AS trade_count,
    sum(size_wei / 1e18)         AS taker_size_sum,
  FROM market_trades
  WHERE block_timestamp >= :window_start AND block_timestamp < :window_end
    AND market_id = :market_id
  GROUP BY 1, 2, 3
),
vol AS (  -- left-closed EWMA over 5min
  SELECT
    market_id,
    bin_start,
    sqrt(
      sum(pow(rate - lag(rate) OVER (ORDER BY bin_start), 2))
        OVER (ORDER BY bin_start ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING)
      / 5
    ) AS ewma_vol_5min
  FROM bins
),
imbalance AS (
  SELECT
    market_id,
    bin_start,
    (SUM(size_wei) FILTER (WHERE side = 'long') - SUM(size_wei) FILTER (WHERE side = 'short'))
      / NULLIF(SUM(size_wei), 0) AS book_imbalance
  FROM order_book_combined
  WHERE snapshot_ts BETWEEN bin_start - INTERVAL 60 SECOND AND bin_start
  GROUP BY 1, 2
)
SELECT
  b.market_id, b.side, b.bin_start, b.trade_count,
  -- Covariate 1: basis spread (Implied - Underlying)
  b.mid_rate - u.underlying_rate                              AS basis_spread,
  -- Covariate 2: imbalance
  i.book_imbalance                                            AS imbalance,
  -- Covariate 3a/b: sin/cos of time-since-settlement (8h period)
  sin(2*pi() * (extract(epoch_seconds from b.bin_start) % 28800) / 28800) AS sin_settlement,
  cos(2*pi() * (extract(epoch_seconds from b.bin_start) % 28800) / 28800) AS cos_settlement,
  -- Covariate 4: EWMA realized vol
  v.ewma_vol_5min                                             AS ewma_vol,
  60.0                                                         AS bin_duration_s
FROM bins b
LEFT JOIN vol v        USING (market_id, bin_start)
LEFT JOIN imbalance i  USING (market_id, bin_start)
LEFT JOIN underlying_apr u USING (market_id, bin_start);
```

### 2. Fit + save (statsmodels + SQLite)

```python
# Source: adapted from statsmodels.org/stable/glm.html + boros_brain pattern
import statsmodels.api as sm
import polars as pl
from .schemas import FitArtifact
from ..state.writers.fill_model_fits import insert_fit_artifact

def fit_market_side(
    features_df: pl.DataFrame,
    market_id: str,
    side: Literal["long", "short"],
    config: FillModelConfig,
    run_id: str,
    sqlite_path: Path,
) -> FitArtifact:
    # Left-closed filter → strict no-leakage
    df = features_df.filter(
        (pl.col("market_id") == market_id) & (pl.col("side") == side)
    ).drop_nulls(subset=config.covariate_whitelist).to_pandas()

    exog_raw = df[config.covariate_whitelist].values
    exog = sm.add_constant(exog_raw)
    endog = df["trade_count"].values
    exposure = df["bin_duration_s"].values

    model = sm.GLM(
        endog=endog,
        exog=exog,
        family=sm.families.Poisson(link=sm.families.links.Log()),
        exposure=exposure,
    )
    results = model.fit(method="IRLS", maxiter=100)

    artifact = FitArtifact(
        run_id=run_id,
        fit_window_start_ts=int(df["bin_start"].min().timestamp()),
        fit_window_end_ts=int(df["bin_start"].max().timestamp()),
        market_id=market_id,
        side=side,
        covariate_whitelist=config.covariate_whitelist,
        beta=results.params.tolist(),
        beta_stderr=results.bse.tolist(),
        log_likelihood=float(results.llf),
        deviance=float(results.deviance),
        aic=float(results.aic),
        n_observations=int(results.nobs),
        converged=bool(results.converged),
        gof_lr_vs_null=float(results.llr),
        fit_status="ok" if _passes_health_gate(results) else "degraded",
    )
    insert_fit_artifact(sqlite_path, artifact)
    return artifact


def _passes_health_gate(results: sm.GLMResults) -> bool:
    if not results.converged:
        return False
    if results.nobs / len(results.params) < 10:
        return False
    if max(abs(results.bse / results.params)) > 10.0:
        return False
    return True
```

### 3. Predict contract (what Phase 4 DecisionEngine calls)

```python
# Target signature — locked for Phase 4 to consume.
from pydantic import BaseModel

class PredictInput(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
    market_id: str
    side: Literal["long", "short"]
    depth_from_mark_ticks: int       # δ
    queue_ahead_wei: int              # from QueueTracker (pessimistic bound by default)
    current_features: dict[str, float]  # keyed by covariate_whitelist names
    time_to_epoch_end_s: float        # epoch_end - chain_time.now_cached()

class PredictOutput(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}
    p_fill_this_epoch: float           # ∈ [0, 1]
    lambda_per_second: float           # instantaneous intensity (diagnostic)
    fit_run_id: str                    # which fit produced this
    fit_age_s: float                   # staleness
    fit_status: Literal["ok", "degraded", "stale"]


class FillModelStaleFeatureError(RuntimeError): ...
class FillModelNoFreshFitError(RuntimeError): ...


def predict(req: PredictInput) -> PredictOutput:
    """
    Returns P(at least one fill at this depth on this side in the remaining epoch).

    Raises FillModelStaleFeatureError if any covariate is NaN — caller (DecisionEngine)
    routes this to a cancel-all-and-pause breaker, NOT to a silent fallback.
    Raises FillModelNoFreshFitError if the most-recent fit is older than
    fill_model.fit_max_staleness_s — caller treats as "model unavailable," pauses
    order placement until refit completes.

    Cadence: called by DecisionEngine at 1 Hz per in-flight order per cycle.
    Sync (not async). Budget: <10ms p95 per call. statsmodels.GLMResults.predict()
    on 5-feature vector is ~50µs; the main cost is artifact-load caching + queue-ahead
    integration.
    """
```

### 4. Time-change goodness-of-fit (Rosenblatt transform)

```python
# Source: Daley & Vere-Jones (2003), "An Introduction to the Theory of Point Processes"
# The time-change theorem: if λ is correct, then integrating λ at event times produces
# a unit-rate Poisson, equivalently, the transformed inter-arrivals are i.i.d. Exp(1).
from scipy import stats
import numpy as np

def gof_rosenblatt(
    event_times_s: np.ndarray,           # actual trade times in the window
    lambda_fn,                            # lambda_fn(t) -> intensity at time t
) -> dict[str, float]:
    """Null hypothesis: λ is the true intensity. Rejected ⟹ fit is bad."""
    # Compensator at each event time: integral of λ from window_start to t_i
    compensator = np.array([_integrate_lambda(lambda_fn, event_times_s[0], t) for t in event_times_s])
    # Inter-compensator gaps: should be i.i.d. Exp(1) under correct λ
    gaps = np.diff(compensator)
    ks_stat, ks_pval = stats.kstest(gaps, "expon", args=(0, 1))  # loc=0, scale=1
    return {"ks_stat": float(ks_stat), "ks_pval": float(ks_pval), "n_gaps": len(gaps)}
```

## Feature Engineering / Data Flow

Phase 1 already delivers every input Phase 2 needs. **No new data ingester code** — Phase 2 is pure consumer.

### Phase 2 reads (from Phase 1)
| Source | Path / module | What Phase 2 uses |
|--------|--------------|-------------------|
| `parquet.market_trades` | `data/parquet/market_trades/` | Binned trade counts per (market, side, bin) — the endog (`trade_count`). `eventIndex` for tie-breaking intra-block replay order. |
| `parquet.order_book_raw` | `data/parquet/order_book_raw/` | Hourly replay anchors for `QueueTracker`. |
| `parquet.order_book_combined` | `data/parquet/order_book_combined/` | AMM share (`combined − raw`) for `AMMConsumption`. Per-tick depth for `imbalance` covariate. |
| `parquet.underlying_apr` | `data/parquet/underlying_apr/` | `basis_spread` covariate numerator (Underlying side). |
| `state.clo_history` | SQLite `clo_history` table | `cloLower/cloUpper` bounds for δ anchoring; `f_index_raw` for implied-rate proxy. |
| `state.reward_budget_history` | SQLite | Not an input to the fit itself, but informs covariate scaling on Long/Short asymmetry. **Optional** for v0.5 (deferred to `sizing` in Phase 3). |
| `brain.duckdb_layer.setup` | `duckdb_layer/setup.py` | Pre-registered VIEWs over all the above — Phase 2 queries go through this, no new attach logic. |

### Phase 2 writes
| Artifact | Location | Cadence | Notes |
|----------|---------|---------|-------|
| `fill_features` parquet | `data/parquet/fill_features/market_id=.../side=.../window_end_ts=.../features.parquet` | on fit trigger | The binned feature table — materialized for reproducibility + backtest reuse. Hive-partitioned by `(market_id, side, window_end_ts)`. |
| `state.fill_model_fits` | new SQLite table | one row per fit completion | Columns: `run_id, fit_window_start_ts, fit_window_end_ts, market_id, side, covariate_whitelist (JSON), beta (JSON), beta_stderr (JSON), log_likelihood, deviance, aic, n_observations, converged, fit_status, gof_ks_pval, gof_lr_vs_null, created_at`. Primary key: `(market_id, side, fit_window_end_ts)`. Owned by single writer `state/writers/fill_model_fits.py`. |
| `fill_predictions` parquet (backtest only) | `data/parquet/fill_predictions/...` | on calibration run | Per-bin predicted vs. realized, for the calibration plot in FILL-05/Phase 5. Not written in live mode (1-Hz writes would swamp parquet). |

### Fit cadence

- Initial fit at bot startup (synchronous; boot blocks until fit completes — ~30s).
- Periodic refit every `fill_model.refit_cadence_s` (default 900 = 15 min) via an `asyncio.create_task` loop styled after `run_markets_poller` in `data/poller/markets_poller.py`.
- Forced refit on circuit-breaker events (CLO shift, regime-change — Phase 4).
- **Prediction uses the most-recent-by-`fit_window_end_ts` row**, not an in-memory cache — restart-safe.

## Decision-Engine Interface (FILL-05)

**Contract (locked — Phase 4 will consume this exact shape):**

| Property | Value |
|----------|-------|
| Module path | `boros_brain.fill_model.predict` |
| Entry function | `predict(req: PredictInput) -> PredictOutput` (see §Code Examples #3) |
| Sync / async | **Sync**. The entire call chain is <10ms p95; making it async would add event-loop overhead without benefit. |
| Cadence | Once per in-flight order per decision cycle. v0.5 single-market single-order = 1 call per second. |
| Thread-safety | Single-threaded assumption. brain is asyncio. predict() is pure-Python + numpy BLAS; no shared mutable state. |
| Failure modes | `FillModelStaleFeatureError` (NaN covariate) → DecisionEngine treats as `cancel_all_and_pause` (Phase 4 breaker). `FillModelNoFreshFitError` (all fits stale) → DecisionEngine treats as `cannot_place_new_orders` (blocks PLACE, does not cancel existing). |
| Staleness semantics | `fit_age_s` in the return payload is diagnostic only. `fit_status == "stale"` (age > `fill_model.fit_warn_staleness_s`) logs a warning; `age > fill_model.fit_max_staleness_s` raises `FillModelNoFreshFitError`. |
| Monotonicity contract | For fixed (side, features, time_to_epoch_end): (a) increasing `depth_from_mark_ticks` → decreasing `p_fill_this_epoch`; (b) increasing `queue_ahead_wei` → decreasing `p_fill_this_epoch`. Unit-test property-level via hypothesis. |

**Rationale for these choices:**
- Sync keeps the Phase 4 decision loop simple; the cost of awaiting a model call is zero in non-async code.
- Raising on NaN (not returning a sentinel) forces the caller to confront staleness. Silent sentinels are how PITFALLS accumulate.
- Separating `fit_degraded` (soft) from `fit_missing` (hard) gives the decision engine the right affordance: a degraded fit can still place orders (with warning); a missing fit cannot.

## Logging + RUN_MANIFEST Additions

Every Phase 2 knob lands on `BotConfig.fill_model: FillModelConfig` — this makes them auto-surface in RUN_MANIFEST via the reflection-based writer from Plan 01-03 (per PROTO-01).

### New `BotConfig.fill_model` sub-model

| Knob | Default | Range | Purpose |
|------|---------|-------|---------|
| `window_days` | `14` | `7 ≤ x ≤ 30` | Rolling window for fit (FILL-06) |
| `bin_duration_s` | `60.0` | `30.0 ≤ x ≤ 300.0` | Time-bin width for Poisson counts |
| `refit_cadence_s` | `900.0` | `60.0 ≤ x ≤ 3600.0` | How often the fit loop refits |
| `covariate_whitelist` | `["basis_spread", "imbalance", "sin_settlement", "cos_settlement", "ewma_vol"]` | subset of allowed | List of covariates in THIS fit (extra covariates ignored; missing ones raise at fit time). 5 entries because sin+cos is one covariate *pair*, so 4 model features: basis, imbalance, settlement (encoded as sin/cos), ewma_vol. |
| `queue_tracker_bias_mode` | `"pessimistic"` | `Literal["pessimistic", "optimistic", "realized"]` | Which bound the decision engine consumes via `queue_ahead_wei` |
| `gof_ks_pval_threshold` | `0.0` | `0.0 ≤ x ≤ 0.5` | **Unused until bootstrap-calibrated in first fit** — initial value 0 disables the gate. Populated with the 5th-percentile in-sample bootstrap after first fit (see §5). |
| `gof_lr_ratio_threshold` | `null` (not yet calibrated) | populated at first-fit | Same bootstrap-calibration path. |
| `fit_warn_staleness_s` | `1800.0` (30 min = 2× refit cadence) | `600.0 ≤ x ≤ 7200.0` | Log a warning if fit older than this |
| `fit_max_staleness_s` | `3600.0` (1 hour = 4× refit cadence) | `fit_warn_staleness_s < x ≤ 28800.0` | Raise `FillModelNoFreshFitError` if fit older than this |
| `bracket_width_warn_multiplier` | `0.5` | `0.1 ≤ x ≤ 2.0` | Flag epochs where `pessimistic-optimistic > multiplier × hourly_mean_queue` |
| `min_events_per_param_ratio` | `10` | `5 ≤ x ≤ 50` | Fit health gate; GLM declared degraded below this |

### New log events (structlog, `run_id`-tagged)

| Event key | Level | Fields | When |
|-----------|-------|--------|------|
| `fill_model.fit_completed` | info | market_id, side, fit_window_end_ts, n_observations, converged, gof_ks_pval, fit_status | Every refit |
| `fill_model.fit_degraded` | warning | +reason (e.g. "non_convergence", "stderr_inflated", "gof_below_threshold") | When `fit_status != "ok"` |
| `fill_model.predict_nan_covariate` | warning | missing_features (list[str]) | Before raising `FillModelStaleFeatureError` |
| `fill_model.no_fresh_fit` | warning | fit_age_s, fit_max_staleness_s | Before raising `FillModelNoFreshFitError` |
| `fill_model.queue_drift_reconciliation` | info | market_id, side, drift_signed_mean, drift_magnitude_mean, drift_std, n_ticks | Every hourly snapshot reconciliation |
| `fill_model.bracket_width_warn` | warning | epoch, market_id, side, bracket_width, hourly_mean_queue, multiplier | When bracket_width_warn_multiplier exceeded |
| `fill_model.amm_conservation_violation` | error | epoch_start, epoch_end, identity_delta | Runtime (not ingest-time) conservation identity failure |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + hypothesis 6.x + pytest-asyncio 0.24 (already in pyproject.toml dev deps) |
| Config file | `python/pyproject.toml` `[tool.pytest.ini_options]` block; `tests/conftest.py` for shared fixtures |
| Quick run command | `cd python && uv run pytest tests/test_fill_model_* -x` |
| Full suite command | `cd python && uv run pytest -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FILL-01 | Fit with log-linear intensity on 5 covariates returns converged GLM with finite β | unit | `pytest tests/test_fill_model_fit_basic.py::test_fit_converges_on_synthetic_poisson -x` | ❌ Wave 0 |
| FILL-01 | Fit on empty / rank-deficient data marks fit_status=degraded and does not crash | unit | `pytest tests/test_fill_model_fit_basic.py::test_fit_degrades_on_sparse -x` | ❌ Wave 0 |
| FILL-02 | Covariate whitelist enforced: non-whitelisted covariate = ConfigError | unit | `pytest tests/test_fill_model_fit_basic.py::test_covariate_whitelist -x` | ❌ Wave 0 |
| FILL-02 | Left-closed EWMA (no look-ahead): last-bin trade does not affect its own ewma_vol | unit | `pytest tests/test_fill_model_features.py::test_ewma_no_lookahead -x` | ❌ Wave 0 |
| FILL-03 | Queue tracker: pessimistic ≥ realized ≥ optimistic for every tick, every snapshot | property | `pytest tests/test_fill_model_queue_tracker.py::test_bracket_invariant -x` | ❌ Wave 0 |
| FILL-03 | Queue tracker: `eventIndex`-ordered replay matches hand-computed expectation on tiny tape | unit | `pytest tests/test_fill_model_queue_tracker.py::test_replay_on_fixture -x` | ❌ Wave 0 |
| FILL-03 | Drift diagnostic reports non-zero signed mean on synthetic biased tape | unit | `pytest tests/test_fill_model_queue_tracker.py::test_drift_bias_detected -x` | ❌ Wave 0 |
| FILL-04 | `amm_share(δ, t) ≥ 0` at every (δ, t) on fixture | property | `pytest tests/test_fill_model_amm_consumption.py::test_amm_share_non_negative -x` | ❌ Wave 0 |
| FILL-04 | Per-epoch conservation identity holds on synthetic epoch | unit | `pytest tests/test_fill_model_amm_consumption.py::test_epoch_conservation -x` | ❌ Wave 0 |
| FILL-05 | `predict()` returns p ∈ [0,1] on happy path | unit | `pytest tests/test_fill_model_predict_contract.py::test_predict_in_unit_interval -x` | ❌ Wave 0 |
| FILL-05 | `predict()` raises FillModelStaleFeatureError on NaN covariate | unit | `pytest tests/test_fill_model_predict_contract.py::test_predict_raises_on_nan -x` | ❌ Wave 0 |
| FILL-05 | `predict()` monotone-decreasing in δ (ceteris paribus) | property | `pytest tests/test_fill_model_predict_contract.py::test_predict_monotone_in_depth -x` | ❌ Wave 0 |
| FILL-05 | `predict()` monotone-decreasing in queue_ahead | property | `pytest tests/test_fill_model_predict_contract.py::test_predict_monotone_in_queue -x` | ❌ Wave 0 |
| FILL-05 | Calibration-plot predicted P(fill) matches realized within documented tolerance on hold-out | integration | `pytest tests/test_fill_model_calibration_gof.py::test_calibration_on_holdout -x` | ❌ Wave 0 |
| FILL-06 | Rolling 14-day refit loop produces new fit artifact each cadence | integration | `pytest tests/test_fill_model_calibration_gof.py::test_refit_loop_writes_artifact -x` | ❌ Wave 0 |
| FILL-06 | GoF Rosenblatt-KS below threshold triggers `fit_degraded` log | unit | `pytest tests/test_fill_model_calibration_gof.py::test_degraded_warning_on_regime_shift -x` | ❌ Wave 0 |
| FILL-06 | `bracket_width_warn` log emitted on synthetic widening bracket | unit | `pytest tests/test_fill_model_queue_tracker.py::test_bracket_width_warn -x` | ❌ Wave 0 |
| PROTO-04 | All fill_model knobs appear in RUN_MANIFEST (reflection-driven) | integration | `pytest tests/test_manifest_reflection.py::test_manifest_contains_fill_model_knobs -x` | ❌ Wave 0 |
| PROTO-02 | architecture.yml contains every new node + edge | lint | `pytest tests/test_architecture_lint.py -x && python scripts/architecture_lint.py` | — hook |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_fill_model_* -x` (<10s on a warm cache)
- **Per wave merge:** `uv run pytest -x` (full brain suite, <2 min)
- **Phase gate:** full suite green before `/gsd-verify-work 2`; calibration plot committed as an artifact (not a test); GoF threshold bootstrap-calibrated on real 14-day history of the confirmed shortlist market from Phase 1.

### Nominal vs. Adversarial Inputs

| Dimension | Nominal | Adversarial (must not break) |
|-----------|---------|------------------------------|
| Fit window | 14 days of trades, ~5000–20000 events | 1 hour of history (new market) → fit_status=degraded, no crash |
| Tape gaps | eventIndex-ordered, no gaps | 5-minute gap (chain sequencer outage, ingester lag) → feature pipeline emits gap flag, bins during gap excluded from fit, no NaN leak |
| Combined/Raw sync | snapshots at identical timestamps | combined < raw on one tick (race on snapshot) → DATA-05 assertion fires at ingest, Phase 2 never sees the violation |
| Covariate feeds | all present | underlying_apr stale → predict raises FillModelStaleFeatureError, no silent fallback |
| Fit convergence | IRLS converges in ~10 iterations | IRLS hits maxiter without converging → fit_status=degraded, fallback to intercept-only GLM |
| Predict call | chain_time fresh, fit recent | chain_time stall 30s → fit_age_s computed against stale chain_time; predict still returns (fit_age_s is diagnostic) |
| Refit loop | 15-min cadence succeeds | Refit crashes mid-fit → asyncio task restart (launchd-style inside brain); fit_status remains "stale" on previous artifact until refit succeeds |
| Queue bracket | pessimistic − optimistic < 20% of mean | Bracket widens 3× hourly mean → bracket_width_warn fired, fit continues (the bracket *is* the diagnostic — widening is information, not failure) |

### Nyquist-rate sampling implication

The 14-day fit window at 60s bins → **20,160 bins per market-side**. Hold-out should be the last **20% = 2,880 bins** of each window (≈ 2.8 days). This gives the calibration tolerance room: 2,880 bins × ~1 event/bin (on a typical market) → ~2,880 events → ~95% CI on realized frequency is ±1.8% of observed — tighter than the ±5% "calibration-test tolerance" FILL-05 requires (tolerance TBD in plan — recommend 5pp absolute across P(fill) deciles per the calibration-plot convention). If we went to 1-day hold-out (200 bins), we'd lose discriminative power on the calibration plot's extremes.

### Wave 0 Gaps

- [ ] `python/tests/test_fill_model_queue_tracker.py` — covers FILL-03
- [ ] `python/tests/test_fill_model_amm_consumption.py` — covers FILL-04
- [ ] `python/tests/test_fill_model_features.py` — covers FILL-02 feature pipeline
- [ ] `python/tests/test_fill_model_fit_basic.py` — covers FILL-01
- [ ] `python/tests/test_fill_model_predict_contract.py` — covers FILL-05
- [ ] `python/tests/test_fill_model_calibration_gof.py` — covers FILL-06
- [ ] `python/tests/fixtures/fill_model_tiny_tape.ndjson` — synthetic 100-trade tape for queue replay
- [ ] `python/tests/fixtures/fill_model_synthetic_poisson.parquet` — known-β Poisson realization for fit regression
- [ ] `python/tests/fixtures/fill_model_regime_shift.parquet` — regime-change fixture for GoF degradation
- [ ] Dependency install: `uv add statsmodels>=0.14.6 tick==0.8.0.1` — if `tick` wheel fails on macOS arm64, fall back to tick 0.7.x and document in [[python-stack-v05]]

## Security Domain

`security_enforcement` not set in `.planning/config.json`; default is **enabled**. Phase 2 is math/analysis code with **no external network I/O** — the attack surface is almost entirely **input-validation** of upstream data.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | no new auth surface |
| V3 Session Management | no | no sessions |
| V4 Access Control | no | same-process internal API only |
| V5 Input Validation | **yes** | Pydantic v2 `FillModelConfig` + PredictInput (strict + frozen + extra=forbid); parquet schemas already enforced by Phase 1 ingester |
| V6 Cryptography | no | no crypto — never hand-roll |
| V7 Error Handling | **yes** | Structured exceptions (`FillModelStaleFeatureError`, `FillModelNoFreshFitError`) with enumerated types; no bare `except Exception` |
| V8 Data Protection | **yes (minor)** | Fit artifacts may leak market identity in logs → PII-adjacent for an anonymous wallet, but market IDs are public anyway. Redaction not required. |
| V10 Malicious Code | **yes** | `statsmodels` + `tick` are both widely-used open-source libraries; wheels verified on PyPI with standard signing |
| V14 Configuration | **yes** | Every knob in BotConfig schema; no environment-variable knobs in Phase 2 |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Parquet file tampering (malicious actor writes bad feature bins) | Tampering | Phase 1 DATA-05 conservation assertion; Phase 2 schema validation via polars; `.parquet` files live under `data/parquet/` which is gitignored — not distributed |
| NaN-injection via stale covariate feed | Tampering / DoS | `FillModelStaleFeatureError` raised, NOT silently substituted |
| Log injection via unsanitized market_id | Log injection | structlog JSONRenderer already escapes; no f-string in log messages |
| Dependency supply-chain (statsmodels/tick compromise) | Malicious code | `uv.lock` pins hashes; `uv sync --locked` in CI |
| DoS via pathological fit window (very small data) | DoS | fit health gate declares degraded + returns; does not block decision loop indefinitely |
| Numerical overflow in `exp(β · x)` | DoS (NaN propagation) | Clip features to `[−10, 10]` standardized (default scale), `exp` at most ≈ 22000 — comfortably below float64 overflow |

## Engineering-Protocol Deltas

### Protocol 1: LLM Wiki — pages to cite + pages to file

**Cite (already exist):**
- `[[strategy-thesis-lo-liquidity-rewards]]` — core thesis; Phase 2's purpose is to quantify the "don't get filled" input
- `[[EV cancel rule]]` — where `P(fill)` lands in the EV equation
- `[[architecture-overview-v05]]` — where FillModel sits in the brain
- `[[amm-conservation-assertion-data-05]]` — Phase 1 foundation for §4
- `[[eventIndex coverage]]` — Phase 2 `QueueTracker` depends on this invariant
- `[[sqlite-state-spine-v05]]` — new `fill_model_fits` table slots into this
- `[[pydantic-botconfig-schema-v05]]` — `FillModelConfig` follows this pattern
- `[[python-stack-v05]]` — amend to add statsmodels + reframe tick's role
- `[[live-e-liq-polling-data-11]]` — optional Phase 2 input (deferred to v0.5 simplification)
- `[[fill-loss-coarse-bound-v05]]` — NOT used by Phase 2 directly, but the decision engine uses this alongside `P(fill)` until Phase 3

**Must file (new — Phase 2 write-back obligation):**
- `[[Fill model library decision tick vs statsmodels]]` — why we changed critical-path library; Status: `Current — v0.5 regime`
- `[[Covariate selection v05]]` — 4/7 rationale; Status: `Current — v0.5 regime`
- `[[NHPP log-linear GLM fit procedure]]` — §Pattern 1 + §Code Examples, canonical fit recipe; Status: `Current`
- `[[Queue tracker algorithm v05]]` — §3 + §Pattern 2 + §Pattern 3; Status: `Current — v0.5 regime`
- `[[AMM consumption model v05]]` — §4 + conservation identity; Status: `Current — v0.5 regime`
- `[[Fill model goodness of fit — Rosenblatt time change]]` — §5 methodology + threshold bootstrap; Status: `Current`
- `[[Fill model predict contract]]` — §6 exact Python signature + failure modes; Status: `Current — v0.5 regime`
- `[[Rolling 14-day refit cadence + staleness]]` — §7 cadence + staleness knobs; Status: `Current — v0.5 regime`
- `[[Known issues — NaN covariate silent fallback — DO NOT]]` — new pitfall entry; Status: `Current`
- `[[Python stack v0.5]]` **update** — append statsmodels row to the Core table; amend tick row from "NHPP learner" to "NHPP simulator + v1.0 Hawkes staging"; Status remains `Current — v0.5 regime`

**Supersedence:** `[[python-stack-v05]]` needs amendment, not supersedence — the page stays correct about `tick`'s presence in the stack; it just needs to correct the role. No other existing page is contradicted.

### Protocol 2: Architecture.yml deltas

**New nodes (module type):**
- `brain.fill_model.features` — `python/src/boros_brain/fill_model/features.py` — `public_functions: [build_features_table, FeatureSet]` (FeatureSet is a class; functions: `build_features_table`)
- `brain.fill_model.queue_tracker` — `python/src/boros_brain/fill_model/queue_tracker.py` — `public_functions: [QueueTracker, compute_drift_diagnostic]` (QueueTracker is a class)
- `brain.fill_model.amm_consumption` — `python/src/boros_brain/fill_model/amm_consumption.py` — `public_functions: [compute_amm_share_timeseries, assert_epoch_conservation]`
- `brain.fill_model.fit` — `python/src/boros_brain/fill_model/fit.py` — `public_functions: [fit_market_side, FitArtifact]` (FitArtifact is Pydantic)
- `brain.fill_model.predict` — `python/src/boros_brain/fill_model/predict.py` — `public_functions: [predict, PredictInput, PredictOutput]`
- `brain.fill_model.calibration` — `python/src/boros_brain/fill_model/calibration.py` — `public_functions: [gof_rosenblatt, bootstrap_gof_threshold, run_calibration]`
- `brain.fill_model.cli` — `python/src/boros_brain/fill_model/cli.py` — `public_functions: [main]`
- `brain.fill_model.schemas` — `python/src/boros_brain/fill_model/schemas.py` — `public_functions: []` (Pydantic classes only)
- `brain.fill_model.constants` — `python/src/boros_brain/fill_model/constants.py` — `public_functions: []`
- `brain.state.writers.fill_model_fits` — `python/src/boros_brain/state/writers/fill_model_fits.py` — `public_functions: [insert_fit_artifact, get_latest_fit]`

**New storage nodes:**
- `state.fill_model_fits` — `state/state.sqlite#fill_model_fits` — new table
- `parquet.fill_features` — `data/parquet/fill_features/**/*.parquet` — Hive-partitioned (`market_id, side, window_end_ts`)
- `parquet.fill_predictions` — `data/parquet/fill_predictions/**/*.parquet` — backtest only; Hive-partitioned

**New config nodes (one per BotConfig.fill_model.* leaf):**
- `config.fill_model.window_days` default 14
- `config.fill_model.bin_duration_s` default 60.0
- `config.fill_model.refit_cadence_s` default 900.0
- `config.fill_model.covariate_whitelist` default `["basis_spread", "imbalance", "sin_settlement", "cos_settlement", "ewma_vol"]`
- `config.fill_model.queue_tracker_bias_mode` default `"pessimistic"`
- `config.fill_model.gof_ks_pval_threshold` default 0.0 (disabled until bootstrap-calibrated)
- `config.fill_model.gof_lr_ratio_threshold` default null
- `config.fill_model.fit_warn_staleness_s` default 1800.0
- `config.fill_model.fit_max_staleness_s` default 3600.0
- `config.fill_model.bracket_width_warn_multiplier` default 0.5
- `config.fill_model.min_events_per_param_ratio` default 10

**New edges (summary — exact `from/to/type` list is a plan-level output):**
- `brain.fill_model.features reads parquet.market_trades, parquet.order_book_combined, parquet.order_book_raw, parquet.underlying_apr, state.clo_history` via `brain.duckdb_layer.setup`
- `brain.fill_model.features writes parquet.fill_features`
- `brain.fill_model.queue_tracker reads parquet.market_trades, parquet.order_book_raw, parquet.order_book_combined`
- `brain.fill_model.amm_consumption reads parquet.order_book_raw, parquet.order_book_combined` and `calls brain.data.ingester.exceptions.AMMConservationError` for the runtime conservation identity
- `brain.fill_model.fit reads parquet.fill_features` and `calls brain.state.writers.fill_model_fits`
- `brain.state.writers.fill_model_fits writes state.fill_model_fits`
- `brain.fill_model.predict reads state.fill_model_fits` via `brain.duckdb_layer.setup` (read-only SQLite attach)
- `brain.fill_model.predict calls brain.data.chain_time` for `now_cached()` in `fit_age_s`
- `brain.fill_model.calibration reads parquet.market_trades, state.fill_model_fits` and `writes parquet.fill_predictions`
- `brain.fill_model.cli calls brain.manifest.writer` (MANIFEST-FIRST invariant)
- `brain.main calls brain.fill_model.fit` at startup + scheduled refit loop
- `depends-on-config` edges from each consumer to its respective `config.fill_model.*` knob

**Lint extension:** `scripts/no_time_time_lint.py` currently bans `time.time()` in `brain/{decision,data,screener}/`. Extend to add `brain/fill_model/` to the banned list in the same plan that lands the module tree (one-line patch).

### Protocol 3: RUN_MANIFEST additions

Every knob listed in §8 appears in the manifest via `BotConfig.model_dump(mode='json')` reflection. **No hand-written manifest schema changes** — this is the whole point of the reflection-based writer from Plan 01-03. The regression guard test `test_manifest_contains_all_knobs` (already in `python/tests/`) automatically catches any knob added to `FillModelConfig` that isn't surfaced.

**No new top-level manifest fields needed.** The manifest already carries `run_id`, `strategy_version`, `market_id`, `side`. Phase 2 is a consumer of manifest context, not an emitter of new top-level fields. (Phase 6, however, adds `chain_time_drift_at_start_seconds` and `agent_wallet_gas_balance_at_start` — see ROADMAP §Phase 6.)

## Out-of-scope / deferred

### Confirmed deferred to v1.0 (OUT OF SCOPE for Phase 2)
- Per-market CV-dispersion-driven model selection (V2-FILL-01/V2-FILL-02/V2-FILL-03/V2-FILL-04). v0.5 = NHPP for all markets that pass Phase 1 screening.
- Hawkes self-excitation overlay on top of NHPP baseline. `tick`'s `HawkesExpKern` will be used when v1.0 lands.
- HMM confirmation overlay on the same covariates.
- Per-market regime-aware hyperparameter sweep on covariate set.

### Surfaced as necessary-but-deferred

1. **Historical `E_liq_per_epoch` reconstruction** — Phase 1 A6 spike concluded `[[historical-reward-budget-reconstruction-infeasible|Infeasible]]` for pre-pipeline data. Phase 2 fit does NOT use reward-budget as a covariate (this was not in the 7-covariate list anyway), so this is not a blocker. But if Phase 5 backtest cross-correlates fill rate with historical reward-budget shifts and finds regime changes, v1.0 should add the budget-history covariate.

2. **Per-side asymmetry in covariate coefficients** — Currently planned as two independent fits per (market_id, side). If the two fits produce wildly different β magnitudes, a **shared-β with side-interaction** model may be more data-efficient. Defer to v1.0; v0.5 simpler two-fit approach is fine.

3. **Outside-range wall covariate (PITFALLS §A8)** — `outside_range_wall_flag` is computed by Phase 1 screener (SCALE calibration). Not currently in the 4-covariate Phase 2 set because its predictive value on *fill probability specifically* is unproven. If v0.5 calibration plot shows systematic bias at CLO-edge ticks, v1.0 adds it as a 5th covariate.

4. **`eventIndex` missing-market fallback** — `[[eventIndex coverage]]` status is `Current — PARTIAL`. If the Phase-1 confirmed shortlist market has `eventIndex`, Phase 2 proceeds. If the market added to the shortlist in a future re-screen (DATA-10) lacks `eventIndex`, Phase 2 operates in degraded mode: queue tracker collapses to `blockTimestamp` ties, documented in wiki + manifest-flagged. Not a v0.5 blocker unless it happens on the confirmed market.

## Pitfalls specific to Phase 2 (summary, see §Common Pitfalls for detail)

From PITFALLS.md:
- **B1 (Queue drift direction):** §3 — signed drift logging + P/O bracket
- **B3 (AMM double-count):** §4 — runtime conservation identity in addition to Phase 1 ingest-time assertion
- **B4 (Fit health):** §Common Pitfalls #3 — convergence + event/param ratio + stderr inflation gate
- **B5 (OU regime shift):** N/A — Phase 2 does not touch OU (that's Phase 3). But the same scaffolding — GoF + rolling refit — applies.

New pitfalls (this research):
- **NaN-covariate silent-exp(β₀)** — §Common Pitfalls #6 — MUST raise, never substitute
- **Look-ahead EWMA windowing** — §Common Pitfalls #5 — strict left-closed windows
- **Covariate co-linearity (`dRate/dt` vs. `ewma_vol`)** — §Common Pitfalls #4 — VIF check in fit diagnostics
- **In-memory fit lost on restart** — §Common Pitfalls #7 — fit persisted to SQLite
- **Intuition-set GoF threshold** — §Common Pitfalls #8 — bootstrap-calibrated

## Environment Availability

Phase 2 is pure code + Python deps. No OS-level or external-service dependencies.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | brain | ✓ | 3.12.x | — |
| `uv` | package mgmt | ✓ | 0.9.24 `[VERIFIED: uv --version 2026-04-24]` | — |
| statsmodels | critical-path fit | ✗ (not yet installed) | install >=0.14.6 | scipy-hand-rolled L-BFGS-B (50 LoC) |
| tick 0.8.0.1 | simulation + v1.0 staging | ✗ (not yet installed) | install 0.8.0.1 | tick 0.7.x (no covariate-baseline change) |
| DuckDB | already pinned | ✓ | 1.5.0 | — |
| polars | already pinned | ✓ | 1.40.1 | — |

**Missing dependencies with fallback:** statsmodels → scipy hand-roll (not preferred but possible). tick → tick 0.7.x.
**Missing dependencies with no fallback:** none — Phase 2 is fully constructible from the current + two proposed additions.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `tick` as NHPP-with-covariates learner | `statsmodels.GLM(Poisson, log)` | This research, 2026-04-24 | No code change needed (no fill-model code yet); ROADMAP wording correction; STACK.md role-change for tick |
| "Conservative queue drift" assumption | Signed drift diagnostic + P/O bracket | PITFALLS §B1, absorbed into §3 | Replaces a silent assumption with a measured quantity |
| Raw-only book for queue tracking | Raw-only book with AMM share subtracted from taker flow | ROADMAP Phase 2 scope; implemented via §4 | Prevents "AMM ate the taker" / "AMM got credit for taker" mis-attributions |
| Point-estimate `P(fill)` for decision engine | Pessimistic bound for decision engine (conservative cancel) | §3 + §Common Pitfalls #1 | Mitigates B1 |
| Hand-tuned GoF threshold | Bootstrap-calibrated threshold | §Common Pitfalls #8 | Mitigates false-degraded alerts on healthy markets |

**Deprecated/outdated (for this project's scope):**
- `tick` as NHPP-with-covariates learner: the ROADMAP + STACK.md assumption is now outdated. This research corrects it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | statsmodels.GLM(Poisson, log, exposure) converges in <60s on 20k-bin × 5-covariate data | §Standard Stack | Fit takes longer at startup — not a blocker; refit loop absorbs it. |
| A2 | The confirmed Phase-1 shortlist market will have ≥ 5000 trades in 14-day windows | §Common Pitfalls #3 | If <5000 trades, B4 fit-degraded fires at the first fit; fallback to intercept-only GLM still produces a (worse) probability. v0.5 remains shippable. |
| A3 | `eventIndex` is universally present on the confirmed shortlist market's market-trades NDJSON | §3 | If absent, queue tracker collapses to blockTimestamp ties and reports `eventIndex_coverage: degraded` in fit artifact. Downstream still functions, just with wider brackets. [[eventIndex coverage]] status tracks this. |
| A4 | `order_book_combined` snapshots are close enough in time to `order_book_raw` (same hour, same synchronization) that linear interpolation of AMM share between them is accurate to ~5% | §4 | If not, per-epoch conservation identity fires and flags the affected hour. Fit continues with the hour sample-weighted down, not excluded. |
| A5 | Phase 2 refit cadence of 15 min is sufficient for regime-change responsiveness at v0.5 single-market scale | §8 | If regime shifts happen faster, DecisionEngine's circuit breakers (Phase 4) should fire first; refit-cadence tuning is a Phase 5 backtest output, not a v0.5 kill concern. |
| A6 | Phase 4 DecisionEngine can consume sync `predict()` at 1 Hz per in-flight order without degrading the 1-Hz loop cadence | §6 | Plan constraint; if `predict` p95 > 100ms, Phase 4 absorbs the sync penalty or we move to async with a shared results cache. Latency budget has 900ms of headroom per cycle. |
| A7 | `FillModelConfig` knobs all surface in RUN_MANIFEST via existing reflection writer (Plan 01-03) | §8 | Regression test `test_manifest_contains_all_knobs` already exists; mechanically enforced. |

**All other claims are `[VERIFIED: …]` or `[CITED: …]` inline.**

## Open Questions

1. **Bin duration — 60s vs 30s vs 120s**
   - What we know: 60s is a typical NHPP bin; fit takes ~20k bins on 14 days; statsmodels handles 20k rows trivially.
   - What's unclear: whether 60s averages away genuine intensity structure (e.g. rapid clustering within 60s).
   - Recommendation: Plan 02-01 starts with 60s. First-fit diagnostic includes AIC for 30s / 60s / 120s on the same window; if a different bin width is materially better, operator updates the knob. Track as a v0.5 kill-gate-or-tune output in the first fit's SUMMARY.

2. **Covariate scaling — standardize on rolling-window stats vs. hard-coded scale**
   - What we know: GLM converges faster on standardized covariates; coefficient interpretability is also better.
   - What's unclear: whether scaling should use the full-14-day window's mean/std (trivial) or a narrower window (avoids stat leakage across regimes).
   - Recommendation: Standardize using the **same 14-day fit window's** mean/std. At predict time, the PredictInput's `current_features` are standardized using the fit-window stats (stored in the fit artifact). Not a regime leak — the standardization is parameter-shrinkage only, not information flow.

3. **Cross-market β pooling for thin markets**
   - What we know: If the confirmed shortlist has one thin market, fit may degrade.
   - What's unclear: whether v0.5 can borrow β from a sister market (same underlying, different maturity) via weighted fit.
   - Recommendation: Defer to v1.0. v0.5 single-market doesn't need this. Log a "thin-market caveat" in the fit artifact if n_observations/params < 10 so the operator knows.

4. **Epoch-boundary handling in `time_to_epoch_end_s`**
   - What we know: Epoch = weekly (Fri 00:00 UTC → Thu 23:59 UTC). `P(fill_this_epoch)` integrates λ from now to epoch end.
   - What's unclear: how to handle the last ~minute of the epoch when `time_to_epoch_end_s → 0` (probability should → 0 for sane integration, but rounding / clock drift could produce negative values).
   - Recommendation: Clip `time_to_epoch_end_s` to `[0, 7×86400]`. If ≤ 0, return `p_fill_this_epoch = 0.0` with `fit_status = "ok"` (it's a correct prediction). Flag in the DecisionEngine's epoch-rollover logic (Phase 4) to avoid placing orders within ~5 min of epoch close — separate concern from this model.

5. **Calibration-tolerance numeric value (FILL-05 success criterion)**
   - What we know: The ROADMAP says "matches realized fill frequency within the calibration-test tolerance on backtest hold-out data."
   - What's unclear: the tolerance number. Standard calibration-plot convention is ±5pp absolute per decile bin of predicted probability.
   - Recommendation: Lock to ±5pp absolute across each decile of predicted `p_fill_this_epoch` on the hold-out. Document this in `[[Fill model goodness of fit — Rosenblatt time change]]`. Phase 5 backtest can sharpen the tolerance if data supports it.

## Planner Hand-Off

Decisions the planner must make (recommendation included for each):

1. **Library change — tick → statsmodels for the critical-path fit.** (§1, §Standard Stack)
   - **Recommendation: Adopt.** FILL-01's spirit (log-linear NHPP per market-side) is preserved; FILL-01's letter (fit via tick) is amended. This is the single most important decision in the phase; everything else follows from it. Call it out in the first plan SUMMARY so ROADMAP/STACK.md can get the amendment notes (wiki page `[[Fill model library decision tick vs statsmodels]]`).

2. **Covariate selection — 4/7.** (§2, §FILL-02)
   - **Recommendation:** `basis_spread` + `imbalance` + `sin_settlement, cos_settlement` (counts as one covariate pair, but 2 model features) + `ewma_vol`. Drop: CEX spot move, time-to-maturity, `dRate/dt`.
   - **Rationale:** basis spread is the natural state-of-book primitive (the strategy IS a basis-farming bet); imbalance is orthogonal and cheap; sin/cos settlement captures the 8h funding cycle without a time-to-maturity confound; EWMA vol captures volatility regime. `dRate/dt` is co-linear with EWMA vol. CEX spot move introduces external-feed risk (A7) without predictive uplift on fill *probability*. Time-to-maturity doesn't vary within a 14-day fit window.

3. **Fit cadence — 15 min default.** (§8)
   - **Recommendation: 15 min.** 4× refit per hour is aggressive enough to catch regime shifts within one epoch; cheap enough at ~15-30 seconds of CPU per refit. Operator can tune via `BotConfig.fill_model.refit_cadence_s`.

4. **Queue tracker default consumer — pessimistic bound.** (§3)
   - **Recommendation: `queue_tracker_bias_mode = "pessimistic"` default.** The strategy is fill-avoidance; the decision engine wants the conservative queue estimate (higher predicted queue, lower P(fill), more willing to hold). Optimistic mode reserved for research / sensitivity sweeps.

5. **GoF metric — KS on Rosenblatt-transformed inter-arrivals + LR vs null.** (§5)
   - **Recommendation:** Both. KS p-value is the headline number; LR is the secondary. Threshold bootstrap-calibrated from first fit (5th-percentile in-sample); do not hard-code.

6. **New BotConfig.fill_model sub-model.** (§8)
   - **Recommendation:** 11 knobs exactly as listed in §8. Each with default + range + Field docstring. Each adds a node to `architecture.yml` in the same plan.

7. **Fit-artifact storage — SQLite table + parquet sidecar.** (§7)
   - **Recommendation:** SQLite for quick-lookup (`get_latest_fit(market_id, side) → FitArtifact`); parquet sidecar for the full covariate-coefficient-with-CI dump. Single writer `state/writers/fill_model_fits.py` (Phase 1 pattern).

8. **Staleness contract — two thresholds.** (§6, §8)
   - **Recommendation:** `fit_warn_staleness_s = 1800` (30 min) → log warn; `fit_max_staleness_s = 3600` (60 min) → raise `FillModelNoFreshFitError`. Decision engine treats the raise as "cannot place new orders, but existing orders' cancel logic uses the stale fit with a warning" — not a kill.

9. **Test-file wave-0 gaps — 6 new test files + 3 fixtures.** (§Validation Architecture)
   - **Recommendation:** Plan 02-01 lands the `fill_model/` module tree + all 6 test files as stubs (wave_0_scaffold markers) + the 3 fixture files. Subsequent plans implement against those stubs.

10. **Phase 2 plan decomposition — how many sub-plans?** (meta)
    - **Recommendation:** 4 plans.
      - **02-01 (Feature pipeline + FillModelConfig + directory scaffold):** `features.py`, `FillModelConfig` in BotConfig, test stubs, fixtures. One wave.
      - **02-02 (Queue tracker + AMM consumption, parallel plan):** `queue_tracker.py`, `amm_consumption.py`, their tests. Depends on 02-01's fixtures.
      - **02-03 (Fit + predict):** `fit.py`, `predict.py`, `schemas.py`, `state/writers/fill_model_fits.py`. Depends on 02-01 + 02-02.
      - **02-04 (Calibration + CLI + refit loop wiring into brain.main):** `calibration.py`, `cli.py`, refit-loop integration in `main.py`. Depends on 02-03.

11. **`tick` installation risk on macOS arm64.** (§Standard Stack)
    - **Recommendation:** In 02-01, `uv add tick==0.8.0.1` with a conditional fallback note. If the wheel build fails, fall back to `tick==0.7.x` and document in [[python-stack-v05]] amendment. **Note:** tick is not on the critical path (Simulator only), so a fallback does not block Phase 2.

12. **`FILL-01` language reconciliation in REQUIREMENTS.md.** (§Phase Requirements)
    - **Recommendation:** Update FILL-01 wording from "using `tick` 0.8.0.1" to "using `statsmodels.GLM(Poisson, log)` for the covariate-driven baseline fit; `tick` retained for simulation + v1.0 Hawkes overlay." This is a doc-only commit; it does not change the spirit of FILL-01 (NHPP per market-side with log-linear intensity).

## Sources

### Primary (HIGH confidence)
- [statsmodels GLM Poisson with log-link and exposure](https://www.statsmodels.org/stable/glm.html) — confirmed the canonical binned-NHPP fitting primitive
- [tick library docs — hawkes module](https://x-datainitiative.github.io/tick/modules/hawkes.html) — confirmed `SimuInhomogeneousPoisson` is a simulator, HawkesExpKern / HawkesSumExpKern / HawkesEM are Hawkes learners, **no covariate-driven NHPP learner**
- [tick GitHub doc/modules/hawkes.rst](https://github.com/X-DataInitiative/tick/blob/master/doc/modules/hawkes.rst) — cross-verification of learner inventory
- [PyPI: tick 0.8.0.1](https://pypi.org/project/tick/) — release date 2026-04-20, Python 3.11–3.13 wheels
- `/Users/macbookair/boros/.planning/research/PITFALLS.md §B1, §B3, §B4, §B5, §B6` — canonical pitfall specifications absorbed into this research
- `/Users/macbookair/boros/.planning/research/STACK.md §Hawkes/arrival-process library, §Python Side` — prior stack analysis, with correction on tick's scope in this research
- `/Users/macbookair/boros/boros_consolidated_plan.md L143-170, L387` — canonical 7-covariate list + per-market model class by CV dispersion (v1.0)
- `/Users/macbookair/boros/docs/architecture.yml` — Phase 1 node/edge inventory Phase 2 extends
- `/Users/macbookair/boros/python/src/boros_brain/config/schema.py` — BotConfig pattern FillModelConfig follows
- `[[amm-conservation-assertion-data-05]]` — Phase 1 ingest-time foundation for §4
- `[[strategy-thesis-lo-liquidity-rewards]]` + `[[EV cancel rule]]` — strategy constraints

### Secondary (MEDIUM confidence)
- [Poisson regression and rates (Freakonometrics on exposure)](https://freakonometrics.hypotheses.org/8028) — confirmed exposure as the standard offset pattern for rate models
- Daley & Vere-Jones, *An Introduction to the Theory of Point Processes* — time-change theorem for point-process GoF (citation, not fetched URL)
- `/Users/macbookair/boros/boros_bot_guide.md L206` — f_index decoding details (consumed by Phase 1)

### Tertiary (LOW confidence — verification deferred)
- macOS arm64 wheel availability for `tick 0.8.0.1` — assumed based on general wheel publication; first fact-check is the `uv add tick==0.8.0.1` step.

## Metadata

**Confidence breakdown:**
- Standard stack: **MEDIUM-HIGH** — `statsmodels.GLM(Poisson, log)` is textbook; `tick` role reframing is well-documented but a course-correction to prior research.
- Architecture: **HIGH** — mirrors Phase 1 patterns; no novel IPC or process structure.
- Queue-tracker + AMM: **HIGH** — algorithms well-specified; PITFALLS B1/B3 already absorbed.
- GoF methodology: **HIGH** — time-change theorem is standard; bootstrap-calibrated thresholds are a project-specific design choice with clear rationale.
- Covariate selection: **MEDIUM** — defensible choice, but could change after Phase 5 backtest on real data.

**Research date:** 2026-04-24
**Valid until:** 2026-05-24 (stable libraries; primary risk is tick package updates — revisit if `tick >=0.9` ships with a covariate-aware NHPP learner, which would reverse the §1 recommendation).
