# Roadmap: Boros Reward Farming Bot

## Overview

v0.5 delivers a single-user, single-market, $100-collateral real-capital validator for the Pendle Boros Limit Order Liquidity Rewards strategy. The journey runs Phase 0 (cheap empirical kill-gate on six open questions) → Phase 1 (infrastructure spine + data pipeline + economics gate, Engineering Protocols installed here so every downstream artifact inherits them) → Phases 2–3 (three EV input models: fill probability, conditional loss, reward share) → Phase 4 (EV-based decision engine + predictive circuit breakers with exclusive kill authority) → Phase 5 (event-driven backtest as bootstrap ship-gate) → Phase 6 (TypeScript execution layer with pre-signed cancel calldata) → Phase 7 (2–4 week paper trading reconciliation) → Phase 8 (live rollout at $100, one market, one side, 2-week observation). Any phase that fails its exit criteria halts the project; Phase 0 in particular is a hard kill-gate — if the protocol minimum order size exceeds $100-collateral-equivalent (P0-02), the project halts with no capital deployed and no further engineering.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 0: Prerequisite Resolution & Kill Gate** - Close six empirical open questions; halt on minimum-order-size failure before any engineering. **COMPLETE 2026-04-23** — all 6 questions resolved cheaply via docs + official-team statement + spot probe (no engineering required); halt condition (P0-02) cleared (no protocol minimum); each answer filed as a wiki page with `Status: Current`. Phase 1 schema defaults set per resolutions (`voluntary_cancel_forfeits_accumulated=False`, `socket.io-client` over raw `ws`, `submission_path` knob dropped, Send Txs Bot mandatory).
- [ ] **Phase 1: Foundation (Infrastructure Spine + Data Pipeline + Economics Gate)** - Install Engineering Protocols, ZMQ/SQLite/manifest/wiki, ingest data, compute economics kill-switch; second cheap-kill gate on empty shortlist.
- [ ] **Phase 2: Fill Model (NHPP v0.5)** - Calibrated `P(fill | δ, side, queue_ahead, features)` with queue tracker and AMM consumption model.
- [ ] **Phase 3: Loss & Reward-Share Models + Sizing** - Empirical `E[loss|fill]`, capped pro-rata reward share with live budget polling, sizing optimizer.
- [ ] **Phase 4: Decision Engine + Predictive Circuit Breakers** - EV cancel rule wired over the three input models; ten predictive breakers with exclusive KILL authority.
- [ ] **Phase 5: Event-Driven Backtest (Ship-Gate)** - `eventIndex`-ordered, queue-aware, AMM-aware replay with cancel-latency sweep; bootstrap 5th-percentile ship-gate against alt-yield.
- [ ] **Phase 6: Execution Layer (TypeScript hands)** - Dual-wallet + pre-signed cancel calldata + WebSocket fill listener + gas monitor; hot path stays in-process.
- [ ] **Phase 7: Paper Trading (2–4 Weeks)** - Live feeds, no capital; phantom fills logged, backtest reconciled; divergence > 1σ blocks live promotion.
- [ ] **Phase 8: Live Rollout** - $100 collateral, one market, one side, protocol-minimum order size, 2-week observation window; weekly P&L reconciliation.

## Phase Details

### Phase 0: Prerequisite Resolution & Kill Gate
**Goal**: Close six binary empirical open questions cheaply (before any engineering past Phase 1) so the strategy, the EV rule, and the $100 premise are not built on air. Project halts here on any existential failure — minimum order size > $100 is the dominant halt condition.
**Depends on**: Nothing (first phase)
**Requirements**: P0-01, P0-02, P0-03, P0-04, P0-05, P0-06
**Scope**:
  - ~~Trace `cancelOrder()` in `pendle-finance/boros-core-public` reward distributor to determine whether voluntary cancel forfeits accumulated epoch time-weight~~ **RESOLVED 2026-04-23**: Boros official team statement confirms voluntary cancel does NOT forfeit accumulated LO reward ("accumulated rewards won't go to zero even if users cancel"). Wiki page filed at [[Voluntary cancel reward behavior]]; `voluntary_cancel_forfeits_accumulated = False` in Phase 1 config schema. Follow-up contract trace is opportunistic only, not a blocker (P0-01, absorbs pitfall A1 Phase-0 portion).
  - ~~Confirm actual protocol minimum order size~~ **RESOLVED 2026-04-23** ([[Minimum order size]]): docs state "No minimum order size requirement." Existential halt condition is off the table (P0-02).
  - ~~Verify Boros WebSocket URL, subscription schema, heartbeat/reconnect semantics, per-account fill channel~~ **RESOLVED 2026-04-23** ([[Boros WebSocket API]]): `wss://api.boros.finance/pendle-dapp-v3` via **Socket.IO** (stack change: `socket.io-client` replaces `ws 8.20`), per-account channel `account-updates:ROOT` emits `order-update` with `efs` fill-size + `os` status. REST poll stays as reconciliation backup. Heartbeat/event-replay-on-reconnect verified empirically in Phase 1 implementation (P0-03).
  - ~~Verify @pendle/sdk-boros sign-only primitive~~ **RESOLVED 2026-04-23** ([[Sign-only cancel primitive]] + [[Send Txs Bot integration]]): Send Txs Bot is the mandatory submission lane via `POST /v2/agent/bulk-direct-call` (multi) and `/v2/agent/direct-call` (single), v2 only. Pre-signing the cancel calldata at placement time remains the correct optimization (saves one hot-path roundtrip). Direct-to-chain submit ruled out as a design goal — the `submission_path` knob is dropped from Phase 6 scope (P0-04).
  - ~~Run `eventIndex`-coverage probe across candidate markets~~ **SPOT-CONFIRMED 2026-04-23** ([[eventIndex coverage]]): present on ETHUSDT sample + on WS `order-update` field `ei`. Cross-market probe absorbed into Phase-1 ingester DATA-01 / DATA-08; missing-market fallback to price-touch already specified (P0-05).
  - ~~Enumerate full fee schedule~~ **MOSTLY RESOLVED 2026-04-23** ([[Boros fee schedule]]): maker 0, taker ~0.05% per-market (`MarketConfig.takerFee`) formula `|Size|×Rate×TimeToMaturity` discountable, settlement `|Size|×Rate×Period` non-discountable, entrance ~$1/market one-time, no protocol cancel fee. Gas measured empirically per DECIDE-03 (P0-06).
  - Engineering Protocols 1 (wiki) and 3 (manifest) apply — each answer lands as a wiki page with `Status: Current`; Protocol 2 (diagram) N/A at this phase since no code exists yet.
**Success Criteria** (what must be TRUE):
  1. Each of the six P0 questions has a wiki page filed at `../LLM Wiki/workspaces/boros/wiki/` with `Status: Current` and a concrete answer (or `Status: Current — PARTIAL` with a documented fallback if the protocol truly doesn't expose the answer). **Status 2026-04-23:** P0-01, P0-02, P0-03, P0-04, P0-06 resolved; P0-05 spot-confirmed with cross-market probe absorbed into Phase 1 ingester.
  2. The `voluntary_cancel_forfeits_accumulated` boolean is set to `False` in the Phase 1 config schema per P0-01 resolution 2026-04-23 ([[Voluntary cancel reward behavior]]). Phase 5 backtest still sweeps both branches as a sanity-check row, not as a blocking gate.
  3. ~~The minimum-order-size check has produced a go/no-go decision~~ **RESOLVED** — no protocol minimum ([[Minimum order size]]); project proceeds. Economic sizing is a Phase 1 economics-gate concern (DATA-09), not a Phase 0 halt.
  4. The fee schedule is enumerated with concrete numbers per candidate market such that the EV equation's `fee_cost` term will have real inputs in Phase 4.
**Plans**: TBD
**UI hint**: no

### Phase 1: Foundation (Infrastructure Spine + Data Pipeline + Economics Gate)
**Goal**: Install the full Engineering-Protocol-compliant infrastructure (SQLite, ZMQ bus, RUN_MANIFEST writer, structured logger, architecture diagram + pre-commit lint, wiki seeding, encrypted secrets, process supervision) and ingest the confirmed market data, then pass the economics kill-switch so no downstream model code is built on a market that can't beat alt-yield. This phase is load-bearing for every subsequent artifact — logs emitted before the manifest writer exists are unreadable by design. The cross-cutting Protocols (PROTO-01..05) anchor here and apply to every subsequent phase.
**Depends on**: Phase 0
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INFRA-07, INFRA-08, INFRA-09, INFRA-10, INFRA-11, INFRA-12, INFRA-13, INFRA-14, DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08, DATA-09, DATA-10, DATA-11, PROTO-01, PROTO-02, PROTO-03, PROTO-04, PROTO-05
**Scope**:
  - Monorepo `python/` + `ts/` + `configs/` + `docs/` layout; `uv` + `pnpm` package managers (INFRA-01).
  - Single Pydantic v2 `BotConfig` class with mode-specific sections, `extra='forbid'`, frozen; round-trip test in pre-commit (INFRA-02, PROTO-04, absorbs pitfall D4).
  - SQLite WAL spine with single-writer-per-table discipline: `open_orders`, `decisions`, `tx_receipts`, `queue_positions`, `run_manifests`, `epoch_rewards`, `clo_history`, `reward_budget_history` (INFRA-03).
  - DuckDB read-only layer over parquet + SQLite for analytical reads (INFRA-04).
  - ZMQ IPC: `ipc:///tmp/boros.cmd` PUSH/PULL with KILL priority lane; `ipc:///tmp/boros.events` PUB/SUB; 5s heartbeat both directions; "lost sibling" protocol (INFRA-05).
  - `RUN_MANIFEST` writer by Pydantic reflection: ULID `run_id`, `git_sha`, `git_dirty`, `strategy_version`, `market_id`, `side`, `wallet_address_hash`, full knob tree; mid-run knob change → new `run_id` with `parent_run_id` (INFRA-06, PROTO-01, absorbs pitfall D2).
  - `structlog` JSON logger with `contextvars`-bound `run_id` across async tasks; `pino` mirror on TS side with same contract; logs to `logs/<YYYY-MM-DD>/<run_id>.log.jsonl` (INFRA-07).
  - `docs/ARCHITECTURE.md` (Mermaid) + `docs/architecture.yml` (machine-readable) with module/function/command/config-knob nodes and typed edges (`calls`, `reads`, `writes`, `emits-event`, `subscribes-to`, `depends-on-config`) (INFRA-08, PROTO-02).
  - `scripts/architecture_lint.py` pre-commit hook that parses `architecture.yml`, walks source tree, fails commit on drift (INFRA-09, absorbs pitfall D3).
  - LLM Wiki boros workspace seeded from planning docs + research docs + Phase 0 answers; `index.md` thematic + alphabetical map populated; every seed page has `Status:` set (INFRA-10).
  - Wiki-cite pre-commit hook: any new `research/`, `decisions/`, or `postmortem/` markdown without `[[wiki-link]]` fails commit (INFRA-11, PROTO-03, absorbs pitfall D1).
  - `dotenvx` encrypted `.env.vault`; `.env.keys` in macOS Keychain, gitignored; agent wallet key decrypted at startup only (INFRA-12, absorbs pitfall C3).
  - `launchd` LaunchAgent plist for `brain` and `hands`, `KeepAlive`, `ThrottleInterval=30`; logs to `logs/supervisor/` (INFRA-13, absorbs pitfall C-category supervision concern).
  - NTP/chain-time drift monitor in `brain`: log delta every minute, >5s warns, >30s halts; all time comparisons use `chain_time` cache, not `time.time()` (INFRA-14, absorbs pitfall C7).
  - NDJSON ingester: `market-trades/` with `eventIndex`/`blockTimestamp`/`rate`/`side`/`size`/`txHash` preserved, wei→float explicit; `order-book/{market}/raw/` hourly; `order-book/{market}/combined_{tickSize}/`; `underlying-apr/`; `settlement/` + `market-data/` (DATA-01, DATA-02, DATA-03, DATA-04).
  - AMM conservation assertion: `combined_size(δ) − raw_book_size(δ) ≥ 0` per tick on every combined snapshot; violations fail ingest loud (DATA-05, absorbs pitfall B3).
  - `GET /markets` live poller (~30s) detects `cloLowerThresh`/`cloUpperThresh` changes, writes timestamped rows to `clo_history` (DATA-06).
  - `fIndexOracle.getLatestFIndex()` on-chain reader decoding packed `bytes26 → bytes32`; `latestAnnualizedRate()` spot rate reader; both cached ≤1s (DATA-07).
  - Market screener: trades last 60d, inter-arrival CV using `eventIndex`-ordered intervals, mid-rate realized vol, reversal count, depth at incentivized range, `cloLower`/`cloUpper` non-zero, ≥30d to maturity; outputs shortlist of 2–4 markets (DATA-08, absorbs pitfall B2).
  - Reward-share economics kill-switch: `R_apr_on_collateral = R_share_per_epoch × epochs_per_year / required_collateral`; drops markets below `alternative_yield + estimated_fill_loss_rate`; empty shortlist after filter halts project with a written kill report (DATA-09, cheap-kill gate).
  - Daily automated re-screen reruns DATA-08 + DATA-09, flags new-entrant or dropped markets (DATA-10, absorbs pitfall A5).
  - Live `E_liq_per_epoch` + Long/Short split polling every cycle (1–5s); writes to `reward_budget_history` (DATA-11, absorbs pitfall A2 data-collection portion).
  - Supersedence discipline (PROTO-05): new wiki finding → grep wiki for pages restating old claim → update in same commit with `Status: Historical — superseded by [[new-page]]`.
**Success Criteria** (what must be TRUE):
  1. A `brain` process can start, emit a `RUN_MANIFEST` as first log line + sidecar JSON, stamp every subsequent log line with the active `run_id`, and crash-restart under `launchd` with no orphan state; `hands` does the same on the TypeScript side.
  2. A commit that modifies source without updating `docs/architecture.yml` is rejected by the pre-commit hook, and a commit that adds a new `research/` or `decisions/` markdown without a `[[wiki-link]]` is rejected by the wiki-cite hook.
  3. Running the ingester against the confirmed candidate markets produces partitioned parquet with `eventIndex`-ordered trade tape, hourly raw + combined snapshots that pass AMM conservation, underlying APR series, and writes timestamped `clo_history` + `reward_budget_history` rows in SQLite.
  4. Running the market screener + economics kill-switch produces either a non-empty shortlist with per-market `R_apr_on_collateral` above `alternative_yield + estimated_fill_loss_rate` (project continues to Phase 2), or an empty shortlist with a written kill report (project halts).
  5. The LLM Wiki `index.md` lists the seeded pages (Python stack, TS stack, IPC boundary, architecture overview, nonce model, strategy thesis, EV cancel rule, A1/min-order open questions with Status flags) such that a future session can cite `[[page-name]]` instead of re-deriving conclusions.
**Plans**: TBD
**UI hint**: no

### Phase 2: Fill Model (NHPP v0.5)
**Goal**: Produce a calibrated `P(fill_this_epoch | δ, side, queue_ahead, features)` function exposed to the decision engine — one of the two EV-rule inputs (with `E[loss|fill]`). Use NHPP with four covariates as the v0.5 universal model; the v1.0 per-market Hawkes/RP selection is explicitly deferred. Queue-position tracker and AMM consumption model are dependencies, not add-ons: price-touch fill simulation overstates P&L.
**Depends on**: Phase 1
**Requirements**: FILL-01, FILL-02, FILL-03, FILL-04, FILL-05, FILL-06
**Scope**:
  - NHPP fit per market-side `λ_s(δ, t) = exp(β_0 + Σ β_i feature_i(t))` via `statsmodels.GLM(family=Poisson(link=log), exposure=bin_duration_s)` — the Poisson-GLM equivalent of the hand-rolled scipy MLE endorsed as the fallback in `STACK.md` §Fallbacks. `tick` 0.8.0.1 remains pinned for `SimuInhomogeneousPoisson` simulation support + v1.0 Hawkes staging; it does not ship a covariate-driven NHPP learner. Supersedence recorded at `[[Fill model library decision tick vs statsmodels]]` (filed in Plan 02-01) (FILL-01).
  - Covariates: time-since-funding-settlement (mod 8h), basis spread `B(t) = Implied − Underlying`, order-book imbalance, EWMA realized-vol of mid-rate (last 5min), underlying CEX spot move (last 5min), time-to-maturity, `dRate/dt` of mark APR (FILL-02).
  - Queue-position tracker: replay `market-trades/` tape between hourly `raw/` snapshots, decrement resting size as takers consume, with drift-direction bias diagnostic and pessimistic/optimistic bounds (FILL-03, absorbs pitfall B1).
  - AMM consumption model: subtract `combined_size − raw_book_size` AMM share from incoming taker flow before crediting resting book (FILL-04, absorbs pitfall B3 model-side portion).
  - `P(fill_this_epoch | δ, side, queue_ahead, features)` exposed to decision engine; calibration tests on backtest hold-out (FILL-05).
  - Rolling 14-day window fits per market, goodness-of-fit metric, threshold-based fit-degradation warning (FILL-06, absorbs pitfall B4 Hawkes-fit-health scaffolding).
  - Engineering Protocols 1/2/3 apply: cite `[[Python stack v0.5]]`, `[[Strategy thesis]]`; update `docs/architecture.yml` with `FillModel` node + its covariate reader edges; every calibration run emits `RUN_MANIFEST`.
**Success Criteria** (what must be TRUE):
  1. The `FillModel.predict(δ, side, queue_ahead, features)` function returns a probability in `[0, 1]` on the confirmed candidate market's trade tape and the prediction matches realized fill frequency within the calibration-test tolerance on backtest hold-out data.
  2. The queue-position tracker's drift-direction bias diagnostic reports consistent sign (pessimistic ≤ realized ≤ optimistic) across 14-day rolling windows on historical data.
  3. The AMM conservation assertion from Phase 1 holds during queue replay — no tick ever shows `AMM_share < 0` after subtracting `raw` from `combined`.
  4. A degraded fit (goodness-of-fit below the configured threshold) emits a warning log line that is grep-able by `run_id` and surfaces in the periodic calibration report.
**Plans**: TBD
**UI hint**: no

### Phase 3: Loss & Reward-Share Models + Sizing
**Goal**: Deliver the other two EV-rule inputs — empirical `E[loss|fill]` and capped pro-rata reward-share `R_capped(Q_me)` — plus the sizing optimizer. At $100 collateral the cap never binds (sub-cap regime), but cap-binding code must exist so scale-up doesn't silently oversize. OU-on-basis parametric loss is scaffolded as a v1.0 interface-only stub so the decision engine doesn't need restructuring later.
**Depends on**: Phase 2
**Requirements**: LOSS-01, LOSS-02, LOSS-03, REWARD-01, REWARD-02, REWARD-03, REWARD-04
**Scope**:
  - Empirical post-fill path replayer: slice historical fills by `(depth-from-mark-at-fill-time, time-to-maturity bucket)`; compute empirical post-fill PnL distribution per cell under the operator's immediate-close policy (LOSS-01).
  - `E[loss | fill at tick X, τ]` exposed to decision engine with documented nearest-neighbor fallback for sparse cells (with warning) (LOSS-02).
  - v1.0 OU-on-basis parametric loss scaffold: module + interface + failing stub test so v1.0 drops in without restructuring (LOSS-03).
  - Capped pro-rata reward calculator: `R_uncapped(Q_me) = E_liq_per_epoch × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)`; `R_capped(Q_me) = min(R_uncapped, 10 × collateral × epoch_days/365)` (REWARD-01, absorbs pitfall A4 kinked-curve geometry).
  - `Q_total_in_range` tracker polled every cycle from `GET /v2/accounts/all-limit-orders` or direct order-book aggregation (REWARD-02, absorbs pitfall A8 competition tracking).
  - Sizing optimizer: `Q_me_target = argmax R_capped − E[loss|fill] × P(fill) subject to Q_min ≤ Q_me ≤ Q_max`; at $100 collateral `Q_me_target = Q_min` always (sub-cap regime), tested explicitly (REWARD-03).
  - `Q_cap` computation present in code (cap-binding regime boundary) even though it doesn't bind at $100, tested (REWARD-04).
  - Fee-schedule term from Phase 0 P0-06 absorbed into `E[loss|fill]` calculation so the EV equation has a proper `fee_cost` input (absorbs pitfall A6).
  - Engineering Protocols 1/2/3 apply: cite `[[Reward cap geometry]]`; update `architecture.yml` with `LossModel`, `RewardShareModel`, `Sizer` nodes; manifest every calibration run.
**Success Criteria** (what must be TRUE):
  1. `LossModel.expected_loss(depth, τ)` returns a number for every cell in the `(depth, τ)` grid over historical fills on the candidate market, with a logged warning when a sparse-cell nearest-neighbor fallback is used.
  2. `RewardShareModel.R_capped(Q_me)` at $100 collateral produces the sub-cap-regime curve labeled `sub_cap` (not `cap_binding` or `market_saturated`) across realistic `Q_total_in_range` values, and the cap-binding branch unit test passes at scaled-up collateral inputs.
  3. `Sizer.Q_me_target()` returns `Q_min` deterministically on $100 collateral across the candidate market's competitive conditions, while a scale-up unit test with collateral > $1k confirms `Q_me_target < Q_cap` in cap-binding regime.
  4. The LossModel scaffold's OU-on-basis interface exists with a failing stub test so v1.0 can drop in the parametric implementation without restructuring the decision engine.
**Plans**: TBD
**UI hint**: no

### Phase 4: Decision Engine + Predictive Circuit Breakers
**Goal**: Wire the three EV inputs from Phases 2–3 into the cancel rule — the core strategy primitive — and install ten predictive circuit breakers with exclusive KILL authority over the ZMQ priority lane. The decision engine has no threshold dials (self-calibrating); the breakers are predictive (margin trajectory, 0.7× oracle-stale) rather than reactive. Breaker coordinator is the only component authorized to submit orders when any breaker is tripped.
**Depends on**: Phase 3
**Requirements**: DECIDE-01, DECIDE-02, DECIDE-03, DECIDE-04, SAFE-01, SAFE-02, SAFE-03, SAFE-04, SAFE-05, SAFE-06, SAFE-07, SAFE-08, SAFE-09, SAFE-10
**Scope**:
  - `DecisionEngine.evaluate()` implements `EV_hold = R_liq_share_per_epoch × P(no_fill_and_unpurged) − E[loss|fill] × P(fill_this_epoch) − cancel_cost × P(purge)` per side per in-flight order per cycle; cancels iff `EV_hold < 0` (DECIDE-01).
  - `voluntary_cancel_forfeits_accumulated` boolean (from Phase 0 P0-01) toggles between punitive / benign branches; **default = `False` (benign, forward-looking cancel)** per P0-01 resolution 2026-04-23 ([[Voluntary cancel reward behavior]]). Punitive branch kept as dead-code fallback; both covered by tests; Phase 5 backtest sweeps both as sanity check (DECIDE-02, absorbs pitfall A1).
  - `cancel_cost` drawn from recent on-chain gas history (measured, not hardcoded) (DECIDE-03).
  - No threshold dials — only knobs are EV-input model parameters + breaker thresholds (DECIDE-04).
  - CLO-shift "stay-out-of-range-for-rest-of-epoch" branch in the EV rule — sometimes better than immediate repost when A1 punitive branch is active (absorbs pitfall A1×A3×C1 compound risk).
  - Margin trajectory breaker: at current `dNetBalance/dt`, if time-to-maintenance-margin < 30s, emergency close all positions + cancel all orders (SAFE-01).
  - Oracle staleness breaker: `now − fTime > 0.7 × maxUpdateDelay` cancels all orders (SAFE-02).
  - CLO removal breaker: `cloLowerThresh == 0 OR cloUpperThresh == 0` cancels all + alerts (SAFE-03).
  - CLO shift breaker: `|new_clo − old_clo| > N ticks` cancels, recalibrates, reposts (SAFE-04, absorbs pitfall A3).
  - Fill-rate runaway breaker: >K fills in last hour (K=3 for v0.5) pauses for manual review (SAFE-05).
  - Competition-collapse breaker: `Q_total_in_range` dropped >50% in 1 epoch pauses with investigation alert (SAFE-06).
  - Maturity-migration breaker: `time_to_maturity × R_me_per_epoch < migration_cost` rolls position to next maturity (SAFE-07).
  - Per-side budget rebalance breaker: `E_liq_per_epoch` split moves >30% away from posted side in one epoch → halve position or cancel pending operator review (SAFE-08, absorbs pitfall A2).
  - Underlying-feed-stale breaker: underlying CEX funding feed not updated within 2× expected cadence → halt (SAFE-09, absorbs pitfall A7).
  - Breaker coordinator has exclusive kill authority; messages use ZMQ priority KILL lane; no other component can submit orders when any breaker is tripped (SAFE-10).
  - OU-fit-degraded breaker (absorbs pitfall B5: shrink to Q_min when OU fit degrades) — wired as a Phase-3-LossModel-output-consumer that flows through the breaker coordinator.
  - Pre-deployment re-screen gate (absorbs pitfall A5 phase-gate portion): blocks Phase 6→7 transition until fresh economics-gate pass.
  - Engineering Protocols 1/2/3 apply: cite `[[EV cancel rule]]`; update `architecture.yml` with `DecisionEngine`, `CircuitBreakers` nodes + kill-lane edge; RUN_MANIFEST includes breaker configuration knobs.
**Success Criteria** (what must be TRUE):
  1. `DecisionEngine.evaluate()` on a stream of simulated book/feature states returns PLACE/HOLD/CANCEL decisions whose EV-sign matches the EV equation line-by-line, with both `voluntary_cancel_forfeits_accumulated` branches producing distinguishable decisions on a shared test scenario.
  2. Each of the ten circuit breakers (SAFE-01..10) fires under its documented trigger condition in a unit-test scenario and causes the ZMQ `CANCEL_ALL` or `EMERGENCY_CLOSE` message to be published on the priority KILL lane.
  3. When any breaker is tripped, any subsequent PLACE command from `DecisionEngine` is suppressed by the breaker coordinator and the suppression is logged with `run_id` — i.e., kill authority is verifiably exclusive.
  4. `cancel_cost` in the EV equation is measured from the most recent N on-chain gas observations (a stubbed-hardcoded value fails a linter check).
**Plans**: 8 plans (6 original + 2 gap-closure)
- [ ] 04-01-PLAN.md — Wave 0: Test scaffolding (17 RED tests + conftest fixtures + 2 lint script skeletons)
- [ ] 04-02-PLAN.md — Wave 1: Foundation (BotConfig + DecisionEngineConfig schema, alembic 0007 with 4 new tables, 3 state writers, MarginPoller, Breaker ABC, EvaluateInput/Output, OWNER_MAP extension)
- [ ] 04-03-PLAN.md — Wave 2A: DecisionEngine + GasHistoryCache + 2 lint scripts hardened (DECIDE-01..04 GREEN)
- [ ] 04-04-PLAN.md — Wave 2B: 6 breakers — margin_trajectory, oracle_stale, clo_removal, clo_shift, fill_rate, loss_fit_degraded (SAFE-01..05 + B5 absorbed GREEN)
- [ ] 04-05-PLAN.md — Wave 2C: 4 breakers — competition, maturity, side_budget, underlying_stale + CompetitionTracker SQLite write (SAFE-06..09 GREEN)
- [ ] 04-06-PLAN.md — Wave 3: BreakerCoordinator (SAFE-10) + predeploy_gate CLI (A5) + main.py 1 Hz decision loop + atomic Phase-4 architecture delta + manifest leaf-count test
- [ ] 04-07-PLAN.md — Gap closure (post-VERIFICATION): MaturityBreaker gas_cache mandatory + DECIDE-03 lint GREEN + architecture.yml maturity→gas_history edge + wiki supersedence
- [ ] 04-08-PLAN.md — Gap closure (post-VERIFICATION): bound-method identity test fix + full Phase 4 pytest greenrun captured to var/ (operator pivot point for Phase 5)
**UI hint**: no

### Phase 5: Event-Driven Backtest (Ship-Gate)
**Goal**: Deliver an `eventIndex`-ordered, queue-aware, AMM-aware, cancel-latency-aware replay engine that produces honest P&L and passes the bootstrap ship-gate (5th-percentile annualized P&L exceeds `alternative_yield + all_fees`). This is the BACK-07 ship-gate — point estimates above alt-yield are not sufficient; distribution tail matters. Phase 5 pass is a hard prerequisite for Phase 7 paper trading.
**Depends on**: Phase 4
**Requirements**: BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, BACK-06, BACK-07, BACK-08
**Scope**:
  - Event-driven replay engine: process trade tape in `eventIndex` order, maintain per-tick resting-size state from hourly snapshot anchors, simulate AMM consumption via `combined − raw`, record every decision live bot would have made (BACK-01, absorbs pitfall B1 queue-drift + B3 AMM + B6 look-ahead).
  - Cancel latency simulation: operator-configurable latency (2–5s default) injected into fill-response decisions; both order-of-event and time-since-event modeled (BACK-02).
  - Cancel-latency sensitivity sweep: backtest runs across L ∈ {0.5s, 1s, 2s, 3s, 5s, 10s}; reports `dP&L/dL` as concrete "is VPS worth it?" answer (BACK-03).
  - Competition sensitivity sweep: synthetic `Q_total_in_range` multipliers; reports `dP&L / dQ_competing` for scaling discipline (BACK-04).
  - Backtest outputs: net P&L per unit collateral annualized, Sharpe-equivalent, max drawdown, calibration plot (predicted P(fill) vs realized), `dP&L/dL` curve, `dP&L/dQ_competing` curve (BACK-05).
  - Voluntary-cancel sensitivity: runs both branches of `voluntary_cancel_forfeits_accumulated` as a sanity-check row; P0-01 resolved 2026-04-23 with flag = `False` ([[Voluntary cancel reward behavior]]), so divergence no longer blocks paper trading — but material divergence flags the EV formula as sensitive to a still-official-only (not contract-traced) finding, warranting opportunistic contract verification (BACK-06).
  - Bootstrap ship-gate: Phase 5 passes only if 5th percentile of bootstrapped annualized P&L exceeds `alternative_yield + all_fees` (BACK-07, absorbs pitfall B7 fragile-P&L-false-positive).
  - Perturbation grid: ±20% individual knob perturbations; sign-flipping on any knob is a fragility flag in the ship-gate report (BACK-08).
  - Historical-vs-current-budget A/B row in backtest outputs (absorbs pitfall B6 look-ahead on reward budget): pre-pipeline data marked as "current-budget synthetic" if historical budget reconstruction is infeasible.
  - 2D sensitivity contour on two most-uncertain knobs reported in ship-gate report.
  - Nautilus-adapter vs hand-rolled ~1500 LoC bailout decision made day-1 of Phase 5; no pre-phase research needed, but the decision is explicit and wiki-filed.
  - Engineering Protocols 1/2/3 apply: cite `[[Architecture overview v0.5]]`; update `architecture.yml` with `BacktestEngine` node; every backtest run emits RUN_MANIFEST.
**Success Criteria** (what must be TRUE):
  1. The replay engine processes the candidate market's full trade tape in `eventIndex` order with no out-of-order events, maintains AMM conservation on every snapshot, and produces a P&L number that is reproducible bit-for-bit across reruns with the same `RUN_MANIFEST`.
  2. The `dP&L/dL` cancel-latency sweep and `dP&L/dQ_competing` competition sweep both produce monotonic-in-expected-direction curves (or an explicit anomaly report if they don't), and a calibration plot shows predicted vs realized `P(fill)` within the documented tolerance.
  3. The bootstrap ship-gate evaluates: 5th-percentile annualized P&L from N resamples `>` `alternative_yield + all_fees` (pass → proceed to Phase 6+7) OR `≤` that threshold (fail → strategy kill, project halts with written report).
  4. The voluntary-cancel sensitivity row is produced as a sanity check; P0-01 is resolved (benign branch, flag = `False`), so Phase 7 paper is no longer gated on this. Material divergence between branches, if observed, is logged as a follow-up trigger for opportunistic contract verification — not a blocker.
  5. The perturbation grid report identifies any knob whose ±20% perturbation flips the sign of the ship-gate decision — such knobs are flagged as fragility concerns in the phase-transition note.
**Plans**: TBD
**UI hint**: yes

### Phase 6: Execution Layer (TypeScript hands)
**Goal**: Build the TypeScript `hands` process that owns the hot path (WS fill → pre-signed cancel calldata → Send Txs Bot submit with no IPC hop). This phase has the highest concentration of non-obvious engineering pitfalls (C1–C7); the nonce model must be documented in `docs/ARCHITECTURE.md` before any cancel code is written. Target software cancel latency <500ms; end-to-end budget 2–5s. Build in parallel with Phases 4–5 where possible.
**Depends on**: Phase 4 (decision engine + breakers produce commands it must execute; Phase 5 can run in parallel)
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06, EXEC-07, EXEC-08, EXEC-09, EXEC-10
**Scope**:
  - Dual-wallet: root cold (deposits/withdrawals/approvals only), agent hot (trading only) via `https://api.boros.finance/send-txs-bot/v2/`; 7-day agent-approval renewal scheduler (EXEC-01, absorbs pitfall C3 ops-portion).
  - `OrderExecutor` via `@pendle/sdk-boros` 1.1.44 wrapper: `POST /calldata/place-orders-with-rate`; `GTC` order type for reward farming (EXEC-02).
  - `PreSignedCancelCache` in-memory `Map<orderId, signedCalldata>`: generated + cached at order-placement time; fired instantly on WS fill or decision-engine cancel command — no HTTP roundtrip in critical path (EXEC-03).
  - Nonce-chain management: pre-signed cancels use deterministic nonces; operator policy for nonce-chain stalls (timeout → re-sign or resubmit-with-replacement) documented in `docs/nonce-policy.md`; v0.5 same-nonce model acceptable at single-order scale, scale-up migration path noted (EXEC-04, absorbs pitfall C1).
  - `WsFillListener` via `ws` 8.20 hand-rolled reconnect loop: subscribe per market; on fill → sync Map lookup → `SendTxsBotClient.submit(calldata)` with no await on IPC (EXEC-05, absorbs pitfall C4 reconnect-storm).
  - REST fill-diff poller at 1 Hz on `/v2/accounts/all-limit-orders`: cross-checks against expected state; discrepancies raise alerts and can trigger breakers (EXEC-06).
  - WS reconnect with exponential backoff + heartbeat; disconnect triggers `CANCEL_ALL` after configurable grace period to prevent unsupervised fill exposure (EXEC-07).
  - Gas-balance three-level monitor: info (>3d cover), warn (1d), halt (<1hr); halt cancels all + alerts operator; auto-topup not implemented for v0.5 (manual on warn) (EXEC-08, absorbs pitfall C6).
  - Self-trade prevention check before placement: verify no conflicting orders in own book per Boros SDK constraints (EXEC-09, absorbs NP-01 promotion).
  - Immediate market close on fill: `close_position(market_order)` fires unconditionally; no hold-for-reversion branch exists in code (enforced by absence) (EXEC-10).
  - 5-step cancel latency instrumentation (absorbs pitfall C2): instrument each of the 5 steps (WS→lookup→submit→broadcast→confirm); configure private primary RPC + public fallback; private RPC is mandatory ship-gate before scaling past $100 (deferred to Phase 8).
  - Merkle claim scheduler with retry + balance-delta verification wired here (absorbs pitfall C5), activated at Phase 8 — the module lives in `hands`.
  - `RUN_MANIFEST` fields `chain_time_drift_at_start_seconds` + `agent_wallet_gas_balance_at_start` added.
  - `launchd` plist finalized for `hands` (brain plist from Phase 1).
  - Engineering Protocols 1/2/3 apply: cite `[[Nonce model — single-nonce v0.5]]`, `[[TypeScript stack v0.5]]`; update `architecture.yml` with `OrderExecutor`, `WsFillListener`, `PreSignedCancelCache`, `SendTxsBotClient`, `AgentApprovalScheduler`, `GasBalanceMonitor` nodes.
**Success Criteria** (what must be TRUE):
  1. On a simulated WS fill event in a dev environment, the `PreSignedCancelCache` lookup + `SendTxsBotClient.submit()` happens with no IPC hop in the hot path and software latency (excluding chain confirmation) is measured under 500ms on the operator's machine.
  2. `docs/nonce-policy.md` and `docs/ARCHITECTURE.md` both document the same-nonce model for v0.5 single-order regime and the scale-up migration path, committed before any cancel code was merged.
  3. A forced WS disconnect triggers reconnect with exponential backoff; a reconnect failure beyond the grace period fires `CANCEL_ALL` and the 1 Hz REST diff poller confirms order state before and after.
  4. The gas-balance monitor hits warn level (1-day cover) and halt level (<1hr cover) on synthetic balance inputs and emits the correct alerts with `run_id` stamped; a balance in the info range does not alert.
  5. Pre-placement self-trade prevention rejects a conflicting order in a unit-test scenario before any REST call is made.
**Plans**: TBD
**UI hint**: no

### Phase 7: Paper Trading (2–4 Weeks)
**Goal**: Run the full bot in live-feeds, no-capital mode for 2–4 weeks, logging every decision and counterfactual; reconcile paper-fills and paper-rewards against backtest predictions; divergence > 1σ blocks live promotion. Paper is the single layer that validates that the bot's in-memory model state matches what the live feed produces — it catches schema drift, WS-reconnect edge cases, and calibration bias that backtest-on-historical-data cannot.
**Depends on**: Phase 5, Phase 6
**Requirements**: PAPER-01, PAPER-02, PAPER-03, PAPER-04, PAPER-05, PAPER-06
**Scope**:
  - Live-feeds / no-capital mode: all data pipelines and decision logic run live; no `send-txs-bot` submission; phantom execution layer logs what would have happened (PAPER-01).
  - Counterfactual decision log per tick: `{timestamp, run_id, decision, reason, predicted_P(fill), E[loss|fill], R_share, EV_hold, would_have_filled, would_have_earned}` (PAPER-02).
  - Backtest-reconciliation report at session end: compare phantom fills / phantom rewards / decision accuracy against backtest predictions; divergence > 1σ blocks live promotion (PAPER-03).
  - Perturbed-parameter neighbor runs: occasional ±20% individual knob perturbations; realized sensitivity vs backtest sensitivity (BACK-08 validation) (PAPER-04).
  - Merkle-claim reconciliation (phantom): predicted accrual per epoch reconciled against actual Merkle root values post-epoch; tolerance documented (PAPER-05, absorbs pitfall B6 live-validation portion).
  - Minimum 2-week paper session; 4 weeks recommended by consolidated plan (PAPER-06).
  - Confirm `eventIndex` presence in live WS payload vs historical NDJSON (absorbs pitfall B2 live-validation portion) — any schema mismatch halts paper until resolved.
  - Cancel latency median vs live comparison (instrumentation from Phase 6) — feeds the "is private RPC necessary" decision for Phase 8.
  - Pre-deployment re-screen gate runs once more before Phase 8 promotion (absorbs pitfall A5).
  - Engineering Protocols 1/2/3 apply: RUN_MANIFEST on every paper session; every decision log line has `run_id`; any surprise (unexpected WS schema field, divergence spike) filed as a wiki page with `Status: Current` before session close.
**Success Criteria** (what must be TRUE):
  1. A paper session runs for ≥2 weeks continuously (with `launchd` restarting across operator sleeps/wakes) and produces one counterfactual decision log line per tick with the full `{predicted_P(fill), E[loss|fill], R_share, EV_hold, ...}` payload joinable by `run_id`.
  2. The backtest-reconciliation report at session end shows phantom-fills vs backtest-predicted fills within 1σ per epoch and phantom-rewards vs Merkle-root-delivered rewards within the documented tolerance — divergence beyond either threshold blocks live promotion with a written report.
  3. `eventIndex` is confirmed present and consistently formatted in live WS trade events (matching the historical NDJSON schema from Phase 1); any schema drift is filed as a wiki page and resolved before paper-close.
  4. Cancel latency measured end-to-end (WS fill phantom → phantom cancel submit) is within the 2–5s budget on the operator's machine with public RPC; private RPC upgrade is either validated as necessary (for Phase 8) or deferred with evidence.
**Plans**: TBD
**UI hint**: yes

### Phase 8: Live Rollout
**Goal**: Deploy $100 real collateral on the single highest-conviction market from the Phase 1 shortlist, one side, protocol-minimum order size, 2-week observation; weekly P&L reconciliation against paper predictions; scale only if live matches paper within statistical noise. Merkle claim scheduler goes live. Private RPC is the mandatory ship-gate before scaling past $100.
**Depends on**: Phase 7
**Requirements**: LIVE-01, LIVE-02, LIVE-03, LIVE-04, LIVE-05, LIVE-06, LIVE-07, LIVE-08
**Scope**:
  - Single market, highest-conviction from Phase 1 shortlist; no multi-market in v0.5 (LIVE-01).
  - One side only at a time — posting long XOR short based on Mark-vs-Underlying per Pendle team endorsement (0x0Kippon tweet) (LIVE-02).
  - Minimum viable order size = protocol minimum from P0-02 (collateral is sizing budget; order size is protocol floor) (LIVE-03).
  - 2-week observation window before any scale-up consideration (LIVE-04).
  - Live vs paper reconciliation: weekly comparison of realized P&L vs paper-predicted P&L; divergence >1σ halts and triggers debug (LIVE-05).
  - Merkle claim scheduler polls distributor contract for new root every 15min during claim day (Monday); auto-submits proof when root updates; retry + balance-delta verification (LIVE-06, absorbs pitfall C5 live activation).
  - Private RPC endpoint for Arbitrum — public `arb1.arbitrum.io/rpc` fine for reads, private required before live to prevent rate-limits during cancel burst; acceptable: operator's own node, paid provider, or curated public-provider rotation (LIVE-07, absorbs pitfall C2 live activation).
  - Config-dry-run gate: any config change goes live only after a dry-run backtest + paper-replay passes; bypass requires explicit `--force` flag with loud RUN_MANIFEST warning (LIVE-08).
  - Fresh re-screen before considering a second market (absorbs pitfall A5 live portion).
  - 7-day agent-approval renewal on schedule (from Phase 6, active here).
  - Engineering Protocols 1/2/3 apply: live RUN_MANIFEST every run (including `chain_time_drift_at_start_seconds` and `agent_wallet_gas_balance_at_start`); architecture diagram reflects `MerkleClaimScheduler` as live node; weekly P&L report filed as wiki page with `Status: Current — Week N of live observation`.
**Success Criteria** (what must be TRUE):
  1. The bot runs for ≥2 weeks with $100 real collateral on one market, one side, protocol-minimum order size, with `launchd` auto-restart surviving operator sleeps/wakes and zero unsupervised fill exposure (any WS disconnect triggers `CANCEL_ALL` within the grace period).
  2. Weekly P&L reconciliation report shows realized P&L within 1σ of paper-predicted P&L; a divergence >1σ triggers halt + debug, not silent continuation.
  3. Merkle claim is submitted on each Monday during the observation window and the PENDLE balance delta matches the expected claim amount within documented tolerance; a missed week blocks any scale-up decision.
  4. Private RPC is confirmed active for all write operations (cancel/close/claim) with public RPC only used for reads; a rate-limit event on the private RPC is logged and surfaces in the weekly P&L report.
  5. After 2 weeks, the operator has enough evidence (P&L vs alt-yield, paper-live divergence, cancel-latency realization, competition stability) to make an explicit scale-or-kill decision, with the decision filed as a wiki page with `Status: Current`.
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. Prerequisite Resolution & Kill Gate | N/A (no-engineering phase) | **Complete** | 2026-04-23 |
| 1. Foundation (Infra + Data + Economics Gate) | 12/12 | **Complete** (`human_needed` on 3 live-network UAT items + DATA-11 known-broken; see Hole #1) | 2026-04-24 |
| 2. Fill Model (NHPP v0.5) | 4/4 | **Complete** (verified 12/12, 1 minor PROTO-01 violation on first-log-event) | 2026-04-24 |
| 3. Loss & Reward-Share Models + Sizing | 4/4 | **Complete** (verified 7/7) | 2026-04-25 |
| 4. Decision Engine + Predictive Circuit Breakers | 8/8 (6 original + 2 gap-closure) | **Complete** (re-verified 7/7 after 04-07/04-08) | 2026-04-26 |
| 5. Event-Driven Backtest (Ship-Gate) | 0/TBD | Not started | - |
| 6. Execution Layer (TypeScript hands) | 0/TBD | Not started | - |
| 7. Paper Trading (2–4 Weeks) | 0/TBD | Not started | - |
| 8. Live Rollout | 0/TBD | Not started | - |
