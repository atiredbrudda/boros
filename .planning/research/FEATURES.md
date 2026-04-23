# Feature Research — Boros Reward-Farming Bot

**Domain:** On-chain limit-order reward-farming bot (Pendle Boros IRS CLOB, Arbitrum, single-user personal deployment)
**Strategy thesis:** Avoid-fills; harvest only the Limit Order Liquidity Rewards pool (size × time-in-range); ignore the Maker Volume pool by design
**Researched:** 2026-04-23
**Confidence:** HIGH on consolidated-plan features (doc is the canonical spec + already verified against live data); MEDIUM on comparative framing against other on-chain MM bots
**Inputs:** `boros_consolidated_plan.md` (Phases 0–10, source of truth), `boros_bot_guide.md` (platform ref + risk framework), `plan_comparison.md` (NDJSON inspection, per-market CV), `PROJECT.md` (scope, protocols)
**Wiki pages consulted:** `workspaces/boros/wiki/index.md` (seed-only — no pages filed yet; seeding is Phase 0/1 work)

---

## Scope reminder (from PROJECT.md)

- Single-user personal bot, one wallet pair, CLI + notebooks only.
- $100 starting collateral — **sub-cap regime on every market**; size at protocol minimum; one side at a time.
- v0.5: NHPP fill model + one market. v1.0: per-market model selection (Hawkes/NHPP/RP based on CV) across the shortlist.
- Engineering Protocols are cross-cutting features, not optional polish: Wiki-first (LLM Wiki), state-chain diagram (`docs/ARCHITECTURE.md`), RUN_MANIFEST on every run.

This file classifies every feature in the consolidated plan, plus surfaces features common to the broader on-chain MM / reward-farming class that the plan doesn't include — so REQUIREMENTS.md can decide include/exclude explicitly rather than by omission.

---

## Feature Landscape

### Table Stakes — v0.5 must-haves (if missing, strategy is broken)

These are the features without which either (a) the bot cannot operate at all, (b) the bot operates but the thesis cannot be tested, or (c) silent-drift / unsafe-state risks are unacceptable at real capital.

| # | Feature | Phase | Why Non-Negotiable | Complexity |
|---|---------|-------|-------------------|------------|
| TS-01 | Boros REST client + market config loader (`GET /markets`) | 1 | Without market config (cloLower/Upper, iTickThresh, oracle address, maxOpenOrders), no order placement is legal. | S |
| TS-02 | `fIndexOracle` on-chain reader (`getLatestFIndex()`, `latestAnnualizedRate()`) with byte-decoding | 1 | CLO threshold conversion to APR requires the live fIndex; no APR → tick conversion possible without it. | M |
| TS-03 | Hourly raw order-book snapshot ingestion + wei→float conversion | 1 | Exact queue-state anchors for backtest replay; without these, P&L is pure fiction. | S |
| TS-04 | Market-trades tape ingestion with `eventIndex` intra-block ordering | 1 | Arbitrum blocks are ~250ms, multiple trades per block; `blockTimestamp` alone ties and breaks Hawkes/NHPP calibration. | S |
| TS-05 | Combined book+AMM snapshot ingestion | 1 | AMM share = `combined − raw`; needed to subtract AMM consumption from taker flow. | S |
| TS-06 | Underlying APR ingestion (Binance/OKX/Hyperliquid) | 1 | Basis `B = Implied − Underlying` is input to both OU loss model and NHPP covariates. | S |
| TS-07 | Market screening gate (trades/60d, CV, vol, reversals, depth, CLO active, t-to-maturity) | 1b | Without the gate, the bot runs on markets where the model has no data and the economics don't work. | M |
| TS-08 | Reward-share economics kill-switch (pre-code APR calc vs alternative yield) | 1d | Cheapest possible kill; if R_apr_on_collateral < alt_yield + fill_loss, everything downstream is waste. | S |
| TS-09 | Per-market fill model — v0.5 NHPP with covariates (basis, t-since-settlement, imbalance, EWMA vol) | 2 | P(fill) is one of two terms in the EV rule; without a calibrated model, "cancel iff EV < 0" has no teeth. | M |
| TS-10 | Queue-position tracker (snapshot anchor + trade-tape replay between snapshots) | 2b | Price-touch fills overstate P&L; without queue tracking the backtest lies. | M |
| TS-11 | AMM consumption model (`combined − raw` per tick, subtract from taker flow before crediting book) | 2c | Without this, queue is credited fills that actually went to the AMM. | S |
| TS-12 | Conditional-loss model — v0.5 empirical post-fill path replay | 3b | E[loss\|fill] is the other EV term; empirical is cheap and gives the sanity check anchor. | S |
| TS-13 | Reward-share model with live `E_liq_per_epoch` + Long/Short split polling | 4 | Per-side budgets rebalance dynamically; caching them silently biases sizing. | M |
| TS-14 | 1000%-APR cap in sizing (`R_capped = min(R_uncapped, 10 × collateral × epoch_days/365)`) | 4 | At $100 collateral cap never binds, but the cap-binding branch must exist in code so scaling later doesn't silently over-size. | S |
| TS-15 | EV-based cancel rule with `voluntary_cancel_forfeits_accumulated` flag | 5 | The core decision primitive. Flag existence preempts Phase 0 open-question fallout. | M |
| TS-16 | Predictive circuit breakers (margin trajectory, oracle staleness, CLO removal, CLO shift, fill-rate runaway, competition collapse, maturity migration) | 6 | Each one has a distinct failure mode in `boros_bot_guide.md` Risk 1–6; omitting any is a known unsafe state. | M |
| TS-17 | Event-driven backtest (queue-aware, AMM-aware, cancel-latency-aware, `eventIndex`-ordered) | 7 | The only honest way to measure P&L on a CLOB; price-touch backtest is disqualifying. | L |
| TS-18 | Pre-signed cancel calldata at order-placement time | 8 | Biggest leverage point on fill avoidance (consolidated plan "5 things that matter" #1); no HTTP roundtrip in critical path. | M |
| TS-19 | Dual-wallet architecture (root cold, agent hot) via Send Txs Bot | 8 | Enforced by Boros SDK conventions; running a hot root wallet is straight-up negligent. | M |
| TS-20 | WebSocket fill detection (subscribe account/orders) | 8 | Required upstream of the pre-signed-cancel trigger. Polling is too slow for the fire-on-fill path. | M |
| TS-21 | Paper-trading harness (live feeds, no capital, counterfactual decision logging) | 9 | 2–4 weeks of paper is the contract for "live readiness"; without it, there's no reconcile layer between backtest and live. | M |
| TS-22 | Phantom-fill / phantom-reward logging during paper | 9 | "Would have filled here, would have earned $X" is the calibration signal against backtest predictions. | S |
| TS-23 | Live rollout at $100, one market, protocol minimum size, 2-week observation | 10 | The scope of v0.5 itself. Below this, the bot is an exercise. | S |
| TS-24 | Merkle distributor claim scheduler (poll on-chain for new root, submit proof weekly) | 10 | Rewards only exist when claimed; an unclaimed reward is a 0% APR reward. | S |
| TS-25 | Gas-balance top-up and alerting (Send Txs Bot gas balance) | 8 | Empty gas balance = silently stuck orders = silent accrual of fill risk with no way to cancel. | S |
| TS-26 | RUN_MANIFEST on every run (git SHA, strategy version, full knob tree, run_id ULID) stamped into logs + sidecar | Cross-cutting | Engineering Protocol #3 — strategy+knobs stamp is load-bearing; logs without manifest are unreadable by design. | S |
| TS-27 | State-chain diagram (`docs/ARCHITECTURE.md` Mermaid + `architecture.yml`) consulted before change, updated atomically | Cross-cutting | Engineering Protocol #2 — review gate; PRs without diagram updates are rejected. | M |
| TS-28 | LLM Wiki check-first / write-back discipline (`../LLM Wiki/workspaces/boros/`) | Cross-cutting | Engineering Protocol #1 — prevents re-litigating resolved questions across sessions. | S (process) |
| TS-29 | Structured JSON logs with `run_id` join key | Cross-cutting | Required so any P&L / calibration / debug tool can join across manifest + event stream. | S |
| TS-30 | Isolated-margin enforcement; immediate market close on fill | Constraint | PROJECT.md hard constraint — no cross-margin, no hold-for-reversion. Accept taker fee as insurance. | S |

**Total table-stakes count: 30.** About right for a single-user personal bot operating real capital on a CLOB with IRS-grade risk.

### Differentiators — competitive edge features

These are the features that separate "generic maker bot" from "Boros liquidity-pool harvester that actually works." Most come directly from the consolidated plan's "5 things that actually matter" list plus the post-verification additions.

| # | Feature | Value Proposition | Complexity | Notes |
|---|---------|-------------------|------------|-------|
| DF-01 | **EV-based cancel rule (no threshold dials)** | Self-calibrating under competition / maturity / vol shifts. As `R_liq_share` drops from competition or hits cap, as `E[loss\|fill]` rises near maturity, the cancel trigger adjusts automatically. Every other bot class with hand-tuned thresholds drifts out of regime. | M | Hard-dep on fill model + loss model + reward-share model |
| DF-02 | **Per-market model selection (NHPP / Hawkes / RP by CV)** | Verified non-optional — ETHUSDT-26SEP2025 CV=6.06 (Hawkes), BTCUSDT-26DEC2025 CV=0.46 (RP). Universal Hawkes overfits under-dispersed markets; universal Poisson under-predicts clustered markets. | L | v1.0 feature; v0.5 ships NHPP-only. Phase 2 equivalent. |
| DF-03 | **Pre-signed cancel calldata fired on WS fill** | Biggest leverage point on fill avoidance (consolidated plan "matters #1"). Removes HTTP roundtrip from the critical path; realized cancel latency ~2–5s budget. | M | Hard-dep on WS fill detection (TS-20) + Send Txs Bot |
| DF-04 | **Live per-cycle polling of `E_liq_per_epoch` + Long/Short budget split** | Protocol rebalances between sides to attract the thinner side; caching the split per-market silently biases sizing. Observed anchor: ETHUSDT 29-May-2026 Long 6.663 PENDLE/day, Short 39.05 PENDLE/day, Short APR 957% (cap-binding). | S | Trivial code, high-leverage correctness |
| DF-05 | **Competition-tracked sizing via `Q_total_in_range`** | Reward share is endogenous on competing notional; without this `R_share` is fiction. Consolidated plan "matters #2". | M | Hard-dep on order-book poller + CLO-range APR conversion |
| DF-06 | **OU-on-basis parametric loss model with closed-form integral** | Smoother than pure-empirical; extrapolates to unobserved (tick-distance, t-to-maturity) cells; 90% CI on loss estimate. | M | v1.0 upgrade; v0.5 ships empirical-only (TS-12). Phase 3a. |
| DF-07 | **Predictive (not reactive) circuit breakers** | Margin-trajectory extrapolation triggers before maintenance breach; `fTime > 0.7 × maxUpdateDelay` triggers before full oracle stale. Reactive breakers always fire too late on fast Arbitrum. | M | Included in TS-16; the **predictive** framing is the differentiator vs typical MM bot reactive breakers |
| DF-08 | **Cancel-latency sensitivity sweep in backtest** | Tells us whether VPS / colocation is worth buying — dP&L/dL is an empirical decision, not a vibe. | S | Knob on the event-driven backtest |
| DF-09 | **Per-run strategy+knob attribution (RUN_MANIFEST protocol)** | Every log line joinable to the exact knob values that produced it; eliminates silent parameter drift between backtest / paper / live. Rare in retail MM bots. | S (one-time) | TS-26 is the mechanism; the **attribution discipline** is the differentiator |
| DF-10 | **LLM Wiki as persistent canonical knowledge base** | Decisions, surprises, failed hypotheses, calibrations filed with `Status:` field and `[[links]]`; prevents re-litigating resolved questions across sessions. Engineering Protocol #1. | S (process) | TS-28 is the mechanism; the **write-back discipline** is the differentiator |
| DF-11 | **Maintained state-chain diagram (Mermaid + YAML) with pre-commit blast-radius check** | Every change traces upstream/downstream nodes before edit; diagram-drift blocks merge. Engineering Protocol #2. | M (one-time + maintained) | TS-27 is the mechanism; the **review-gate discipline** is the differentiator |
| DF-12 | **`voluntary_cancel_forfeits_accumulated` boolean with both-branch backtest sensitivity** | Preempts the Phase 0 open question — ship either branch; if sensitivity is material, the docs/Discord answer gates paper trading. | S | Branch already scoped in Phase 5 of consolidated plan |
| DF-13 | **Adversarial "just-outside-range" hypothesis study in backtest** | Consolidated plan anchor: 363.52 YU cluster at tick 1.5% (just outside the 1.49% upper CLO). Hypothesis: collect Maker Volume rewards on natural taker flow while not diluting own liquidity-pool share. Confirm/falsify on historical data — changes whether "tighter placement" is ever EV-positive under a pure-liquidity thesis. | S | Analysis task, not a shipped bot feature; results feed Phase 4 sizing |
| DF-14 | **Run-ID-keyed decision-log review tools (notebook-based)** | Every cancel/hold/repost decision reviewable with counterfactual; postmortems reconstruct from one `run_id`. | S | Depends on TS-22 + TS-26 |

**Total differentiators: 14.** Items DF-01, DF-03, DF-05, DF-04 are the four that most tightly map to the consolidated plan's "5 things that actually matter." DF-02 is the sixth-matters addition from verification (per-market CV dispersion).

### v1.0 Upgrades — defer from v0.5, plan for them

These are the features that the consolidated plan's "two-track build option" explicitly defers from v0.5 to v1.0, plus a few observed-during-paper adaptations that only make sense after real feedback.

| # | Feature | v0.5 Substitute | v1.0 Trigger | Complexity |
|---|---------|-----------------|--------------|------------|
| V1-01 | Per-market fill model selection (Hawkes for CV>1.5, NHPP for 0.7–1.5, RP for CV<0.7) | NHPP-only on one market | v0.5 live shows consistent paper-matches-backtest and shortlist has ≥2 markets | L |
| V1-02 | OU-on-basis parametric loss model + empirical cross-check | Empirical-only | v0.5 live shows empirical cells are too sparse (expected — fills are rare by design) | M |
| V1-03 | Backtest on all shortlisted markets (not just one) | Backtest on one market | V1-01 available | M |
| V1-04 | Multi-market live operation (sequential addition, one at a time with 4-week stability gate) | One market, one side | Market 1 stable for 4 weeks per Phase 10 contract | M |
| V1-05 | Optional 2-state HMM confirmation overlay | Skip entirely | 4 weeks of paper shows NHPP-based EV misses regime transitions | M |
| V1-06 | Brownian-bridge correction near maturity (<14 days) | Migration trigger (exit early) | Operator wants to capture late-maturity markets (currently out of scope by migration rule) | L |
| V1-07 | Randomized placement timing + decoy orders (anti-front-run) | None — competition-collapse breaker only | Live shows competing bots responding to our placement pattern | M |
| V1-08 | Colocation / VPS deployment | Local machine | Cancel-latency sensitivity (DF-08) shows dP&L/dL is materially negative and local latency dominates | M (ops) |
| V1-09 | Second side activation (Long + Short simultaneously on same market) | One side at a time | v0.5 single-side live stable; per-user cap still not binding; both-side fill-rate independent | S |
| V1-10 | `latestAnnualizedRate` velocity-based side cancel (pre-emptive one-side pause) | Predictive margin breaker only | Paper shows fills cluster with rate-velocity signals not captured by NHPP covariates | S |
| V1-11 | CLI live dashboard (tail + per-market status panel) | Flat-file logs + notebook review | Operator attention cost of grepping logs becomes the bottleneck | S |
| V1-12 | Automatic market-shortlist re-screening (scheduled weekly) | Manual re-run of Phase 1b | Operator wants zero-touch market universe refresh | S |

### Anti-Features — explicitly NOT building, with rationale

Preempts "should we add X?" loops. Every one of these was considered in the consolidated plan and rejected with a reason.

| # | Anti-Feature | Why Requested / Tempting | Why Rejected | Alternative |
|---|-------------|---------------------------|--------------|-------------|
| AF-01 | **Capturing the Maker Volume Rewards pool** (fill-based incentive) | "Double incentive — why not capture both?" | Paying on fills; including `+ R_maker_volume × P(fill)` in EV pushes optimizer toward tighter placement and higher fill probability. Inverts the thesis. | If pursued later, plan it as a separate spread-capture strategy |
| AF-02 | **Predicting where rates go (directional alpha)** | "If we can predict direction we avoid the bad fills preemptively." | Not the thesis. Rate forecasting is a different, richer-competition game; the bot models *when takers arrive at depth*, conditional on features. | Stay mechanically Bayesian: features in, P(fill) out, EV rule decides |
| AF-03 | **Cross-margin on Boros** | "Capital efficiency." | Increases liquidation radius across markets; one bad fill cascades. Isolated margin is a containment firewall at $100. | Isolated margin only |
| AF-04 | **CEX hedging (Binance/OKX spot-perp) to neutralize fills** | "If filled, hedge the IRS exposure instead of closing at market." | Two systems to maintain, two sets of risk, non-atomic execution across venues, and the strategy claims to capture rewards, not arb. | Close immediately at market, accept taker fee as insurance |
| AF-05 | **Holding fills for mean-reversion** | "OU says it'll revert — why pay the taker fee?" | That is a different strategy (stat-arb on basis). Mixing it in makes fill cost stochastic and unbounded. | Close on fill, always |
| AF-06 | **One-size-fits-all fill model (universal Hawkes)** | "Simpler codepath, one model to calibrate." | Verified wrong: CV spread 0.46–6.06 across markets; Hawkes on CV=0.46 would fit *negative excitation* (regular flow) and be worse than Poisson. | Per-market model selection (DF-02) |
| AF-07 | **Continuous-diffusion (OU) on raw Implied APR for fill probability** | "OU is simple and calibratable." | CLOB price is a step function; fills happen when takers arrive, not when rates "drift." OU fitted to a step function produces a σ with no mechanical meaning. | NHPP / Hawkes / RP on taker arrivals |
| AF-08 | **Brownian-bridge correction on implied APR** | "Theoretically correct near maturity." | True in principle but maturity-migration rule (Phase 6) exits >14d before expiry; bridge regime is never reached. | Migration trigger; keep OU-on-basis for loss integral only |
| AF-09 | **Front-running / adversarial defense against competing bots** | "Other bots might cancel-race us." | Competition-collapse circuit breaker covers the catastrophic case; full randomization + decoys is v2+ (V1-07). | Circuit breaker is sufficient at $100 |
| AF-10 | **Cold-start on brand-new markets (listing-day participation)** | "Maximum emissions on day 1." | Each market needs its own calibration window; no covariate history, no CV estimate, no screening-test pass. | Require ≥60 days of data before onboarding |
| AF-11 | **Multi-user / SaaS deployment (accounts, auth, tenant isolation)** | "Others might pay for this." | Ops surface area 10×, security surface area 100×, and the operator doesn't want the business. | Single-user personal bot; one wallet pair |
| AF-12 | **Mobile / web GUI dashboard** | "Easier to monitor from phone." | CLI + Jupyter cover it; web UI is never "done" and becomes a maintenance tax. | CLI logs + notebook analytics (V1-11 CLI panel is the cap) |
| AF-13 | **Cloud / VPS deployment for v0.5** | "Lower latency." | $100 collateral doesn't justify $20–50/mo VPS; sensitivity sweep (DF-08) decides whether V1-08 is ever warranted. | Local machine for v0.5 |
| AF-14 | **Multi-sig / social-recovery wallet** | "Safer." | Root wallet is cold and only signs deposits/withdrawals — the multi-sig slowdown is on the path the operator uses weekly. Dual-wallet (TS-19) is the separation; multi-sig adds complexity without risk reduction at $100. | Dual-wallet only |
| AF-15 | **Auto-compounding claimed PENDLE back into collateral** | "Compound growth." | Requires a swap leg (PENDLE→USDC→collateral) and an on-chain approval; silent gas + slippage + an extra failure mode. Weekly claim, manual compound while operator decides whether to scale. | Manual compound decision at operator discretion |
| AF-16 | **Broadcast endpoint / public API for the bot's decisions** | "Others might want to mirror us." | Immediate adverse-selection magnet; competitors front-run cancellations on signal. | Keep decisions local |
| AF-17 | **Integration with wallet UIs (Rabby / Frame notifications)** | "Nice ergonomics." | Adds a non-essential dependency; structured JSON logs + RUN_MANIFEST are the notification layer. | Log stream only |

### Features common elsewhere but NOT in the consolidated plan — surfaced for explicit include/exclude

These are features that show up in other on-chain MM / reward-farming bot designs (Hyperliquid MMs, Polymarket MMs, rebate-farming bots) that are not in `boros_consolidated_plan.md`. The REQUIREMENTS.md author should make an explicit call on each, not default to "not in plan → not built."

| # | Feature | Seen In | Recommendation | Rationale |
|---|---------|---------|----------------|-----------|
| NP-01 | **Self-trade prevention check before placement** | Every CLOB MM bot | **Include as TS** (cheap, catches a real mis-configuration bug) | `boros_bot_guide.md` mentions STP is protocol-enforced, but our own pre-check prevents wasted gas + rejected txs on a misconfigured two-sided setup. S complexity, high-leverage correctness. |
| NP-02 | **`maxOpenOrders` cap tracking + backpressure** | CLOB MMs on multi-market venues | **Include as TS** | Each market has an 80–100 cap. At v0.5 one market one side we're nowhere near, but the check is S and a silent drop of a place-order after V1-04 multi-market expansion is a real bug. |
| NP-03 | **Order-placement simulation (`GET /simulations/place-order`) before submit** | Polymarket MM bots | **Include as TS** (thin wrapper, already in REST) | Catches purge bounds (`loUpperConst + loUpperSlope × TTM`) before we spend gas. Endpoint already exists. S. |
| NP-04 | **Rate-limit / exponential backoff on Boros REST** | Every API-driven bot | **Include as TS** | Single-operator bot is unlikely to breach rate limits, but 429 handling on a fill-detection path that falls back to REST when WS is down is load-bearing. S. |
| NP-05 | **WebSocket reconnect + heartbeat monitoring** | Every WS-driven bot | **Include as TS** | Silent WS disconnect = no fill detection = no pre-signed cancel fire. The one failure mode that voids TS-18. S–M. |
| NP-06 | **REST-polling fallback for fill detection when WS dropped** | Every WS-driven bot | **Include as TS** | If WS reconnect (NP-05) fails for >N seconds, fall back to polling `GET /accounts/active-positions` and cancel all as a safety stance. M. |
| NP-07 | **Per-market config schema validation (Pydantic / Zod) on startup** | Any multi-config bot | **Include as TS** | Engineering Protocol #3 requires the config schema to be the knob inventory source of truth. A knob not in schema → not in RUN_MANIFEST → silent drift. S. |
| NP-08 | **Dry-run mode (same codepath, no send-txs-bot calls)** | Every trading bot | **Include as TS** | Paper-trading harness (TS-21) is this, essentially. But dry-run is also the "can we start the bot on a laptop we just installed" smoke test. S once paper exists. |
| NP-09 | **Alerts on fills, purges, circuit-breaker fires (email / Telegram / Discord webhook)** | Most personal bots | **Include as v1.0** | At v0.5 the operator is watching logs manually; structured logs + CLI panel (V1-11) cover it. Push alerts become meaningful when operator steps away or scales markets. S. |
| NP-10 | **On-chain approval renewal monitoring** | Every on-chain bot | **Include as TS** | Approvals can expire or be revoked; silent inability to deposit / re-collateralize is an unsafe state. S. |
| NP-11 | **Wallet balance / nonce drift reconciliation vs expected** | Every on-chain bot | **Include as TS** | Detects a stuck tx or nonce gap before it causes pile-up. S. |
| NP-12 | **Daily / weekly P&L report (flat markdown or notebook)** | Personal bots | **Include as TS (S)** | Required to make a scale/kill decision weekly. The decision is "keep running?" and the input is last week's net. S. |
| NP-13 | **Reward claim reconciliation (on-chain claimed vs Merkle-computed expected)** | Rewards claim bots | **Include as TS** | Silent under-distribution of rewards = silent strategy underperformance. S once TS-24 ships. |
| NP-14 | **Gas-price-aware tx submission (delay cancel if gas spikes 10×)** | Gas-sensitive bots | **Exclude for v0.5** | Arbitrum gas is near-zero and variance is small; noise, not signal, at current scale. Consolidated plan correctly says gas is negligible. |
| NP-15 | **Chainlink / multi-oracle cross-check on `fTime`** | High-stakes on-chain bots | **Exclude for v0.5** | Boros has one oracle per market; circuit breaker (TS-16 oracle-stale) covers the failure mode. Cross-oracle makes sense only if we don't trust the single oracle, which is out of scope. |
| NP-16 | **MEV protection (Flashbots-style private submission)** | DEX trading bots | **Exclude** | Cancel + close-at-market on Arbitrum; the sandwich-attack surface on an IRS CLOB is minimal relative to gas cost. Not a real threat at this scale. |
| NP-17 | **Copy-trading / strategy mirroring** | Polymarket / Hyperliquid bot products | **Exclude (AF-16 covers the inverse)** | Anti-feature by design — we don't broadcast, we don't mirror. |
| NP-18 | **ML-based fill-probability ensemble (XGBoost + NN blend)** | Advanced MM bots | **Exclude for v0.5, consider v2** | NHPP/Hawkes are interpretable and calibratable; ensemble blends lose the EV-rule grounding. Revisit if paper shows NHPP covariate residuals have learnable structure. |
| NP-19 | **Inventory-balancing bias (skew quotes to reduce net IRS exposure)** | Bidirectional CLOB MMs | **Exclude (one side at a time is the v0.5 rule)** | Only relevant if we run both sides; defer with V1-09. At that point, since any fill is closed at market, inventory is ~0 by construction anyway. |
| NP-20 | **Secret management (vault / 1password CLI integration) for agent private key** | Any personal-custody bot | **Include as TS** | Env-vars in shell history / plaintext files are a real surface at $100, worse at scale. Protocol mandates dual-wallet; it's an empty security theater if the hot key is in a `.env`. S. |
| NP-21 | **Time-sync / NTP check on the operator's machine** | Latency-sensitive bots | **Include as TS (S)** | Clock drift against Arbitrum block times confuses the `eventIndex` ordering logic downstream. Five-line boot check. |
| NP-22 | **Deposit/withdraw calldata (root wallet ops)** | Every deposit-gated venue | **Include as TS** | v0.5 starts with $100 deposit; not having the deposit codepath means manual-UI dependency for rebalance. S. |

**Summary recommendation from NP list:** Promote NP-01, NP-02, NP-03, NP-04, NP-05, NP-06, NP-07, NP-08, NP-10, NP-11, NP-12, NP-13, NP-20, NP-21, NP-22 into TS. Keep NP-09 as v1.0. Explicitly reject NP-14, NP-15, NP-16, NP-17, NP-18, NP-19 with rationale above. **Net: +15 TS features beyond the consolidated plan's 30 = ~45 TS features for v0.5 scope.** Most are S-complexity polish on top of the core engine.

---

## Feature Dependencies

Critical chains for phase ordering in the roadmap. Read top-down: upstream features must ship in earlier phases.

```
TS-01 (market config)
  └── TS-02 (fIndex oracle) ─────────────────┐
  └── TS-03 (raw book snapshots) ────────┐   │
  └── TS-04 (trade tape + eventIndex) ─┐ │   │
  └── TS-05 (combined book+AMM) ─────┐ │ │   │
  └── TS-06 (underlying APR) ──────┐ │ │ │   │
                                   │ │ │ │   │
                                   ▼ ▼ ▼ ▼   ▼
                    TS-07 (market screening gate)
                                   │
                                   ▼
                    TS-08 (economics kill-switch)
                                   │
                                   ▼
         ┌────────────────── TS-09 (fill model NHPP) ──────────────────┐
         │                         │                                   │
         ▼                         ▼                                   │
  TS-10 (queue tracker)   TS-11 (AMM consumption)                     │
         │                         │                                   │
         └──────────┬──────────────┘                                   │
                    │                                                  │
                    ▼                                                  │
        TS-17 (event-driven backtest) ←──── DF-08 (latency sweep)      │
                    │                                                  │
                    │                        TS-12 (empirical loss) ◄──┤
                    │                             │                    │
                    │                             ▼                    │
                    │                        DF-06 (OU-on-basis) [v1.0]│
                    │                             │                    │
                    │                        TS-13 (reward-share)      │
                    │                        TS-14 (cap logic)         │
                    │                        DF-04 (live budget poll)  │
                    │                        DF-05 (Q_total tracker)   │
                    │                             │                    │
                    └────────────┬────────────────┘                    │
                                 ▼                                     │
                    TS-15 (EV cancel rule) ──────────────── DF-12      │
                    DF-01 (EV self-cal)    ◄──── DF-02 (per-market)[v1]│
                                 │                                     │
                                 ▼                                     │
                    TS-16 (circuit breakers) ◄──── DF-07 (predictive)  │
                                 │                                     │
                                 ▼                                     │
                    TS-19 (dual-wallet) ──► TS-20 (WS fill) ──► TS-18 (pre-signed cancel)
                                 │                                     │
                                 ▼                                     │
                                                                       │
                    TS-21 (paper harness) ◄──── TS-22 (phantom logs) ◄─┘
                                 │
                                 ▼
                    TS-23 (live, one market, $100)
                                 │
                                 ▼
                    TS-24 (Merkle claim scheduler)

Cross-cutting (apply to every phase):
  TS-26 (RUN_MANIFEST) ──► TS-29 (JSON logs + run_id) ──► DF-09 (attribution)
  TS-27 (state-chain diagram) ──► DF-11 (review gate)
  TS-28 (LLM Wiki check-first) ──► DF-10 (write-back)
  TS-25 (gas top-up) / TS-30 (isolated margin) / NP-10 (approvals) / NP-11 (nonce)

Supporting hygiene (promote from NP-):
  NP-07 (config schema validation) ──► feeds TS-26 knob inventory
  NP-20 (secret mgmt) ──► required by TS-19
  NP-21 (NTP check) ──► required by TS-04 eventIndex ordering
  NP-03 (placement simulation) ──► feeds TS-16 purge-bound check
  NP-05 (WS heartbeat) / NP-06 (REST fallback) ──► guard TS-20
```

### Key dependency notes

- **DF-01 (EV cancel rule) has three upstream hard-deps:** TS-09 (fill model) + TS-12 (loss model) + TS-13 (reward share). All three must ship before the decision engine is meaningful. The EV equation is `R_share × P(no_fill) − E[loss|fill] × P(fill) − cancel_cost × P(purge)` — remove any input and the output is garbage.
- **TS-18 (pre-signed cancel) is gated on TS-20 (WS fill detection) + TS-19 (Send Txs Bot + agent wallet).** The fire-path is WS event → pre-signed calldata in memory → Send Txs Bot submit. Skip the WS event and the HTTP roundtrip is back in the critical path.
- **TS-17 (event-driven backtest) depends on TS-10 (queue tracker) + TS-11 (AMM consumption) + TS-04 (eventIndex ordering).** Without all three, the backtest reduces to a price-touch indicator and overstates P&L — disqualifying per `plan_comparison.md`.
- **TS-21 (paper harness) depends on the full bot logic already being wired.** Paper is TS-23 minus real capital + real send-txs-bot. You can't ship paper before the decision engine, circuit breakers, and execution layer are connected.
- **DF-02 (per-market model selection) conflicts with v0.5 scope.** The consolidated plan explicitly defers this to v1.0 — ship NHPP-only first, add Hawkes/RP after one market is stable.
- **AF-01 (Maker Volume pool) conflicts with TS-15 (EV cancel rule).** Adding `+ R_maker_volume × P(fill)` to the EV inverts the optimizer. This is why AF-01 is an anti-feature, not a deferred v1.0 feature.
- **Cross-cutting protocols (TS-26/27/28) are NOT feature-level dependencies — they are phase-level discipline.** Every phase must produce artifacts that satisfy them; no phase ships without wiki pages filed, diagram updated, manifest emitted.

---

## MVP Definition

### v0.5 (2 weeks engineering + 2–4 weeks paper + 2 weeks live observation)

**Launch scope:**
- [ ] Data pipeline on one market (TS-01 through TS-06)
- [ ] Market screening gate run once (TS-07, TS-08); skip if the candidate market fails the economics kill-switch
- [ ] NHPP fill model with 4 covariates on that market (TS-09, TS-10, TS-11)
- [ ] Empirical-only loss model (TS-12)
- [ ] Reward-share model with cap logic + live budget polling (TS-13, TS-14, DF-04, DF-05)
- [ ] EV cancel rule with `voluntary_cancel_forfeits_accumulated` flag (TS-15, DF-12)
- [ ] All seven predictive circuit breakers (TS-16, DF-07)
- [ ] Event-driven backtest with cancel-latency sweep (TS-17, DF-08)
- [ ] Dual-wallet + Send Txs Bot integration (TS-19)
- [ ] WebSocket fill detection with heartbeat + REST fallback (TS-20, NP-05, NP-06)
- [ ] Pre-signed cancel calldata fired on WS fill (TS-18) — **this is the single biggest differentiator; if it slips, ship with REST cancel and flag the latency hit**
- [ ] Gas top-up + alerting (TS-25)
- [ ] Isolated margin + immediate market close on fill (TS-30)
- [ ] Paper harness with phantom fills and phantom rewards (TS-21, TS-22)
- [ ] Live at $100 collateral, one market, one side, protocol minimum size, 2-week observation (TS-23)
- [ ] Merkle claim scheduler (TS-24) + reconciliation (NP-13)
- [ ] Cross-cutting protocols stamped into every run (TS-26, TS-27, TS-28, TS-29)
- [ ] Hygiene layer (NP-01, NP-02, NP-03, NP-04, NP-07, NP-08, NP-10, NP-11, NP-12, NP-20, NP-21, NP-22)

**NOT in v0.5 (explicit deferrals):**
- Per-market model selection (V1-01) — NHPP is universal for v0.5
- OU-on-basis parametric loss (V1-02) — empirical-only is enough to test the thesis
- Multi-market (V1-04) — one market, full stop
- HMM overlay (V1-05) — decide after paper
- Both-side operation (V1-09) — one side until v0.5 proves stable
- CLI live dashboard (V1-11) — tail + notebook is enough for one operator
- Push alerts (NP-09) — structured logs cover it at v0.5

### v1.0 (triggered after v0.5 live is stable for 4 weeks)

**Add after validation:**
- [ ] V1-01 (per-market fill model selection) — trigger: shortlist has ≥2 markets + Phase 1c CV values measured
- [ ] V1-02 (OU-on-basis loss model) — trigger: empirical cells too sparse, need to extrapolate
- [ ] V1-03 (backtest on all shortlisted markets) — prerequisite for V1-04
- [ ] V1-04 (second market live) — trigger: first market stable 4 weeks, economics cover operator attention
- [ ] V1-09 (second side on same market) — trigger: first side stable, per-user cap still not binding
- [ ] V1-10 (velocity-based side cancel) — trigger: paper shows rate-velocity residuals in NHPP
- [ ] V1-11 (CLI live dashboard) — trigger: operator attention cost of log grep > dashboard build cost
- [ ] NP-09 (push alerts) — trigger: operator steps away or multi-market expansion

### v2+ (future consideration)

**Defer until v1.0 is stable and the thesis is profitable:**
- [ ] V1-05 (HMM overlay) — only if v1.0 shows regime-transition misses
- [ ] V1-06 (Brownian-bridge near maturity) — only if operator wants to capture late-maturity markets (currently rejected by migration rule)
- [ ] V1-07 (randomized placement + decoys) — only if live shows competing-bot adversarial behavior
- [ ] V1-08 (colocation / VPS) — only if DF-08 sensitivity sweep shows dP&L/dL materially negative AND local dominates
- [ ] V1-12 (auto-shortlist re-screening) — only if operator wants zero-touch market refresh
- [ ] NP-18 (ML ensemble) — only if NHPP covariate residuals show learnable structure after v1.0

---

## Feature Prioritization Matrix

Ratings reflect v0.5 scope decisions. "User value" here is operator-value (personal bot).

| Feature | Operator Value | Impl. Cost | Priority |
|---------|----------------|------------|----------|
| TS-09 (NHPP fill model) | HIGH | MEDIUM | P1 |
| TS-13 (reward-share w/ live polling) | HIGH | MEDIUM | P1 |
| TS-15 (EV cancel rule) | HIGH | MEDIUM | P1 |
| TS-16 (predictive circuit breakers) | HIGH | MEDIUM | P1 |
| TS-17 (event-driven backtest) | HIGH | HIGH | P1 |
| TS-18 (pre-signed cancel calldata) | HIGH | MEDIUM | P1 |
| TS-19 (dual-wallet) | HIGH | MEDIUM | P1 |
| TS-20 (WS fill detection) | HIGH | MEDIUM | P1 |
| TS-21 (paper harness) | HIGH | MEDIUM | P1 |
| TS-26 (RUN_MANIFEST) | HIGH | LOW | P1 |
| TS-27 (state-chain diagram) | HIGH | MEDIUM | P1 |
| TS-28 (LLM Wiki discipline) | HIGH | LOW (process) | P1 |
| DF-04 (live budget polling) | HIGH | LOW | P1 |
| DF-05 (competition tracking) | HIGH | MEDIUM | P1 |
| DF-07 (predictive framing of breakers) | HIGH | MEDIUM | P1 |
| DF-08 (cancel-latency sweep) | MEDIUM | LOW | P1 |
| DF-12 (voluntary-cancel flag + sensitivity) | HIGH | LOW | P1 |
| NP-05 (WS heartbeat) | HIGH | LOW | P1 |
| NP-06 (REST fallback) | HIGH | MEDIUM | P1 |
| NP-20 (secret mgmt) | HIGH | LOW | P1 |
| TS-24 (Merkle claim) | HIGH | LOW | P1 |
| NP-13 (claim reconciliation) | HIGH | LOW | P1 |
| V1-01 (per-market model selection) | MEDIUM | HIGH | P2 |
| V1-02 (OU-on-basis) | MEDIUM | MEDIUM | P2 |
| V1-04 (second market) | MEDIUM | MEDIUM | P2 |
| V1-09 (second side) | LOW | LOW | P2 |
| V1-11 (CLI dashboard) | MEDIUM | LOW | P2 |
| NP-09 (push alerts) | MEDIUM | LOW | P2 |
| V1-05 (HMM overlay) | LOW | MEDIUM | P3 |
| V1-07 (anti-front-run) | LOW | MEDIUM | P3 |
| V1-08 (colocation) | LOW | MEDIUM (ops) | P3 |

**Priority key:**
- **P1** — v0.5 must-have. Skipping any of these ships a strategy that cannot be honestly evaluated.
- **P2** — v1.0, add after v0.5 live is stable for ≥4 weeks.
- **P3** — v2+, only if specific evidence from v1.0 operation justifies.

---

## Comparative Feature Analysis

Bot classes with overlapping primitives but different theses. The point of this table is to anchor which differentiators are specific to our avoid-fills liquidity-pool capture vs. generic MM-bot table stakes.

| Feature | Generic on-chain MM (rebate farming) | Hyperliquid / Polymarket MM bots | Standard Pendle YT farmer | **Boros Liquidity-Pool Bot (ours)** |
|---------|--------------------------------------|-----------------------------------|---------------------------|-------------------------------------|
| Primary income | Maker rebates + spread | Maker rebates | PENDLE + base yield | **Time-weighted liquidity rewards only** |
| Fill preference | Fills are revenue | Fills are revenue | N/A (buy and hold) | **Fills are pure cost** |
| Cancel criterion | Threshold dials | Threshold dials | N/A | **EV-based, self-calibrating (DF-01)** |
| Model selection | Single fill model | Single fill model | N/A | **Per-market NHPP / Hawkes / RP (DF-02, v1.0)** |
| Fill detection | WS + REST poll | WS + colo | N/A | **WS + heartbeat + REST fallback** |
| Cancel-calldata strategy | Sign on fill detection | Pre-sign sometimes | N/A | **Pre-sign at placement; fire on WS (DF-03)** |
| Competition modeling | Ignored or heuristic | Usually heuristic | Not applicable | **Live `Q_total_in_range` + `E_liq_per_epoch` polling (DF-04, DF-05)** |
| Inventory management | Skew bias, hedge | Quote skew | Passive hold | **Close immediately on fill; isolated margin** |
| Circuit breakers | Reactive (net-balance trip) | Mix | Optional | **Predictive (margin trajectory, 0.7× oracle-stale) (DF-07)** |
| Run attribution | Optional logs | Optional logs | N/A | **RUN_MANIFEST every run, git SHA + knob tree (DF-09)** |
| Knowledge base | Tribal / Notion | Tribal / Notion | Docs | **LLM Wiki check-first + write-back (DF-10)** |

**Implication:** DF-01, DF-03, DF-05, DF-06, DF-07, DF-09, DF-10, DF-11 together form a coherent "avoid-fills, self-calibrating, provenance-obsessive" stance that distinguishes this bot class from generic on-chain MM. None of these are optional polish — they each address a specific failure mode that generic MM bot patterns produce in the avoid-fills regime.

---

## Confidence and open gaps

**HIGH confidence:**
- All 30 table-stakes items trace directly to `boros_consolidated_plan.md`, `boros_bot_guide.md`, `PROJECT.md`, or Engineering Protocols. The plan is opinionated and the opinions have been verified against live NDJSON data.
- Anti-features AF-01 through AF-17 are all explicitly rationalized in the consolidated plan or PROJECT.md "Out of Scope."
- Dependency chain is directly read from the Phases 0–10 structure.

**MEDIUM confidence:**
- NP-01 through NP-22 features are comparative-class inferences from other on-chain MM bot designs (WebSearch corroborated standard patterns: dual-wallet, WS + REST fallback, batch cancel, pre-signed orders, colocation). Promotion-to-TS recommendations are my judgement, not canonical; REQUIREMENTS.md may re-classify based on operator preference.
- V1-05 (HMM) and V1-06 (Brownian bridge) priority rankings depend on paper-trading findings that don't yet exist.

**LOW confidence / gaps:**
- Anti-front-run (V1-07) threat model isn't empirically characterized — no data on whether other bots on Pendle Boros actually respond to our placement pattern. Deferral to v2+ is correct, but the trigger ("live shows competing bots responding") is qualitative.
- Reward claim reconciliation expected-vs-actual tolerance (NP-13) is undefined until we see how the Merkle distributor actually rounds PENDLE amounts.
- **Phase 0 open questions are still open and affect feature priority:**
  - Voluntary-cancel reward-preservation behavior — DF-12 (flag + both-branch backtest) is the mitigation, but if the punitive branch is true and sensitivity is large, the EV equation materially changes.
  - Protocol minimum order size — if actual min > $100 collateral-equivalent, v0.5 can't launch, and the feature set is moot. Existentially blocks TS-23.

---

## Sources

- `/Users/macbookair/Documents/project/test/rerun7/boros/boros_consolidated_plan.md` — canonical 10-phase feature map (HIGH)
- `/Users/macbookair/Documents/project/test/rerun7/boros/boros_bot_guide.md` — platform reference, REST/WS/Send Txs Bot, Risk 1–6 framework (HIGH)
- `/Users/macbookair/Documents/project/test/rerun7/boros/plan_comparison.md` — NDJSON verification, per-market CV spread (0.46–6.06), hourly snapshot frequency (HIGH)
- `/Users/macbookair/Documents/project/test/rerun7/boros/.planning/PROJECT.md` — scope, constraints, Engineering Protocols #1/#2/#3 (HIGH)
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/index.md` — seeded but empty; seeding is Phase 0/1 work (reference only)
- WebSearch (MEDIUM): generic on-chain MM bot architecture patterns — Polymarket CLOB bots, Hyperliquid MMs, rebate-farming one-sided quoting patterns — corroborated standard table-stakes (dual-wallet, WS + REST fallback, pre-signed orders, circuit breakers) but surfaced no Boros-specific public bot designs to compare against

---
*Feature research for: Boros Liquidity Rewards Bot, v0.5 scope*
*Researched: 2026-04-23*
