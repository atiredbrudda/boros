# Pitfalls Research — Boros Reward Farming Bot

**Domain:** Pendle Boros IRS limit-order liquidity-reward farming on Arbitrum (Python models + TypeScript execution, $100 starting collateral, local macOS deployment)
**Researched:** 2026-04-23
**Confidence:** HIGH for on-chain/execution pitfalls (verified from Arbitrum docs, nonce mechanics, public reference), MEDIUM for Boros-specific reward pitfalls (strategy logic from consolidated plan + plan_comparison.md data inspection), LOW for a handful of items flagged below where verification is still open (voluntary-cancel reward preservation, per-side budget rebalancing cadence, protocol minimum order size).

**Scope note.** This document *extends* the existing risk coverage rather than restating it. Already covered and not repeated here: Risk 1 (Fills), Risk 2 (Purges), Risk 3 (Maturity decay), Risk 4 (Collateral opportunity cost), Risk 5 (CLO range shift), Risk 6 (Smart contract / oracle) — see `boros_bot_guide.md` L252-323. The per-phase kill table in `boros_consolidated_plan.md` L399-413 is the canonical list of "headline" strategy-killers. Below, items explicitly marked **[NEW vs plans]** surface failure modes neither doc names.

**Wiki check (Engineering Protocol #1).** Read `../LLM Wiki/workspaces/boros/wiki/index.md` on 2026-04-23 — index is empty (0 pages), no prior pitfall pages exist. This document should be filed back as the seed of `Known issues & failed hypotheses` per the seeding plan.

**How to read this file.** Pitfalls are grouped into four layers matching the orchestrator's request: (A) Strategy/economics, (B) Modeling/backtest, (C) Engineering/execution, (D) Protocols (wiki / manifest / dependency diagram / config schema). Each pitfall carries: Severity (Low / Medium / High / Catastrophic), Warning signs (early-detect heuristics), Prevention (a concrete phase/task addition, not "be careful"), Phase mapping (0–10 from the consolidated plan), and where relevant a Recovery column in the summary tables.

---

## A. Strategy / Economics Pitfalls

### A1: Voluntary-cancel forfeits accumulated time-weight — "churn trap" [NEW vs plans, EXTENDS Phase 0 open question]

**Severity:** Catastrophic (if true) / Negligible (if false). Binary.

**What goes wrong:** Bot reposts on every CLO range drift, every competition shift, every EV flip-sign. If voluntary cancels *forfeit* the epoch-to-date (size × time-in-range) contribution, a bot that reposts 5×/day accumulates effectively zero reward in the epoch because the time-weight denominator keeps restarting while the pool's weekly integral rolls on. The bot runs all week, earns nothing, pays gas, eats fill losses.

**Why it happens:** The bot guide L269 ("time-weight accumulation resets") is ambiguous between "on *purge*" and "on any cancellation." The worst-case reading is the whole strategy. The EV cancel rule assumes rewards accrue continuously while the order rests — if they reset on cancel, the rule's numerator is fiction.

**Warning signs (early detect):**
- Paper/backtest: implement both branches (`voluntary_cancel_forfeits_accumulated = True/False`). If the two branches produce P&L that differs by >30% on the same replay, the answer is load-bearing.
- Live: weekly Merkle claim arrives materially below backtest prediction after matching fills/cancels within tolerance — suggests accumulator is resetting.
- Arbiscan trace: decode reward distributor events for a cancelled-and-reposted order — check whether the pre-cancel contribution shows up in the epoch accounting.

**Prevention (concrete):**
- **Phase 0 task:** Before any Phase 2+ code, walk `pendle-finance/boros-core-public` reward distributor contract and find the function that computes per-user epoch contribution. If `cancelOrder()` decrements the running accumulator, answer = forfeits. If it only removes from `Q_total_in_range` for the forward tally, answer = preserved. Escalate to Pendle Discord only if the on-chain code is ambiguous.
- **Phase 5 task:** Engine ships with the `voluntary_cancel_forfeits_accumulated` boolean as a first-class config knob (already planned in consolidated plan L277–281). Write the EV rule such that setting `True` adds a sunk-cost penalty term `forfeited_accumulation × R_per_unit_time_weight_remaining_epoch` to the cancel cost. Don't hardcode — it must be a knob so Phase 7 can sweep.
- **Phase 7 task:** Explicit sensitivity row in backtest output: `dP&L / d(forfeits_flag)`. If the flip meaningfully changes decisions, the answer gates Phase 9 (paper). If it barely moves P&L, document "question moot at this collateral scale" in the wiki and ship the benign branch.

**Phase to address:** 0 (primary), 5 (implementation), 7 (sensitivity).

---

### A2: Per-side budget rebalances away from your side exactly when you scale [NEW vs plans, EXTENDS consolidated plan L53 "polled live per cycle"]

**Severity:** High.

**What goes wrong:** The consolidated plan (L53, L225) already says `E_liq_per_epoch` and the Long/Short split must be polled live. What neither plan says: the protocol likely *rebalances toward the thinner side to attract liquidity*, which means the moment you enter the thin side with meaningful size, the thin side is no longer thin, and the protocol's budget allocator sees that and shifts budget toward whichever side is now undersupplied — which is now the *other* side, not yours. Your per-epoch reward is computed against a budget number that was true when you placed but is false by hour 24 of the epoch.

**Why it happens:** ETHUSDT 29-May anchor (consolidated plan L67): Short budget is ~5.9× Long (39.05 vs 6.663 PENDLE/day) *because* Short is thin. Post entrant on Short → Short becomes less thin → budget re-splits → Short payout per participant drops by both the competition dilution *and* the budget shrinkage. Double-counted in human intuition as a single "dilution."

**Warning signs:**
- Polling loop logs `E_liq_per_epoch × long_share` and `× short_share` and shows the split moving toward the side you *didn't* enter within 1–3 epochs of your placement.
- Backtest with a static budget split shows markedly higher P&L than backtest with an empirical split trajectory replayed from the polling logs.
- The thin-side APR visible on the Boros UI drops >50% within hours of scaling a position up.

**Prevention (concrete):**
- **Phase 1 task:** Data pipeline must *persist* polled `E_liq_per_epoch` + Long/Short split per-poll (not just per-market-per-day), because historical rebalancing trajectories are the only way to calibrate how fast the split moves. The planning docs imply this is live-only; upgrade the pipeline spec to *log everything polled, always, to NDJSON sidecar*.
- **Phase 4 task:** Sizing equation takes `E_liq_per_epoch_t` as a process, not a constant. Report `Q_me_target` under a pessimistic budget-shrinkage scenario (e.g., your side's budget shrinks 20% within 48h of your entry) as a stress case.
- **Phase 6 task:** Add a predictive circuit breaker: `E_liq_per_side[my_side]_t < 0.5 × E_liq_per_side[my_side]_{t-3d}` → pause new placements, hold existing, re-evaluate EV with the new budget.

**Phase to address:** 1 (logging), 4 (sizing), 6 (breaker).

---

### A3: CLO range shifts mid-epoch and re-posting forfeits accrued time [NEW vs plans, COMPOUND of A1 + existing Risk 5]

**Severity:** High (conditional on A1 = forfeits).

**What goes wrong:** The consolidated plan L52 confirms CLO range shifts *continuously* as a design feature — observed ETHUSDT range drifted -1.34%/-0.85% → 0.71%/1.49% over ~2 weeks (crossed zero). If the bot's order is outside the shifted range, it's either purged (already covered in Risk 2) or still resting but no longer in-range → no longer accruing → must cancel + repost. If cancel forfeits (A1), you take the hit from *both* sides: you lost the epoch-to-date accumulation AND you restart at zero in an epoch that's already 40% spent. Effective APR is halved on a single range shift.

**Why it happens:** The two plans handle CLO shift and cancel-behavior as separate risks. They interact multiplicatively at mid-epoch. The existing Risk 5 mitigation ("cancel existing orders, recalibrate, repost in new range") is exactly the operation that trips the A1 trap.

**Warning signs:**
- Histogram of observed CLO midpoint shifts per pool per epoch — if the 90th-percentile shift within an epoch exceeds the cloUpper-cloLower half-width, you're going to be repositioning mid-epoch regularly.
- Paper-mode P&L systematically lower than backtest on weeks that had a large mid-epoch range shift.

**Prevention (concrete):**
- **Phase 1 task:** Pre-compute empirical intra-epoch CLO-shift distribution per market. Markets with >50% of epochs needing intra-epoch repositioning get an explicit flag in the screener: "unstable CLO."
- **Phase 5 task:** Under `voluntary_cancel_forfeits_accumulated = True`, the EV rule on a CLO shift event must compare "repost and lose accumulation" vs. "stay out of range for rest of epoch." The latter is sometimes better; the current plan doesn't consider it.
- **Phase 7 task:** Backtest sensitivity `dP&L / d(CLO_shift_frequency)` per market — identify which shortlisted markets can survive their own volatility.

**Phase to address:** 1 (screener flag), 5 (EV branch logic), 7 (sensitivity).

---

### A4: $100 collateral, 1000% APR cap: the cap is a ceiling you can't grow past linearly [NEW vs plans — the cap gets mentioned but its *shape* isn't drawn]

**Severity:** Medium (economics), but pedagogically Catastrophic if misunderstood at scale-up.

**What goes wrong:** The 1000% APR cap (Phase 0 L48, Phase 4 L231–249) is stated but its implication for scaling is under-emphasized. At $100 collateral, cap = $1000/yr = ~$19.2/week reward ceiling regardless of how much is in the pool. On a market where the pool is so starved that one $100 entrant *would* earn 2500% APR, you earn 1000% — the excess 1500% vanishes to nobody's benefit. Then when the operator scales from $100 → $500, the cap scales proportionally to $5000/yr — *but* the reward pool is now diluted because you added 5× the liquidity, so the uncapped APR might now be 300% (below cap). Scaling capital past the cap-binding threshold is linearly rewarded; scaling from below-cap region is sub-linear. **Operator intuition that "more collateral = more reward" is correct in sub-cap regime and wrong in cap-binding regime, and the transition is not smooth.**

The cap-saturation anchor (consolidated plan L227) — ETHUSDT 29-May Short at 957% APR with ~60 YU competing — says current competition already puts the operator in the cap-binding regime on that market. At $100 the cap is almost certainly binding on every currently-viable market.

**Why it happens:** Treating reward APR as linear in collateral is instinctive; the cap creates a piecewise-linear function that's flat-then-sloped-then-flat-again as `Q_me` grows. Phase 4's `Q_cap` formula (L245–248) captures this but doesn't plot it.

**Warning signs:**
- Backtest output uses "reward APR" as a scalar per market rather than "reward APR(collateral)" as a function.
- Operator's scale-up plan assumes linear reward growth.
- Phase 4 calibration report doesn't show the `R_capped(Q_me)` curve with the kink clearly drawn.

**Prevention (concrete):**
- **Phase 4 task:** Every per-market screening report ships with a `R_capped(Q_me)` plot, annotated with `Q_cap`, the current operator collateral, and the market saturation point. Scale-up decisions refer to this plot, not a scalar APR number.
- **Phase 4 task:** The sizing optimizer output includes "regime" as a first-class field: `sub_cap` / `cap_binding` / `market_saturated` (where `Q_cap < Q_min`). Different regimes have different scale-up implications.
- **Wiki page:** File `Reward cap geometry` as a wiki page with the kinked curve, before Phase 7.

**Phase to address:** 4 (curve + regime label), 7 (backtest reports regime per run), Wiki.

---

### A5: Competition dynamics — thin market becomes fat market between "screen" and "deploy" [NEW vs plans, EXTENDS Phase 1d economics gate]

**Severity:** High.

**What goes wrong:** Phase 1d economics gate passes because market X has low `Q_total_in_range` → high R_share → high APR → pass the gate. By the time the bot is engineered, paper-traded for 2 weeks, and deployed live, market X has been discovered by other bots (or by humans on Discord, or indexed into a public bot-tracking dashboard that we don't control). `Q_total_in_range` has 5×'d. R_share is now a fifth of what the screener said. APR is below alternative yield. Strategy is -EV on the only market it ever qualified on.

This is especially acute because the consolidated plan L75 flags the strategy universe as structurally narrow (only ~5/113 markets pass density screening), meaning if a market becomes profitable and visible, it has a short half-life.

**Why it happens:** Screener snapshot ≠ deployment-time state. The 3-month engineering gap is enough for market dynamics to shift. Plan_comparison L411 flags this at Phase 10 ("competing bots see your orders and respond") but misses that the shift can happen *pre-deployment* with no bot interaction yet — just ambient market-discovery risk.

**Warning signs:**
- `Q_total_in_range` on the shortlisted market has doubled or more between Phase 1 screening and Phase 9 paper start.
- Implied APR on that market's CLO edge has been flat or declining over the engineering window — signals participants have crowded in.
- Boros UI-visible "Days to earn rewards" or implied APR on a market fell from >200% to <50% over the build period.

**Prevention (concrete):**
- **Phase 1 task:** Screener reruns daily (automated) while engineering proceeds. Shortlist is a *live* list, not a snapshot. If shortlist shrinks from 3 to 1 to 0 during engineering, the schedule is cooked and the operator needs to know *immediately*, not at paper-start.
- **Phase 6 task:** Circuit breaker — "pre-deployment re-screen fails" — blocks transition Phase 8 → 9 until a fresh re-screen shows the target market still passes.
- **Phase 9/10 task:** Before live, re-run Phase 1d gate on that day's `Q_total_in_range`. If it fails, don't deploy. This is a 15-minute check, not a decision.

**Phase to address:** 1 (daily re-screen), 6 (pre-deploy re-screen breaker), 9/10 (gate check).

---

### A6: Forced-close taker fee + fee-structure surprises [NEW vs plans — fee table not enumerated]

**Severity:** Medium.

**What goes wrong:** Plan assumes "if filled, close immediately at market, accept taker fee as insurance" (PROJECT.md L123). Neither plan ever enumerates the actual fee schedule: (a) maker fee on the filled order — may be negative (rebate) or zero, (b) taker fee on the immediate close, (c) any settlement fee at maturity, (d) any market-entrance or exit fee, (e) gas for the close transaction. At small capital these fees are non-trivial relative to the reward rate. A single fill + close cycle at 0.05% taker fee against $100 = $0.05, but at one fill/week across 52 weeks, that's $2.60 — ~15% of one week's capped reward ceiling.

**Why it happens:** Planning docs focus on the reward side and fill-loss side of EV, never on transaction-cost side beyond gas. The bot_guide L134-150 shows some fee fields but doesn't apply them to the EV rule.

**Warning signs:**
- EV equation has no `trading_fees` term.
- Phase 7 backtest output shows P&L without a line-item for cumulative trading fees.
- Paper vs backtest divergence that correlates with fill count.

**Prevention (concrete):**
- **Phase 0 task:** Enumerate actual fee schedule from Boros SDK/API + one live test on paper. Record: maker fee bps, taker fee bps, settlement fee bps, gas per (place / cancel / close) in gwei at p95 Arbitrum congestion. File as wiki page `Fee schedule 2026-04`.
- **Phase 5 task:** EV equation gets a `fee_cost` term. Specifically for the "forced close on fill" branch: `P(fill) × (taker_fee + close_gas + any_settlement)`.
- **Phase 7 task:** Backtest output has a fee line: cumulative fees paid / week and as a fraction of cumulative rewards claimed. If fees > 10% of rewards at $100, the strategy's unit economics are thin and sizing up is the only fix.

**Phase to address:** 0 (fee wiki), 5 (EV term), 7 (backtest line-item).

---

### A7: Underlying CEX funding-rate spike / halt — basis blow-up [NEW vs plans — Risk 6 covers oracle, not underlying]

**Severity:** High in rare events.

**What goes wrong:** The OU-on-basis loss model (Phase 3a) assumes the basis `B(t) = Implied − Underlying` is stationary over the rolling 14-day window. A Binance/OKX funding-rate outlier (historical example: October 2023 FTX collapse aftermath, April 2024 BTC halving spike, various alt-coin-specific squeezes) blows the underlying out by 10× its normal range for 1–6 hours. Basis becomes non-stationary for the duration; OU MLE produces nonsense θ; `E[loss|fill]` is hopelessly wrong; bot happily holds orders because its loss estimate is still saying "small." Then one of them fills and the close is against a runaway rate.

Additionally: if the underlying CEX *halts trading* (happens during extreme events), the underlying feed is literally stale while implied keeps moving on Boros — the basis sign flips, the bot may think the CLO edge is safe, and a taker sweep lands the bot with inventory against a frozen underlying (no hedge venue, no price discovery).

**Why it happens:** Plan treats Boros oracle staleness (Risk 6 / Phase 6 breaker) as the staleness risk, but the *underlying CEX* staleness is a separate failure mode not listed. Binance halts are rare but real.

**Warning signs:**
- Rolling z-score of underlying funding rate > 4 on current 14-day window → OU has outlier in fitting data.
- Implied − Underlying |basis| > 3× its 14-day stdev.
- `underlying-apr/` feed age > 30 minutes on market with normal 15-min cadence.
- Exchange-status endpoint (Binance `/sapi/v1/system/status`) reports maintenance / degraded.

**Prevention (concrete):**
- **Phase 3 task:** OU fitter is robust-MLE (Huber or trim top 1% residuals), not vanilla MLE. Report the trimmed-out fraction alongside the fit — if >2% of points are trimmed, flag the fit as low-confidence.
- **Phase 6 task:** Add circuit breaker — "underlying outlier": `|z(underlying_funding_rate, window=14d)| > 4` → cancel all, pause for 6h, re-fit OU on post-event window.
- **Phase 6 task:** Add circuit breaker — "underlying feed stale": `now − last_underlying_APR_tick > 2 × normal_cadence` → cancel all, alert.
- **Phase 6 task:** Poll CEX system-status endpoints for operator's configured underlying exchanges once per minute; maintenance/halt status → cancel all.

**Phase to address:** 3 (robust MLE), 6 (three new breakers).

---

### A8: "Just-outside-range" adversary [NEW vs plans — flagged as hypothesis on L229, not resolved]

**Severity:** Medium (strategy-shape question).

**What goes wrong:** Consolidated plan L229 observed a 363.52 YU cluster one tick *outside* the 1.49% upper incentive bound — hypothesizing participants position there to catch Maker Volume rewards on natural taker sweeps without diluting their liquidity-pool share. If the hypothesis holds, the "outer edge of CLO range" (our posting strategy) is systematically *behind* these outside-range walls. Takers hit the outside-range wall first, only penetrate into our incentivized tick if they have oversupply. Our fill rate is lower than naive queue-replay predicts (good for P&L) but our effective reward rate is also capped by what slim volume slips past the outside-range wall to make our tick visible to market. Worse: the outside-range crowd is price-insensitive (they get paid on fills, not on time), so our "outer edge" may be chronically shielded by a wall we can't beat.

**Why it happens:** It's a second-order equilibrium — the two reward pools interact. Plans model the liquidity-pool alone and treat the maker-volume pool as "not for us." Other participants' strategic positioning creates structural blockers.

**Warning signs:**
- Phase 1 data inspection: depth at `tick = cloUpperTick + 1` or `cloLowerTick - 1` consistently exceeds depth at `tick = cloUpperTick` or `cloLowerTick` in the same market.
- Empirical fill rate at the just-outside-range tick materially higher than at just-inside-range tick over the same window.
- Backtest P&L is positive because fills are rare, but sensitivity analysis shows rewards are negative — you never earn but you also rarely lose.

**Prevention (concrete):**
- **Phase 1 task:** Screener computes depth-at-CLO-edge and depth-one-tick-outside-CLO-edge per market. Report ratio. If >2 on either side for >30% of observations, flag: "outside-range wall market."
- **Phase 2 task:** Fill model includes "outside-range wall size" as a covariate in the baseline intensity for the CLO-edge tick — when the wall is thick, our fill rate is lower conditional on sweeps of similar magnitude.
- **Phase 7 task:** Backtest reports per-epoch reward *accrual time* (time the order was actually in-range-and-accruing) as a ratio of epoch length. If median <60%, the wall is blocking us from earning and the strategy is fighting a losing structural battle on that market.

**Phase to address:** 1 (screener), 2 (covariate), 7 (accrual-time report).

---

## B. Modeling / Backtest Pitfalls

### B1: Queue-position drift over the hour — *direction* matters [NEW vs plans — L306 says "conservative noise" but doesn't prove it]

**Severity:** Medium.

**What goes wrong:** The plan asserts (consolidated L306, plan_comparison L306) that inter-snapshot queue drift is *conservative* because unseen cancellations would have shortened the queue ahead of us — i.e., the replay over-estimates our queue protection, which makes our fill predictions conservative. **This is not actually proven.** It's correct for cancellations ahead of us but wrong for *new placements* ahead of us (happens when a competing bot lowers its tick-priority by reposting at a better spot, pushing its time-priority to the back but its tick-priority ahead of others). If placements ahead outpace cancellations ahead, replay *under*-estimates our queue and over-estimates fill probability (liberal, not conservative). Backtest P&L then looks worse than reality, operator kills a viable strategy.

Hourly snapshots means 3600 seconds of drift. A live bot reposts on every CLO shift, and per A3 those are frequent. Number of invisible placement/cancel events per hour is non-trivial.

**Why it happens:** "Conservative" is the assumption when the only invisible event is cancellation. Hourly snapshots make both placement and cancellation invisible.

**Warning signs:**
- Reconciliation drift at each hour snapshot has a *non-zero mean* — if cancels dominated, the expected drift would skew our queue shorter on average; if placements dominated, skew shows our queue longer than replay said.
- Backtest predicted-fill-rate systematically below realized-fill-rate on the hold-out.
- Net change in book depth at each tick per hour > 50% of snapshot magnitude regularly.

**Prevention (concrete):**
- **Phase 2 task:** At each hourly reconciliation, log `drift_direction` and `drift_magnitude` per tick. Aggregate: if the signed mean drift across an epoch is not-zero, flag the replay as biased and *name the direction*. Don't assume.
- **Phase 2 task:** Bracket every fill-probability estimate with a pessimistic (all invisible events are placements ahead) and optimistic (all are cancellations ahead) bound. Ship the bracket to the EV engine — use pessimistic for cancel decisions, not the point estimate.
- **Phase 7 task:** Backtest reports calibration plot separately for snapshot-hour (high confidence) vs mid-hour (low confidence). If the mid-hour calibration is worse than snapshot-hour by >1σ, the hourly-snapshot resolution is the limiting factor and the data vendor should be asked for finer cadence before going live.

**Phase to address:** 2 (bias measurement + bracketing), 7 (calibration-by-offset plot).

---

### B2: `eventIndex` may not be present in all markets / older data [NEW vs plans — L92 asserts, plan_comparison L70 asserts, but universality not confirmed]

**Severity:** High (if missing in live data) / Medium (if missing only in thin-market historical).

**What goes wrong:** Both plans rely on `eventIndex` for intra-block ordering (consolidated L92, plan_comparison L70, this project's data inspection found it in ETHUSDT-26SEP2025). But the NDJSON sample is from *one market*, August 2025. The 108/113 markets without sufficient trade data may also lack `eventIndex` — possibly because they predate its introduction, or because thin markets don't emit enough within-block events for it to be tested. If `eventIndex` is missing on a market we want to screen, all within-block ordering collapses to `blockTimestamp` ties, the Hawkes clustering analysis (A multi-fill sweep shows up as one single-timestamp event instead of many ordered fills) mis-estimates the cluster intensity, and the CV value used to choose model class is wrong.

Worse: if `eventIndex` is present historically but the live websocket feed's event payload omits it, the live bot can't replicate the backtest's ordering discipline and queue tracking silently degrades in production.

**Why it happens:** Sampling one market and generalizing. Live feed schema ≠ historical NDJSON schema is common.

**Warning signs:**
- Phase 1 data pipeline pulls 10 markets; grep for `eventIndex` field coverage across all of them. If <100%, flag.
- WebSocket `orderFilled` or similar payload in dev mode — if `eventIndex` is missing, flag before any Phase 8 engineering.
- Within-second trade clusters in the live feed show as a single event while the historical NDJSON shows as multiple — schema mismatch.

**Prevention (concrete):**
- **Phase 1 task:** Schema assertion at ingest — every row from `market-trades/` across every market checked for `eventIndex` present and non-null. Markets with incomplete coverage are flagged and either dropped from the shortlist or the CV is computed with a documented caveat ("tied-timestamp inflation factor = X%").
- **Phase 8 task:** Live WebSocket payload tested for `eventIndex` presence before any pre-signed-calldata work. If missing, escalate to Boros team before continuing.
- **Wiki task:** File `eventIndex schema coverage` page after Phase 1 with per-market coverage.

**Phase to address:** 1 (ingest assertion), 8 (live WS check), Wiki.

---

### B3: AMM consumption double-count / under-subtract — replay engine silently off [NEW vs plans — L172-179 describes the subtraction but not the edge cases]

**Severity:** High.

**What goes wrong:** `amm_share(δ) = combined_size(δ) − raw_book_size(δ)` at the snapshot is correct when both files are from the exact same instant. If snapshots of `raw/` and `combined_{tickSize}/` are even one block apart (~250ms), or if `combined_` uses a different tick aggregation than the replay engine assumes, the subtraction produces negative AMM shares (impossible) or leaks actual resting book into the "AMM" bucket. The replay engine then either double-counts a taker print against both the AMM and the book (under-estimates our fills), or never credits the print to anyone (over-estimates our fills).

**Why it happens:** Two files with independently-timed snapshots are a race condition by default. Tick aggregation differs between granularities.

**Warning signs:**
- Per-snapshot sanity check: `∀ δ: amm_share(δ) ≥ 0` — any negative value is evidence of time-skew or aggregation mismatch.
- Sum of queue-replay changes over an hour ≠ sum of trade-tape consumption minus AMM swaps in the same hour.
- Simulated fill probability with and without AMM subtraction differs by an *implausible* amount (e.g., factor of 3×).

**Prevention (concrete):**
- **Phase 1 task:** Ingest asserts `amm_share(δ) ≥ 0` for every snapshot, every tick, every market. Any violation is a hard error — fix the snapshot alignment before continuing.
- **Phase 2 task:** Replay engine emits a per-epoch conservation check: `book_ahead_of_us(t_end) = book_ahead_of_us(t_start) − taker_consumption_ahead_of_us + net_placements_ahead_of_us`. If the identity fails, the replay has a bug (likely AMM double-count or miss).
- **Phase 7 task:** Sensitivity check — run backtest with AMM subtraction at 0.8× and 1.2× the computed share. P&L delta > 10% → AMM estimation error is a dominant source of P&L uncertainty; tighten the Phase 2 logic.

**Phase to address:** 1 (ingest assertion), 2 (conservation check), 7 (sensitivity).

---

### B4: Hawkes MLE convergence failures / negative excitation on under-dispersed markets [NEW vs plans — plans acknowledge the dispersion test but not the failure mode if the test is ignored]

**Severity:** High if Hawkes is applied blindly.

**What goes wrong:** Hawkes MLE on a market with CV < 1.0 (Poisson-ish) or CV < 0.7 (under-dispersed — BTCUSDT-26DEC2025 had CV=0.46) either fails to converge, produces nonsense negative excitation, or worse fits a spurious small positive excitation that passes significance tests on the fitting data but predicts nothing on hold-out. The bot then over-predicts cluster arrivals on a market where arrivals are actually more-regular-than-Poisson, cancels too aggressively, forfeits reward time-weight (if A1 holds), and pays gas for needless cancel/replace cycles.

The dispersion test (Phase 1c) is the correct gate, but implementation discipline matters: what happens when a market is 0.69 (just below cutoff) one week and 0.72 the next? Model class flapping is dangerous.

**Why it happens:** Under-dispersed arrivals violate Hawkes's generative assumption (point process with positive self-excitation). MLE doesn't refuse; it returns a bad answer.

**Warning signs:**
- Fitted α (excitation magnitude) < 0 — Hawkes library either refuses or silently clips to 0 depending on implementation.
- Log-likelihood ratio vs. pure Poisson null is tiny or negative on hold-out.
- CV bootstrap confidence interval crosses both 0.7 and 1.5 → model class is undefined for that market.
- Fitted branching ratio (α / β) near 1.0 is instability; near 0 is Hawkes-is-Poisson; neither is useful.

**Prevention (concrete):**
- **Phase 1 task:** CV is reported with a bootstrap 95% CI, not a point value. If the CI straddles a model-class boundary, the market is flagged `model_class = undetermined` and uses NHPP (the middle option) with a wider covariate set.
- **Phase 2 task:** Every Hawkes fit returns health diagnostics: `convergence_flag`, `alpha_positive`, `loglik_vs_poisson_holdout`, `branching_ratio`. Fit is only used if all four pass a sanity gate. Otherwise fall through to NHPP.
- **Phase 2 task:** Rolling 14-day fits on the same market emit `class_stability`: fraction of windows that picked the same model class over the calibration period. If <80%, the market is model-class unstable — flag and prefer NHPP regardless of instantaneous CV.

**Phase to address:** 1 (CV CI), 2 (fit diagnostics + stability).

---

### B5: OU on basis — regime shift mid-window makes fit meaningless [NEW vs plans — mentioned obliquely in A7, deserves its own entry]

**Severity:** Medium.

**What goes wrong:** OU on basis assumes the basis process has a single stationary regime over the fitting window. Boros underlying funding-rate regimes shift (risk-on vs risk-off; pre-halving vs post-halving; high-vol vs low-vol). If the 14-day fit window straddles a regime boundary — e.g., underlying ETH funding was -0.01% for 7 days then +0.08% for 7 days — the fitted OU has a θ (mean-reversion speed) that's a lie (really there are two OU regimes, not one) and a μ (long-run mean) halfway between the two. `E[loss|fill]` integral is computed against a mean the basis will never revisit in the short term. Bot systematically wrong on loss.

**Why it happens:** Rolling windows paper over regime changes. Mean of a bimodal distribution is not a representative value of either mode.

**Warning signs:**
- OU residuals have heavy tails (kurtosis > 5) or are bimodal on kernel-density plot.
- Fitted μ on consecutive 14-day windows jumps by >2 standard errors — regime shift.
- Augmented Dickey-Fuller on the basis window fails to reject unit root at 5% — non-stationary, OU is inappropriate.

**Prevention (concrete):**
- **Phase 3 task:** Every OU fit runs ADF on the input window. Non-stationary → reject fit, widen window or fall back to empirical-only loss estimate (plan_comparison's plan B).
- **Phase 3 task:** Report fitted μ and θ as rolling time-series, not point values. Discontinuities > 2σ flag regime shifts; loss estimates during the discontinuity are marked low-confidence.
- **Phase 6 task:** Circuit breaker — OU fit degraded (ADF rejected or residual kurtosis spiked) → shrink position sizing to Q_min until a clean fit is restored.

**Phase to address:** 3 (fit diagnostics), 6 (sizing breaker).

---

### B6: Look-ahead / survivorship bias in historical reward anchors [NEW vs plans — subtle, not covered]

**Severity:** Medium.

**What goes wrong:** Backtest uses *current* `E_liq_per_epoch` and Long/Short budgets (e.g., ETHUSDT 29-May anchor: 39.05 PENDLE/day Short, 6.663 Long — consolidated plan L227) when replaying historical August 2025 trades. But the historical budgets were different — the protocol emission schedule has almost certainly changed between Aug 2025 and Apr 2026, and the Long/Short rebalancing per A2 has happened through that entire window. Backtest says "you'd have earned X" based on current-budget × historical-fill-rate, but historical earnings were `historical_budget × historical_fill_rate`. These are different numbers. Usually current budgets are higher than historical (protocols tend to raise emissions to bootstrap, then cut them), so backtest over-predicts P&L.

**Why it happens:** Reward budgets are treated as a market constant; they're a time-series. Plan L225 says "polled live" but doesn't say "historical values also time-series-logged from day one of data pipeline."

**Warning signs:**
- Backtest replay uses a single `E_liq_per_epoch` value for the entire replay window.
- No time-series of historical reward budgets in the data pipeline.
- Paper-trading Merkle claim systematically lower than backtest-predicted claim for the same week.

**Prevention (concrete):**
- **Phase 1 task:** Data pipeline scrapes / reconstructs historical `E_liq_per_epoch` + Long/Short split per market per day from distributor contract events. If contract-level reconstruction isn't possible, log going forward and explicitly mark backtest results prior to pipeline-go-live with "reward-budget assumed constant — N epochs are synthetic."
- **Phase 7 task:** Backtest P&L report separates (a) rewards computed with historical-budget replay vs (b) rewards computed with current-budget static. If (b) − (a) is positive and large, the strategy's "current" attractiveness is partly an artifact of current emission rates — which may revert.
- **Phase 9 task:** Paper-trading reconciliation checks *predicted* Merkle claim against *realized* Merkle claim for each of the first 3 epochs. If predicted is 2× realized, the backtest's budget assumption is wrong; fix before scaling.

**Phase to address:** 1 (budget time-series), 7 (A/B report), 9 (reconciliation).

---

### B7: "Positive-P&L only in narrow parameter region" — concrete red flags [EXTENDS consolidated plan L410]

**Severity:** High.

**What goes wrong:** Consolidated plan L410 flags this at Phase 7 but doesn't name the red flags. Concretely, a fragile-P&L regime shows up as:
- P&L sign flips on `cancel_latency ∈ [2, 5]s` sweep. Not a sensitivity — a flip.
- P&L sign flips on `target_share ∈ [0.05, 0.25]`.
- Highest-P&L point lies in the corner of the parameter grid, not in its interior.
- P&L is positive in-sample and negative on the 20% hold-out.
- Sharpe > 3 from a back-test — too good to be true; likely look-ahead bias from B6 or B3.

**Why it happens:** High-dimensional parameter grid + a single "best" metric → you find the lucky corner.

**Warning signs (detection protocol):**
- Parameter grid 2D contour of P&L: if sign-flips are within 1 std-error of each other, strategy is fragile.
- P&L(best_params) / P&L(random_params_in_region) — if the best is >3× the median of its neighborhood, you've found an overfit point.
- Bootstrap resampling of trades: P&L 5th percentile < 0 → strategy fails under reasonable sampling noise.

**Prevention (concrete):**
- **Phase 7 task:** Output includes (a) bootstrap-resampled P&L distribution per parameter setting, (b) 2D sensitivity contour on the two most-uncertain knobs, (c) in-sample vs hold-out delta. The README for the output names each of these as a ship-gate.
- **Phase 7 task:** "Ship-gate": P&L 5th percentile on bootstrap > alternative yield *after* fees + reward-budget haircut from B6. Weaker gates ship strategies that look good and aren't.
- **Phase 9 task:** Paper-trading runs at the operator-selected parameter point AND at two perturbed neighbors. If neighbors are within noise of selected, robust. If neighbors diverge, overfit.

**Phase to address:** 7 (bootstrap + ship gate), 9 (perturbation runs).

---

## C. Engineering / Execution Pitfalls

### C1: Pre-signed cancel calldata + sequential nonces = cancel chain [NEW vs plans — biggest non-obvious execution pitfall]

**Severity:** Catastrophic (in multi-order regime) / Medium (single-order regime).

**What goes wrong:** Ethereum transactions from the agent wallet have sequential nonces starting at 0. Pre-signing cancel calldata at order-placement time means each cancel has a specific nonce baked in. If the operator holds orders A, B, C (nonces 10, 11, 12 for their respective cancels), and order B fills first: the bot wants to cancel C urgently (to avoid the next fill). But C's cancel tx has nonce 12, and nonce 11 (B's cancel) is no longer needed — C's cancel can't land until *something* uses nonce 11. If the bot tries to submit 12 without 11 mined, it sits in mempool indefinitely. Meanwhile the 2–5s cancel-latency budget blows past 60+ seconds.

Two deeper issues:
1. Re-signing every cancel on every placement/cancel event to avoid chained nonces means 3× as many signatures held, plus wallet-key exposure time grows (C3).
2. Send Txs Bot / Safe account multisig with queued txs has its own ordering model that may or may not be nonce-order-strict. If it is, same pitfall. If it isn't, a different pitfall: tx replayed out-of-order could cancel the wrong order (A's cancel lands after A already filled, wastes gas and emits a misleading log).

**Why it happens:** Pre-signing and cancellation-selectivity are in tension. The plan endorses pre-signing (consolidated L329, L438) but doesn't surface the nonce-chain constraint.

**Warning signs:**
- Cancel latency on paper-mode test exceeds 10s with 3+ pre-signed cancels held.
- Cancel tx broadcast returns `replacement transaction underpriced` or `nonce too high` — ordering issue.
- A cancel tx is mined with the wrong `orderId` because pre-signed tx A's nonce was used after its order was already cancelled via a different path.

**Prevention (concrete):**
- **Phase 8 task:** Document the nonce model explicitly in `docs/ARCHITECTURE.md` for the execution node. Either (a) all cancels use the *same* nonce (only one cancel can land per block, rest invalidate — simple, correct for single-order bot, wrong for multi-order), or (b) cancel calldata is signed at *cancel decision time*, not placement time (adds ~500ms signing latency but no nonce-chain fragility), or (c) pre-sign a batch of cancels with consecutive nonces and re-sign the tail on every fill — bookkeeping cost.
- **Phase 8 task:** Architecture decision doc: for $100 single-order-at-a-time single-market regime, option (a) is fine. For multi-order scale-up, option (b) or (c) is mandatory. *Do not skip this choice at scale-up.*
- **Phase 9 task:** Paper-trading test case — hold 3 orders, pre-sign all cancels, fire middle-order fill. Measure cancel latency on the remaining two. If either > 10s, the nonce model is broken.

**Phase to address:** 8 (nonce-model decision + doc), 9 (test case).

---

### C2: Cancel latency dominated by Arbitrum RPC queue — not local sign time [NEW vs plans — plan budgets 2–5s but doesn't decompose]

**Severity:** High.

**What goes wrong:** The 2–5s cancel-latency budget is treated as one number. It's actually: (1) WebSocket fill notification latency (network RTT + WS server processing + Boros-side event emission), (2) local decision logic, (3) broadcast to RPC, (4) sequencer inclusion, (5) confirmation. On a public Arbitrum RPC (`https://arb1.arbitrum.io/rpc`, which PROJECT.md L119 lists as default) during any congestion or if the RPC provider rate-limits the agent wallet's IP, step 3 alone can be 3–10 seconds or fail. Plan budgets 2–5s and local sign time is ~100ms; everything over 500ms is *network-side*, which you don't control on a public endpoint.

Arbitrum public RPC "limits requests to prevent DoS" (Offchain Labs docs). No published rate-limit numbers in the current docs (confidence MEDIUM), but practitioner consensus is that `eth_sendRawTransaction` from an unknown wallet on public endpoints is deprioritized vs. private ones.

**Why it happens:** "Local bot on local machine" sounds like 0-RTT to the chain. It's not. The bot's outbound network to the sequencer is the bottleneck.

**Warning signs:**
- Cancel latency histogram: p50 < 1s, p95 > 5s, p99 > 10s. Fat tail means network, not code.
- Cancel txs periodically fail with `429` or `503` from RPC.
- Paper-mode cancel-latency median differs from live median by >2× — live has higher load or different IP reputation.

**Prevention (concrete):**
- **Phase 8 task:** Measure latency decomposition explicitly. Instrument each of the 5 steps. Log histogram per hour. If step (3) p95 > 2s, switch RPC providers.
- **Phase 8 task:** Configure *two* RPC providers: primary (private, paid — e.g., Chainstack / Alchemy / QuickNode dedicated Arbitrum endpoint) + fallback (Offchain Labs public). Health-check the primary every 30s; failover on consecutive failures or on step-(3) latency > 3s.
- **Phase 10 task:** Before scaling past $100, upgrade to private RPC is a ship-gate. $100 operator can run public RPC because one lost cancel is $0.50, not $50.

**Phase to address:** 8 (RPC measurement + failover), 10 (private-RPC gate).

---

### C3: Hot agent-wallet key exposure on macOS local [NEW vs plans — wallet model covered, key storage not]

**Severity:** Medium (at $100) / Catastrophic (at scale).

**What goes wrong:** Agent wallet private key needs to sign frequently (every place + every cancel). Storage options on macOS local: (a) plaintext file — obvious fail, (b) OS keychain via `security` CLI — safer but keychain lookup every sign is slow (~20–50ms), (c) in-memory after one keychain fetch — fast but persists in RAM indefinitely, (d) a YubiKey / hardware module — high friction for a bot. Plans don't specify. If a malicious dependency, compromised developer tool (VSCode extension, homebrew package), or process-inspection malware gets file/memory access, it extracts the key and drains the agent wallet. Root wallet is cold per the plan, but whatever the agent holds — and it holds gas + collateral — is at risk.

macOS-specific: any process with your UID can `ptrace` your bot's memory with one-time TCC prompt unless hardened. Homebrew-installed Python is not hardened by default.

**Why it happens:** "Local" is assumed safe. It's safer than cloud but not safe; macOS's default process isolation is permissive.

**Warning signs:**
- Bot run under a process debugger (`ptrace`, `lldb`) reveals the key plaintext in heap dump within seconds.
- `ps` or `lsof` shows unexpected child processes spawned by the bot process.
- Agent wallet balance changes without a corresponding bot log entry.

**Prevention (concrete):**
- **Phase 8 task:** Key stored in macOS Keychain (encrypted at rest), fetched once on bot start, held in memory for bot lifetime. No plaintext file, ever. `.env` contains *no* private keys — only wallet addresses (for reference) and references to keychain entries.
- **Phase 8 task:** Agent wallet holds only `max(gas_for_1_week, collateral)` — nothing else. Root wallet tops up agent weekly, not keeps bulk on agent.
- **Phase 8 task:** Bot binary / script runs with a dedicated non-admin macOS user account (operator creates `borosbot` user), not the main developer user. Cross-process memory access is much harder across users.
- **Phase 10 task:** Before scaling past $500, migrate to a Safe (multi-sig) or hardware-signer model where the hot key is a *session key* scoped to trading actions only (Pendle SDK supports this via the Send Txs Bot / session-key pattern). $100 operator can skip this.

**Phase to address:** 8 (keychain + user isolation), 10 (session-key scale-gate).

---

### C4: WebSocket reconnection storms [NEW vs plans — not mentioned]

**Severity:** High (once triggered).

**What goes wrong:** WebSocket disconnect (ISP blip, macOS sleep/wake, server-side restart) triggers reconnect. Naive retry-immediately loop hits Boros WS server with tight-loop connection attempts. Server rate-limits or blacklists the IP. Bot is disconnected for 5+ minutes while its orders rest exposed and un-monitored. If a fill happens in that window, the cancel-of-the-fellow-orders logic doesn't fire — one fill can cascade to multiple.

Additionally: reconnect-and-replay. On reconnect, bot must re-request recent fills, reconcile local state against server-reported order statuses, and not double-cancel already-cancelled orders. Skipping reconciliation causes ghost orders (bot thinks they're live, they're not → no rewards) or phantom cancels (bot cancels twice, wastes gas, may trigger wallet-level nonce issues per C1).

**Why it happens:** "WebSocket reconnect" feels trivial. Backoff discipline, state reconciliation, and disconnect-window risk management are the real work.

**Warning signs:**
- Bot log shows >3 WS reconnect attempts in 10s — no backoff.
- On reconnect, bot doesn't log a "state reconciliation" event — silent drift.
- Fill events received after a reconnect don't match local order-state.

**Prevention (concrete):**
- **Phase 8 task:** WS client uses exponential backoff — 1s, 2s, 4s, 8s, 16s, 30s cap. After 60s of continuous failure, cancel all orders via HTTP (separate code path, not the pre-signed chain) and pause until WS is healthy for 60s continuously.
- **Phase 8 task:** On every reconnect, bot fetches `GET /v2/accounts/my-orders` (or equivalent) and reconciles against local state before processing any new WS events. Any mismatch → log + pause for manual review.
- **Phase 8 task:** macOS `caffeinate` wrapper on the bot command prevents sleep. `launchd` job restarts on exit. Disconnect window monitored and alerted if > 30s.

**Phase to address:** 8 (backoff + reconciliation + caffeinate).

---

### C5: Merkle claim failing silently [NEW vs plans — "claim Monday" mentioned, failure modes not]

**Severity:** Medium.

**What goes wrong:** Weekly Merkle claim polls distributor contract, submits `claim(merkleProof)` tx. Failure modes: (a) Merkle root hasn't been updated yet (timing assumption wrong — "typically Monday" can slip), tx reverts with `InvalidProof`, (b) tx succeeds but claim amount is zero because bot's epoch contribution was zero (A1, A2, A3 all possible causes), (c) tx fails on reorg — rare on Arbitrum but possible when the distributor is a cross-L1/L2 contract, (d) RPC returns stale state and the bot submits against a Merkle root that was just superseded.

If this fails silently, weeks of reward go unclaimed. They don't expire immediately but there may be an epoch-expiry window (check docs — not confirmed in plans).

**Why it happens:** Claim code path runs once a week. It's the least-tested code path by volume. Silent failures accumulate.

**Warning signs:**
- `claim` tx receipt success: true but amount: 0.
- Bot log doesn't have a line like "Claimed N PENDLE for epoch W" every Monday.
- On-chain balance of PENDLE on agent wallet doesn't increase week-over-week.

**Prevention (concrete):**
- **Phase 8 task:** Claim logic has retry with backoff (same as C4) and waits until `distributor.root() ≠ last_claimed_root` before submitting. If >72h post-epoch-end passes without a new root, alert ("Merkle update overdue — check Pendle status").
- **Phase 8 task:** Every claim tx is verified post-confirmation: check PENDLE balance delta = expected claim amount (within dust). Mismatch is a hard alert.
- **Phase 8 task:** Backup path — if on-chain claim fails 3× in a row, bot emits a manual-claim instruction (the Merkle proof + calldata) to the operator's logs so the operator can submit from a wallet / Safe UI manually.
- **Phase 10 task:** Merkle claim reconciliation is part of weekly report; any missed week blocks scale-up.

**Phase to address:** 8 (retry + verify + backup), 10 (reconciliation gate).

---

### C6: Gas balance runs dry mid-day → uncancellable orders [NEW vs plans — mentioned vaguely L332 "auto-maintained"]

**Severity:** Catastrophic.

**What goes wrong:** Agent wallet runs out of ETH for gas. Bot tries to cancel on a fill alert — cancel tx rejected by mempool (`insufficient funds for gas`). Order stays live, more fills happen, inventory grows unbounded, account heads toward maintenance margin. Root wallet has ETH but there's no automated bridge in the critical path — the plan says "maintained" but not "maintained from what source on what trigger."

On Arbitrum, gas is cheap ($0.01–0.05 per simple tx), which is the point. That makes it *easy* to forget gas exists. $5 worth of ETH lasts weeks; but weeks later, no one remembers to top up.

**Why it happens:** Gas-balance check is orthogonal to strategy logic. Easy to skip.

**Warning signs:**
- Agent wallet ETH balance < 0.005 ETH and no alert fired.
- Cancel tx fails with `insufficient funds` ever — means the warning threshold is wrong.
- Gas-balance-over-time line in logs is absent.

**Prevention (concrete):**
- **Phase 8 task:** Bot checks gas balance every minute. Alert at `balance < 50 × p95(gas_per_cancel)` — operator has time to act. Halt *new order placements* at `balance < 20 × p95(gas_per_cancel)` — can still cancel existing, won't dig deeper. Emergency `cancelAll` at `balance < 5 × p95(gas_per_cancel)`.
- **Phase 8 task:** Manual top-up procedure documented in the runbook. No cloud automation for $100 operator — "send 0.01 ETH from root to agent" is a 30-second operator task when the alert fires.
- **Phase 8 task:** `RUN_MANIFEST` includes `agent_wallet_gas_balance_at_start` as a first-class field. Low-balance-start runs are flagged and short-circuited.

**Phase to address:** 8 (balance monitor + manifest field + runbook).

---

### C7: Clock drift between bot and chain [NEW vs plans — not mentioned]

**Severity:** Medium.

**What goes wrong:** Bot's wall-clock is used for epoch-boundary logic (is it Friday 00:00 UTC yet?), oracle-staleness check (`now − fTime > 0.7 × maxUpdateDelay`), and EV time-remaining-in-epoch. Chain uses block timestamp, which for Arbitrum is sequencer time, close-to but not identical to UTC. macOS laptop that's been sleeping or has drifted NTP can be off by seconds to minutes. If bot's `now` is 30s ahead of chain time, oracle-staleness breaker fires early (false positive — cancels everything unnecessarily). If bot's `now` is 30s behind, staleness fires late (false negative — may place orders against stale oracle).

Epoch-boundary bugs are worst: bot places an order at "23:59:58 UTC" thinking it's in the old epoch, chain stamps it in the new epoch, operator's records disagree with reality.

**Why it happens:** macOS NTP is mostly reliable but not monitored. Laptop sleep/wake can desync briefly.

**Warning signs:**
- `abs(bot_time − arbitrum_block.timestamp) > 2s` at any point — likely drift.
- Epoch-boundary orders show up in the wrong epoch's accounting.
- Oracle-staleness breaker fires when the operator can see (on-chain) the oracle updated 3s ago.

**Prevention (concrete):**
- **Phase 8 task:** All time comparisons use `chain_time` (from an `eth_blockNumber`+`eth_getBlockByNumber(latest).timestamp` query cached with 1s freshness), not `time.time()`. Only exception: internal logging timestamps.
- **Phase 8 task:** Bot startup check: query chain time, compare to system time, refuse to start if drift > 5s. Operator knows before trading that their clock is wrong.
- **Phase 8 task:** `RUN_MANIFEST` includes `chain_time_drift_at_start_seconds`.

**Phase to address:** 8 (chain-time-as-source-of-truth + startup check + manifest field).

---

## D. Protocol Pitfalls (Cross-Cutting — PROJECT.md "Engineering Protocols")

The three engineering protocols in PROJECT.md (Wiki / Dependency diagram / Run manifest) are themselves prone to specific failure modes that make them *appear* to be followed while silently degrading. Each is listed below.

### D1: LLM Wiki not checked first → session rediscovers resolved question [NEW vs plans — protocol stated, failure mode not]

**Severity:** Medium (compounds over many sessions).

**What goes wrong:** Protocol #1 says "check the wiki first." An agent skips the check because the question feels general ("what's an OU process?") when it's actually specific ("what did we decide about OU on basis for Boros?"). Agent re-derives conclusions already in the wiki, sometimes arriving at a *different* answer because they lacked context of prior discoveries. Decisions drift; wiki becomes fictional — stated to be authoritative, not actually consulted.

**Why it happens:** Wiki-check discipline is easy to pay lip service to. No enforcement mechanism.

**Warning signs:**
- Agent output doesn't cite any `[[page-name]]` links.
- A research task produces a recommendation that contradicts an existing wiki page without explaining why.
- Wiki page count grows but each page restates the same conclusion from a slightly different angle.

**Prevention (concrete):**
- **Phase 0/1 task:** Seed the wiki *before* Phase 2. Every research task thereafter is prompted with "you MUST cite at least one wiki page or explicitly state 'no relevant page found and here's the new page I'm filing'." Task templates enforce this.
- **All phases, ongoing:** Grep/linter on research deliverables: `grep -c "\[\[" deliverable.md` must be > 0, or the file has a justification comment.
- **Continuous:** After every task, agent writes back findings. `lint_engine --check-writeback` catches empty writebacks.

**Phase to address:** Cross-cutting, starts Phase 0.

---

### D2: RUN_MANIFEST missing fields → log analysis fabricates conclusions [NEW vs plans — protocol #3 risk]

**Severity:** High (silent).

**What goes wrong:** Strategy version tag is stamped, but a new knob gets added to the engine and the author forgets to add it to the manifest schema. Every run logs the other knobs; this new one has a default that's never surfaced. Later, backtest vs paper divergence gets analyzed — analysis assumes both runs used the same value for the missing knob because the manifests don't distinguish, but in reality backtest used default `X`, paper used a manually-patched `Y`. Analysis concludes "execution pipeline differs from simulation" when actually the code was configured differently. Engineer chases a ghost.

**Why it happens:** Manifest schema is human-maintained. New knob adder doesn't update schema. No compile-time enforcement unless schema is the single source of truth.

**Warning signs:**
- Manifest JSON has fewer fields than `git grep 'Config\.'` finds references to.
- Backtest and paper both "succeed" but P&L differs unexpectedly; knob comparison shows identical manifests.
- A new knob default is set in code without a corresponding migration note.

**Prevention (concrete):**
- **Phase 1 task:** Config schema (Pydantic model) is the single source of truth. Manifest generator *reads the schema by reflection*, not a hand-maintained list. Adding a knob automatically adds it to the manifest.
- **Phase 1 task:** Pre-commit hook: `test_manifest_contains_all_knobs` — run a dummy bot init, confirm the manifest JSON contains all fields from the Pydantic schema. Fails → commit rejected.
- **Phase 7+ task:** Any log-analysis tool refuses to compare two runs whose manifest schemas differ in *field set* (not just values) without explicit operator acknowledgement.

**Phase to address:** 1 (schema-driven manifest + hook), 7+ (analysis tool).

---

### D3: Dependency diagram diverges from code → blast-radius reviews become fiction [NEW vs plans — protocol #2 risk]

**Severity:** High (in review workflow).

**What goes wrong:** Protocol #2 says diagram updates atomically with code. In practice, atomicity requires discipline: agent edits `src/fill_model.py` to add a new input feature, marks the PR as "small change, diagram untouched." Reviewer sees the code + unchanged diagram, traces the blast radius on the old diagram, concludes "this only affects Phase 2 — ship it." But the new feature pulls from the underlying-APR pipeline, which is a node the diagram didn't connect. When underlying-APR changes cadence, fill_model silently breaks. The review *said* the blast radius was known; it wasn't, because the diagram lied.

**Why it happens:** "Atomic update" is a norm, not a mechanical enforcement. Every dropped update is invisible until much later.

**Warning signs:**
- `git log --oneline docs/ARCHITECTURE.md` shows fewer commits than `git log --oneline src/`.
- Reviewer comment "let me trace blast radius" without referencing specific diagram nodes.
- A bug post-mortem traces to a dependency not drawn in the diagram.

**Prevention (concrete):**
- **Phase 1 task:** `architecture.yml` (machine-readable manifest) is the ground truth. Write a linter `architecture_lint.py` that: (a) parses `src/` for imports/calls and compares to the `yml` graph, (b) flags code edges not in the yml, (c) flags yml edges not in code. Pre-commit hook rejects on mismatch.
- **Phase 1 task:** PR template requires the author to list *affected graph nodes* and *blast-radius nodes* as a separate checklist item. Reviewer can verify against the yml.
- **Continuous:** Every bug post-mortem includes "was the relevant edge in the diagram?" as the first question. Answer "no" triggers a diagram-audit sprint.

**Phase to address:** 1 (linter + hook), Continuous (post-mortem gate).

---

### D4: Config schema drift across backtest / paper / live [NEW vs plans — not explicitly called out]

**Severity:** High.

**What goes wrong:** Backtest uses a knob `max_position_size = 0.1`. Paper code adds a knob `max_position_size_usd = 100` which supersedes the fractional one, but only in paper config. Live deploys from paper config and has `max_position_size_usd = 100`, which happens to equal the backtest's `max_position_size = 0.1 × $1000 = $100` at the backtest's test capital of $1000 but *not* at the operator's $100 real capital. Live deploys with effective 100% position size. First fill takes out the entire collateral.

This is the canonical "config schema drift" bug. It happens across exactly the backtest → paper → live pipeline that this project is organized around.

**Why it happens:** Three Pythonic configs (Pydantic models) in three places, maintained separately. Each phase adds a knob that solves its own problem; nobody integrates.

**Warning signs:**
- More than one `Config` class in the codebase.
- A knob with similar name (`max_position`, `max_position_usd`, `max_position_size`) appears in multiple modules.
- Paper run uses a config file that the backtest can't parse.

**Prevention (concrete):**
- **Phase 1 task:** Single Pydantic config class, hierarchical by mode (e.g., `BotConfig` with fields `mode: Literal['backtest', 'paper', 'live']`, `backtest: BacktestConfig | None`, `paper: PaperConfig | None`, `live: LiveConfig | None`). All three modes read the same config class. Missing mode-specific section → default, not fork the schema.
- **Phase 1 task:** `config_schema_test.py` — round-trip every config file through the schema, assert no warnings. Pre-commit hook.
- **Phase 7 task:** Backtest run logs the full resolved config tree (from D2's reflection-based manifest). Paper/live do too. Comparison tool for "is this the same knob value across modes" is trivial.
- **Phase 9/10 task:** Gate: before live, run paper with *exactly* the live config (via `--mode live-dry-run`). Any `KeyError` or `ValueError` → config schemas drifted.

**Phase to address:** 1 (single-source schema + hook), 7/9/10 (comparison tool + dry-run gate).

---

### D5: Wiki decay — no write-back when task is rushed [NEW vs plans — EXTENDS protocol #1]

**Severity:** Medium (compounds slowly).

**What goes wrong:** Agent finds something surprising during a Phase 4 sizing calibration — say, `Q_cap` formula has a corner case at `collateral_me = 0`. Tests pass with the fix, PR merges, agent moves on. Wiki never gets the discovery. Next session, different agent, same edge case — time spent rediscovering. 10 sessions later, the wiki has 5 pages but there should be 25. The wiki is *partially* useful, which is worse than being known-incomplete, because people trust its completeness.

**Why it happens:** Write-back is the last step. Under time pressure the last step is the one that gets skipped.

**Warning signs:**
- Ratio of PRs merged to wiki pages filed is > 3:1 on non-trivial PRs.
- A bug fix commit mentions a subtle edge case; no corresponding wiki page is added or updated.
- Post-mortem contains "we've seen this before" without a prior wiki page on the prior occurrence.

**Prevention (concrete):**
- **Ongoing:** PR template requires a "Wiki page filed or updated: [[page-name]] or N/A with justification" field. PRs without this get auto-reject from CI (a GitHub Action or pre-push hook for a local workflow).
- **Weekly:** Operator does a 15-minute wiki review — for every merged PR without a wiki write-back, spend 2 minutes asking whether one should exist. Fill in retroactively.
- **Phase 7/9/10:** Every post-mortem is filed as a wiki page in `Known issues & failed hypotheses`. The existence of a post-mortem doc elsewhere without a wiki entry is a protocol breach.

**Phase to address:** Cross-cutting, continuous.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single config class file instead of schema-per-mode with dry-run gate | Skip 1 day of Phase 1 | Config drift (D4); $100 wipeout possible at live transition | Never — Phase 1 must-have |
| Skip `eventIndex` assertion, trust one-market sample | Skip 0.5 day data pipeline work | Silent CV miscalculation on thin markets; wrong model class picked | Never — it's a 30-line assertion |
| Cache `E_liq_per_epoch` per market per day instead of polling | Simplify Phase 4 | Miss per-side budget rebalancing (A2); over-estimate reward | Never — plan already forbids |
| Use public Arbitrum RPC for live | Save ~$50/mo | Cancel latency blowouts (C2); p99 > 10s | At $100 capital only; mandatory to upgrade before $500 |
| Hand-maintained manifest schema instead of reflection from Pydantic | Save 0.5 day Phase 1 | Silent missing-knob analysis bugs (D2) | Never — reflection is a one-day setup |
| Plaintext private key in `.env` for "development" | Skip keychain setup | Any dependency leak → wallet drain (C3) | Never — use keychain even in dev |
| Hardcoded single RPC endpoint | Skip failover logic | Single-provider outage = total trading halt | Acceptable only in backtest; not in paper or live |
| Skip bootstrap resampling in backtest output | Skip 0.5 day Phase 7 | Fragile-strategy false positive (B7) | Never — ship gate requires it |
| Rolling 14-day OU fit without ADF check | Skip 1 day Phase 3 | Regime-shift blind spot (B5); wrong loss estimates | Acceptable in v0.5 if empirical-only loss is used as fallback |
| Wiki writeback deferred to "later" | Save 10 min per PR | Wiki decay (D5); compounds to weeks of rediscovery | Never past Phase 1 seeding |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Arbitrum public RPC | Treat as zero-latency, production-grade | Private RPC for live (paid) with public as fallback; instrument latency per step |
| Boros WebSocket | Naive `while True: reconnect()` tight-loop | Exponential backoff + state reconciliation on reconnect + 60s health window before resuming |
| Pendle SDK `@pendle/sdk-boros` (TS) ↔ Python models | File-based IPC with implicit schema | Explicit schema (Pydantic ↔ Zod from the same source-of-truth, e.g., JSON schema); versioned; log schema version in RUN_MANIFEST |
| Send Txs Bot / agent wallet | Pre-sign all cancels at placement time with sequential nonces | Choose nonce model (same-nonce / sign-at-decision / pre-sign-batch) explicitly per C1; document in ARCHITECTURE.md |
| Merkle distributor contract | Submit claim on Monday regardless of on-chain root state | Poll `distributor.root()`, submit only when root ≠ last-claimed; retry with backoff; verify balance delta post-confirmation |
| Underlying CEX funding-rate feeds | Trust feed freshness unconditionally | Track feed age + z-score outliers; circuit-break on stale/outlier (A7) |
| Historical reward-budget reconstruction | Assume current budget applies to backtest | Reconstruct from distributor events if possible; else mark pre-live data as "current-budget synthetic" and discount |
| macOS local deployment | `caffeinate` not wrapped; laptop sleeps | `launchd` job with `KeepAlive`; `caffeinate -i` wrapper; alert on disconnect > 30s |

---

## Performance Traps

Small-capital (not scale) traps relevant at $100:

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Gas per cancel/claim > reward accrual rate | Weekly Merkle claim < gas spent on cancels that week | Log gas cost / weekly reward claim ratio; if >10%, size is too small or cancel frequency too high | Already at $100 if cancels fire > 5×/day |
| Python model latency exceeds cancel-latency budget | Local decision step (C2 step 2) is > 500ms | Profile per decision; hot-path must be numpy, not pandas; JIT-compile Hawkes intensity computation | At >50 decisions/second, or at any latency if fill cascades |
| OU refit on every decision instead of on-schedule | CPU pegged, latency degrades | OU refit once per hour on the rolling window, cache θ/μ/σ; use cached values for EV | At any production volume |
| Full order-book snapshot on every WS event | Memory bloat, GC pauses | Incremental book updates from WS deltas; periodic resync from REST snapshot | At >10 WS events/sec sustained |
| `pandas` for per-trade replay in backtest | Replay of 72K trades/market takes hours | Vectorized numpy per-tick; pandas only for aggregation/reporting | At >1 market or >30 days of replay |

---

## Security Mistakes

Domain-specific (DeFi / on-chain bot), not generic:

| Mistake | Risk | Prevention |
|---------|------|------------|
| Agent private key in `.env` or committed config | Wallet drained on any dep leak | Keychain only; `.env` has references not keys; pre-commit hook blocks hex strings matching private-key pattern |
| Root wallet holds session-key approvals for agent beyond scope | Agent compromise drains root | Agent approval scoped to Boros trading contracts only, with per-market allowance and time-bound expiry |
| RPC endpoint URL with API key in logs | Log leak → RPC usage hijack, rate-limit DoS | URLs with keys are env-only; log redacts all query-string secrets |
| Merkle claim on unverified `merkleProof` from a 3rd-party API | Malicious proof → loss of claim ability (if revert is charged) | Construct proof locally from distributor contract state, not from external API |
| Agent wallet funded with > 2 weeks of operating capital | Theft loss exceeds recovery tolerance | Weekly top-up from root; agent holds `gas_buffer + collateral` only |
| Code signing: homebrew-installed Python is the "ok to run" default | Compromised homebrew package runs with UID access | Run bot under a dedicated `borosbot` macOS user with no admin privileges |
| WebSocket server-cert not verified (TLS opt-out for "dev convenience") | MITM can inject fake fill events → bot cancels real orders / submits bad cancels | TLS cert verification always on; pin the cert fingerprint in production config |
| Pre-signed cancel calldata stored in plaintext log | Log leak → future replay attack? (limited, nonce-bound) | Never log the signed tx; log tx hash + intent only. Pre-signed blobs live in memory only |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces specific to this project:

- [ ] **EV cancel rule:** Often missing the `fee_cost` term (A6) and the `forfeited_accumulation` term (A1). Verify both branches are in the final equation.
- [ ] **Reward share sizing:** Often missing live `E_liq_per_epoch` polling (A2) — snapshot-based sizing is wrong. Verify the polling loop runs in paper.
- [ ] **Backtest:** Often missing `eventIndex`-based ordering (B2), AMM conservation check (B3), bootstrap-resampled P&L (B7), historical-vs-current budget A/B (B6). Verify each is a line in the output report.
- [ ] **Hawkes fit:** Often missing convergence diagnostics and `α > 0` gate (B4). Verify fit health checks are in the model-selection flow.
- [ ] **OU fit:** Often missing ADF test (B5). Verify every fit has a stationarity pass.
- [ ] **Queue tracking:** Often missing bias-direction diagnostic at snapshot reconciliation (B1). Verify the sign of drift is logged.
- [ ] **Pre-signed cancel:** Often missing nonce-model decision doc (C1). Verify the nonce model is explicit in `docs/ARCHITECTURE.md`.
- [ ] **Cancel latency budget:** Often missing 5-step decomposition (C2). Verify instrumentation names each step.
- [ ] **Agent key storage:** Often defaults to plaintext `.env`. Verify keychain integration is live, not future work.
- [ ] **WebSocket reconnect:** Often missing state reconciliation. Verify reconnect emits a reconciliation log line.
- [ ] **Merkle claim:** Often missing post-claim balance verification. Verify the PENDLE balance delta check is in the claim path.
- [ ] **Gas monitoring:** Often missing the three-level alert/halt/emergency structure (C6). Verify all three trigger in a paper test.
- [ ] **Clock drift:** Often uses `time.time()` throughout. Verify all chain-relevant logic uses the chain-time cache (C7).
- [ ] **RUN_MANIFEST:** Often stale relative to the config schema. Verify reflection-based generation is wired (D2).
- [ ] **Config schema:** Often forked across modes. Verify single Pydantic class with mode-specific sections (D4).
- [ ] **Dependency diagram:** Often out-of-date with code. Verify `architecture_lint.py` passes on current `main` (D3).
- [ ] **Wiki:** Often lagging PRs. Verify ratio of merged PRs to wiki pages filed is reasonable (D5).
- [ ] **Circuit breakers:** Often reactive, not predictive. Verify each breaker operates on an extrapolated trajectory, not a realized threshold.
- [ ] **Shortlist:** Often a snapshot. Verify daily auto-re-screen during engineering (A5).

---

## Recovery Strategies

When pitfalls occur despite prevention:

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| A1 (voluntary-cancel forfeits) confirmed `True` mid-paper | MEDIUM | Rerun backtest with the flag; decide if remaining phase budget can accommodate the lower P&L; if not, kill and document wiki page `Known issues: forfeit-branch strategy dead` |
| A2 (budget rebalance) observed | LOW-MEDIUM | Reduce sizing to the lower of current-side budget-weighted optimum; update wiki with observed rebalance cadence |
| A5 (competition crowded in) | LOW | Re-screen; if no market passes, pause indefinitely with weekly automated re-screen continuing |
| A7 (underlying outlier) | LOW | Breaker cancels all; wait 6h; refit OU; resume |
| B2 (`eventIndex` missing live) | HIGH | Blocks Phase 8+ — escalate to Boros team before re-engineering workaround |
| B3 (AMM double-count) | MEDIUM | Re-verify one epoch of replay by hand against on-chain data; fix subtraction; re-run backtest |
| B7 (fragile P&L) | HIGH | Do not deploy. Either find a wider robust region or abandon the strategy on that market |
| C1 (nonce chain stuck) | LOW (per incident) | Cancel via HTTP fallback (not pre-signed chain); manually bump nonce with self-transfer; reset pre-signed queue |
| C2 (RPC latency spike) | LOW | Failover to secondary RPC; investigate primary |
| C3 (agent key suspected leaked) | HIGH | Immediate root-wallet `revokeApproval` on Boros contracts; drain agent to root; rotate agent keypair; root never exposed |
| C4 (WS storm) | LOW | 60s backoff already applied by breaker; if not, kill process, manually verify order state via REST, restart |
| C5 (Merkle claim silent fail) | LOW-MEDIUM | Manual claim via operator wallet using logged Merkle proof; investigate why auto-claim failed |
| C6 (gas empty) | LOW | Operator tops up root → agent; if fills happened, close each manually at market |
| D1 (wiki not checked, duplicate work) | LOW | Wiki audit; merge duplicate pages; add prior-art link |
| D2 (manifest missing fields, analysis fabricated) | HIGH | Any analysis produced against missing-field manifests is discarded; rerun with fixed manifest generator |
| D3 (diagram divergence causing review miss) | HIGH | Incident post-mortem; diagram audit sprint; hook enforcement check |
| D4 (config drift, wrong live sizing) | CATASTROPHIC | If caught pre-fill: halt, reconcile configs, restart. If post-fill: close immediately, restart at min size, full post-mortem before re-enabling any scaling |

---

## Pitfall-to-Phase Mapping

How roadmap phases should prevent each pitfall.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| A1 Voluntary-cancel forfeit | 0 (resolve), 5 (flag), 7 (sensitivity) | Sensitivity row in Phase 7 report; wiki page `Voluntary cancel reward preservation` |
| A2 Per-side budget rebalance | 1 (log), 4 (sizing), 6 (breaker) | Polling log + stress-case output in Phase 4 report |
| A3 CLO shift + forfeit compound | 1 (screener), 5 (EV branch), 7 (sensitivity) | Intra-epoch shift distribution in Phase 1 output; EV branch test |
| A4 1000% APR cap non-linearity | 4 (plot), 7 (regime report), Wiki | `R_capped(Q_me)` plot in screener output; regime label in all runs |
| A5 Competition crowd-in | 1 (daily re-screen), 6 (pre-deploy gate), 9/10 (gate check) | Daily screener output file; CI gate on re-screen before Phase 9 |
| A6 Fee structure in EV | 0 (fee wiki), 5 (EV term), 7 (line item) | Wiki page; EV equation has `fee_cost` term; Phase 7 report has fees line |
| A7 Underlying outlier / halt | 3 (robust MLE), 6 (3 breakers) | Breaker tests in Phase 6 suite |
| A8 Outside-range wall | 1 (screener), 2 (covariate), 7 (accrual-time report) | Screener flag; accrual-time % in Phase 7 |
| B1 Queue drift direction | 2 (bias measurement), 7 (calibration-by-offset) | Signed drift log; split calibration plot |
| B2 `eventIndex` coverage | 1 (ingest assert), 8 (live WS check), Wiki | Assertion test passes for all markets; wiki page |
| B3 AMM double-count | 1 (ingest assert), 2 (conservation check), 7 (sensitivity) | Conservation identity test in CI |
| B4 Hawkes MLE failure | 1 (CV CI), 2 (fit diagnostics) | Fit-health gates in model selection; class-stability metric |
| B5 OU regime shift | 3 (fit diagnostics), 6 (sizing breaker) | ADF check in every OU fit; residual-kurtosis alert |
| B6 Historical reward bias | 1 (budget time-series), 7 (A/B), 9 (reconcile) | A/B P&L line in Phase 7; reconciliation check in Phase 9 |
| B7 Fragile P&L region | 7 (bootstrap + gate), 9 (perturbation) | Bootstrap 5th percentile > threshold ship-gate; perturbation runs |
| C1 Nonce chain | 8 (nonce model doc), 9 (multi-order test) | ARCHITECTURE.md has explicit nonce section; Phase 9 test case |
| C2 RPC latency | 8 (measurement + failover), 10 (private-RPC gate) | Per-step histogram in logs; health-check failover test |
| C3 Agent key exposure | 8 (keychain + user isolation), 10 (session-key gate) | Keychain integration; `borosbot` user runs bot |
| C4 WS reconnect storm | 8 (backoff + reconciliation) | Reconnect backoff unit test; reconciliation log on every reconnect |
| C5 Merkle claim silent fail | 8 (retry + verify + backup), 10 (reconciliation gate) | Claim path has balance-delta check; weekly report reconciliation |
| C6 Gas empty | 8 (3-level monitor + runbook) | 3 thresholds trigger in paper test |
| C7 Clock drift | 8 (chain-time source + startup check) | Startup check rejects > 5s drift; no `time.time()` in chain-relevant code |
| D1 Wiki not checked | 0/1+ ongoing | Research deliverables cite `[[pages]]` or add new one |
| D2 RUN_MANIFEST missing fields | 1 (schema + hook) | Pre-commit hook test; manifest reflects schema |
| D3 Diagram drift | 1 (linter + hook), continuous | `architecture_lint.py` passes; PRs list affected nodes |
| D4 Config schema drift | 1 (single schema), 7/9/10 (dry-run gate) | Schema round-trip test; `--mode live-dry-run` gate before live |
| D5 Wiki decay | continuous | PR template checklist; weekly wiki review |

---

## Sources

- `/Users/macbookair/Documents/project/test/rerun7/boros/.planning/PROJECT.md` (constraints, engineering protocols, open Phase 0 questions — L79-83, L85-113, L114-125)
- `/Users/macbookair/Documents/project/test/rerun7/boros/boros_consolidated_plan.md` (consolidated plan; kill-condition table L399-413; Phase 0 L34-81; Phase 4 sizing L209-253; Phase 6 breakers L294-308; anchor ETHUSDT 29-May L67, L227, L229)
- `/Users/macbookair/Documents/project/test/rerun7/boros/boros_bot_guide.md` (Risk framework L252-323; Minimum answers-required L324+)
- `/Users/macbookair/Documents/project/test/rerun7/boros/plan_comparison.md` (NDJSON data inspection; CV diagnostics L234-268; hourly snapshot nuance L298-306; open items L322-327)
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md` (wiki index — empty, seeding plan L47-53)
- Arbitrum Docs — RPC methods, rate-limit behavior on public endpoints ([docs.arbitrum.io/build-decentralized-apps/reference/node-providers](https://docs.arbitrum.io/build-decentralized-apps/reference/node-providers), [docs.arbitrum.io/for-devs/troubleshooting-building](https://docs.arbitrum.io/for-devs/troubleshooting-building)) — informs C2.
- Ethereum nonce semantics / pre-signed tx constraints (Quicknode nonce guide, Etherscan cancel guide) — informs C1.
- Practitioner consensus on cross-block sequencer ordering, `eventIndex` usage on Arbitrum — informs B2.

---
*Pitfalls research for: Pendle Boros limit-order reward-farming bot (Python + TypeScript, Arbitrum, local macOS)*
*Researched: 2026-04-23*
