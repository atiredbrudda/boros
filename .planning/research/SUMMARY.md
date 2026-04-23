# Project Research Summary

**Project:** Boros Reward-Farming Bot (Pendle Boros IRS, Arbitrum)
**Domain:** Personal DeFi limit-order liquidity-reward harvesting bot
**Researched:** 2026-04-23
**Confidence:** HIGH (strategy, architecture, pitfalls trace to verified sources); MEDIUM (WS fill semantics, SDK sign-only surface — needs Phase 0 verification)

---

## Executive Summary

The Boros bot is a single-user Python + TypeScript system that posts resting limit orders at the outer edges of Pendle Boros CLO ranges and earns time-weighted PENDLE rewards by *never filling* — fills are the enemy, not revenue. The strategy is mathematically sound (EV cancel rule with calibrated fill-probability model + loss model + reward-share model), and the economics are real: ETHUSDT Short APR was 957% on 2026-04-22, well above stablecoin alternatives, even with the 1000%-APR-per-account cap. The v0.5 scope is deliberately conservative — one market, one side, protocol-minimum size, $100 collateral — and validates economics cheaply before committing to the full v1.0 multi-market per-model-selection build.

The recommended architecture is a **split-brain design**: a long-lived Python process (`brain`) owns all model inference, the decision clock, circuit breakers, and backtest/paper replay; a long-lived TypeScript process (`hands`) owns the Pendle SDK, WebSocket fill listener, pre-signed cancel calldata cache, and Send-Txs-Bot dispatcher. They communicate over ZMQ IPC sockets (`pyzmq` + `zeromq.js`), with a shared SQLite WAL spine for durable state. This is not an optional architectural choice — the hot path (WS fill detected → pre-signed cancel submitted) *must* stay inside the TypeScript process to protect the 2–5 s end-to-end latency budget. Any IPC hop on that path burns budget irreversibly.

The three highest risks are: (1) the voluntary-cancel forfeit question (A1) is binary and catastrophic — it must be answered in Phase 0 before any model code is written; (2) the protocol minimum order size may be higher than $100, which existentially blocks v0.5; (3) the pre-signed cancel nonce-chain (C1) is the most non-obvious execution pitfall and requires an explicit nonce-model decision in Phase 8 documentation before any live cancellation code is written. Everything downstream of these three depends on the answers.

---

## Key Findings

### Recommended Stack

**Resolved delta between STACK.md and ARCHITECTURE.md — ZMQ wins over stdin/stdout:**
STACK.md recommends stdin/stdout JSON Lines as the IPC boundary; ARCHITECTURE.md recommends ZMQ `PUSH/PULL` + `PUB/SUB`. ARCHITECTURE.md wins. The reason is concrete: `CircuitBreakers` needs to preempt `DecisionEngine` and send `KILL`-priority commands to `hands` independently of the normal PLACE/CANCEL queue. A priority-message concept maps naturally onto ZMQ's `PUSH/PULL` with a priority-field routing slot. stdin/stdout JSON Lines has no clean preemption mechanism without layering a priority-envelope protocol on top — at which point you have re-invented ZMQ badly. Use ZMQ. Budget `pyzmq` (Python) and `zeromq` (npm) as explicit dependencies. Update the stack wiki pages at Phase 1 kickoff to reflect this resolution.

**Python side (`brain`):**
- **CPython 3.12** — best wheel coverage across all scientific deps (tick 0.8.0.1, polars 1.40.1, nautilus_trader 1.225)
- **`tick` 0.8.0.1** — Hawkes + NHPP arrival-process fitting; verified release April 20, 2026; 3.11–3.13 wheels on PyPI
- **`scipy` 1.14** — hand-rolled OU MLE (no OU library exists in production quality; statsmodels issue #7883 open since 2021)
- **`polars` 1.40.1 + `duckdb` 1.5.0** — polars for NDJSON streaming of historical trades/books; DuckDB for ad-hoc SQL and backtest cross-checks (read-only on parquet + SQLite)
- **`pydantic` 2.13.3** — config schema is the single knob inventory; `model_dump(mode='json')` generates `RUN_MANIFEST` by reflection (critical for D2 pitfall prevention)
- **`structlog` 25.5.0** — JSON logs with `contextvars`-based `run_id` propagation across async tasks
- **`web3.py` 7.15.0** — async on-chain reads (fIndexOracle, Merkle distributor); use `AsyncWeb3`
- **`nautilus_trader` 1.225.0** — event-driven backtest engine; Phase 7 bailout clause: if Nautilus adapter fights AMM-merged-book replay, switch to hand-rolled ~1500 LoC replay on day 1 of Phase 7
- **`pyzmq`** — ZMQ IPC transport
- **`httpx` 0.27** — async REST client for Boros API reads (Python side reads; TypeScript side writes all orders)
- **`uv`** — packaging + lockfile; `ruff` + `mypy` in pre-commit

**TypeScript side (`hands`):**
- **Node.js 24 LTS** — not 22 (Node 22 exits active support April 2026)
- **`@pendle/sdk-boros` 1.1.44** — pins `viem@2.44.4` directly; all TS EVM library choices flow from this pin
- **`viem` 2.44.4** — match SDK pin exactly; `walletClient.signTransaction()` → raw tx in memory → fire on fill; do not use ethers (duplicates wallet state with the SDK's viem)
- **`ws` 8.20.0** — native WebSocket client; hand-rolled 30-line reconnect loop (no reconnect wrappers — silent reconnect = missed fill = lost money)
- **`zeromq`** (npm) — ZMQ IPC transport matching the Python side
- **`zod` 3.23** — runtime validation of every Boros REST/WS payload at the boundary
- **`pino` 9** — JSON logging with `run_id` on the TS side
- **`tsx` 4.21** — development only; production runs `tsc` → `dist/` under bare `node`

**Cross-cutting:**
- **Supervision:** `launchd` LaunchAgent plist (macOS-native; survives reboots; zero daemon overhead vs 83 MB pm2)
- **Secrets:** `dotenvx` encrypted `.env.vault`; agent wallet key decrypted at startup only; root wallet never enters bot process
- **Process manager (v0.5 dev):** `overmind` (Procfile-based, foreground; upgrade to launchd at v1.0 when bot proves itself)

### Expected Features — v0.5 Table Stakes

The full list is 30 features from the consolidated plan plus 15 promoted NP-hygiene items. The following are the minimum set without which the strategy is broken or unsafe at real capital.

**Core engine chain (all three EV inputs must ship together — removing any makes the EV rule output garbage):**
- Data pipeline: REST `/markets` config loader, `fIndexOracle` on-chain reader, hourly raw + combined book snapshots with AMM non-negativity assertion, market-trades tape with `eventIndex` intra-block ordering, underlying APR ingestion (TS-01 through TS-06)
- Market screening gate + economics kill-switch: if `R_apr < alt_yield + fill_loss`, stop before building anything (TS-07, TS-08)
- NHPP fill model with 4 covariates + queue-position tracker with drift-direction bias diagnostic + AMM consumption model with conservation check (TS-09, TS-10, TS-11)
- Empirical conditional-loss model (TS-12); reward-share model with live `E_liq_per_epoch` + Long/Short split polling, capped pro-rata (TS-13, TS-14)
- EV cancel rule with `voluntary_cancel_forfeits_accumulated` flag — both branches implemented, fee term included (TS-15, DF-12, A6 term)
- Seven predictive circuit breakers: margin trajectory, oracle staleness, CLO shift, fill-rate runaway, competition collapse, underlying-feed-stale/outlier, maturity migration (TS-16)

**Execution layer (all or none — partial = unsafe):**
- Dual-wallet (root cold, agent hot) via Send Txs Bot (TS-19)
- WebSocket fill detection with heartbeat + 1 Hz REST fallback when WS dropped (TS-20, NP-05, NP-06)
- Pre-signed cancel calldata at order-placement time, fired synchronously on WS fill event (TS-18, DF-03) — the single largest fill-avoidance lever
- Gas balance monitor with three-level alert/halt/emergency structure (TS-25, C6 prevention)

**NP-promoted hygiene items (required, not optional polish):**
- Self-trade prevention check before placement (NP-01)
- Config schema validation on startup: Pydantic/Zod, unknown knob = hard error (NP-07)
- NTP/clock-drift check: refuse to start if system time diverges from chain time > 5s; all time comparisons use `chain_time` cache, not `time.time()` (NP-21, C7 prevention)
- Reward claim reconciliation: verify PENDLE balance delta matches expected claim amount post-confirmation (NP-13, C5 prevention)
- Nonce-model decision documented explicitly in `docs/ARCHITECTURE.md` before any cancel code is written (C1 prevention)

**Cross-cutting protocols (every phase, every run):**
- `RUN_MANIFEST` on every run: ULID `run_id`, git SHA, strategy version, full knob tree by Pydantic reflection; every log line carries `run_id` (TS-26, D2 prevention)
- `docs/ARCHITECTURE.md` Mermaid + `architecture.yml` with `architecture_lint.py` pre-commit hook (TS-27, D3 prevention)
- LLM Wiki check-first / write-back on every task — cite `[[page-name]]` or file a new page (TS-28, D1 prevention)
- Structured JSON logs with `run_id` join key (TS-29)
- Single Pydantic `BotConfig` with mode-specific sections; config round-trip test in pre-commit (D4 prevention)

**v0.5 explicit non-scope (defer to v1.0):** per-market Hawkes/RP model selection, OU-on-basis parametric loss, multi-market operation, both sides simultaneously, push alerts.

### Architecture Approach

The system is a split-brain, two-process design. Python (`brain`) is a long-lived `asyncio` process at 1 Hz that owns all stateful model inference, the decision clock, and kill authority via `CircuitBreakers`. TypeScript (`hands`) is a long-lived Node process that is stateless except for its in-memory `PreSignedCancelCache` (`Map<orderId, signedCalldata>`); it reacts to ZMQ commands from `brain` and WebSocket events from Boros. The hot path (fill detected → cancel fired) is a synchronous Map lookup plus `SendTxsBotClient.submit()` entirely inside TS — no IPC hop, target < 500 ms software latency. The slow path (book update → model score → EV decision → cancel command) crosses ZMQ in both directions and targets < 2 s. SQLite WAL (`var/state.sqlite`) is the shared state spine with single-writer-per-table discipline; DuckDB reads it alongside parquet for analysis. Backtest and paper modes reuse the exact same `DecisionEngine` — backtest replaces `hands` with an in-process mock; paper stubs the Send-Txs-Bot calls while keeping live WebSocket feeds.

**Major components:**
1. **`brain:MarketDataLoop`** (Python asyncio) — 1–5 s poll of Boros REST + fIndexOracle `eth_call`; drives the decision clock
2. **`brain:QueuePositionTracker`** (Python) — replays trade tape between hourly raw-book snapshots using `eventIndex`; subtracts AMM share from `combined_*` snapshots
3. **`brain:FillModel`** (Python module) — NHPP (v0.5) / Hawkes / RP (v1.0); returns `P(fill | δ, t, features)` as a pure function called by `DecisionEngine`
4. **`brain:LossModel`** (Python module) — empirical post-fill replay (v0.5); OU-on-basis with ADF check and robust MLE (v1.0)
5. **`brain:RewardShareModel`** (Python module) — polls live `E_liq_per_epoch` + Long/Short split; computes capped pro-rata share
6. **`brain:DecisionEngine`** (Python module) — `EV_hold = R_share × P(no_fill) − E[loss|fill] × P(fill) − cancel_cost × P(purge)`; emits PLACE/HOLD/CANCEL
7. **`brain:CircuitBreakers`** (Python module) — holds kill authority; preempts `DecisionEngine`; emits `CANCEL_ALL` or `EMERGENCY_CLOSE` directly to `hands` with priority-9 ZMQ message
8. **`hands:WsFillListener`** (TypeScript) — Socket.IO subscription + 1 Hz REST diff; on fill → sync Map lookup → `SendTxsBotClient.submit(calldata)` with no await on IPC
9. **`hands:OrderExecutor`** (TypeScript) — `@pendle/sdk-boros` wrapper; populates `PreSignedCancelCache` on every `PLACE`
10. **`hands:PreSignedCancelCache`** (TypeScript) — in-memory `Map<orderId, signedCalldata>`; rebuilt from REST on `hands` restart

**ZMQ topology:**
- `brain PUSH → hands PULL` on `ipc:///tmp/boros.cmd` — PLACE, CANCEL, KILL (priority 9)
- `hands PUB → brain SUB` on `ipc:///tmp/boros.events` — FILL_DETECTED, ORDER_PLACED, TX_FAILED, WS_DISCONNECTED
- Heartbeat every 5 s both directions; missed 3 consecutive heartbeats → "I lost my sibling" protocol (hands cancels all open orders autonomously; brain enters no-dispatch mode)

**Note on WS fill detection confidence:** The public Boros Socket.IO feed does NOT surface per-account fill events directly (confirmed in ARCHITECTURE.md §4). Fill detection relies on `orderbook:{marketId}:full:update` events plus the 1 Hz REST diff of `/accounts/limit-orders` as belt-and-suspenders. WS-only fill detection is MEDIUM confidence; the REST fallback is the safety net. This is load-bearing for TS-18 (pre-signed cancel); if the WS fill event is missing or delayed, the REST poll catches it within 1 s.

### Critical Pitfalls (Top 7 by Severity)

The full research document enumerates 29 pitfalls across 4 categories. The 7 below have the highest single-failure impact on a $100 real-money deployment. The roadmap must explicitly address each.

1. **A1 — Voluntary-cancel forfeits accumulated time-weight (Catastrophic / Negligible — binary)**
If cancelling an order voids its epoch-to-date size×time contribution, a bot that reposts on CLO shifts earns zero reward all week while paying gas and fill-loss. The EV cancel rule assumes rewards accrue while resting; if they reset on cancel, the numerator is fiction. Phase 0 must trace `cancelOrder()` in `boros-core-public` reward distributor contract before any Phase 2+ code. Ship the `voluntary_cancel_forfeits_accumulated` boolean as a first-class config knob; Phase 7 backtest sweeps both branches.

2. **Minimum order size existential check (Catastrophic)**
If the protocol minimum order size exceeds $100-collateral-equivalent, v0.5 cannot launch. Binary go/no-go. Must be confirmed in Phase 0 from Boros SDK / API / Discord before any engineering. No bypass.

3. **A2 — Per-side budget rebalances away from your side (High)**
Entering a thin side makes it less thin, causing the protocol's budget allocator to shift budget toward the other side. Reward share drops from both competition dilution AND budget shrinkage — these are distinct, multiplicative effects. Poll `E_liq_per_epoch` + Long/Short split live on every decision cycle; persist the time-series from Phase 1 onward for calibration.

4. **C1 — Pre-signed cancel nonce chain (Catastrophic in multi-order; Medium in single-order)**
Pre-signing cancel calldata bakes a specific nonce. If order B fills and the bot wants to urgently cancel C, C's cancel (nonce N+2) cannot land until nonce N+1 (B's now-stale cancel) is consumed. Cancel latency blows from 2–5 s to 60+ s. Phase 8 must document the nonce model explicitly in `docs/ARCHITECTURE.md` before any cancel code exists. At $100 single-order-per-market: same-nonce model is acceptable. At multi-order scale-up: sign at decision time.

5. **C2 — RPC rate-limit dominates cancel latency (High)**
The 2–5 s cancel budget decomposes as 5 steps; on the public Arbitrum RPC, step 3 (broadcast) alone can hit 3–10 s under congestion. Instrument all 5 steps in Phase 8. Configure primary private RPC + public fallback. Private RPC is a mandatory ship-gate before scaling past $100.

6. **A1 × A3 × C1 compound risk (Catastrophic when all three are active)**
CLO range shift mid-epoch triggers cancel-and-repost. If cancel forfeits (A1), the bot loses epoch-to-date accumulation AND restarts at zero in a partly-spent epoch. If multiple orders have stale nonces (C1), the repost is delayed further. Phase 5 EV rule must include a "stay-out-of-range for rest of epoch" branch — sometimes better than immediate repost.

7. **D1–D4 — Protocol decay (High, cumulative)**
Four protocol failure modes that appear compliant but silently degrade: D1 (wiki not consulted → re-litigates resolved questions), D2 (manifest schema hand-maintained → missing knobs invisible in log analysis), D3 (dependency diagram diverges from code → blast-radius reviews are fiction), D4 (config schema forks across backtest/paper/live → wrong knob values in live). All four require Phase 1 infrastructure before any model code — Pydantic reflection-based manifest, `architecture_lint.py` pre-commit hook, single-source config class, wiki seeded.

---

## Implications for Roadmap

The consolidated plan has 10 phases. **The single most important roadmap modification is expanding Phase 1 into a Phase 1a infrastructure spine (before any model code) plus Phase 1b–d (data pipeline and screening).** The reason is that D1–D4 pitfalls compound silently from the very first commit. The wiki, dependency diagram, ZMQ bus skeleton, and manifest writer must be load-bearing infrastructure before models produce logs, or every subsequent phase produces artifacts that cannot be trusted. Installing them retroactively costs exponentially more than doing it first. Phase 1a is a 2–3 day setup investment that protects every subsequent phase.

### Phase 0 — Prerequisite Resolution
**Rationale:** Three Phase 0 questions are binary go/no-go. Engineering past Phase 0 without answers wastes weeks on a strategy that may not be viable.
**Delivers:** Confirmed answers to voluntary-cancel behavior (A1), protocol minimum order size, WS endpoint/schema, SDK sign-only surface, fee schedule, and `eventIndex` field universality.
**Must confirm before Phase 1:**
1. Does voluntary cancel forfeit accumulated time-weight? (trace `boros-core-public` reward distributor `cancelOrder()`)
2. Actual protocol minimum order size — must be ≤ $100-collateral-equivalent
3. Exact Boros WebSocket URL + subscription payload schema
4. Does `@pendle/sdk-boros` 1.1.44 expose sign-only (no-submit) for cancel calldata?
5. Actual fee schedule: maker bps, taker bps, gas per place/cancel/close at Arbitrum p95
6. Is `eventIndex` present across all target market trade files or only ETHUSDT-26SEP2025?
**Avoids:** A1 (existential strategy question), minimum-size block, C1 (nonce model hinges on order count)
**Research flag:** Empirical verification against live API, on-chain contract, and Discord — not library research.

### Phase 1a — Infrastructure Spine
**Rationale:** D1–D4 require infrastructure before model code. Installing afterward creates compounding drift in every phase.
**Delivers:**
- SQLite schema + alembic migrations for all tables (open_orders, decisions, tx_receipts, queue_positions, run_manifests, epoch_rewards)
- ZMQ bus skeleton: `brain PUSH/PULL` + `hands PUB/SUB` + heartbeat protocol on both channels
- `RUN_MANIFEST` writer: Pydantic-reflection-based, emits on every bot start, stamps every log line with `run_id` via `structlog.contextvars`
- `StructuredLogger`: NDJSON append-only + SQLite mirror; single writer, no interleaving
- `architecture_lint.py` pre-commit hook: parses `docs/architecture.yml`, flags code/YAML mismatches
- Single `BotConfig` Pydantic class with mode-specific sections; `config_schema_test.py` pre-commit round-trip
- `docs/ARCHITECTURE.md` initial Mermaid diagram + `docs/architecture.yml` seed from research
- LLM Wiki seeded from planning docs (per wiki seeding plan below)
**Uses:** `structlog`, `pydantic`, `python-ulid`, `alembic`, `pyzmq`, `zeromq` (npm), `better-sqlite3`, `pino`, `zod`
**Avoids:** D1 (wiki), D2 (manifest schema), D3 (diagram linter), D4 (config drift)
**Research flag:** Standard patterns — no phase research needed; fully specified in ARCHITECTURE.md §7.

### Phase 1b–d — Data Pipeline + Market Screener + Economics Gate
**Rationale:** No model code is meaningful without confirming a market passes the economics gate. The screener also serves as the daily re-run tool during all subsequent engineering (A5 prevention).
**Delivers:** Ingestion of `market-trades/`, raw + combined order books, underlying APRs; `eventIndex` assertion across all markets (B2); AMM share non-negativity assertion (B3); per-market CV bootstrap CI + dispersion test; `Q_total_in_range` tracking; economics kill-switch; daily automated re-screen; `E_liq_per_epoch` + Long/Short split time-series logging from day one (A2); historical reward-budget reconstruction from distributor contract events (B6); outside-range wall depth ratio (A8 covariate)
**Avoids:** A2, A5, A8, B2, B3, B6
**Research flag:** Standard DuckDB/polars patterns. One possible spike: historical reward-budget reconstruction from distributor contract event log.

### Phase 2 — Fill Model (NHPP v0.5)
**Rationale:** P(fill) is one of two EV inputs. Required before the decision engine can be wired.
**Delivers:** NHPP with 4 covariates; queue position tracker with drift-direction bias diagnostic and pessimistic/optimistic bounds; AMM consumption conservation check; Hawkes fit-health diagnostics scaffolded for v1.0
**Uses:** `tick` 0.8.0.1, `scipy`, `polars`
**Avoids:** B1 (queue drift bias), B3 (AMM double-count), B4 (Hawkes on wrong CV market)
**Research flag:** Standard; tick library is well-documented.

### Phase 3 — Loss Model
**Rationale:** `E[loss|fill]` is the other EV input. Empirical-only for v0.5; OU plumbing scaffolded for v1.0.
**Delivers:** Empirical post-fill replay; OU-on-basis MLE with Tang-Chen bias correction, ADF stationarity check on every fit, robust MLE (trim top 1% residuals), rolling-window fit with regime-change detection; fee-schedule term added to EV equation; underlying-outlier z-score monitor (|z| > 4 → flag low-confidence)
**Uses:** `scipy.optimize.minimize`, hand-rolled OU log-likelihood, ADF from `statsmodels`
**Avoids:** A6 (fee term missing from EV), A7 (CEX outlier blows OU fit), B5 (regime shift mid-window)
**Research flag:** No research needed; OU MLE is textbook.

### Phase 4 — Reward-Share Model + Sizing
**Rationale:** Third EV input. Also produces the `R_capped(Q_me)` curve that informs all scale-up decisions.
**Delivers:** Live `E_liq_per_epoch` + Long/Short split polling (not cached); capped pro-rata share with regime labels (`sub_cap` / `cap_binding` / `market_saturated`); `R_capped(Q_me)` plot per market with `Q_cap` annotated; sizing optimizer; `Q_total_in_range` competition tracking
**Avoids:** A2, A4 (cap geometry), A8 (outside-range wall), DF-04, DF-05
**Research flag:** Standard; fully specified in consolidated plan.

### Phase 5 — Decision Engine + EV Cancel Rule
**Rationale:** All three EV inputs now exist. Wire them into the decision rule.
**Delivers:** `DecisionEngine.evaluate()` with full EV equation (fill term, loss term, reward term, fee term, forfeited-accumulation term); `voluntary_cancel_forfeits_accumulated` as first-class config knob; CLO-shift "stay-out-of-range-for-rest-of-epoch" branch; paper-mode stub for `hands`
**Uses:** All brain modules from Phases 2–4; ZMQ bus from Phase 1a
**Avoids:** A1 (forfeit term), A3 (A1+A3 compound), A6 (fee term)
**Research flag:** Standard; fully specified.

### Phase 6 — Circuit Breakers
**Rationale:** Kill authority must be independent of and capable of preempting the decision engine. Predictive framing is the key differentiator.
**Delivers:** Seven predictive circuit breakers (all from TS-16 + A7 underlying-outlier and underlying-feed-stale additions); pre-deployment re-screen gate (A5: blocks Phase 8→9 transition until fresh economics pass); OU-fit-degraded breaker (B5: shrink to Q_min)
**Avoids:** A3, A5, A7, B5
**Research flag:** Standard; conditions fully specified in ARCHITECTURE.md Flow 3 and Flow 5.

### Phase 7 — Event-Driven Backtest
**Rationale:** Price-touch backtest overstates P&L on a CLOB with AMM; queue-aware event replay is the only honest gate.
**Delivers:** Nautilus-adapter replay (or hand-rolled fallback if day-1 adapter friction is too high) with: `eventIndex`-ordered trade replay; AMM conservation check; cancel-latency sweep (dP&L/dL); `voluntary_cancel_forfeits_accumulated` sensitivity row; historical-vs-current-budget A/B row; bootstrap-resampled P&L distribution; 2D sensitivity contour on two most-uncertain knobs; reward accrual time ratio per epoch; ship-gate: P&L 5th-percentile bootstrap > alternative yield after fees + budget haircut
**Avoids:** B1 (queue drift), B3 (AMM double-count), B6 (look-ahead), B7 (fragile P&L false positive)
**Research flag:** Nautilus custom-venue adapter is MEDIUM confidence for AMM-merged-book replay. Budget 2 days to bail to hand-rolled if adapter fights the shape. Evaluate day 1 of Phase 7 — no pre-phase research needed.

### Phase 8 — Execution Layer + Pre-Signed Cancel
**Rationale:** Hot path (WS fill → cancel) must stay in TypeScript end-to-end. This phase also has the highest concentration of non-obvious engineering pitfalls (C1–C7).
**Delivers:** Dual-wallet setup + 7-day agent-approval renewal scheduler; `OrderExecutor` via `@pendle/sdk-boros`; `PreSignedCancelCache` in-memory Map; `WsFillListener` (Socket.IO + 1 Hz REST diff); `SendTxsBotClient`; nonce-model documented in `docs/ARCHITECTURE.md` (same-nonce model for v0.5 single-order); 5-step cancel latency instrumentation; dual-RPC setup (private primary + public fallback); agent-key in macOS Keychain (not `.env`); WS exponential backoff + state reconciliation on reconnect; gas balance three-level monitor; chain-time-as-source-of-truth; `caffeinate` wrapper; Merkle claim scheduler with retry + balance-delta verification; `launchd` plist (upgrade from overmind); `RUN_MANIFEST` fields `chain_time_drift_at_start_seconds` + `agent_wallet_gas_balance_at_start`
**Avoids:** C1 (nonce chain), C2 (RPC latency), C3 (key exposure), C4 (WS reconnect storm), C5 (claim fails silently), C6 (gas runs dry), C7 (clock drift)
**Research flag:** Phase 0 answers (WS URL, SDK sign-only surface) must be confirmed before Phase 8 begins. No additional research.

### Phase 9 — Paper Trading (2–4 weeks)
**Rationale:** Paper reconciles backtest predictions against live feed behavior before real capital is at risk.
**Delivers:** Paper harness with phantom fills + phantom rewards; perturbation runs at selected params + two neighbors (B7 robustness); paper-backtest reconciliation for first 3 epochs' Merkle claims (B6); confirmed `eventIndex` presence in live WS payload (B2); cancel latency median vs live comparison; pre-deployment re-screen gate
**Avoids:** B6, B7, B2 (live WS schema vs historical NDJSON mismatch)
**Research flag:** None — observation and calibration phase.

### Phase 10 — Live Rollout + Scale Gate
**Rationale:** $100 collateral, one market, one side, protocol-minimum size, 2-week observation. Scale only if live matches paper within statistical noise.
**Delivers:** Live bot at minimal scale; weekly P&L report (scale/kill decision input); Merkle claim reconciliation (gate: any missed week blocks scale-up); private RPC upgrade gate (mandatory before scaling past $100); fresh re-screen before second market; 7-day approval renewal on schedule
**Avoids:** A5 (market crowded before deployment), C2 (public RPC at scale)
**Research flag:** None.

### Phase Ordering Rationale

The dependency chain is hard-wired: Phase 0 answers gate Phase 1 design choices; Phase 1a infrastructure (manifests, ZMQ bus, SQLite, wiki) must exist before any module produces logs; Phases 2–4 each contribute exactly one EV input and must all complete before Phase 5 (the EV rule requires all three simultaneously); Phase 5 feeds Phase 6 and Phase 7 independently; Phase 7's bootstrap ship-gate must pass before Phase 9; Phase 8's execution layer is built in parallel with Phases 5–7 but must be complete before Phase 9 uses live feeds. The Phase 1a expansion is the single most important departure from a naive sequential reading of the consolidated plan.

### Research Flags

**Phases requiring empirical verification (not library research):**
- **Phase 0:** Live API probing, on-chain contract tracing, possibly Pendle Discord. Cannot be done from documentation alone.
- **Phase 1b spike:** Historical reward-budget reconstruction from MultiTokenMerkleDistributor contract events — may be infeasible; fallback is marking pre-pipeline backtest data as "current-budget synthetic."

**Phases with well-documented patterns (skip pre-phase research):**
- **Phase 1a:** ZMQ IPC + SQLite + Pydantic reflection + structlog are all standard, fully-documented patterns.
- **Phases 2–4:** `tick` library, OU MLE, reward-share formula — all fully specified; no design ambiguity.
- **Phases 5–6:** Fully specified in ARCHITECTURE.md; no design ambiguity.
- **Phase 8:** Pitfall-dense but design is fully specified; risk is implementation discipline, not unknown patterns.
- **Phases 9–10:** Observation phases; no research needed.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified on PyPI/npm 2026-04-23. viem pinned to SDK's 2.44.4 (not latest 2.47.x) — intentional and correct. ZMQ replaces stdin/stdout per ARCHITECTURE.md; resolution is explicit. |
| Features | HIGH (table stakes) / MEDIUM (NP-promoted hygiene) | 30 table-stakes items trace directly to `boros_consolidated_plan.md`, `boros_bot_guide.md`, or `PROJECT.md`. 15 NP-promoted items are comparative inference from CLOB MM bot patterns — promotion decisions are MEDIUM confidence. |
| Architecture | HIGH (design) / MEDIUM (WS fill semantics) | Design decisions are well-reasoned with explicit alternatives-rejected rationale. One MEDIUM: public Socket.IO does NOT surface per-account fill events directly — WS fill detection relies on book-update events + 1 Hz REST diff. REST fallback is the safety net. |
| Pitfalls | HIGH (on-chain/execution C1–C7) / MEDIUM (Boros-specific A1–A3) / LOW (A1 exact behavior until Phase 0 confirms) | C-category pitfalls grounded in Arbitrum nonce mechanics and standard WS patterns. A-category pitfalls grounded in consolidated plan data and reward-distributor contract mechanics, but exact voluntary-cancel behavior (A1) and rebalancing cadence (A2) are LOW confidence until Phase 0 confirms. |

**Overall confidence:** HIGH on design and stack; MEDIUM on the three critical empirical questions Phase 0 must resolve before any confidence in v0.5 economics is warranted.

### Gaps to Address in Phase 0

All four research docs converge on the same short list:

1. **Voluntary-cancel reward behavior (A1) — LOW confidence:** Trace `cancelOrder()` in `boros-core-public` reward distributor contract. Does it decrement the running epoch accumulator or only remove the forward tally? Answer gates the EV rule numerator and the Phase 5 forfeit-branch design.

2. **Protocol minimum order size — LOW confidence:** If > $100-collateral-equivalent, v0.5 cannot launch. Blocks all downstream engineering. Confirm from `getMarketConfig()` SDK call or `/markets` API response before Phase 1 begins.

3. **Boros WebSocket URL + subscription schema — LOW confidence:** SDK is confirmed REST-only (`boros-api-examples` repo). The WS URL needs live verification against `api.boros.finance/open-api/docs` or Discord. Does not change the library choice but changes implementation shape.

4. **SDK sign-only (no-submit) surface — LOW confidence:** Pre-signed cancel calldata depends on generating a signed cancel tx without submitting. If the SDK only exposes `cancelOrders()` (sign + send), the bot must compose `POST /calldata/cancel-order` + viem `signTransaction` manually. Verify at Phase 8 kickoff. Noted here so the Phase 8 plan budgets for the two implementation paths.

5. **`eventIndex` field coverage across all markets — LOW confidence (one market confirmed):** Phase 1 ingestion must assert field presence across every market. Markets with absent `eventIndex` are flagged `model_class = undetermined` or dropped.

6. **Fee schedule — not enumerated anywhere:** Maker bps, taker bps, gas per place/cancel/close at Arbitrum p95. Required for the EV equation `fee_cost` term. File as wiki page `Fee schedule 2026-04` in Phase 0.

---

## Wiki Seeding Obligations (Engineering Protocol #1)

Wiki index confirmed empty as of 2026-04-23 (0 pages). The following pages must be filed at Phase 1a kickoff. Seeding is not Phase 0 work (requires wiki tooling); but all pages must exist before Phase 2 begins so subsequent sessions can cite `[[page-name]]` instead of re-deriving conclusions.

**From STACK.md:**
- `[[Python stack v0.5]]` — CPython 3.12, tick, scipy, polars, duckdb, pydantic, structlog, web3.py, pyzmq; Status: Current
- `[[TypeScript stack v0.5]]` — Node 24 LTS, @pendle/sdk-boros 1.1.44, viem 2.44.4, ws, zeromq; Status: Current
- `[[IPC boundary — ZMQ over stdin-stdout]]` — ZMQ wins; stdin/stdout rationale and rejection; supersedes STACK.md IPC section; Status: Current
- `[[Alternatives rejected — ethers, pandas, pm2, vectorbt, hawkeslib]]` — the "what NOT to use" table; Status: Current

**From ARCHITECTURE.md:**
- `[[Architecture overview v0.5]]` — split-brain, ZMQ topology, SQLite spine, hot-path constraint, component table; Status: Current
- `[[Nonce model — single-nonce v0.5]]` — explicit decision on cancel nonce model + scale-up migration path (C1); Status: Current — v0.5 single-order regime; must update at multi-order scale-up

**From FEATURES.md:**
- `[[Strategy thesis]]` — avoid-fills, time-weighted reward, EV cancel rule framing; Status: Current
- `[[EV cancel rule]]` — full equation with all three input terms, fee term, both A1 branches; Status: Current — pending Phase 0 voluntary-cancel answer

**From PITFALLS.md:**
- `[[Open question: voluntary-cancel reward behavior]]` — A1 pitfall, resolution path via contract trace, Phase 0 task; Status: Current — OPEN until Phase 0
- `[[Open question: protocol minimum order size]]` — existential check, Phase 0 task; Status: Current — OPEN until Phase 0
- `[[Fee schedule 2026-04]]` — to be filed after Phase 0 enumerates actual fees; Status: Pending Phase 0
- `[[Reward cap geometry]]` — A4: kinked R_capped(Q_me) curve, Q_cap, regime labels (`sub_cap` / `cap_binding` / `market_saturated`); Status: Current
- `[[Known issues: eventIndex coverage]]` — B2: confirmed in ETHUSDT-26SEP2025 only; assertion required in Phase 1; Status: Current — OPEN until Phase 1 ingestion validates all markets

---

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — all package versions verified on PyPI/npm 2026-04-23
- `.planning/research/FEATURES.md` — traces to `boros_consolidated_plan.md`, `boros_bot_guide.md`, `plan_comparison.md`, `PROJECT.md`
- `.planning/research/ARCHITECTURE.md` — design decisions with explicit alternatives-rejected rationale; HIGH on design, MEDIUM on WS fill semantics
- `.planning/research/PITFALLS.md` — 29 pitfalls with severity, warning signs, concrete prevention tasks per phase
- `.planning/PROJECT.md` — project scope, constraints, Engineering Protocols
- PyPI/npm registry metadata — version dates verified for all recommended packages

### Secondary (MEDIUM confidence)
- `pendle-finance/boros-api-examples` repo — confirms SDK is REST-only (no WS helper); viem 2.44.4 SDK pin
- `pendle-finance/boros-core-public` — reward distributor contract structure (A1 resolution path); not yet traced at function level
- Arbitrum public RPC behavior — practitioner consensus on `eth_sendRawTransaction` deprioritization; no published rate-limit numbers confirmed

### Tertiary (LOW confidence — Phase 0 must upgrade these)
- Voluntary-cancel reward preservation behavior — inferred from plan ambiguity; not confirmed from on-chain contract
- Boros WebSocket exact URL and subscription schema — referenced in ARCHITECTURE.md diagram; needs live verification
- `@pendle/sdk-boros` sign-only (no-submit) surface — not confirmed from SDK inspection
- `eventIndex` field coverage across all 113 Boros markets — confirmed in one market only

---

*Research completed: 2026-04-23*
*Ready for roadmap: yes — pending Phase 0 resolution of 6 open empirical questions listed in Gaps section*
