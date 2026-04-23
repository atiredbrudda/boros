# Boros Reward Farming Bot

## What This Is

A personal, single-user Python + TypeScript bot that captures **Pendle Boros Limit Order Liquidity Rewards** on Arbitrum by resting limit orders at the outer edges of each market's incentivized CLO range — deliberately avoiding fills so capital earns time-weighted PENDLE rewards without taking unwanted IRS exposure. It runs locally on one operator's machine against one (eventually a small shortlist of) market(s), starting with $100 of collateral as a real-capital validator.

## Core Value

**Earn net-positive yield on posted collateral from the Liquidity Rewards pool that beats stablecoin alternatives, after gas and any fill-loss costs — on a live, single-market deployment.** If fills dominate or the reward economics don't cover alternatives, the strategy must detect that cheaply and kill itself, not limp along.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. Derived from the consolidated plan v0.5 → v1.0 path. -->

- [ ] **Phase 0 prerequisites closed** — cancel-behavior (voluntary-cancel reward preservation) and actual minimum order size confirmed from Boros docs/SDK/Discord before engineering past Phase 1
- [ ] **Data pipeline + market screener** — ingest `market-trades/`, raw + combined order books, underlying APRs; rank markets by CV, vol, reversal count, depth, time-to-maturity, CLO activity
- [ ] **Reward-share economics gate** — compute `R_apr_on_collateral` (capped at 1000% APR) per shortlisted market; drop the market if below alternative yield + estimated fill-loss rate
- [ ] **Per-market fill model** — v0.5: non-homogeneous Poisson (NHPP) with covariates (basis, time-since-settlement, imbalance, EWMA vol, dRate/dt, t-to-maturity); v1.0: add Hawkes for CV > 1.5, renewal process for CV < 0.7
- [ ] **Queue position + AMM consumption tracker** — replay trade tape from hourly `raw/` snapshots, subtract AMM share from `combined_*`, use `eventIndex` for intra-block ordering
- [ ] **Conditional loss model** — OU on basis `B(t) = Implied − Underlying` with closed-form `E[loss|fill]`; empirical post-fill replay as cross-check
- [ ] **Reward share model** — capped pro-rata with live polling of `E_liq_per_epoch` and Long/Short budget split; honor 1000% APR per-account cap
- [ ] **EV-based decision engine** — cancel iff `R_liq_share_per_epoch × P(no_fill_and_unpurged) − E[loss|fill] × P(fill) − cancel_cost × P(purge) < 0`, parameterized by `voluntary_cancel_forfeits_accumulated` flag until confirmed
- [ ] **Predictive circuit breakers** — margin trajectory, oracle staleness (`fTime > 0.7 × maxUpdateDelay`), CLO removal/shift, fill-rate runaway, competition collapse, maturity migration
- [ ] **Event-driven backtest** — queue-aware, AMM-aware, cancel-latency-aware replay on per-trade data; Sharpe-equivalent, max DD, calibration plot, dP&L/dL sensitivity
- [ ] **Execution layer** — dual-wallet (root cold, agent hot) via Send Txs Bot; pre-sign cancel calldata at placement time; WebSocket-driven fill detection
- [ ] **Paper trading harness (2–4 weeks)** — live feeds, no capital; log every decision and counterfactual; reconcile against backtest
- [ ] **Live, one market, $100 collateral, minimum order size** — observe 2 weeks, scale only if live matches paper within statistical noise
- [ ] **Merkle claim scheduler** — poll distributor contract, claim weekly when Merkle root updates

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- **Capturing the Maker Volume Rewards pool** — that pool pays on fills, which this strategy avoids by design. Including it would push the optimizer toward tighter placement and higher fill probability, inverting the thesis. Spread-capture is a different strategy; if pursued later, plan it separately.
- **Predicting where rates go** — the bot models *when takers arrive at depth*, not rate direction. No directional alpha, no forecasting implied APR.
- **Cross-bot adversarial defense** — beyond the competition-collapse circuit breaker, no defenses against competitors learning our placement pattern and front-running cancellations. Randomized timing and decoy orders are a v2+ problem.
- **Cold-start on brand-new markets** — each market needs its own calibration window. Listing-day participation is out of scope.
- **Multi-user / SaaS deployment** — this is a personal bot for one wallet. No multi-tenancy, accounts, auth, or sharing.
- **Mobile / GUI dashboard** — CLI logs + flat-file / notebook analytics only. No web UI beyond the decision-log review.
- **Cross-margin strategies or hedging into the underlying CEX** — isolated margin only; no Binance/OKX hedges to neutralize accidental fills beyond "close immediately at market and eat the taker fee."
- **One-size-fits-all fill model** — the consolidated plan explicitly rejects this. v0.5 uses NHPP as a universal starting point, but v1.0 is per-market selection based on the dispersion test.
- **Continuous-diffusion (OU) on raw implied APR for fill probability** — CLOB price is a step function; OU on the *basis* is kept only for the conditional-loss integral, not the fill model.

## Context

**Domain — Pendle Boros:** On-chain interest rate swap (IRS) platform on Arbitrum. Each market is a bet on whether a floating funding rate (Binance/OKX/Hyperliquid/Bybit/staking/commodity) clears higher or lower than a fixed rate until maturity. Hybrid CLOB + AMM with 65,536 exponential tick levels and rate-time priority. Markets have `cloLowerThresh`/`cloUpperThresh` defining the incentivized range; orders resting in-range accrue PENDLE rewards time-weighted (size × time-near-market-rate).

**Reward economics (answered as of 2026-04-22):**
- Reward token = PENDLE.
- Dual pool per market: (a) Maker Volume Rewards on fills (not targeted); (b) Limit Order Liquidity Rewards on resting size × time-in-range (targeted).
- Per-user cap = 1000% APR on collateral. Binds sizing in thin markets.
- Epoch = weekly (Fri 00:00 UTC → Thu 23:59 UTC). Merkle updates weekly, claim Monday typically. Gas on Arbitrum is negligible.
- One-sided posting qualifies independently (team-endorsed Mark-vs-Underlying side-pick tweet by @0x0Kippon).
- CLO range shifts continuously to track current mid — design feature, handled via circuit breakers.
- Per-side budget likely rebalances dynamically; `E_liq_per_epoch` must be polled live, not cached.
- Concrete anchor: ETHUSDT 29-May-2026 snapshot 2026-04-22 — Short 957% APR (cap-binding) at ~60 YU competing, Long 198% APR at ~20 YU; per-side budgets 6.663/39.05 PENDLE/day Long/Short.

**Data — confirmed available:**
- `market-trades/`: per-trade, second-resolution `{eventIndex, blockTimestamp, rate, side, size, txHash}`. `eventIndex` orders within a 250ms Arbitrum block.
- `order-book/{market}/raw/`: hourly snapshots, per-tick `{t, sz}` where size is wei string (must convert explicitly).
- `order-book/{market}/combined_{tickSize}/`: book merged with AMM liquidity for AMM consumption estimation.
- `underlying-apr/`: per-exchange funding rate histories (Binance, OKX, Hyperliquid).
- Coverage: ~8+ months from Aug 2025, updated every 2–3 days.
- Density: ETHUSDT-26SEP2025 has ~9,216 trades/month (CV=6.06, extreme clustering → Hawkes candidate). BTCUSDT-26DEC2025 has CV=0.46 (under-dispersed → renewal process candidate). **Only ~5 / 113 markets have >500 KB trade data** — strategy universe is structurally narrow.

**Prior work on this repo:** Three planning documents already exist in the project root — `boros_bot_guide.md` (platform reference + risk framework), `boros_consolidated_plan.md` (final superseding 10-phase spec, treat as source of truth), `boros_alternative_plan.md`, `boros_model_recommendation.md`, `plan_comparison.md` (rebuttal/synthesis). The consolidated plan explicitly supersedes the others.

**Open Phase 0 questions still blocking Phase 1+ engineering:**
1. Voluntary cancel behavior — are accumulated reward contributions preserved on cancel, or voided? Resolution path: (1) check `pendle-finance/boros-core-public` repo + reward distributor contract, (2) then Pendle Discord. Worst-case assumption = forfeited until confirmed. Build engine with `voluntary_cancel_forfeits_accumulated` boolean flag; Phase 7 backtest reports sensitivity to both branches.
2. Actual protocol minimum order size — working assumption $100 collateral-equivalent. **Existentially important** at the user's $100 starting capital: if the true minimum is higher, the operator cannot participate at all. Must verify before paper trading.

**Known markets as of April 2026:** BTC, ETH, SOL, XRP, HYPE + XAU/XAG/oil/S&P500 across Hyperliquid, Binance, OKX, Bybit, Lighter. Maturities 24-Apr through 25-Sep 2026. ETH Binance markets share `cloLower=9300, cloUpper=9500`. BTC Binance markets `cloLower=309.69, cloUpper=316.35`. Markets with `clo=0` are not incentivized.

## Constraints

- **Budget**: $100 starting collateral, real money the operator can afford to lose. Scale only if live proves economics beat stablecoin alternatives. — Implication: sub-cap regime on every market (1000% cap never binds at $100), always size at protocol minimum, single market, one side at a time until proven.
- **Tech stack**: Python (models, backtest, data analysis, Jupyter-friendly workflow) + TypeScript (Pendle SDK `@pendle/sdk-boros`, Send Txs Bot integration, WebSocket fill detection, pre-signed cancel calldata). — IPC/boundary between them is a design decision (file-based, HTTP localhost, or single TS process calling out to Python via child process).
- **Deployment**: Operator's local machine. No cloud/VPS for v0.5. — Implies acceptable but not optimal cancel latency; keep pre-signed cancel calldata + WebSocket fill detection, measure realized latency in paper, budget 2–5s.
- **Network**: Arbitrum One via `https://arb1.arbitrum.io/rpc` (or operator's own RPC). Boros REST at `https://api.boros.finance/open-api/v1/`.
- **Dependencies**: `@pendle/sdk-boros` (TS), Hawkes/arrival-process library (Python — candidates: `tick`, hand-rolled MLE), numpy/scipy/pandas, `ethers` or `viem` for on-chain reads, WebSocket client.
- **Wallet model**: Dual-wallet mandatory. Root wallet cold (deposits/withdrawals/approvals only). Agent wallet hot, limited to trading, routed through Send Txs Bot. Gas balance auto-maintained with alerts.
- **Timeline**: No deadline. Prefer correctness over speed. v0.5 in ~2 weeks engineering is the stated target from the consolidated plan, but flexibility allowed.
- **Safety**: Isolated margin only, no cross-margin. Any fill is closed immediately at market (accept taker fee as insurance). No holding fills hoping for reversion.
- **Privacy / ops**: Single operator, single wallet pair, no multi-user. Logs and decision records local.

## Key Decisions

<!-- Decisions made during initialization, captured here. Add more as project progresses. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Target only the Limit Order Liquidity Rewards pool, ignore Maker Volume Rewards | Thesis requires avoiding fills; Maker Volume pays on fills, so including it inverts the optimizer | — Pending |
| v0.5 → v1.0 build path (start with NHPP + 1 market, upgrade to per-market model selection) | De-risks engineering; proves economics cheaply at $100; per-market selection has real justification (verified CV spread 0.46–6.06) but is a 2-week addition | — Pending |
| EV-based cancel rule (no threshold dials) | Self-calibrating under competition / maturity / vol shifts; superseded the regime-threshold approach from earlier drafts | — Pending |
| OU on *basis* (Implied − Underlying) for `E[loss|fill]`, NOT raw implied APR for fill probability | Basis is stationary; raw APR is a step function on a CLOB. OU on basis has closed-form loss integral; empirical replay is the sanity check, not production input | — Pending |
| `eventIndex` (not `blockTimestamp`) for intra-block ordering | Arbitrum block ~250ms; multiple trades per block are common; `blockTimestamp` ties at the second | — Pending |
| Pre-sign cancel calldata at order-placement time | Biggest leverage point on fill avoidance; removes HTTP roundtrip from the critical path | — Pending |
| Python (models/backtest) + TypeScript (SDK/execution) split | Python has the quant library ecosystem; Boros SDK is TypeScript-native; splitting along that boundary avoids fighting either side | — Pending |
| Build engine with `voluntary_cancel_forfeits_accumulated` flag, run both branches in backtest | Phase 0 question still open; sensitivity analysis tells us whether the answer gates paper trading or is moot | — Pending |
| Local deployment for v0.5 | $100 doesn't justify a VPS; re-evaluate at scale-up if live observation shows cancel latency dominates | — Pending |
| Personal, single-user bot — no multi-tenancy | Keeps scope tight; one wallet, one operator, CLI + notebooks only | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-23 after initialization*
