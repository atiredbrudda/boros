# Roadmap: Boros Reward Farming Bot

## Overview

v0.5 delivers a single-user, single-market, $100-collateral real-capital validator for the Pendle Boros Limit Order Liquidity Rewards strategy. The journey runs Phase 0 (cheap empirical kill-gate on six open questions) → Phase 1 (infrastructure spine + data pipeline + economics gate, Engineering Protocols installed here so every downstream artifact inherits them) → Phases 2–3 (three EV input models: fill probability, conditional loss, reward share) → Phase 4 (EV-based decision engine + predictive circuit breakers with exclusive kill authority) → Phase 5 (event-driven backtest as bootstrap ship-gate) → Phase 6 (TypeScript execution layer with pre-signed cancel calldata) → Phase 7 (2–4 week paper trading reconciliation) → Phase 8 (live rollout at $100, one market, one side, 2-week observation). Any phase that fails its exit criteria halts the project; Phase 0 in particular is a hard kill-gate — if the protocol minimum order size exceeds $100-collateral-equivalent (P0-02), the project halts with no capital deployed and no further engineering.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 0: Prerequisite Resolution & Kill Gate** - Close six empirical open questions; halt on minimum-order-size failure before any engineering. **COMPLETE 2026-04-23** — all 6 questions resolved cheaply via docs + official-team statement + spot probe (no engineering required); halt condition (P0-02) cleared (no protocol minimum); each answer filed as a wiki page with `Status: Current`. Phase 1 schema defaults set per resolutions (`voluntary_cancel_forfeits_accumulated=False`, `socket.io-client` over raw `ws`, `submission_path` knob dropped, Send Txs Bot mandatory).
- [x] **Phase 1: Foundation (Infrastructure Spine + Data Pipeline + Economics Gate)** - Install Engineering Protocols, ZMQ/SQLite/manifest/wiki, ingest data, compute economics kill-switch; second cheap-kill gate on empty shortlist. **COMPLETE 2026-04-24** — 12/12 plans, 23/23 must-haves verified; 3 live-network UAT items remain operator-only (carry to Phase 7). DATA-11 ELiqPoller dormant per Phase 3 LOCKED D-01 supersedence.
- [x] **Phase 2: Fill Model (NHPP v0.5)** - Calibrated `P(fill | δ, side, queue_ahead, features)` with queue tracker and AMM consumption model. **COMPLETE 2026-04-24** — 4/4 plans, 12/12 verified; 1 minor PROTO-01 cosmetic carry (first-log-event field naming).
- [x] **Phase 3: Loss & Reward-Share Models + Sizing** - Empirical `E[loss|fill]`, capped pro-rata reward share with operator-manual `E_liq_per_epoch` calibration (LOCKED D-01 supersedes live-polling assumption A5), sizing optimizer. **COMPLETE 2026-04-25** — 4/4 plans, 7/7 verified.
- [x] **Phase 4: Decision Engine + Predictive Circuit Breakers** - EV cancel rule wired over the three input models; ten predictive breakers with exclusive KILL authority. **COMPLETE 2026-04-26** — 8/8 plans (6 original + 2 gap-closure 04-07/04-08), 7/7 verified after re-verification; full Phase-4 pytest greenrun captured (311 passed). One known-flake hang carried to Phase 5 Wave 0 (test-fixture issue, not regression).
- [x] **Phase 5: Event-Driven Backtest (Ship-Gate)** - `eventIndex`-ordered, queue-aware, AMM-aware replay with cancel-latency sweep; bootstrap 5th-percentile ship-gate against alt-yield. Wave-0 prerequisite: fix carried ZMQ test-fixture hang + add `pytest-timeout`. (completed 2026-05-04)
- [ ] **Phase 05.5: Predict-Layer Look-Ahead + Fill Multi-Close Fixes (INSERTED 2026-05-06)** - Fix two engine bugs blocking every binding ship-gate verdict: (1) predict-side look-ahead in `get_latest_fit` / `get_latest_loss_grid` (no `current_chain_ts` filter on artifact retrieval; future-dated rows from prior runs poison every prediction in a historical replay); (2) fill multi-close in `replay.py` (1 fill schedules 11 close timers in same Arbitrum block). Re-run baseline-only ship-gate; classify against the unchanged Phase 05.3 band JSON. Mini-plan: no sweep / perturbation / contour scope.
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
**Plans**: N/A — no-engineering phase; resolutions filed as wiki pages instead.
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
  - ~~Live `E_liq_per_epoch` + Long/Short split polling every cycle (1–5s); writes to `reward_budget_history`~~ **SUPERSEDED 2026-04-24 by Phase 3 LOCKED D-01** ([[e-liq-per-epoch-source-decision]]): comprehensive Phase-3 probe confirmed NO live source exists for `E_liq_per_epoch` (fields absent from `/markets`; `liqSettings` is liquidation-incentive params, not LO rewards; distributor emits only `SetMerkleRoot` + per-user `Claimed`; SDK Incentives API endpoints all return 404). Resolution: operator-manual calibration in `state.market_reward_calibration` (Alembic 0006) via `python -m boros_brain.reward_model calibrate` CLI. ELiqPoller is dormant — kept for `reward_budget_history` row-shape semantics only. SAFE-08 (Phase 4) reads the new table for trend detection (DATA-11, absorbs pitfall A2 data-collection portion).
  - Supersedence discipline (PROTO-05): new wiki finding → grep wiki for pages restating old claim → update in same commit with `Status: Historical — superseded by [[new-page]]`.
**Success Criteria** (what must be TRUE):
  1. A `brain` process can start, emit a `RUN_MANIFEST` as first log line + sidecar JSON, stamp every subsequent log line with the active `run_id`, and crash-restart under `launchd` with no orphan state; `hands` does the same on the TypeScript side.
  2. A commit that modifies source without updating `docs/architecture.yml` is rejected by the pre-commit hook, and a commit that adds a new `research/` or `decisions/` markdown without a `[[wiki-link]]` is rejected by the wiki-cite hook.
  3. Running the ingester against the confirmed candidate markets produces partitioned parquet with `eventIndex`-ordered trade tape, hourly raw + combined snapshots that pass AMM conservation, underlying APR series, and writes timestamped `clo_history` rows in SQLite. (`reward_budget_history` is dormant per Phase 3 LOCKED D-01 supersedence — operator-manual `market_reward_calibration` is the active source; see [[e-liq-per-epoch-source-decision]].)
  4. Running the market screener + economics kill-switch produces either a non-empty shortlist with per-market `R_apr_on_collateral` above `alternative_yield + estimated_fill_loss_rate` (project continues to Phase 2), or an empty shortlist with a written kill report (project halts).
  5. The LLM Wiki `index.md` lists the seeded pages (Python stack, TS stack, IPC boundary, architecture overview, nonce model, strategy thesis, EV cancel rule, A1/min-order open questions with Status flags) such that a future session can cite `[[page-name]]` instead of re-deriving conclusions.
**Plans**: 12 plans (01-01..01-12), all complete — see `.planning/phases/01-foundation-infrastructure-spine-data-pipeline-economics-gate/`
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
**Plans**: 4 plans (02-01..02-04), all complete — see `.planning/phases/02-fill-model-nhpp-v0-5/`
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
**Plans**: 4 plans (03-01..03-04), all complete — see `.planning/phases/03-loss-reward-share-models-sizing/`. **LOCKED D-01 (2026-04-24):** operator-manual `market_reward_calibration` table replaces failed live `E_liq_per_epoch` polling assumption from Phase 1 (DATA-11 dormant). See `[[e-liq-per-epoch-source-decision]]` + `[[market-reward-calibration-operator-workflow]]`.
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
**Plans**: 8 plans (6 original + 2 gap-closure) — **all complete 2026-04-26**
- [x] 04-01-PLAN.md — Wave 0: Test scaffolding (17 RED tests + conftest fixtures + 2 lint script skeletons)
- [x] 04-02-PLAN.md — Wave 1: Foundation (BotConfig + DecisionEngineConfig schema, alembic 0007 with 4 new tables, 3 state writers, MarginPoller, Breaker ABC, EvaluateInput/Output, OWNER_MAP extension)
- [x] 04-03-PLAN.md — Wave 2A: DecisionEngine + GasHistoryCache + 2 lint scripts hardened (DECIDE-01..04 GREEN)
- [x] 04-04-PLAN.md — Wave 2B: 6 breakers — margin_trajectory, oracle_stale, clo_removal, clo_shift, fill_rate, loss_fit_degraded (SAFE-01..05 + B5 absorbed GREEN)
- [x] 04-05-PLAN.md — Wave 2C: 4 breakers — competition, maturity, side_budget, underlying_stale + CompetitionTracker SQLite write (SAFE-06..09 GREEN)
- [x] 04-06-PLAN.md — Wave 3: BreakerCoordinator (SAFE-10) + predeploy_gate CLI (A5) + main.py 1 Hz decision loop + atomic Phase-4 architecture delta + manifest leaf-count test
- [x] 04-07-PLAN.md — Gap closure (post-VERIFICATION): MaturityBreaker gas_cache mandatory + DECIDE-03 lint GREEN + architecture.yml maturity→gas_history edge + wiki supersedence
- [x] 04-08-PLAN.md — Gap closure (post-VERIFICATION): bound-method identity test fix + full Phase 4 pytest greenrun captured to var/ (operator pivot point for Phase 5)
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
  - Reward-budget lineage discipline (absorbs pitfall B6 look-ahead): backtest replay reads `e_liq_per_epoch_pendle` from `state.market_reward_calibration` (operator-vintage rows, lineage marker `data_source='operator'`) for the prospective period. Historical-budget reconstruction was ruled infeasible per Phase 3 LOCKED D-01; pre-calibration synthetic rows in legacy `reward_budget_history` carry `data_source='synthetic_current'` and MUST NOT contaminate ship-gate calculations. The backtest emits an A/B summary row showing pessimistic-vs-realistic reward-budget assumptions at the operator's calibration point.
  - 2D sensitivity contour on two most-uncertain knobs reported in ship-gate report.
  - Nautilus-adapter vs hand-rolled ~1500 LoC bailout decision made day-1 of Phase 5; no pre-phase research needed, but the decision is explicit and wiki-filed.
  - Engineering Protocols 1/2/3 apply: cite `[[Architecture overview v0.5]]`; update `architecture.yml` with `BacktestEngine` node; every backtest run emits RUN_MANIFEST.
  - **Wave-0 prerequisite — test-infra cleanup (carried from Phase 4):** Fix the pre-existing ZMQ ipc-fixture leak that causes `tests/test_breaker_coordinator_publishes_kill_lane_per_safe.py::test_coordinator_publishes_kill_lane_per_safe[*]` to deadlock when run in the full 323-test collection (passes in Phase-4 subset run; hangs when ordered alongside other ZMQ tests). Concrete tasks: (a) add `pytest-timeout` dev-dep + `[tool.pytest.ini_options].timeout = 30` so future hangs fail fast; (b) diagnose the `ipc_dir` fixture or `zmq.asyncio.Context.instance()` singleton leak across parametrize params; (c) full pytest -q must produce 323/323 green before any BACK-* deliverable ships. Forcing function: BACK-07 ship-gate explicitly requires full-suite green.
**Success Criteria** (what must be TRUE):
  1. The replay engine processes the candidate market's full trade tape in `eventIndex` order with no out-of-order events, maintains AMM conservation on every snapshot, and produces a P&L number that is reproducible bit-for-bit across reruns with the same `RUN_MANIFEST`.
  2. The `dP&L/dL` cancel-latency sweep and `dP&L/dQ_competing` competition sweep both produce monotonic-in-expected-direction curves (or an explicit anomaly report if they don't), and a calibration plot shows predicted vs realized `P(fill)` within the documented tolerance.
  3. The bootstrap ship-gate evaluates: 5th-percentile annualized P&L from N resamples `>` `alternative_yield + all_fees` (pass → proceed to Phase 6+7) OR `≤` that threshold (fail → strategy kill, project halts with written report).
  4. The voluntary-cancel sensitivity row is produced as a sanity check; P0-01 is resolved (benign branch, flag = `False`), so Phase 7 paper is no longer gated on this. Material divergence between branches, if observed, is logged as a follow-up trigger for opportunistic contract verification — not a blocker.
  5. The perturbation grid report identifies any knob whose ±20% perturbation flips the sign of the ship-gate decision — such knobs are flagged as fragility concerns in the phase-transition note.
  6. `cd python && uv run pytest -q` produces a single deterministic green-run on the full 323-test collection (no `--ignore` exclusions) — i.e. the Phase-4 carried `test_breaker_coordinator_publishes_kill_lane_per_safe[*]` ZMQ ipc-fixture hang is fixed; `pytest-timeout` is wired so future hangs fail fast rather than block the suite.
**Plans**: TBD
**UI hint**: yes

### Phase 05.1: Ship-Gate Execution: Historical Data Fetch + Ingest + Screener + Economics Gate + Backtest Run (INSERTED) — HALTED 2026-04-29

**HALT VERDICT:** Phase 05.1 TERMINATES with FAIL on 2026-04-29. Binding backtest: BINANCE-ETHUSDT-25SEP2026 long, run_id=01KQB9CPQAQS31P2ZSY14DHYH6, p5=0.49% APR vs threshold 6.00% APR. Kill report: docs/kill-report-20260429.md. Wiki: [[ship-gate-verdict-20260429]] (Status: Current). Phase 6 BLOCKED. All 5 plans executed (01 Wave 0, 02 Wave 1, 03 Wave 2, 04/04b Wave 3, 05 Wave 4).

**Goal:** Run the Phase-5 backtest engine end-to-end against real Boros historical data and produce a binding ship-gate verdict (PASS → Phase 6 unblocked; FAIL → real kill report + project halt). Phase 5 verified the engine is correct on synthetic tests; Phase 5.1 verifies the *strategy* by feeding real data through it. Bridges the gap that Phase 1 left open — only a 41-row `clo_history` UAT snapshot and a single `BINANCE-ETHUSDT-29MAY2026` fill-model artifact exist on disk; no `market-trades/`, no `order-book/`, no `underlying-apr/`, no operator-calibrated `market_reward_calibration` rows, alembic head still at `0002` (behind Phase-4's `0007`). Source identified: `https://historical-data.boros.finance` (public ZIP/NDJSON dumps, no auth, layout matches the Phase-1 ingester 1:1).

**Depends on:** Phase 5

**Requirements**: BACK-07 (operationalize bootstrap ship-gate against real data), DATA-08 (run screener on real ingested tape), DATA-09 (run economics kill-switch — empty shortlist halts project), DATA-10 (record re-screen baseline). Cross-cutting: PROTO-01..05 apply (RUN_MANIFEST per run, architecture.yml updates, wiki cite + supersedence on every finding).

**Scope**:
  - **Schema reconciliation**: `cd python && uv run alembic upgrade head` — bring local SQLite from `0002` → `0007`. Verify `market_reward_calibration` table exists post-upgrade.
  - **Historical-data fetcher** (~50–100 LOC, new): `scripts/fetch_historical_data.py` — pull ZIP archives from `https://historical-data.boros.finance` per `{kind, market, YYYY-MM}`, unzip into `data/ndjson/{kind}/{market}/{YYYY-MM}.ndjson` (or matching layout the ingester expects). Operator-overridable URL pattern + checksum/size telemetry. Reconnaissance step: 5-min HTTP probe to determine exact URL template (directory listing JSON vs presigned ZIP per folder vs static file tree). Document findings in a wiki page.
  - **Bulk ingest**: for each market in the 29-market `clo_history` set with non-zero `cloLowerThresh`/`cloUpperThresh`, fetch + ingest 60d trade tape + matching order-book raw + `combined_{tickSize}/` snapshots + underlying-apr (Binance/OKX/HyperLiquid funding history for the appropriate exchange) + settlement + market-data via `python -m boros_brain.data.ingester.cli`. Validate AMM conservation per DATA-05 (B3 pitfall).
  - **Screener run**: `python -m boros_brain.screener` against the ingested tape → produces real `var/reports/shortlist.json` (current placeholder is `{"markets":["MKT"]}`). Persist screener inputs + outputs with `RUN_MANIFEST`.
  - **Economics gate**: `python -m boros_brain.screener.economics_gate` — drops markets where `R_apr_on_collateral < alt_yield + estimated_fill_loss_rate`. **Empty shortlist = real kill report at `docs/kill-report-<ULID>.md` with concrete numbers and project halt.** Distinct from the existing test-residue `docs/kill-report-20260426.md` (which uses fixture market `MARKET-PASSING-DATA08`).
  - **Reward-budget operator calibration**: `python -m boros_brain.reward_model calibrate` for each shortlist market — writes `market_reward_calibration` rows with `data_source='operator'` per Phase 3 LOCKED D-01. Backtest reads these (NOT `reward_budget_history`).
  - **Fill-model calibration**: run Phase 2 fill-model fits on shortlist markets so `data/parquet/fill_model_artifacts/` covers each rather than just ETHUSDT-29MAY2026.
  - **Backtest CLI run**: `python -m boros_brain.backtest` end-to-end → emits `RUN_MANIFEST`, runs replay → cancel-latency sweep → competition sweep → forfeit-branch sanity row → bootstrap ship-gate → perturbation grid → 2D contour. Writes `ship_gate_verdict.json` + `ship_gate_report.md` + Hive-partitioned result parquets.
  - **Verdict + wiki + supersedence**: regardless of PASS/FAIL, file the verdict as a wiki page with `Status: Current` (PASS) or `Status: Current — Phase 5 ship-gate FAIL, project halted YYYY-MM-DD` (FAIL). On PASS, supersede the test-residue `docs/kill-report-20260426.md` (or delete it, since it never represented a real halt).
  - Engineering Protocols 1/2/3 apply: every fetch/ingest/screen/calibrate/backtest run emits RUN_MANIFEST; `docs/architecture.yml` updated with `HistoricalDataFetcher` node; every finding (URL pattern, per-market screener pass/fail rationale, calibration values) gets a wiki page.

**Success Criteria** (what must be TRUE):
  1. Local SQLite alembic head is `0007`; `market_reward_calibration` table exists; downstream tools no longer crash on missing-table.
  2. `data/ndjson/` contains a real 60d window of trade tape + order-book + underlying-apr for at least every screener-eligible market (non-zero CLO bounds, ≥30d to maturity); `data/parquet/` mirrors after ingest with AMM conservation passing on every snapshot.
  3. `var/reports/shortlist.json` contains a real list of 0–4 markets that passed DATA-08 + DATA-09 (replacing the `["MKT"]` placeholder), and either: (a) shortlist is non-empty AND backtest produces a `ship_gate_verdict.json` with PASS/FAIL set, OR (b) shortlist is empty AND a real kill report is filed at `docs/kill-report-<ULID>.md` with per-market R_apr numbers + halt rationale; project state moves to halted.
  4. On PASS: backtest results parquets exist under `data/parquet/backtest_results/` per Phase 5 BACK-05 spec; `ship_gate_report.md` is filed and wiki-cited; perturbation grid + 2D contour outputs are present; the verdict is the wiki-recorded artifact that gates Phase 6.
  5. On FAIL: kill report names which markets failed, by how much (`R_apr − threshold`), and what would need to change for the strategy to be viable; `STATE.md` reflects project halt; no Phase 6 work begins.
  6. `docs/architecture.yml` has the `HistoricalDataFetcher` node + edges; pre-commit `architecture_lint.py` exits 0; full pytest suite remains green (412 passed baseline from Phase 5 verification).

**Plans**: TBD (run `/gsd-plan-phase 05.1` to break down)
**UI hint**: no

### Phase 05.2: Sizer + Replay Reconcile-to-Production (INSERTED 2026-04-30) — UNBLOCKS 05.1 HALT
**Goal**: Reconcile the v0.5 backtest engine to the live Pendle Boros protocol's actual margin/sizing model. Phase 05.1's binding ship-gate FAIL was caused by 5 compounding engine bugs surfaced via dapp UI probing on 2026-04-30 — sizing knob (`notional_per_yu_usd = 90,000` placeholder hardcoded to BTC value, semantically should be `margin_per_yu_usd ≈ $18.30`), backwards-entered `long_side_split` (0.784 vs actual 0.327), empty `competition_history` table silently producing `sigma_others = 0`, sparse-event tick under-counting, and the units bug fixed in commit 9625c93. With all five fixed, predicted verdict for $100 collateral on BINANCE-ETHUSDT-25SEP2026 long is ~415% USD-APR (vs reported 0.0334%). Falsifiable: if Wave 5 re-run lands materially below the prediction, a sixth bug exists.
**Depends on**: Phase 05.1 (artifacts), Phase 5 (replay engine)
**Requirements**: BACK-07 (re-evaluation), DATA-09 (re-evaluation)
**Success Criteria**:
  1. `notional_per_yu_usd` renamed to `margin_per_yu_usd` in `sizer/config.py`; per-market values entered from operator dapp probes; `q_max` formula updated; full test suite green.
  2. `market_reward_calibration.long_side_split` for binding market corrected to 0.327; schema gains `effective_at_utc` + refresh policy; CLI for re-entry from dapp UI exists.
  3. Backtest reads `sigma_others` from `order_book_raw` parquet at each tick (mirroring live `CompetitionTracker`); empty pool raises `EmptyCompetitionPoolError`, no silent zero-default; `sigma_others_min_pendle` floor applied.
  4. `_maybe_emit_tick` synthesizes 1 Hz reward-accrual ticks between trade events; full-epoch integration test passes to 0.01% relative tolerance.
  5. n_fills audit (Wave 0 E4): implied APR series plotted against edge placements; either confirms n_fills=0 is real or surfaces the simulator's edge-fill detection bug.
  6. Fresh end-to-end ship-gate run on units + sizing + sigma + tick all corrected; verdict in defensible USD-APR units; if PASS, halt is lifted and Phase 6 unblocked; if FAIL, kill-report names the residual gap and the missing 6th-bug investigation.

**Plans**: 7 plans
- [ ] 05.2-01-PLAN.md — Wave 0: Pre-flight evidence (operator E1/E2/E3/E5 + Claude E4 n_fills audit script)
- [ ] 05.2-02-PLAN.md — Wave 1: Sizer schema rename `notional_per_yu_usd` → `margin_per_yu_usd` + per-market overrides + YAMLs + architecture
- [ ] 05.2-03-PLAN.md — Wave 2a: Alembic 0008 (`effective_at_utc` + `next_refresh_at_utc` columns) + writer schema bump + Pydantic
- [ ] 05.2-04-PLAN.md — Wave 3: CLI `recalibrate` flags + binding-market row insert (long_split 0.784 → 0.327; depends on PLAN 03 — co-runs with PLAN 05 in wave 3)
- [ ] 05.2-05-PLAN.md — Wave 3: Backtest sigma_others from parquet + `EmptyCompetitionPoolError` + Bug #6 xfail probe (parallel with PLAN 04)
- [ ] 05.2-06-PLAN.md — Wave 4: 1 Hz sparse-tick synthesis (`_iter_chain_seconds`) + decision_log streaming + 0.01% reward integration
- [ ] 05.2-07-PLAN.md — Wave 5: Fresh binding ship-gate run + verdict routing + STATE.md flip / kill-report wiki supersedence chain — **VERDICT INVALIDATED 2026-04-30** (Bug #6 fixed in commit `cad821f`; Bug #7/#8/#9 surfaced post-W5 review and routed to Phase 05.3)
**UI hint**: no

### Phase 05.3: Fill-Path Repair (INSERTED 2026-04-30) — UNBLOCKS BINDING SHIP-GATE
**Goal**: Make the simulator's fill leg observable. Phase 05.2's Wave 5 binding ship-gate produced `n_fills = 0` not because outer-edge placement avoided fills, but because the fill-detection path is structurally broken in three coupled ways: (1) `size_wei` is null across the binding-market trade parquet (ingester correctly records null when source emits decimal-float sizes; backtest's `evt.get("size_wei") or 0` then dies silently); (2) `replay.py` treats `clo_*_thresh` as a tick coordinate and applies a `/10_000` rescale, but those thresholds are in fIndex display units that the screener already converts via `_clo_findex_to_tick`; (3) the W4 inter-event rate-crossing check is gated on `queue_ahead_wei == 0`, but the only writer of that value is the dead trade handler from (1). The W0 audit's `sim_bug_under_counting` verdict (filed 2026-04-30) was never closed; this phase closes it. Without fill detection, every ship-gate verdict measures only the gross reward leg of EV (`R_share × P(no_fill)`), with the loss leg silently zero — Phase 6 (live hands) would surface the gap on the first real fill.
**Depends on**: Phase 05.2 (Bug #6 reward-path fix landed in `cad821f`)
**Requirements**: BACK-07 (re-evaluation, fill-detection branch)
**Success Criteria**:
  1. Unit convention: queue position, trade size comparisons, and order size all expressed in YU throughout the simulator. `queue_ahead_wei` renamed to `queue_ahead_yu`. `size_float` consumed directly; `size_wei = NULL` no longer silently kills fill detection.
  2. CLO threshold conversion: replay uses the same `_clo_findex_to_tick` helper as the screener (lifted to a shared module). Seeded order's resting tick + edge-crossing check are unit-coherent and round-trip to the binding market's incentivized rate range.
  3. Fill-detection decoupling: inter-event rate-crossing fires unconditionally when `evt_rate ≤ clo_lower` (long) or `≥ clo_upper` (short). Queue position uncertainty handled by `p_fill` in the decision engine, not by a hard simulator gate. Double-counting prevented by the existing `_trade_consumes_order` skip-condition.
  4. Live-path parity: `fill_model/queue_tracker.py` audited; either renamed to align (YU) or an adapter at the seam documented.
  5. Smoke regression: synthetic 26-day fixture with K controlled rate-crossings produces `n_fills ≈ K` (latency-scheduler tolerance). RED test committed first, GREEN after T2-T4.
  6. Re-run binding ship-gate on the fully repaired engine. `n_fills` from the new `decision_log` matches W0 audit's edge-crossing count. Verdict JSON reports gross-vs-net reward decomposition explicitly. PASS classification requires net-of-fills `p5 ≥ threshold × adequate_margin` (5× starting band); FAIL classification names the residual gap.

**Plans**: 2 plans (one engineering, one research; runnable in parallel)
- [x] 05.3-01-PLAN.md — Fill-path repair: T1–T5 complete (5 atomic commits `4c75d9a` → `c435378`); T6/T7 routed to Phase 05.4 due to 4 prerequisite bugs surfaced during T6 dry-run. See `05.3-01-SUMMARY.md`.
- [x] 05.3-02-PLAN.md — Reward-path research: T1–T4 complete (1 commit `1ba8481` + 3 wiki pages + band JSON). Outputs consumed unchanged by Phase 05.4-04 T7. See `05.3-02-SUMMARY.md`.
**UI hint**: no

### Phase 05.4: Verdict Prerequisites + Binding Ship-Gate Re-Run (INSERTED 2026-04-30) — COMPLETES PHASE 05.3 T6/T7
**Goal**: Produce a clean binding ship-gate verdict on the all-bugs-fixed engine, classified against the (unchanged) Phase 05.3 expected-verdict band. The Phase 05.3 Plan 01 T6 dry-run (run_id `01KQFABR9VNPMKKQYPTQGRJMDR`) validated the fill-path fix empirically (11 FILL_REALIZED entries; reconstructed p5 = 894% from reward leg only — directional PASS) but surfaced 4 separate prerequisite bugs that block a binding verdict regardless of engine repair. This phase fixes those bugs (sequentially where dependent, parallel where independent), then re-runs T6/T7 against the inherited classification rule.
**Depends on**: Phase 05.3 Plan 01 T1–T5 (fill-path repair landed in HEAD `c435378`); Phase 05.3 Plan 02 T1–T4 (band + classification rule pinned in `var/reports/expected_verdict_band_2026-04-30.json`)
**Requirements**: BACK-07 (re-evaluation, fill-detection branch); inherits classification thresholds from Phase 05.3 Plan 02 T4
**Success Criteria**:
  1. Bug A fixed: Alembic migration 0008 applied; `effective_at_utc` column live in `state.market_reward_calibration`; prior + current epoch operator rows inserted for binding market; `_load_operator_calibration_history` returns ≥2 rows; `no_operator_calibration` warnings drop to 0 in a smoke run.
  2. Bug B resolved: replay loop processes the full 237-trade tape (or root cause documented as a cascade of Bug A and explicitly verified). `decision_log['current_chain_ts'].max()` reaches at least the last trade's blockTimestamp.
  3. Bug C addressed: fill_model fit window bounded to `current_chain_ts` per tick (or per-day refit), OR look-ahead bias quantified with explicit band widening for verdict classification.
  4. Bug D fixed: `pnl_pendle` column persisted in decision_log parquet; regression test verifies parquet-aggregation matches in-memory aggregation to 1e-9 rel tolerance.
  5. Re-run binding ship-gate: produces a real `ship_gate_verdict.json` with `p5_annualized_pnl` AND `n_fills > 0`. Verdict classifier (read from band JSON's `classification_rule` block):
     - `p5 ∈ [pass_lo=0.42, pass_hi=18.10]` → **PASS — within band**, halt-lift candidate.
     - `p5 < fail_lo=0.0` → **FAIL** with kill report.
     - else → **FLAG**, route to Phase 05.5 (sixth-bug investigation) BEFORE lifting halt.
  6. Phase 05.4 SUMMARY documents the verdict + which bugs were fixed vs deferred + whether the band was widened (if Bug C was deferred).

**Plans**: 4 plans (sequential dependency where bugs may cascade; parallel where independent)
- [x] 05.4-01-PLAN.md — Fix Bug A: apply Alembic 0008 migration + insert prior/current epoch operator calibration rows for binding market. Sequential (must precede 05.4-02).
- [x] 05.4-02-PLAN.md — Investigate Bug B against the A-fixed engine. May reduce to "no-op, was a cascade — document". Investigation budget 2 hours; if root cause not found, route to Phase 05.5.
- [x] 05.4-03-PLAN.md — Fix Bug C (look-ahead in fill/loss fits) AND Bug D (persist pnl_pendle to decision_log parquet). Wave-parallel with 05.4-02.
- [ ] 05.4-04-PLAN.md — Inherit-and-execute T6+T7: binding ship-gate ~4h re-run + verdict classification against `var/reports/expected_verdict_band_2026-04-30.json` (consumed UNCHANGED from Phase 05.3 Plan 02 T4). Includes explicit escape valve to Phase 05.5 if `p5` outside band.

**Inherited artifacts (do NOT re-derive)**:
- Phase 05.3 commits `4c75d9a` → `c435378` (fill-path repair); commit `1ba8481` (band derivation script + smoke tests with classification_rule pinning)
- `var/reports/expected_verdict_band_2026-04-30.json` (band + classification_rule block)
- `[[fill-path-repair-2026-04-30]]` Status: Current
- `[[expected-verdict-band-2026-04-30]]` Status: Current
- `[[pendle-lo-reward-formula-verified]]` Status: Current — PARTIAL
- `[[dapp-apr-reconciliation-2026-04-30]]` Status: Current
- `[[phase-05-3-bugs-discovered-during-t6]]` Status: Current — load-bearing input

**UI hint**: no

### Phase 05.5: Predict-Layer Look-Ahead + Fill Multi-Close Fixes (INSERTED 2026-05-06) — UNBLOCKS BINDING VERDICT
**Goal**: Land the minimal engine fixes needed to produce a clean binding ship-gate verdict on real historical data, then re-run a baseline-only ship-gate (no sweeps, no perturbation, no contour). Two cancelled binding runs (PID 18460 / `01KQTMW2VE7HF408T4V6XV5TDW` and PID 49950 / `01KQYNPPE2CB46414WKHEGCZP5`) both produced `annualized_pnl_pct = 0.0` on every cancel_latency child because of look-ahead bias at the *predict* layer that Phase 05.4-03 (`d954bc5`) did not address — that fix bounded the *write* path of fill_model refits, but the *read* paths (`get_latest_fit`, `get_latest_loss_grid`) have no `current_chain_ts` filter and silently treat future-dated artifacts as fresh (`*_age_s = 0.0` branch in `predict.py:92-106` and `expected_loss.py:101-111`). The fill multi-close bug (`replay.py` schedules 11 closes per fill due to same-block re-firing after `queue_ahead_yu` zeroes) is co-scoped because it inflates fill loss ~11× in any prediction that does realize a fill.

**Depends on**: Phase 05.4 (Bug A/B/C-write/D fixes landed); diagnosis report at `.planning/debug/phase-05-4-look-ahead-at-predict-layer.md`

**Requirements**: BACK-07 (re-evaluation, fill-detection branch); inherits classification thresholds from Phase 05.3 Plan 02 T4

**Success Criteria** (what must be TRUE):
  1. **Predict-layer look-ahead fix lands at both layers.** `get_latest_fit` and `get_latest_loss_grid` accept `current_chain_ts: int | None = None`; when provided, SQL filters `WHERE *_window_end_ts <= ?`. `predict.py` and `expected_loss.py` pass `req.current_chain_ts` through. Phase-4 contract docstrings updated to declare the new bound. RED test (persist two artifacts at later windows, request prediction at earlier `current_chain_ts`, assert older artifact returned) fails on HEAD and passes after fix. Live-brain regression (`current_chain_ts=None` → unchanged behavior) passes.
  2. **Negative-control regression: `predict_future_dated_fit` and `loss_model.future_dated_grid` warning counts drop to 0 in a baseline backtest run.** Currently 266,740 each; post-fix should be 0.
  3. **Fill multi-close fix lands.** `replay.py._handle_trade_event` tracks `_pending_close_order_ids: set[str]` and skips orders already in the set for the rest of the block; cleared on tick boundary. RED test (single fill in a multi-event block produces exactly 1 close, not N) fails on HEAD and passes after fix.
  4. **Baseline ship-gate re-run produces a real `ship_gate_verdict.json` with `n_fills` consistent with the engine state and `p5_annualized_pnl` non-zero.** No cancel_latency / competition / forfeit_branch / perturbation children run.
  5. **Verdict classification (read from `var/reports/expected_verdict_band_2026-04-30.json` `classification_rule` block):**
     - `p5 ∈ [pass_lo=0.42, pass_hi=18.10]` → **PASS — within band**, halt-lift candidate.
     - `p5 < fail_lo=0.0` → **FAIL** with kill report.
     - else (between 0 and 0.42, or above 18.10) → **FLAG**, route to a Phase 05.6 sixth-bug investigation BEFORE lifting halt.
  6. **Co-commit hygiene:** wiki pages filed (`[[fill-model-predict-look-ahead-read-path]]` Status: Current; superseded `[[fill-model-predict-contract]]` if affected); architecture diagram drift check passes; SUMMARY documents which sites were enumerated as part of the contamination-class scope per `feedback_contamination_class_bugs.md`.

**Out of scope (explicit)**:
  - cancel_latency, competition, forfeit_branch sweeps — not run; the verdict is baseline-only this cycle.
  - perturbation grid — not run. The uncommitted `_PERTURBATION_WHITELIST` in `python/src/boros_brain/backtest/perturbation.py` working tree is decided in this plan: either committed with co-commits or reverted; not exercised either way.
  - contour_2d — not run.
  - Secondary `fill_model.refit_failed` "cannot write 'Object' datatype" empty-features-frame polars bug at `features.py:296` — non-fatal; defer to a follow-up phase unless trivially in path during the predict-fix RED→GREEN.

**Plans**: TBD via `/gsd-plan-phase 05.5`. Expected shape: 2 sequential plans (predict-layer fix → multi-close fix → baseline re-run + classify), or 3 if multi-close is wave-parallel with predict-layer.

**Inherited artifacts (do NOT re-derive)**:
  - Phase 05.4 commits (Bug A/B/C-write/D): `87c677c`, `c0b3342`, `d954bc5`, `5417c93`, `eea5b7e`, `696a0e8`
  - `.planning/debug/phase-05-4-look-ahead-at-predict-layer.md` — full diagnosis with file:line citations, log evidence (266k future-dated reads, 0 fills), TDD scaffolding
  - `var/reports/expected_verdict_band_2026-04-30.json` — band + classification_rule (pass_lo=0.42, pass_hi=18.10, fail_lo=0.0)
  - `[[expected-verdict-band-2026-04-30]]` Status: Current
  - `[[fill-path-repair-2026-04-30]]` Status: Current
  - `[[phase-05-3-bugs-discovered-during-t6]]` Status: Current — load-bearing input
  - `feedback_contamination_class_bugs.md` (memory) — class-of-bug enumeration discipline

**UI hint**: no

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
| 1. Foundation (Infra + Data + Economics Gate) | 12/12 | **Complete** (3 live-network UAT items deferred to Phase 7 paper trading; DATA-11 ELiqPoller dormant per Phase 3 LOCKED D-01 supersedence) | 2026-04-24 |
| 2. Fill Model (NHPP v0.5) | 4/4 | **Complete** (verified 12/12, 1 minor PROTO-01 violation on first-log-event) | 2026-04-24 |
| 3. Loss & Reward-Share Models + Sizing | 4/4 | **Complete** (verified 7/7) | 2026-04-25 |
| 4. Decision Engine + Predictive Circuit Breakers | 8/8 (6 original + 2 gap-closure) | **Complete** (re-verified 7/7 after 04-07/04-08) | 2026-04-26 |
| 5. Event-Driven Backtest (Ship-Gate) | 9/9 | Complete   | 2026-05-04 |
| 6. Execution Layer (TypeScript hands) | 0/TBD | Not started | - |
| 7. Paper Trading (2–4 Weeks) | 0/TBD | Not started | - |
| 8. Live Rollout | 0/TBD | Not started | - |
