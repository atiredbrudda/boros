# Requirements: Boros Reward Farming Bot

**Defined:** 2026-04-23
**Core Value:** Earn net-positive yield on posted collateral from the Boros Limit Order Liquidity Rewards pool that beats stablecoin alternatives, after gas and any fill-loss costs — on a live, single-market deployment. If the strategy is -EV, detect it cheaply and kill it, not limp along.

**Scope model:** "v1" below = **v0.5 of the consolidated plan** — the first real-capital validator. "v2" = consolidated plan **v1.0** upgrades (per-market model selection, OU-on-basis parametric loss, multi-market shortlist, HMM overlay, and associated hardening). Out-of-Scope = never for this project (separate strategy / separate product entirely).

---

## v1 Requirements

Requirements for the v0.5 release. Every requirement is testable (either automated test, deterministic check, or live operational verification) and user-centric where applicable. The user here is the single operator.

### Phase 0 — Prerequisites (must close before engineering past Phase 1a)

- [ ] **P0-01**: Operator confirms from Boros docs / `pendle-finance/boros-core-public` repo / reward distributor contract code whether a **voluntary cancel forfeits accumulated reward-time-weight contribution** for the current epoch, and records the answer as a wiki page with `Status: Current` and sets `voluntary_cancel_forfeits_accumulated` in config accordingly.
- [ ] **P0-02**: Operator confirms the **actual protocol minimum order size** (collateral-equivalent) for the shortlisted markets and records it as a wiki page. If the minimum exceeds $100 on every candidate market, the project halts at Phase 0 as a cheap kill — no capital deployed, no further engineering.
- [ ] **P0-03**: Operator verifies the **Boros WebSocket URL, subscription message schema, and heartbeat/reconnect semantics** against the live service (or SDK source) and records findings as a wiki page. Includes answer to: "is there a per-account fill channel?" If no, the 1 Hz REST diff poll is promoted from backup to primary.
- [ ] **P0-04**: Operator verifies whether `@pendle/sdk-boros` v1.1.44 exposes a **sign-only (no-submit) primitive** for cancel calldata, or whether pre-signed cancel calldata must be composed via `POST /calldata/cancel-order` + viem `signTransaction` manually. Wiki page records the answer.
- [ ] **P0-05**: Operator runs an `eventIndex`-coverage probe across all candidate markets from historical NDJSON and confirms `eventIndex` is present on every trade record. Any market missing it is downgraded to price-touch fallback (and documented as a degradation).
- [ ] **P0-06**: Operator enumerates the **full fee schedule** — maker fee (0 expected), taker fee, settlement fee per payment period, market entrance fee — for each candidate market and records to the wiki. Unknown fees block paper trading.

### Phase 1a — Infrastructure Spine (before any model code)

- [ ] **INFRA-01**: Project repo initializes a monorepo layout with `python/` (bot brain, models, backtest) and `ts/` (hands: SDK, execution, WS listener) + a shared `configs/` and `docs/`.
- [ ] **INFRA-02**: A single **Pydantic v2 config schema** is the source of truth for every "knob" (strategy params, thresholds, market targets, API URLs, wallet addresses). Config loads once per run; hot-reload not supported for v0.5.
- [ ] **INFRA-03**: A **SQLite database with WAL mode** holds shared cross-process state: in-flight orders, queue-position estimates, reward accrual tracker, recent fills/PnL. Single-writer-per-table discipline is documented and linted.
- [ ] **INFRA-04**: **DuckDB read-only** layer sits over the NDJSON parquet + SQLite for backtest / analysis queries — no writes, pure analytical reads.
- [ ] **INFRA-05**: **ZMQ IPC** between Python `brain` and TypeScript `hands` over two sockets: `ipc:///tmp/boros.cmd` (PUSH/PULL, priority lanes so KILL preempts placements) and `ipc:///tmp/boros.events` (PUB/SUB).
- [ ] **INFRA-06**: A **RUN_MANIFEST writer** emits the manifest as (a) first log record, (b) `<run_id>.manifest.json` sidecar. Fields: `run_id` (ULID), `started_at`, `mode` (backtest/paper/live), `git_sha`, `git_dirty`, `strategy_version`, `market_id`, `side`, `wallet_address_hash`, full config tree. Mid-run knob change triggers a new `run_id` with `parent_run_id` pointer.
- [ ] **INFRA-07**: A **structured JSON logger** (`structlog`) emits one record per event. Every log line carries the active `run_id` for join-on-grep. Log files written to `logs/<YYYY-MM-DD>/<run_id>.log.jsonl`.
- [ ] **INFRA-08**: `docs/ARCHITECTURE.md` is created with a Mermaid diagram + `docs/architecture.yml` machine-readable manifest listing every module, public function, CLI command, and config knob with typed edges (`calls`, `reads`, `writes`, `emits-event`, `subscribes-to`, `depends-on-config`).
- [ ] **INFRA-09**: A **pre-commit hook** runs `scripts/architecture_lint.py` that parses `architecture.yml`, walks the source tree, and fails the commit if code changes don't touch the architecture manifest when they should (or vice versa). This is the mechanical enforcement of Engineering Protocol #2.
- [ ] **INFRA-10**: LLM Wiki boros workspace is seeded with the initial page set derived from existing planning docs (`boros_bot_guide.md`, `boros_consolidated_plan.md`, `plan_comparison.md`, the four research docs). Every seed page has `**Status:**` set. `index.md` thematic map + alphabetical listing are both populated.
- [ ] **INFRA-11**: A **wiki-cite pre-commit hook** fails any commit that introduces a new `research/`, `decisions/`, or `postmortem/` markdown file without at least one `[[wiki-link]]` cite — mechanical enforcement of Engineering Protocol #1 write-back.
- [ ] **INFRA-12**: Secrets (agent wallet private key, RPC URLs, API keys) are loaded via **`dotenvx`** encrypted envs, never committed plaintext. `.env.vault` is committed; `.env.keys` is gitignored and stored in macOS Keychain.
- [ ] **INFRA-13**: **Process supervision via `launchd`** plist (macOS native) — separate plists for `brain` and `hands`, each auto-restarts on crash, logs to `logs/supervisor/`.
- [ ] **INFRA-14**: An **NTP / chain-time drift monitor** runs in `brain` and logs delta between `time.time()` and Arbitrum block time every minute; excessive drift (>5s) triggers a warning, >30s a halt.

### Phase 1b–d — Data Pipeline + Market Screener + Economics Gate

- [ ] **DATA-01**: NDJSON ingester downloads and parses `market-trades/` for every candidate market, preserving `eventIndex`, `blockTimestamp`, `rate`, `side`, `size`, `txHash`. Stored as partitioned parquet; sizes are explicitly wei → float converted.
- [ ] **DATA-02**: NDJSON ingester downloads `order-book/{market}/raw/` hourly snapshots (per-tick `{t, sz}`) and `order-book/{market}/combined_{tickSize}/` for AMM-merged snapshots.
- [ ] **DATA-03**: NDJSON ingester downloads `underlying-apr/` funding-rate series per relevant CEX-asset pair.
- [ ] **DATA-04**: NDJSON ingester downloads `settlement/` and `market-data/` records for the same markets.
- [ ] **DATA-05**: An **AMM-conservation assertion** runs on every combined snapshot: `combined_size(δ) − raw_book_size(δ) ≥ 0` per tick; violations fail ingest loud.
- [ ] **DATA-06**: `GET /markets` live poller (every ~30s) detects `cloLowerThresh`/`cloUpperThresh` changes and writes a timestamped row to `clo_history` table in SQLite.
- [ ] **DATA-07**: `fIndexOracle.getLatestFIndex()` on-chain reader decodes the packed `bytes26 → bytes32` payload per `boros_bot_guide.md` L203-213 and returns `fTime`, `floatingIndex`, `feeIndex`. `latestAnnualizedRate()` returns current spot rate. Both cached ≤1s.
- [ ] **DATA-08**: **Market screener** computes per candidate market: total trades last 60d, inter-arrival CV using `eventIndex`-ordered intervals, mid-rate realized vol (pp/5min last 14d), mid-rate reversal count (last 3d), order-book depth at incentivized range, `cloLowerThresh`/`cloUpperThresh` both non-zero, time-to-maturity ≥ 30d. Outputs a shortlist of 2–4 markets.
- [ ] **DATA-09**: **Reward-share economics gate** computes `R_apr_on_collateral = R_share_per_epoch × epochs_per_year / required_collateral` per shortlisted market. Markets below `alternative_yield + estimated_fill_loss_rate` are dropped. Empty shortlist after this filter = cheap kill, project halts with a written kill report.
- [ ] **DATA-10**: **Daily automated market re-screen** reruns DATA-08 + DATA-09 and flags any markets newly entering or exiting the shortlist to operator.
- [ ] **DATA-11**: **`E_liq_per_epoch` + Long/Short split polling** every cycle (1–5s) during live/paper operation; values written to `reward_budget_history` in SQLite (feeds DF-04 sizing + A2 rebalance detection).

### Phase 2 — Fill Model (v0.5 NHPP)

- [ ] **FILL-01**: A **non-homogeneous Poisson process (NHPP)** fill model fits per market-side `λ_s(δ, t) = exp(β_0 + Σ β_i feature_i(t))` for depth `δ` and time `t`.
- [ ] **FILL-02**: Covariates include: time-since-funding-settlement (mod 8h), basis spread `B(t) = Implied − Underlying`, order-book imbalance, EWMA realized-vol of mid-rate (last 5 min), underlying CEX spot move (last 5 min), time-to-maturity, `dRate/dt` of mark APR.
- [ ] **FILL-03**: **Queue-position tracker** replays the `market-trades/` tape between hourly `raw/` snapshots, decrementing resting size at each tick as takers consume. Produces queue-ahead estimate per in-flight order.
- [ ] **FILL-04**: **AMM consumption model** subtracts `combined_size − raw_book_size` AMM share from incoming taker flow before crediting the resting book.
- [ ] **FILL-05**: Fill model exposes `P(fill_this_epoch | δ, side, queue_ahead, features)` to the decision engine; covered by calibration tests on backtest hold-out.
- [ ] **FILL-06**: Fill-model fit uses **rolling 14-day windows** per market and emits a goodness-of-fit metric; fit degradation beyond a threshold raises a warning.

### Phase 3 — Conditional Loss Model (v0.5 empirical)

- [ ] **LOSS-01**: **Empirical post-fill path replayer** slices all historical fills by `(depth-from-mark-at-fill-time, time-to-maturity bucket)` and computes the empirical post-fill PnL distribution per cell, conditional on the operator's immediate-close policy (market order).
- [ ] **LOSS-02**: `E[loss | fill at tick X, τ]` is exposed to the decision engine with a documented policy for sparse cells (nearest-neighbor fallback with warning).
- [ ] **LOSS-03**: A **scaffold for the v1.0 OU-on-basis parametric model** exists (module + interface + failing stub test) so v1.0 can drop in without restructuring the decision engine.

### Phase 4 — Reward-Share Model & Sizing

- [ ] **REWARD-01**: Capped pro-rata reward-share calculator: `R_uncapped(Q_me) = E_liq_per_epoch × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)`; `R_capped(Q_me) = min(R_uncapped, 10 × collateral × epoch_days/365)`.
- [ ] **REWARD-02**: `Q_total_in_range` tracker polled every cycle from `GET /v2/accounts/all-limit-orders` or direct order-book aggregation.
- [ ] **REWARD-03**: **Sizing optimizer** returns `Q_me_target = argmax R_capped − E[loss|fill] × P(fill) subject to Q_min ≤ Q_me ≤ Q_max`. At $100 collateral, `Q_me_target = Q_min` always (sub-cap regime); this branch is tested.
- [ ] **REWARD-04**: `Q_cap` computation (cap-binding regime boundary) is present in code even though it doesn't bind at $100, so scale-up doesn't silently oversize.

### Phase 5 — Decision Engine

- [ ] **DECIDE-01**: **EV-based cancel rule** evaluates `EV_hold = R_liq_share_per_epoch × P(no_fill_and_unpurged) − E[loss|fill] × P(fill_this_epoch) − cancel_cost × P(purge)` per side per in-flight order per cycle; cancels iff `EV_hold < 0`.
- [ ] **DECIDE-02**: The `voluntary_cancel_forfeits_accumulated` boolean flag from P0-01 toggles between punitive / benign branches of the decision rule; both branches are covered by tests and in backtest sensitivity analysis.
- [ ] **DECIDE-03**: `cancel_cost` is the measured on-chain transaction cost (not a hardcoded estimate) drawn from recent gas history.
- [ ] **DECIDE-04**: **No threshold dials** — the only knobs are inputs to the EV equation (model parameters) and breaker thresholds. No hand-tuned "cancel when rate drift > X%."

### Phase 6 — Predictive Circuit Breakers

- [ ] **SAFE-01**: **Margin trajectory breaker** — at current `dNetBalance/dt`, if time-to-maintenance-margin < 30s, emergency close all positions and cancel all orders.
- [ ] **SAFE-02**: **Oracle staleness breaker** — `now − fTime > 0.7 × maxUpdateDelay` cancels all orders.
- [ ] **SAFE-03**: **CLO removal breaker** — `cloLowerThresh == 0 OR cloUpperThresh == 0` cancels all and alerts.
- [ ] **SAFE-04**: **CLO shift breaker** — `|new_clo − old_clo| > N ticks` cancels, recalibrates, reposts.
- [ ] **SAFE-05**: **Fill-rate runaway breaker** — more than K fills in last hour (K=3 for v0.5) pauses the bot for manual review.
- [ ] **SAFE-06**: **Competition-collapse breaker** — `Q_total_in_range` dropped > 50% in 1 epoch pauses with an investigation alert (they may know something we don't).
- [ ] **SAFE-07**: **Maturity-migration breaker** — `time_to_maturity × R_me_per_epoch < migration_cost` rolls position to the next maturity.
- [ ] **SAFE-08**: **Per-side budget rebalance breaker** — `E_liq_per_epoch` split moves > 30% away from our posted side in one epoch → halve position or cancel pending operator review (A2 pitfall mitigation).
- [ ] **SAFE-09**: **Underlying-feed-stale breaker** — underlying CEX funding feed not updated within 2× expected cadence → halt (A7 pitfall mitigation).
- [ ] **SAFE-10**: **Kill authority is exclusive to the breaker coordinator** — no other component can submit orders when any breaker is tripped. Breaker messages use the ZMQ priority KILL lane.

### Phase 7 — Event-Driven Backtest

- [ ] **BACK-01**: **Event-driven replay engine** processes the trade tape in `eventIndex` order, maintains per-tick resting-size state from hourly snapshot anchors, simulates AMM consumption via `combined − raw`, and records every decision the live bot would have made.
- [ ] **BACK-02**: **Cancel latency simulation** — operator-configurable latency (2–5s default) is injected into fill-response decisions; both order-of-event and time-since-event are modeled.
- [ ] **BACK-03**: **Cancel-latency sensitivity sweep** — backtest runs across L ∈ {0.5s, 1s, 2s, 3s, 5s, 10s} and reports `dP&L/dL` as a concrete "is colocation / VPS worth it?" answer.
- [ ] **BACK-04**: **Competition sensitivity sweep** — backtest runs with synthetic Q_total_in_range multipliers and reports `dP&L / dQ_competing` for scaling discipline.
- [ ] **BACK-05**: Backtest outputs: net P&L per unit collateral annualized, Sharpe-equivalent, max drawdown, calibration plot (predicted P(fill) vs realized), dP&L/dL curve, dP&L/dQ_competing curve.
- [ ] **BACK-06**: **Voluntary-cancel sensitivity** — backtest runs both branches of the P0-01 flag (`voluntary_cancel_forfeits_accumulated` true/false) and reports divergence. Material divergence blocks paper trading until P0-01 is definitively resolved.
- [ ] **BACK-07**: **Bootstrap ship-gate** — Phase 7 passes only if the 5th percentile of bootstrapped annualized P&L exceeds `alternative_yield + all_fees`. Point estimate > alt yield is insufficient; we need distribution tail.
- [ ] **BACK-08**: **Perturbation grid** — backtest runs with each knob perturbed ±20% individually; sign-flipping on any knob is a fragility flag surfaced in the ship-gate report.

### Phase 8 — Execution Layer (TypeScript `hands`)

- [ ] **EXEC-01**: **Dual-wallet setup**: root wallet cold (deposits/withdrawals/approvals only), agent wallet hot for trading only, routed through `https://api.boros.finance/send-txs-bot/v2/`.
- [ ] **EXEC-02**: **Order placement** via `POST /calldata/place-orders-with-rate` using `@pendle/sdk-boros` v1.1.44; order type is `GTC` for reward farming.
- [ ] **EXEC-03**: **Pre-signed cancel calldata** is generated and cached in memory at order-placement time; on WS fill or decision-engine cancel command, the pre-signed bytes are submitted instantly (no HTTP roundtrip in critical path).
- [ ] **EXEC-04**: **Nonce-chain management** — pre-signed cancels use deterministic nonces; operator policy for nonce-chain stalls (timeout → re-sign or resubmit-with-replacement) is documented and implemented. Decision doc committed at `docs/nonce-policy.md`.
- [ ] **EXEC-05**: **WebSocket fill listener** subscribes per market; on fill event, fires pre-signed close calldata for the fill and fires pre-signed cancels for related orders if policy demands.
- [ ] **EXEC-06**: **REST fill-diff poller** at 1 Hz polls `/v2/accounts/all-limit-orders` and cross-checks against expected state; discrepancies (fill missed by WS, unexpected cancel) raise alerts and can trigger breakers.
- [ ] **EXEC-07**: **WS reconnect with exponential backoff + heartbeat** — disconnect triggers cancel-all-orders after a configurable grace period to prevent unsupervised fill exposure.
- [ ] **EXEC-08**: **Gas-balance three-level monitor** — info (> 3 days cover), warn (1 day), halt (< 1 hr); halt cancels all and alerts operator. Auto-topup not implemented for v0.5 (manual top-up required on warn).
- [ ] **EXEC-09**: **Self-trade prevention check** — before any order placement, verify no conflicting orders in own book per Boros SDK constraints (NP-01 promotion).
- [ ] **EXEC-10**: **Immediate market close on fill** — if a fill slips through, `close_position(market_order)` fires unconditionally; no hold-for-reversion branch exists in code (enforced by absence).

### Phase 9 — Paper Trading

- [ ] **PAPER-01**: **Live-feeds / no-capital mode** — all data pipelines and decision logic run live, but no `send-txs-bot` submission; instead a "phantom" execution layer logs what would have happened.
- [ ] **PAPER-02**: **Counterfactual decision log** — for every tick, log `{timestamp, run_id, decision, reason, predicted_P(fill), E[loss|fill], R_share, EV_hold, would_have_filled, would_have_earned}`.
- [ ] **PAPER-03**: **Backtest-reconciliation report** — at paper session end, compare phantom fills / phantom rewards / decision accuracy against backtest predictions. Divergence > 1σ blocks live promotion.
- [ ] **PAPER-04**: **Perturbed-parameter neighbor runs** — paper runs occasionally with individual knobs perturbed ±20% to measure realized sensitivity vs backtest sensitivity (BACK-08 validation).
- [ ] **PAPER-05**: **Merkle-claim reconciliation (phantom)** — predicted accrual per epoch reconciled against actual Merkle root values post-epoch; tolerance documented.
- [ ] **PAPER-06**: Paper session runs minimum **2 weeks** before live promotion is considered; 4 weeks recommended by consolidated plan.

### Phase 10 — Live Rollout

- [ ] **LIVE-01**: **Single market, highest conviction from shortlist** — no multi-market in v0.5.
- [ ] **LIVE-02**: **One side only at a time** — posting long XOR short based on Mark-vs-Underlying as endorsed by the Pendle team (0x0Kippon tweet).
- [ ] **LIVE-03**: **Minimum viable order size** — the protocol minimum from P0-02, not the $100 user collateral (collateral is the sizing budget; order size is the protocol floor).
- [ ] **LIVE-04**: **2-week observation window** before any scale-up.
- [ ] **LIVE-05**: **Live vs paper reconciliation** — weekly comparison of realized P&L vs paper-predicted P&L; divergence > 1σ halts and triggers debug.
- [ ] **LIVE-06**: **Merkle claim scheduler** polls distributor contract for new root every 15 min during claim day (Monday); auto-submits proof when root updates.
- [ ] **LIVE-07**: **Private RPC endpoint** for Arbitrum — public `arb1.arbitrum.io/rpc` is fine for reads but a private endpoint is required before live to prevent rate-limits during a cancel burst. Acceptable: operator's own node, paid provider, or curated public-provider rotation.
- [ ] **LIVE-08**: **Config-dry-run gate** — before any config change goes live, a dry-run backtest + paper-replay must pass. Bypass requires explicit `--force` flag and emits a loud warning in the run manifest.

### Cross-cutting — Engineering Protocols (apply to every phase)

- [ ] **PROTO-01**: Every run (backtest, paper, live) emits `RUN_MANIFEST` as first log line + sidecar JSON; log lines carry `run_id`. Enforced by INFRA-06.
- [ ] **PROTO-02**: Every commit that touches `python/` or `ts/` source also updates `docs/ARCHITECTURE.md` + `docs/architecture.yml`; pre-commit hook (INFRA-09) blocks non-compliant commits.
- [ ] **PROTO-03**: Every research / decision / postmortem commit cites at least one `[[wiki-link]]` into the LLM Wiki boros workspace; pre-commit hook (INFRA-11) blocks non-compliant commits.
- [ ] **PROTO-04**: Every new "knob" is added to the Pydantic config schema (INFRA-02) — schema is the exhaustive source of truth for `RUN_MANIFEST` field list.
- [ ] **PROTO-05**: Supersedence discipline — when a new wiki page invalidates an older finding, the older page gets `Status: Historical — superseded by [[new-page]]` in the same commit.

---

## v2 Requirements

Deferred to the consolidated plan's **v1.0**. Tracked but not in the current roadmap.

### Per-market fill model selection

- **V2-FILL-01**: Inter-arrival CV dispersion test gates model selection: Hawkes for CV > 1.5, NHPP for 0.7 ≤ CV ≤ 1.5, renewal process (gamma inter-arrivals) for CV < 0.7.
- **V2-FILL-02**: Hawkes MLE estimator (via `tick` library) with covariate-driven baseline.
- **V2-FILL-03**: Renewal process (gamma / Weibull) fit for under-dispersed markets.
- **V2-FILL-04**: Per-market model registry with version-pinned model artifacts.

### Parametric loss model

- **V2-LOSS-01**: OU on basis `B(t) = Implied − Underlying` with bias-corrected MLE on rolling 14-day windows.
- **V2-LOSS-02**: Closed-form `E[loss | fill at X, τ] = E[ ∫_t^{t+τ} (Realized_Funding − X) du ]` with 90% CI.
- **V2-LOSS-03**: OU vs empirical cross-check plot per cell; divergence > 2σ triggers investigation before trusting either.
- **V2-LOSS-04**: Production input = OU; empirical is sanity check.

### Multi-market shortlist operation

- **V2-MULTI-01**: Bot runs across the full 2–4 market shortlist from DATA-08 concurrently.
- **V2-MULTI-02**: Per-market capital allocation optimizer (not equal-weight).
- **V2-MULTI-03**: Cross-market correlation in circuit-breaker triggers (if multiple markets trip simultaneously, something global).

### HMM confirmation overlay (optional)

- **V2-HMM-01**: 2-state Gaussian HMM fit on same covariates as fill model.
- **V2-HMM-02**: 4-week paper evaluation to decide: drop (if noise) or keep (as vetoing layer).

### Scale-up capacity

- **V2-SCALE-01**: Cap-binding regime sizing tests at collateral > $1k (when the 1000% APR cap starts to bind on at least one market).
- **V2-SCALE-02**: VPS / colocation decision based on cancel-latency sensitivity curve from BACK-03.
- **V2-SCALE-03**: Session-key wallet pattern for hot wallet (replaces direct private-key hot storage).

### Adversarial robustness

- **V2-ADV-01**: Randomized placement timing (anti-front-run).
- **V2-ADV-02**: Decoy order patterns (if competing bots learn placement pattern).

---

## Out of Scope

Never for this project. Each is a separate strategy or product entirely.

| Feature | Reason |
|---------|--------|
| Capturing Maker Volume Rewards pool | Pays on fills; this strategy avoids fills by design. Including it inverts the optimizer. |
| Directional rate forecasting (predict where APR goes) | Strategy models taker arrivals, not rate direction. |
| Cross-margin strategies or CEX hedges | Isolated margin only; hedging accidental fills is a different, heavier risk model. |
| Holding fills for mean reversion | Immediate market close on fill is enforced; no reversion branch. |
| Spread-capture / market making on fills | A different strategy entirely. If pursued, new plan. |
| Multi-user / SaaS deployment | Personal bot. No accounts, auth, tenancy. |
| Mobile / web GUI dashboard | CLI logs + notebook analytics only. |
| Cold-start on brand-new markets | Each market needs its own calibration window; listing-day participation excluded. |
| One-size-fits-all fill model for all markets | Verified by CV spread 0.46–6.06 across markets; v0.5 is NHPP-only pragmatically but v1.0 requires per-market selection. |
| OU on raw implied APR for fill probability | CLOB price is a step function; continuous-diffusion models it incorrectly for fills. OU survives only for the post-fill loss integral. |
| Multi-oracle aggregation for CEX funding rates | Single canonical oracle per underlying per market; protocol's choice, not ours. |
| MEV protection (private mempool / Flashbots) | Arbitrum, maker-only limit orders — MEV surface not meaningful for this strategy. |
| Copy-trading / signals-following | Strategy is self-contained; no external signal inputs. |
| ML ensemble fill models | NHPP / Hawkes / RP selected by CV is the method; ML ensemble is unjustified complexity. |
| Inventory skew trading | We avoid inventory by design. |
| Hot-reload of config mid-run | Config load-once; changes require new run (parent_run_id pointer tracks lineage). |

---

## Traceability

Every v1 requirement is mapped to exactly one phase. Phase names are the consolidated roadmap titles (see `.planning/ROADMAP.md`).

| Requirement | Phase | Status |
|-------------|-------|--------|
| P0-01 | Phase 0: Prerequisite Resolution & Kill Gate | Pending |
| P0-02 | Phase 0: Prerequisite Resolution & Kill Gate | Pending |
| P0-03 | Phase 0: Prerequisite Resolution & Kill Gate | Pending |
| P0-04 | Phase 0: Prerequisite Resolution & Kill Gate | Pending |
| P0-05 | Phase 0: Prerequisite Resolution & Kill Gate | Pending |
| P0-06 | Phase 0: Prerequisite Resolution & Kill Gate | Pending |
| INFRA-01 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-02 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-03 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-04 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-05 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-06 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-07 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-08 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-09 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-10 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-11 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-12 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-13 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| INFRA-14 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-01 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-02 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-03 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-04 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-05 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-06 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-07 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-08 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-09 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-10 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| DATA-11 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| PROTO-01 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| PROTO-02 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| PROTO-03 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| PROTO-04 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| PROTO-05 | Phase 1: Foundation (Infra + Data + Economics Gate) | Pending |
| FILL-01 | Phase 2: Fill Model (NHPP v0.5) | Pending |
| FILL-02 | Phase 2: Fill Model (NHPP v0.5) | Pending |
| FILL-03 | Phase 2: Fill Model (NHPP v0.5) | Pending |
| FILL-04 | Phase 2: Fill Model (NHPP v0.5) | Pending |
| FILL-05 | Phase 2: Fill Model (NHPP v0.5) | Pending |
| FILL-06 | Phase 2: Fill Model (NHPP v0.5) | Pending |
| LOSS-01 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| LOSS-02 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| LOSS-03 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| REWARD-01 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| REWARD-02 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| REWARD-03 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| REWARD-04 | Phase 3: Loss & Reward-Share Models + Sizing | Pending |
| DECIDE-01 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| DECIDE-02 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| DECIDE-03 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| DECIDE-04 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-01 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-02 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-03 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-04 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-05 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-06 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-07 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-08 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-09 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| SAFE-10 | Phase 4: Decision Engine + Predictive Circuit Breakers | Pending |
| BACK-01 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-02 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-03 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-04 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-05 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-06 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-07 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| BACK-08 | Phase 5: Event-Driven Backtest (Ship-Gate) | Pending |
| EXEC-01 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-02 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-03 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-04 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-05 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-06 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-07 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-08 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-09 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| EXEC-10 | Phase 6: Execution Layer (TypeScript hands) | Pending |
| PAPER-01 | Phase 7: Paper Trading (2–4 Weeks) | Pending |
| PAPER-02 | Phase 7: Paper Trading (2–4 Weeks) | Pending |
| PAPER-03 | Phase 7: Paper Trading (2–4 Weeks) | Pending |
| PAPER-04 | Phase 7: Paper Trading (2–4 Weeks) | Pending |
| PAPER-05 | Phase 7: Paper Trading (2–4 Weeks) | Pending |
| PAPER-06 | Phase 7: Paper Trading (2–4 Weeks) | Pending |
| LIVE-01 | Phase 8: Live Rollout | Pending |
| LIVE-02 | Phase 8: Live Rollout | Pending |
| LIVE-03 | Phase 8: Live Rollout | Pending |
| LIVE-04 | Phase 8: Live Rollout | Pending |
| LIVE-05 | Phase 8: Live Rollout | Pending |
| LIVE-06 | Phase 8: Live Rollout | Pending |
| LIVE-07 | Phase 8: Live Rollout | Pending |
| LIVE-08 | Phase 8: Live Rollout | Pending |

**Coverage:**
- v1 requirements: 95 total (6 P0 + 14 INFRA + 11 DATA + 6 FILL + 3 LOSS + 4 REWARD + 4 DECIDE + 10 SAFE + 8 BACK + 10 EXEC + 6 PAPER + 8 LIVE + 5 PROTO)
- Mapped to phases: 95
- Unmapped: 0 ✓
- Orphaned phases: 0 ✓
- Note: Earlier header count of "87 total" was a drafting undercount; the detailed list above enumerates 95 REQ-IDs and all 95 are now mapped to exactly one phase.

---
*Requirements defined: 2026-04-23*
*Last updated: 2026-04-23 — traceability table populated by roadmapper*
