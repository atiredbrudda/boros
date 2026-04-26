# Boros Reward Farming — Consolidated Plan

This is the final plan after four rounds of revision: original recommendation → alternative critique → rebuttal → live data verification. It supersedes both `boros_model_recommendation.md` and `boros_alternative_plan.md`. Differences from the alternative plan are marked **[REVISED]**; new sections forced by the verification are marked **[NEW]**.

---

## Executive summary

Build an inventory-avoiding maker that:

1. **Restricts itself to a small universe of markets** [NEW] — ~3–5 markets pass the data-density and dispersion tests. Don't pretend the strategy runs everywhere.
2. **Picks a fill model per market based on a dispersion test** [NEW] — Hawkes for CV > 1.5, regular renewal process for CV < 0.7, non-homogeneous Poisson with covariates in between. One-size-fits-all is wrong because the markets behave differently.
3. **Computes E[loss | fill] via parametric OU on the basis** [REVISED] — synthesizes the two plans: empirical estimation as the sanity check, OU on basis (Implied − Underlying) as the smoother. Use both, not one.
4. **Decides cancel/hold via expected value** — `EV_hold = R_share × P(no_fill) − E[loss|fill] × P(fill) − cancel_cost × P(purge)`. No threshold dials.
5. **Sizes capital against measured competition** — `Q_total_in_range` from the live order book, target reward-share parameter is the main tunable.
6. **Backtests event-driven** — replay trade tape, track queue, subtract AMM, apply realistic cancel latency. Price-touch indicators are not acceptable.
7. **Gates everything on Phase 0 reward-mechanics answers** — token, emission rate, pro-rata mechanics, minimum size, Merkle cadence. Until these are answered, no engineering past Phase 1.

---

## What changed since the alternative plan

| Item | Alternative plan said | Verification revealed | Resolution |
|---|---|---|---|
| Hawkes feasibility | Universal — applies to all markets | Only 5/113 markets have >500KB trade data; CV varies 0.46–6.06 | Per-market model selection; restricted universe |
| Brownian bridge importance | Structural correction | Mostly negligible at >14 days to maturity | Demote to "use basis modeling regardless" — not a structural fix |
| HMM | Skip entirely | 2-state HMM has comparable parameter count to feature-based model | Keep features as primary, optional 2-state HMM as confirmation overlay |
| E[loss \| fill] | Empirical from post-fill paths | Possible but noisy; OU on basis is smoother | Use both — empirical for ground truth, OU as smoother |
| Block timestamp resolution | Per-second is fine | Arbitrum blocks ~250ms — sub-block ordering needs `eventIndex` | Use `eventIndex` for intra-block ordering before any clustering analysis |
| Strategy universe | Implied broad | ~3–5 markets viable | Acknowledge directly; size economics on this basis |

---

## Phase 0 — Hard prerequisites (block until answered)

Engineering past Phase 1 is wasted effort until these are answered.

### Answers gathered (as of 2026-04-22)

| Question | Answer |
|---|---|
| Reward token | **PENDLE** |
| Pool structure | **Dual pool per market**: (a) *Maker Volume Rewards* pro-rata by filled maker YU share; (b) *Limit Order Liquidity Rewards* pro-rata by order size × time-near-market-rate, no fills required |
| Strategy-relevant pool | **(b) only.** This strategy avoids fills by design (see thesis line 9; bot guide L69-70). Maker volume pool is not optimized for. |
| Example emissions (Binance ETHUSDT 29 May 2026) | Maker pool: 80 PENDLE/epoch. Liquidity pool: 27.67 PENDLE/day Long + 18.05 PENDLE/day Short. **Per-market, not uniform** — re-read for each shortlisted market. |
| Pro-rata mechanics (liquidity pool) | Size × time-near-market-rate. Both dimensions contribute; resting unfilled with non-trivial size near the CLO range is what gets paid. |
| Per-user cap | **1000% APR on rewards.** Binds Phase 4 sizing (see below). |
| Epoch | Weekly: Friday 00:00 UTC → Thursday 23:59 UTC |
| Distribution cadence | Merkle root updated after epoch end, claimable typically following Monday |
| Gas cost per claim | Negligible — Arbitrum. Not a real factor in economics. |
| Side qualification | **One-sided posting qualifies independently.** Team-endorsed tweet ([0x0Kippon](https://x.com/0x0Kippon/status/2044063318466539872)) recommends picking one side based on Mark-vs-Underlying — a reward strategy the team endorses can't require two-sided posting. Cross-reference in docs/Discord recommended but not blocking. |
| CLO range dynamic | **Yes, shifts continuously as a design feature** (not a governance risk). The incentive range tracks current mid so the protocol pays for *current* liquidity, not stale levels. Operational handling already in Phase 6 circuit breakers. Observed on ETHUSDT 29-May 2026: range drifted from -1.34%/-0.85% (calibration date Apr 8) to 0.71%/1.49% (Apr 22) — same pool, same market, range crossed zero over ~2 weeks. |
| Per-side rewards dynamic | **Likely yes, by design extension** (protocol should rebalance toward thinner side to attract replenishment) but **not directly observed** — we don't yet have before/after budget numbers from the same market. Treat as "probable shift, confirm empirically from API polling." `E_liq_per_epoch` and its Long/Short split must be **polled live per cycle**, not cached per-market. |
| Minimum order size | **Working assumption: $100 collateral-equivalent per order.** Actual protocol minimum not confirmed — verify before paper trading. |

### Still open

These do not block Phase 1 engineering. Phase 5 and Phase 7 must be parameterized to handle both possible answers (see Phase 5 note).

- [ ] **Cancel behavior — are rewards accumulated up to the cancel point preserved, or forfeited?** Two sub-questions:
  - (a) When an order is *voluntarily cancelled* before epoch end, does its accumulated (size × time-in-range) contribution stay in the epoch tally, or get voided?
  - (b) When a new order replaces it, does time-weight for the new order start at 0 (almost certainly yes)?
  - Bot guide Risk 2 says purges "reset time-weight accumulation" but is ambiguous about which reading. Assume worst case (forfeited) as default for conservatism until confirmed.
  - **Resolution path:** (1) check Boros user/dev docs and SDK source first — answer may already be in `pendle-finance/boros-core-public` or the reward distributor contract. (2) if docs don't resolve, ask Pendle Discord. Don't wait on Discord to start engineering.
- [ ] Confirm actual minimum order size (working assumption: $100 collateral-equivalent — not blocking, pre-paper-trading verification).

### What must be computed before model code

For each shortlisted market:

```
R_liquidity_per_year = 365 × (Long_budget_per_day + Short_budget_per_day) × PENDLE_price_USD
R_my_capture_upper_bound = min(
    R_liquidity_per_year × achievable_share_of_pool,
    10 × collateral_me × PENDLE_price_USD        # 1000% APR cap
)
R_apr_on_collateral = R_my_capture_upper_bound / (collateral_me × PENDLE_price_USD)
```

If `R_apr_on_collateral` (before fill-loss subtraction) is less than (alternative_yield + expected fill-loss APR), the strategy is dead on that market. Cheap kill.

---

## Phase 1 — Data infrastructure and market screening [NEW]

### 1a. Build the data pipeline

- Pull all `market-trades/` and `order-book/{market}/raw/` and `order-book/{market}/combined_*` for candidate markets.
- Pull `underlying-apr/` for each relevant CEX-asset pair.
- Pull `settlement/` and `market-data/` for the same markets.
- Schema confirmed by direct inspection: per-trade events with `eventIndex`, `blockTimestamp`, `rate`, `side`, `size`, `txHash`. Order book entries are `{"t": tick, "sz": size_wei}` (size is wei string, not float — convert explicitly).
- **Use `eventIndex` for ordering, not `blockTimestamp`.** Arbitrum block time is ~250ms; multiple trades land in the same block. `blockTimestamp` ties at the second, `eventIndex` orders within block.

### 1b. Market screening — the gate that didn't exist before

For every candidate market, compute and tabulate:

| Test | Pass criterion |
|---|---|
| Total trades over last 60 days | ≥ 5,000 (anything less can't fit a covariate model with rolling windows) |
| Inter-arrival CV (using eventIndex-ordered intervals) | Recorded — determines model class (Hawkes/NHPP/RP), not a pass/fail |
| Mid-rate realized vol (pp per 5 min, last 14 days) | Recorded — direct proxy for fill probability at the CLO edge. Rank ascending; prefer quieter markets. |
| Mid-rate reversal count (last 3 days) | Recorded — oscillatory markets sweep both edges repeatedly. Rank ascending. A reversal = mid crossing its 1h EMA with magnitude > some ε; pick ε per-market based on pp/5m vol. |
| Order book depth at incentivized range | ≥ 5 ticks of resting size on each side most of the time |
| `cloLowerThresh` and `cloUpperThresh` | Both non-zero (active incentive range) |
| Time to maturity | ≥ 30 days (don't onboard markets near expiry) |

**Expected output**: a shortlist of 2–4 markets the bot will actually run on. Be honest if the list is thinner than hoped.

### 1c. Per-market model selection

Based on inter-arrival CV from 1b:

| CV range | Model | Why |
|---|---|---|
| **CV > 1.5** | **Hawkes** with covariate-driven baseline | Self-excitation present; Poisson would underpredict cluster fills |
| **0.7 ≤ CV ≤ 1.5** | **Non-homogeneous Poisson** with covariates | Approximately memoryless; covariates carry the variation |
| **CV < 0.7** | **Regular renewal process** (gamma-distributed inter-arrivals) | Under-dispersed; trades are more regular than random — likely scheduled algo flow. Hawkes here is *worse* than Poisson, would fit negative excitation. |

The verification surfaced this directly: ETHUSDT-26SEP2025 had CV=6.06, BTCUSDT-26DEC2025 had CV=0.46. Same platform, opposite model. The per-market dispersion test is non-negotiable.

### 1d. Reward-share economics gate

Before any model code:

```
For each shortlisted market:
    R_share_per_epoch = (emission_rate × my_target_share) / Q_total_in_range_now
    R_apr_on_collateral = R_share_per_epoch × epochs_per_year / required_collateral
    
    If R_apr_on_collateral < (alternative_yield + estimated_fill_loss_rate):
        Drop the market from the shortlist.
```

If the shortlist becomes empty after this filter, **the strategy is dead at current competition levels**. Stop. Move on. This is the cheapest possible kill switch.

---

## Phase 2 — Fill model

### 2a. Per-market arrival model

Fit the model selected in 1c, with a covariate-driven baseline intensity:

```
λ_s(δ, t) = exp(β_0 + β_1 · feature_1(t) + β_2 · feature_2(t) + ... ) × [Hawkes self-excitation if applicable]
```

Where `s` is side, `δ` is depth from mid in ticks, and features are:

- Time-since-funding-settlement (mod 8h or appropriate cycle for the underlying CEX)
- Basis spread `B(t) = Implied_APR(t) − Underlying_Funding_APR(t)`
- Order book imbalance (depth bid − depth ask, normalized by total depth)
- EWMA realized vol of mid-rate changes over last 5 min (using `eventIndex`-ordered ticks)
- Underlying CEX spot move over last 5 min
- Time to maturity (in days)
- `dRate/dt` of mark APR

### 2b. Queue position tracking

Use raw order book snapshots (hourly, confirmed by verification) as anchors:

1. At each snapshot, queue position is exact: count of resting size on your tick at higher time-priority.
2. Between snapshots, replay the trade tape sequentially:
   - For each opposing-side print at depth ≤ your tick, decrement queue ahead of you.
   - When your queue → 0, you fill.
3. At the next snapshot, reconcile (drift comes from limit placements/cancels you didn't see). Drift is conservative — overstates queue protection slightly.

Queue tracking accuracy is the main reason event-driven backtest beats price-touch.

### 2c. AMM consumption

Use the `combined_{tickSize}` order book files, which merge book + AMM. The AMM share at each tick is:

```
amm_share(δ) = combined_size(δ) − raw_book_size(δ)
```

Subtract this from incoming taker flow before crediting it to the resting book.

---

## Phase 3 — Conditional loss model [REVISED — synthesis]

Two estimators, both built, cross-checked:

### 3a. Parametric estimator: OU on the basis

Fit OU on `B(t) = Implied_APR − Underlying_Funding_APR` (the basis is approximately stationary; raw implied APR isn't). For a fill at time `t` at tick `X` with time-to-maturity `τ`:

```
E[loss | fill at X, τ] = E[ ∫_t^{t+τ} (Realized_Funding(u) − X) du ]
```

With OU on basis, the integral has a closed form. Use bias-corrected MLE on rolling 14-day windows; report a 90% CI on the loss estimate, not just a point.

### 3b. Empirical estimator: post-fill path replay

Slice all historical fills by (depth from mark at fill time, time-to-maturity bucket). For each cell, compute the empirical post-fill PnL distribution.

**Important**: The rebuttal's claim that "fills at CLO edge are too rare" was wrong-framed. We don't need fills *at the CLO edge specifically* — we need fills at any tick distance, sliced into bins. Verification showed 9,216 trades/month on the densest market, ~5,000/month on others. Plenty of data per cell when sliced reasonably.

### 3c. Cross-check

Plot 3a vs. 3b in each cell. If they diverge >2σ, investigate before trusting either. Use 3a as the production input (smoother, extrapolable to unobserved cells); 3b is the calibration check.

---

## Phase 4 — Reward share model [REVISED — single pool, capped]

The strategy targets **only the Limit Order Liquidity pool** (see Phase 0). The Maker Volume pool is paid on fills and is not optimized for — by design we capture ~0% of it.

Snapshot every poll cycle (1–5s):

1. Read `GET /v2/accounts/all-limit-orders` aggregated over the CLO range, OR the order book directly.
2. Compute `Q_total_in_range` (sum of resting size weighted by time-in-range over the epoch window).
3. Forward-estimate the *liquidity-pool* income:

```
R_liq_me_per_epoch = E_liq_per_epoch × (Q_me × t_me_in_range) / Σ_i (Q_i × t_i_in_range)
```

Where `E_liq_per_epoch = 7 × (Long_budget_per_day + Short_budget_per_day)` for that market.

**`E_liq_per_epoch` and the Long/Short split must be polled live every cycle, not cached per-market.** The protocol dynamically rebalances based on competing liquidity. Magnitude and frequency of shifts within a single pool lifetime is not yet characterized — measure empirically from API polling during Phase 1 data work.

**Cap-saturation calibration anchor (ETHUSDT 29-May 2026, snapshot 2026-04-22):** Market showed Short-side APR at 957% (just under the 1000% cap) with only ~60 YU of competing resting liquidity in the range (Long side: 198% APR, ~20 YU competing). Per-side budgets: Long 6.663 PENDLE/day, Short 39.05 PENDLE/day. A new Short entrant here would immediately dilute existing participants below cap. Use this as a concrete anchor for "saturated regime" testing in backtests — saturated markets behave very differently from thin markets.

**Adversarial pattern to study in backtest (same snapshot):** 363.52 YU cluster resting at 1.5% (one tick *outside* the 1.49% upper incentive bound). Hypothesis: participants position just outside the range so they collect no liquidity rewards but sit where natural taker flow hits first, thereby accumulating fill-based Maker Volume Rewards without diluting their own liquidity-pool share. Confirm or falsify by checking fill rates at just-outside-range ticks vs inside-range ticks — if just-outside has materially higher fill rate, the hypothesis holds.

4. **Sizing rule with per-user APR cap.** The protocol caps rewards at 1000% APR per account, so unbounded scaling doesn't exist:

```
R_uncapped(Q_me) = E_liq_per_epoch × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)
R_capped(Q_me)   = min( R_uncapped(Q_me), 10 × collateral_me × (epoch_days / 365) )

Q_me_target = argmax_{Q_me}  R_capped(Q_me) − E[loss | fill](Q_me) × P(fill)
              subject to Q_min ≤ Q_me ≤ Q_max
```

Two regimes for the optimum:
- **Sub-cap regime**: `R_uncapped < cap` at Q_me_target. Standard pro-rata sizing applies — increasing `Q_me` trades off reward share vs. fill probability.
- **Cap-binding regime**: increasing `Q_me` past `Q_cap` buys no extra reward but keeps adding fill-loss exposure. **Never size past `Q_cap`** where:

```
Q_cap = Σ_others × (10 × collateral_me × epoch_days / 365) /
        (E_liq_per_epoch − 10 × collateral_me × epoch_days / 365 × t_frac)
```

If `E_liq_per_epoch × t_frac ≤ 10 × collateral_me × epoch_days / 365`, the cap never binds at any `Q_me` — in that case the market is undersized relative to your collateral and pro-rata alone governs. If `Q_cap < Q_min`, the market is oversized relative to your collateral — you'll be rewarded at cap with minimum size, so size at `Q_min`.

`target_share` (implied by the chosen `Q_me_target`) is the main tunable in the sub-cap regime. In the cap-binding regime the tunable is instead `collateral_me` — more collateral only helps up to the point where you reach market saturation. Sweep both in backtest.

---

## Phase 5 — Decision engine [REVISED — single income term]

EV-based cancel rule per side per epoch. **Only the liquidity pool is income; fills are pure cost** (inventory-avoiding thesis — see line 9, and bot guide L69-70):

```
EV_hold = R_liq_share_per_epoch × P(in_range_and_unpurged)
        − E[loss | fill]        × P(fill_this_epoch)
        − cancel_repost_cost    × P(purge_this_epoch)

Cancel iff EV_hold < 0
```

Where `R_liq_share_per_epoch` is the capped value from Phase 4 (not the uncapped pro-rata — in the cap-binding regime, marginal benefit to holding is zero).

**What is deliberately NOT in the equation:** `+ R_maker_volume × P(fill)`. The Maker Volume pool pays on fills, which this strategy avoids. Including it would push the optimizer toward tighter placement and higher fill probability — the opposite of the thesis. If a later version wants to capture some maker-volume upside, that is a *different strategy* (spread-capture, not reward-farming) and needs its own plan.

No threshold dials. The cancel point self-calibrates as competition rises (`R_liq_share` drops or hits cap), maturity approaches (loss falls), or vol rises (P(fill) rises). Cancel cost is effectively the on-chain transaction cost; negligible on Arbitrum but not zero — include it so the optimizer doesn't thrash in cap-binding regimes where `R_liq_share` is flat across decisions.

### Parameterization for open cancel-behavior question

The Phase 0 open question — whether voluntary cancels forfeit already-accumulated reward-time-weight contribution — ripples directly into this rule. Build the engine with a boolean config flag `voluntary_cancel_forfeits_accumulated`:

- **If `True` (punitive reading):** cancel decision must weigh the sunk reward contribution that would be voided, on top of go-forward EV. The rule becomes more reluctant — cancel only when expected fill loss clearly exceeds go-forward liquidity reward *plus* the sunk accumulation.
- **If `False` (benign reading):** cancel decision is purely forward-looking — already-accrued is banked regardless of cancel.

Phase 7 backtest must run both scenarios and report sensitivity. If results diverge materially, the docs/Discord answer gates paper trading. If nearly identical, the question was moot — ship either branch.

### Optional: HMM as confirmation overlay [REVISED]

Fit a 2-state Gaussian HMM on the same features as the fill model. Run alongside.

- If HMM consistently agrees with feature-based model output → drop the HMM, it's noise.
- If HMM catches transitions the feature model misses → keep it as a vetoing layer (HMM says "regime 2" → tighten the EV cancel threshold by a fixed factor).

Decide after 4 weeks of paper trading. Don't pre-commit either way.

---

## Phase 6 — Predictive circuit breakers

Same as alternative plan §9. All triggers are predictive (extrapolate from rate-of-change), not reactive:

| Trigger | Rule | Action |
|---|---|---|
| Margin trajectory | At current dNetBalance/dt, time to maintenance < 30s | Emergency close all |
| Oracle staleness | `now − fTime > 0.7 × maxUpdateDelay` | Cancel all |
| CLO range removed | `cloLower == 0 OR cloUpper == 0` | Cancel all, alert |
| Range shifted | `\|new_clo − old_clo\| > N` ticks | Cancel, recalibrate, repost |
| Fill rate exceeds budget | More than K fills in last hour | Pause, manual review |
| Competition collapse | `Q_total_in_range` dropped > 50% in 1 epoch | Investigate before resizing — they may know something |
| Maturity migration | `time_to_maturity × R_me_per_epoch < migration_cost` | Roll to next maturity |

---

## Phase 7 — Backtest

Event-driven replay (alternative plan §7), with one verified addition:

- **Use `eventIndex` for intra-block ordering** — multiple trades per block is common, `blockTimestamp` ties at the second.
- **Snapshot reconciliation every hour** — confirmed by verification, snapshots are exactly 3600s apart for raw book.
- **Cancel latency** — 2–5s conservative range; sweep in sensitivity analysis.

Outputs:
- Net P&L per unit collateral, annualized.
- Sharpe-equivalent and max drawdown.
- Calibration plot of predicted P(fill) vs. realized.
- dP&L / dL (cancel latency sensitivity — informs whether colocation is worth it).
- dP&L / dQ_competing (competition sensitivity — informs scaling discipline).

---

## Phase 8 — Execution

- **Pre-sign cancel calldata at order placement time.** Hold in memory. On WebSocket fill or cancel decision, submit instantly. No HTTP roundtrip in the critical path.
- All trading goes through Send Txs Bot with agent wallet.
- Root wallet stays cold.
- Gas balance maintained automatically; alert when below threshold.

---

## Phase 9 — Paper trading (2–4 weeks)

- Run full bot logic against live feeds.
- Log every decision and the counterfactual: "would have placed at tick -135, would have cancelled at epoch 847 because P(fill)=0.12 and expected loss exceeded reward inflow by $X."
- Compare to backtest predictions:
  - Phantom fills vs. predicted P(fill).
  - Phantom reward time vs. predicted time-in-range.
  - Decision accuracy.

If paper diverges from backtest > 1σ on any metric, debug before going live.

---

## Phase 10 — Live, scaled progressively

1. **One market only** (the highest-conviction from the shortlist).
2. **Minimum viable order size** for 2 weeks.
3. Compare live to paper. Match within statistical noise → scale order size.
4. Diverge → stop, debug.
5. Add second market only after first market stable for 4 weeks.

---

## Implementation timeline

| Phase | Duration | Critical path |
|---|---|---|
| 0: Reward mechanics | Days, not weeks | Discord/team query — block all engineering |
| 1: Data + market screening | 1 week | Reusable across all subsequent work |
| 2: Fill model (per-market selection) | 2 weeks | Hawkes for some markets, NHPP for others, RP for under-dispersed |
| 3: Conditional loss model | 3 days | OU on basis closed-form is fast; empirical cross-check is data scan |
| 4: Reward share model | 3 days | Smallest layer, biggest economic leverage |
| 5: Decision engine | 3 days | Wire EV equation; optional HMM overlay |
| 6: Circuit breakers | 2 days | Predictive triggers |
| 7: Backtest | 1 week | Event-driven replay engine — most engineering effort |
| 8: Execution | 1 week | Pre-signed cancel calldata is the key optimization |
| 9: Paper | 2–4 weeks | Calendar time, not engineering |
| 10: Live (single market) | 2 weeks observation, then scale | Calendar time |

**Total to first live capital: ~8 weeks engineering + 4 weeks paper = ~3 months.**

If Phase 0 reveals the strategy is unprofitable at current competition, total spend is ~1 day. Cheap kill.

---

## Two-track build option

If 8 weeks is too long, ship a v0.5 in 2 weeks:

| Layer | v0.5 (2 weeks) | v1.0 (full plan) |
|---|---|---|
| Fill model | Non-homogeneous Poisson with 4 features (basis, time-since-settlement, imbalance, EWMA vol) | Per-market selection: Hawkes / NHPP / RP |
| Loss model | Empirical only, no parametric | OU on basis + empirical cross-check |
| Decision rule | Same EV equation | Same |
| Reward share | Same | Same |
| Backtest | Event-driven, 1 market | Event-driven, all shortlisted markets |
| Circuit breakers | Same | Same |
| Markets | 1 | All shortlisted |

v0.5 is enough to validate the economic thesis with real capital on one market, then expand to v1.0 if it works. This is the recommended path.

---

## What can kill the strategy at each phase

Honest list of failure modes by phase:

| Phase | Kill condition |
|---|---|
| 0 | Reward emission too low at current competition → strategy is -EV anywhere. **Most likely failure mode.** |
| 1 | Market screening leaves shortlist of 0–1 markets → strategy is too narrow to be worth the engineering. |
| 2 | Fill model calibration is poor on backtest hold-out (predicted P(fill) doesn't match realized in any bucket) → model isn't usefully predictive; revert to threshold-based and accept worse decisions. |
| 3 | OU and empirical loss estimates disagree by orders of magnitude → underlying isn't really mean-reverting; loss is heavy-tailed; cap order size to bound exposure. |
| 4 | Competing notional in range exceeds threshold where R_share × time < expected-loss × P(fill) → wait for competition to thin out, or migrate to thinner market with worse data (back to Phase 1 dilemma). |
| 7 | Backtest P&L is positive only in narrow parameter regions → strategy is fragile; small param changes flip the sign. Don't ship. |
| 9 | Paper trading diverges from backtest > 1σ → execution pipeline is different from simulation. Probably cancel latency or oracle staleness. Debug. |
| 10 | Live diverges from paper → most likely cause is competing-bot adversarial behavior (other bots see your orders and respond). Reduce predictability of placement timing. |

---

## What this plan does NOT do

- **Does not predict where rates go.** It predicts when takers arrive at depth, conditional on observable features.
- **Does not assume one model fits all markets.** Per-market selection is mandatory.
- **Does not promise the strategy is profitable.** It defines the kill switches at every phase to discover unprofitability cheaply.
- **Does not handle competing-bot adversarial behavior** beyond competition-collapse circuit breaker. If a sophisticated competitor learns your placement pattern and front-runs cancellations, that's a v2 problem requiring randomized placement timing and decoy orders.
- **Does not solve the cold-start problem on new markets.** Each market needs its own calibration window before the bot operates.

---

## The five things that actually matter (unchanged from alternative plan, validated by verification)

1. **Pre-sign cancel calldata at placement time** — biggest leverage point on fill avoidance.
2. **Track competing notional in the range every poll** — without this, R_share is fiction.
3. **Event-driven backtest with queue position and cancel latency** — anything else overstates P&L.
4. **EV-based cancel rule, not threshold dials** — interpretable, defensible, self-calibrating.
5. **Resolve Phase 0 reward mechanics first** — the strategy may not be worth running, and finding that out in spreadsheets is free.

Plus one new addition:

6. **[NEW] Per-market dispersion test before model selection.** ETHUSDT and BTCUSDT need different fill models. Universal Hawkes is wrong. The screening test in Phase 1 is the gate.
