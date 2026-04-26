# Boros Reward Farming — Alternative Execution Plan

This is a replacement for `boros_model_recommendation.md`. The previous plan modeled the wrong process, used the wrong outcome variable, ignored the dominant economic driver (competing capital), and proposed a backtest that systematically overstates P&L. This plan reframes around the actual decision being made and the actual mechanics of how fills happen on a CLOB+AMM venue.

---

## 1. Reframe the Problem

The bot is not a rate forecaster. It is an **inventory-avoiding maker** competing for a shared, time-weighted reward stream. Three coupled questions, in order of importance:

1. **Reward share** — how much of the emission flow is mine, given my notional and competing notional in the range?
2. **Fill economics** — for a given posting, what is the expected reward inflow vs. expected loss inflow?
3. **Execution viability** — can I cancel fast enough that my decisions actually take effect before fills land?

Question 3 is a hard constraint (latency budget). Question 1 sets the prize. Question 2 is the only thing a model can usefully optimize. The previous plan only addressed question 2, modeled it wrong, and treated 1 and 3 as out of scope. Both belong in scope.

The single decision the bot makes each tick is:

> **Hold or cancel each side, given expected reward rate, expected loss conditional on fill, and the latency budget I have to react.**

Everything below serves that decision rule.

---

## 2. The Actual Stochastic Object: Taker Arrivals, Not Rate Diffusion

Implied APR on Boros moves only when a trade prints. Between trades, the price is unchanged regardless of how much underlying funding has drifted. A diffusion model attached to that series fits Gaussian noise to a step function and produces a σ that has no mechanical interpretation.

The right primitive is the **arrival of taker volume at each depth from mid**:

```
Λ_buy(δ, t)  = arrival intensity of taker buys at depth δ ticks above mid at time t
Λ_sell(δ, t) = arrival intensity of taker sells at depth δ ticks below mid at time t
```

For a resting order at depth δ on side s with size q and queue position k:

```
P(fill within ΔT) = P(cumulative arrivals at depth ≥ δ on opposite side fill the queue past k+q within ΔT)
```

That decomposes cleanly:

- **Arrival model**: Hawkes (or marked Poisson with covariates) on taker arrivals, fit per market.
- **Depth model**: empirical CDF of taker print depth, conditional on regime features.
- **Queue model**: track your queue position from order book snapshots and your own order events.
- **AMM offset**: the AMM consumes a known share of incoming flow at posted depths — subtract its share before crediting flow to the book.

This is not optional. A fill model that ignores queue position and AMM competition will systematically overpredict fills in calm regimes (where you're deep in queue and protected) and underpredict in volatile regimes (where takers print past your level multi-tick).

### Hawkes intensity, concretely

```
λ(t) = μ_s(t) + Σ_{t_i < t} α · exp(-β(t - t_i))
```

- `μ_s(t)` — baseline intensity, function of observable covariates (time-since-funding-settlement, basis spread, realized vol over last 5 min, order book imbalance).
- `α, β` — self-excitation parameters (one taker often triggers a cluster).
- Fit per side per market by MLE on the trade tape from Boros NDJSON.

Why Hawkes specifically: trade arrivals on crypto venues are demonstrably clustered. Poisson misses the clustering and underestimates short-horizon fill probability — which is exactly the horizon the cancel decision operates on.

### Skip Hawkes if you must

If the implementation cost of Hawkes is too high for v1, fall back to **non-homogeneous Poisson** with covariate-driven intensity. Drop to Hawkes once the Poisson version is in production and the underprediction during clusters is observable in P&L.

---

## 3. Term Structure: The Bridge to Maturity

Implied APR is anchored at maturity to the realized funding accumulation over the pool's life. As `t → T_maturity`, the variance of remaining accumulation collapses, and implied APR is dragged toward realized. This is a **Brownian bridge structure**, not a stationary OU.

Practical model: instead of modeling implied APR directly, model the **basis to spot underlying funding**:

```
B(t) = Implied_APR(t) − Underlying_Funding_APR(t)
```

The basis is approximately stationary (it's a forward-looking error vs. spot), bounded by arbitrage, and behaves much closer to the assumptions a mean-reverting model wants. Fit OU or AR(1) on the basis if you want a continuous summary statistic — but use it only as a **covariate feeding the Hawkes baseline intensity**, not as the fill probability calculation itself.

The previous plan's "estimate μ on a 7-day rolling window" is structurally broken: μ for implied APR isn't constant over the pool's life, it drifts deterministically toward realized accumulation. The basis avoids this trap.

---

## 4. Reward Economics: The Layer That Was Missing

Rewards are pro-rata over notional in the incentivized range. Your per-epoch reward inflow is:

```
R_me = E_market_per_epoch × (Q_me / Q_total_in_range)
```

`Q_total_in_range` is observable — read it from `GET /v2/accounts/all-limit-orders` aggregated over the range, or from order book depth in the CLO range. This is the variable the previous plan ignored entirely, and it dominates the strategy's actual P&L:

- A 2× increase in competing notional halves your reward inflow.
- The break-even fill loss your strategy can absorb is proportional to `R_me`, which collapses with competition.

### The required reward-share model

1. **Snapshot competing notional** in the CLO range every poll cycle.
2. **Estimate emission rate** in collateral-equivalent terms (requires the open question `What token + emission rate?` to be answered first — flag as a hard prerequisite before going live).
3. **Compute `R_me` per epoch** as a forward estimate.
4. **Size your own notional** to maintain a target reward share, capped by max-orders-per-account constraint and your own collateral floor.

### Capital-sizing rule

```
Q_me_target = max(Q_min,
                 min(Q_max,
                     target_share × Q_total_in_range / (1 - target_share)))
```

Pick `target_share` such that `R_me − E[loss flow]` is positive across plausible parameter ranges. Sweeping `target_share` in backtest is more important than sweeping the OU parameters in the previous plan.

---

## 5. The Cancel Decision: Expected Value, Not Arbitrary Threshold

Replace the 5%/15% threshold dials with an explicit expected-value comparison.

For each side per epoch:

```
EV_hold = R_share_per_epoch × P(no_fill_this_epoch)
        − E[loss | fill] × P(fill_this_epoch)
        − cancel_repost_cost × P(purge_this_epoch)

Cancel iff EV_hold < EV_idle
where EV_idle = -opportunity_cost_of_capital_per_epoch
```

You need three inputs:

1. **`P(fill this epoch)`** — from the Hawkes + queue + AMM model in §2.
2. **`E[loss | fill]`** — IRS P&L distribution conditional on entry at your tick. Compute as:
   ```
   E[loss | fill at tick X] = E[ ∫_t^T (Realized_Funding(u) - X) du | fill at t ]
   ```
   Estimate by replaying historical post-fill rate paths from the NDJSON, sliced by tick distance from mark at fill time. This is the missing piece in the previous plan — fill probability without conditional loss magnitude is a dimensionless number that can't be compared to anything.
3. **`P(purge this epoch)`** — from a separate, simple AR model on `mark APR drift`. Purges are mechanical and easy to predict from the bound formula in the guide.

Threshold dials disappear. The only tunable is `target_share` (capital sizing) and the cost weights, both of which have economic interpretations.

---

## 6. Regime Information Without an HMM

The previous plan invokes an HMM to discover latent regimes. Most of what an HMM would discover is observable directly. Replace the HMM with explicit features fed into the Hawkes baseline intensity:

| Feature | Why it's predictive |
|---|---|
| Time since last underlying funding settlement (mod 8h) | Settlement triggers arb flow; intensity spikes ±15 min around the boundary |
| Basis spread `B(t)` (Implied − Underlying) | Wide basis pulls counterparties; Hawkes baseline scales with `|B|` |
| Order book imbalance (depth bid − depth ask, normalized) | One-sided book → next print direction is predictable |
| Realized vol over last 5 min (EWMA on rate changes) | Direct vol input — captures what the HMM would have called "Volatile" |
| Underlying CEX spot move over last 5 min | Funding rate drivers leak through |
| Time to maturity | Variance of remaining accumulation collapses near expiry |
| `dRate/dt` of mark APR | Direct tracking of approach to your level |

These are all observable, all interpretable, and don't require fitting a transition matrix on 270 observations. If after this is in production a residual signal in fill timing remains unexplained, *then* consider a latent-state model.

---

## 7. Backtest That Doesn't Lie

The previous plan's backtest checks "did implied APR touch the CLO edge?" That's an indicator function on a price series. It systematically misrepresents fill outcomes. Replace with an **event-driven replay**:

### Inputs
- Boros NDJSON: every order book snapshot + every trade event with size, side, price.
- Underlying funding rate history per relevant CEX.

### Per-epoch simulation
1. **Place synthetic order** at chosen tick at epoch start. Record queue position from the snapshot (number of resting size ahead of you on your tick).
2. **Replay every taker print** in the epoch in order. For each print on the opposing side that crosses your level:
   - Subtract AMM consumption (estimate from AMM curve at that snapshot).
   - Decrement remaining queue ahead of you.
   - Once queue ≤ 0, you fill. Record entry tick, time, remaining queue size used.
3. **Apply realistic cancel latency** to the decision rule: when the bot would have cancelled (per its decision logic running on snapshots up to time `t`), the cancel doesn't take effect until `t + L`. Set `L` from measured RTT to Arbitrum sequencer + bot loop period (be conservative: 2–5 seconds).
4. **Repost on purge** with the same latency.
5. **Track reward accumulation** per epoch only for time-in-range without-purge.

### Outputs
- Realized fill count, fill PnL distribution, time-in-range fraction, gas count.
- **Counterfactual delta**: realized P&L vs. P&L if cancel latency were 0 (tells you how much value latency costs you — informs whether to invest in colocation).

### What to measure (replacing Brier targets)

| Metric | What it answers |
|---|---|
| Net P&L per unit collateral, annualized | The only number that matters |
| Sharpe-equivalent (mean / std of epoch P&L) | Strategy stability |
| Max drawdown | Tail fill events |
| `P(fill)` calibration plot | Is the Hawkes model usefully calibrated? Plot predicted vs. realized in 10 buckets |
| Cancel-latency sensitivity | dP&L / dL — should be modest; if huge, ship colocation |
| Competition sensitivity | dP&L / dQ_competing — tells you when to scale down |

Brier and AUC are diagnostic, not target. Net P&L at acceptable drawdown is the target.

### What backtest cannot test

- Adverse selection from new entrants who weren't in the historical tape.
- Reward emission changes by governance.
- Behavior of the AMM after parameter updates.

These get caught in paper trading, not backtest. Don't pretend the backtest covers them.

---

## 8. Execution Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      MARKET STATE LOOP (1–5s)                    │
│  • REST: /markets, /markets/order-books, /v2/all-limit-orders    │
│  • WS:   trades, order book diffs, account events                │
│  • RPC:  fIndexOracle.latestAnnualizedRate, getLatestFIndex      │
│  • Maintain rolling features: basis, imbalance, EWMA vol, t-mod-8h│
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│                     FILL MODEL (Hawkes + Queue)                  │
│  • λ(t) per side per depth from current features                 │
│  • Queue position from your order events + book snapshots        │
│  • AMM consumption estimate from current AMM curve               │
│  • Output: P(fill in next epoch) per side                        │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│                   LOSS MODEL (Conditional IRS PnL)               │
│  • E[loss | fill at tick X, time t, t-to-mat τ]                  │
│  • Empirical from historical post-fill paths, sliced by τ        │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│                   REWARD MODEL (Share Estimator)                 │
│  • Q_total_in_range from book aggregation                        │
│  • Q_me_target sizing rule                                       │
│  • R_me per epoch forward estimate                               │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│                     EV DECISION ENGINE                           │
│  • EV_hold per side, compare to EV_idle                          │
│  • Action: PLACE / HOLD / CANCEL / RESIZE                        │
│  • Predictive circuit breakers (see §9)                          │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────┐
│                   EXECUTION (Send Txs Bot)                       │
│  • Pre-sign cancel calldata for every open order on placement    │
│  • Latency-bounded: if decision-to-confirm exceeds budget, alert │
└──────────────────────────────────────────────────────────────────┘
```

### Latency budget — non-negotiable

Every order placement must include a **pre-signed cancel** held in memory, ready to submit instantly. Do not generate cancel calldata at decision time; that adds 100s of ms of HTTP roundtrip when you're trying to beat a sweeping taker. This single optimization is worth more than any model improvement.

### Fill response — speed beats cleverness

On WebSocket fill notification: submit a market close with the **maximum tolerated taker slippage** before recomputing anything. The taker fee + slippage is the cost of insurance. Holding a fill for "one more epoch in case it reverts" is a different strategy with a different model and is out of scope.

---

## 9. Predictive Circuit Breakers

Replace reactive thresholds with predictive triggers based on rate-of-change:

| Trigger | Rule | Action |
|---|---|---|
| Margin trajectory | Linear extrapolation: at current dNetBalance/dt, time to maintenance < 30s | Emergency close all |
| Oracle staleness | `now − fTime > 0.7 × maxUpdateDelay` | Cancel all (don't wait for full breach) |
| CLO range removed | `cloLower == 0 OR cloUpper == 0` since last poll | Cancel all, alert |
| Range shifted by > N ticks | `|new_clo − old_clo| > N` | Cancel, recalibrate, repost |
| Fill rate exceeds budget | More than K fills in last hour | Pause, alert, manual review |
| Competition collapse | `Q_total_in_range` dropped > 50% in 1 epoch | Investigate before resizing — may indicate they know something you don't |
| Maturity migration | `time_to_maturity × R_me_per_epoch < migration_cost` | Roll to next maturity |

The maturity migration trigger is value-based, not the previous plan's arbitrary 14-day threshold.

---

## 10. Calibration Loop

### Parameter estimation

- **Hawkes** — MLE per market on rolling 14-day window. Re-fit daily off-hours.
- **Conditional loss** — non-parametric kernel estimate from historical post-fill paths, refreshed weekly.
- **Reward share** — recomputed every poll cycle from live order book.

### Bias correction

The previous plan's OLS estimator for OU is severely biased on small samples. For Hawkes MLE the same caution applies. Either:
- Use **Bayesian estimation** with informative priors anchored to longer (cross-market pooled) history, or
- Apply **bootstrap bias correction** (Yu 2012-style) to MLE point estimates.

Report parameter uncertainty alongside the point estimate. Propagate it into the EV calculation as a confidence interval on `P(fill)`. If the CI on `P(fill)` is wide enough to flip the cancel decision, default to cancelling — uncertainty itself is a signal.

### Monitoring drift

Plot weekly:
- Hawkes residuals (transformed inter-arrival times should be unit-rate exponential under correct fit; KS test against that is the diagnostic).
- Calibration plot of predicted vs. realized fill probability.
- Strategy P&L vs. backtest counterfactual (paper-vs-backtest divergence is the early warning that the model is decaying).

---

## 11. Implementation Phases

### Phase 0 — Prerequisites (block until answered)

These are the open questions from the guide. Until answered, no live capital. Period.

- Reward token, emission rate per market per epoch.
- Pro-rata mechanics: by size, by time, by both, with caps?
- Minimum order size and posting duration to qualify.
- Merkle root cadence and gas cost to claim.
- SCALE / S calibration for every market the bot will touch.

### Phase 1 — Data infrastructure (1 week)

- Pull all available Boros NDJSON.
- Build event-driven replay engine: order book snapshots + trade tape, queue-tracking.
- Pull underlying funding rate histories (Binance, OKX, Hyperliquid).
- Verify SCALE/S calibration against website-displayed APR for ≥3 markets.

### Phase 2 — Reward share model first (3 days)

Smallest, highest-leverage piece. Build the competing-notional snapshotter. Before any fill modeling, you should know what the reward APR on your collateral *would* be at various target shares right now, in real time. This determines whether the strategy is worth running at all.

### Phase 3 — Fill model v1 (1 week)

- Non-homogeneous Poisson on taker arrivals at depth, conditional on §6 features.
- Queue-tracking integrated with the replay engine.
- Calibration plot on hold-out data.

### Phase 4 — Conditional loss model (3 days)

- Empirical post-fill PnL distribution by tick distance and time-to-maturity.
- Validates against backtest on historical fills.

### Phase 5 — Decision engine + circuit breakers (3 days)

- EV rule wired up.
- Predictive triggers from §9.
- All thresholds derived, none invented.

### Phase 6 — Backtest (1 week)

- Walk-forward on 70/30 split per market.
- Parameter sensitivity on `target_share`, cancel latency `L`, Hawkes window length.
- Decision: ship or kill, based on net P&L distribution.

### Phase 7 — Hawkes upgrade (1 week, optional)

Drop in Hawkes intensity in place of Poisson. Re-run backtest. Ship only if P&L improvement justifies operational complexity.

### Phase 8 — Paper trading (2 weeks minimum)

- Live data, no capital. Log every decision and every counterfactual outcome.
- Verify backtest parity. Divergence > 1σ → debug before proceeding.

### Phase 9 — Live with floor capital (2 weeks)

- Smallest viable order on one market.
- Compare live P&L to paper. Match → scale. Diverge → stop.

### Phase 10 — Scale on confirmed markets only

- Each new market requires its own SCALE/S calibration and its own Hawkes fit.
- Do not assume cross-market parameter transfer.

---

## 12. What to Build vs. What to Buy

| Component | Build | Notes |
|---|---|---|
| NDJSON ingest, replay engine | Build | Custom queue-tracking is the differentiator |
| Hawkes fitter | Build (or use `tick` lib in Python) | MLE is straightforward, but the feature engineering is custom |
| HMM | Skip | Not needed |
| Web3 RPC client | Use `web3.py` | Standard |
| Pendle SDK | Use `@pendle/sdk-boros` | Mandatory for calldata generation |
| Order management state machine | Build | Critical path, can't outsource |
| Monitoring + alerting | Use Grafana + Prometheus | Don't reinvent |

---

## 13. Comparison Summary

| Question | Previous Plan | This Plan |
|---|---|---|
| What is being modeled? | Implied APR diffusion | Taker arrivals at depth, queue position, conditional loss, reward share |
| What predicts fills? | Mid touching a price | A taker print large enough to clear queue ahead of me at my tick |
| What sets cancel decisions? | Arbitrary thresholds (5%, 15%) | Expected value: `P(fill) × E[loss \| fill] vs reward inflow` |
| How are regimes detected? | Hidden Markov Model | Direct observable features (time-mod-8h, basis, imbalance, vol, dr/dt) |
| Term structure to maturity? | Ignored | Brownian-bridge anchor; model basis to underlying instead |
| Competing capital? | Ignored | First-class input, drives sizing |
| Backtest fidelity? | Price-touch indicator | Event-driven replay with queue, AMM, cancel latency |
| Parameter uncertainty? | Point estimates only | Bayesian / bias-corrected, propagated into EV |
| Circuit breakers? | Reactive (1.5× margin) | Predictive (extrapolated time-to-breach) |

---

## 14. The Five Things That Actually Matter

If only five engineering decisions get made right, make these:

1. **Pre-sign cancel calldata at placement time** — the single biggest leverage point on fill avoidance.
2. **Track competing notional in the range every poll** — without this, your reward APR estimate is fiction.
3. **Event-driven backtest with queue position and cancel latency** — anything else overstates P&L.
4. **EV-based cancel rule, not threshold dials** — gives interpretable, defensible decisions.
5. **Resolve the open reward-mechanics questions before any live capital** — the strategy may not be worth running at current emission/competition levels, and that's something to learn in spreadsheets, not in production.

Everything else is refinement.
