# Architecture Research — Boros Reward Farming Bot

**Domain:** Latency-budgeted trading bot with offline-trained models; Python + TypeScript split; local macOS deployment
**Researched:** 2026-04-23
**Confidence:** HIGH (design decisions), MEDIUM (WS fill event semantics — see Section 9)
**Wiki pages consulted:** `workspaces/boros/wiki/index.md` (empty — no prior pages; seeding is Phase 1 work per PROJECT.md Protocol 1)

---

## 0. Executive recommendation (the one-line answer)

**Split-brain architecture with Python owning the clock and TypeScript owning the hot path, communicating over a localhost ZeroMQ bus with a SQLite state spine.** Not a monolith in either language.

- **Python process (`brain`)** — long-lived, runs the 1–5 s decision cycle. Owns: market-data fetcher, fill model, loss model, reward-share model, decision engine, backtest replay engine, paper-mode simulator, circuit breaker coordinator, run manifest writer.
- **TypeScript process (`hands`)** — long-lived, stateless, reactive. Owns: Pendle SDK calls, pre-signed cancel calldata cache, WebSocket fill listener, Send Txs Bot dispatcher, Merkle claim executor.
- **`brain` → `hands`** over ZMQ `PUSH/PULL` on `ipc:///tmp/boros.cmd` — commands like `PLACE`, `CANCEL`, `CANCEL_ALL`, `CLOSE_AT_MARKET`, `CLAIM_REWARDS`.
- **`hands` → `brain`** over ZMQ `PUB/SUB` on `ipc:///tmp/boros.events` — events like `FILL_DETECTED`, `ORDER_PLACED`, `PURGE_DETECTED`, `CANCEL_CONFIRMED`, `TX_FAILED`.
- **Shared state** in `var/state.sqlite` — single-writer-per-table convention: `brain` writes models/decisions/manifests, `hands` writes tx receipts/order state, both read anything.

**Why not a TS monolith?** The quant stack (scipy, numpy, statsmodels, `tick` for Hawkes, pandas for backtest replay) has no equivalent in TS. Shelling out to Python from TS per-decision-cycle for model inference is a kludge and inverts the clock ownership: the brain should drive, not be called.

**Why not a Python monolith with TS shim?** The hot path — WebSocket fill detection → dispatch pre-signed cancel — must not cross a language boundary. Our 2–5 s end-to-end budget includes Arbitrum block inclusion (~250 ms) plus RPC roundtrip (~200–500 ms) plus one Send-Txs-Bot hop. That leaves ~1–3 s of software latency. A Python-to-TS-to-network hop per fill event burns budget on IPC we don't need to pay.

**Why not Redis / full event bus?** Overkill for a single-operator, two-process system. ZMQ IPC sockets give us sub-millisecond latency, zero daemon to run, and survive a restart of either side cleanly (socket reconnects; SQLite is the persistence fallback). Redis would add a third process to launch, monitor, and keep from corrupting — operational tax with no gain.

**Why SQLite for state?** Single-writer-per-table is enforceable with discipline. NDJSON is append-only (good for logs, bad for "current open orders"). DuckDB is great for analytics scans but SQLite gives us row-level upserts, transactions, and cheap crash recovery. We'll use DuckDB **read-only on top of the SQLite file + NDJSON logs** for backtest/analysis; DuckDB reads SQLite natively.

---

## 1. System Overview

### Top-level process map (steady state, `mode=live`)

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Operator's macOS laptop                        │
│                                                                         │
│  ┌──────────────────────────┐        ┌──────────────────────────────┐  │
│  │  brain (Python asyncio)  │        │   hands (Node/TypeScript)    │  │
│  │                          │        │                              │  │
│  │  ┌────────────────────┐  │  cmd   │  ┌────────────────────────┐  │  │
│  │  │ MarketDataLoop 5s  │──┼──PUSH──┼─→│ CommandListener (PULL) │  │  │
│  │  │ (REST+fIndex+book) │  │        │  └───────────┬────────────┘  │  │
│  │  └─────────┬──────────┘  │        │              │               │  │
│  │            ▼             │        │              ▼               │  │
│  │  ┌────────────────────┐  │        │  ┌────────────────────────┐  │  │
│  │  │ FillModel.score()  │  │        │  │ OrderExecutor          │  │  │
│  │  │ LossModel.ev()     │  │        │  │  · place/cancel        │  │  │
│  │  │ RewardShareModel   │  │        │  │  · pre-sign cache      │  │  │
│  │  │ DecisionEngine     │  │        │  │  · Send-Txs-Bot client │  │  │
│  │  └─────────┬──────────┘  │        │  └───────────┬────────────┘  │  │
│  │            ▼             │        │              ▼               │  │
│  │  ┌────────────────────┐  │ events │  ┌────────────────────────┐  │  │
│  │  │ CircuitBreakers    │──┼──SUB───┼──│ EventPublisher (PUB)   │  │  │
│  │  │ (kill authority)   │  │        │  └───────────┬────────────┘  │  │
│  │  └─────────┬──────────┘  │        │              ▲               │  │
│  │            ▼             │        │              │               │  │
│  │  ┌────────────────────┐  │        │  ┌────────────────────────┐  │  │
│  │  │ RunManifest writer │  │        │  │ WsFillListener         │  │  │
│  │  │ StructuredLogger   │  │        │  │ (Socket.IO + order     │  │  │
│  │  └─────────┬──────────┘  │        │  │  state diff poll)      │  │  │
│  │            │             │        │  └────────────────────────┘  │  │
│  │            │             │        │              │               │  │
│  │  ┌─────────▼──────────┐  │        │  ┌───────────▼────────────┐  │  │
│  │  │ MerkleClaimSched.  │──┼──PUSH──┼─→│ MerkleClaimExecutor    │  │  │
│  │  │ (weekly, Mon 00Z)  │  │        │  │ (1x / epoch)           │  │  │
│  │  └────────────────────┘  │        │  └────────────────────────┘  │  │
│  │            │             │        │              │               │  │
│  └────────────┼─────────────┘        └──────────────┼───────────────┘  │
│               │                                     │                   │
│               └──────┬──────────────────────────────┘                   │
│                      ▼                                                  │
│            ┌───────────────────────────────────────┐                    │
│            │  var/state.sqlite   (shared spine)    │                    │
│            │  · open_orders (hands writes)         │                    │
│            │  · queue_positions (brain writes)     │                    │
│            │  · decisions (brain writes)           │                    │
│            │  · tx_receipts (hands writes)         │                    │
│            │  · run_manifests (brain writes)       │                    │
│            │  · epoch_rewards (brain writes)       │                    │
│            ├───────────────────────────────────────┤                    │
│            │  var/logs/<run_id>.ndjson             │                    │
│            │  var/logs/<run_id>.manifest.json      │                    │
│            │  var/logs/tx_receipts/*.json          │                    │
│            └───────────────────────────────────────┘                    │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
                            │                      │
                            ▼                      ▼
              ┌─────────────────────┐   ┌──────────────────────────┐
              │ Arbitrum RPC        │   │ Boros REST + WS          │
              │ arb1.arbitrum.io    │   │ api.boros.finance        │
              │ · fIndexOracle      │   │ secrettune.io (Socket.IO)│
              │ · MerkleDistributor │   │ Send-Txs-Bot             │
              └─────────────────────┘   └──────────────────────────┘
```

### Mermaid diagram (first-pass seed for `docs/ARCHITECTURE.md`)

```mermaid
flowchart TB
    subgraph Operator_macOS["Operator macOS laptop"]
        subgraph brain["brain · Python asyncio process"]
            MDL[MarketDataLoop<br/>poll /markets + fIndex + book]
            QPT[QueuePositionTracker<br/>replay trades between snapshots]
            FM[FillModel<br/>NHPP/Hawkes/RP score]
            LM[LossModel<br/>OU on basis E[loss]]
            RSM[RewardShareModel<br/>poll E_liq_per_epoch, cap]
            DE[DecisionEngine<br/>EV_hold cancel rule]
            CB[CircuitBreakers<br/>margin, oracle, CLO shift]
            MCS[MerkleClaimScheduler<br/>weekly trigger]
            RM[RunManifest writer<br/>ULID + knob tree]
            SL[StructuredLogger<br/>NDJSON + run_id]
            BT[BacktestReplayEngine<br/>same DE, mocked hands]
            PAPER[PaperMode<br/>live feeds, no tx dispatch]
        end

        subgraph hands["hands · Node/TypeScript process"]
            CL[CommandListener<br/>ZMQ PULL]
            OE[OrderExecutor<br/>place/cancel via SDK]
            PSC[PreSignedCancelCache<br/>calldata in memory by orderId]
            WFL[WsFillListener<br/>Socket.IO + state diff poll]
            EP[EventPublisher<br/>ZMQ PUB]
            STB[SendTxsBotClient<br/>agent wallet]
            MCE[MerkleClaimExecutor<br/>1 tx per epoch]
        end

        subgraph state["var/ shared state spine"]
            SQL[(state.sqlite<br/>open_orders, decisions,<br/>tx_receipts, manifests)]
            NDJ[[logs/*.ndjson<br/>append-only events]]
            PARQ[[parquet/duckdb<br/>historical trades + books]]
        end
    end

    RPC[Arbitrum RPC<br/>fIndexOracle, Merkle]
    REST[Boros REST<br/>api.boros.finance]
    WS[Boros WebSocket<br/>Socket.IO orderbook+trades]
    STB_RPC[Send-Txs-Bot<br/>api.boros.finance/send-txs-bot]

    MDL -->|reads| REST
    MDL -->|eth_call| RPC
    MDL -->|writes tick data| SQL
    MDL -->|subscribes| QPT
    QPT -->|reads book snapshots| PARQ
    QPT -->|writes queue est| SQL
    QPT -->|features| FM
    FM -->|P_fill| DE
    LM -->|E_loss| DE
    RSM -->|R_share_capped| DE
    RSM -->|reads /markets| REST
    DE -->|emits DECISION| SL
    DE -->|enqueue cmd| CL
    CB -->|kill auth| DE
    CB -->|kill auth| CL
    CB -->|reads oracle, margin| MDL
    RM -->|stamps run_id| SL
    SL -->|appends| NDJ
    SL -->|upserts| SQL
    MCS -->|CLAIM cmd| CL

    CL --> OE
    CL --> MCE
    OE -->|SDK call| REST
    OE -->|pre-signs| PSC
    OE -->|dispatch| STB
    STB --> STB_RPC
    MCE -->|claim tx| RPC
    WFL -->|subscribes| WS
    WFL -->|polls orders| REST
    WFL -->|fires cancel calldata| PSC
    PSC -->|dispatch| STB
    WFL --> EP
    OE --> EP
    EP -->|events| CB
    EP -->|events| DE
    OE -->|writes order rows| SQL
    STB -->|writes tx receipts| SQL

    BT -->|replays| PARQ
    BT -.reuses same DE/FM/LM/RSM.-> DE
    PAPER -.reuses same brain, stubs hands.-> CL
```

---

## 2. Component boundaries — process vs module, Python vs TS

Node granularity matches PROJECT.md Protocol 2 (module, long-lived task, external dependency, named knob).

| Component | Process | Language | Why | Talks to (edge type) |
|---|---|---|---|---|
| **MarketDataLoop** | `brain` | Python | Drives the decision clock (1–5 s cycle). Needs pandas/numpy for feature computation in the same process as `FillModel`. | `reads` Boros REST `/markets`, `/markets/order-books`, `/v2/accounts/all-limit-orders`; `reads` Arbitrum RPC `fIndexOracle.getLatestFIndex()` + `latestAnnualizedRate()`; `writes` `state.sqlite:tick_data`; `emits-event` `MARKET_TICK` to `DecisionEngine`, `CircuitBreakers`, `QueuePositionTracker` |
| **QueuePositionTracker** | `brain` | Python | Replays trade tape between hourly raw-book snapshots; purely analytical, heavy pandas work. | `reads` `parquet/market-trades` + `parquet/order-book-raw`; `writes` `state.sqlite:queue_positions`; `emits-event` features to `FillModel` |
| **FillModel** | `brain` module | Python | Per-market arrival process (NHPP / Hawkes / RP). Inference is a pure function; `DecisionEngine` imports it directly, no IPC. | `calls` `QueuePositionTracker.current_queue()`; returns `P(fill \| δ, t, features)` |
| **LossModel** | `brain` module | Python | OU on basis, closed-form + empirical cross-check. Pure function. | `reads` `parquet/market-trades` + `parquet/underlying-apr`; returns `E[loss \| fill]` |
| **RewardShareModel** | `brain` module | Python | Poll `E_liq_per_epoch` live; compute capped share. Must run same cycle as decisions. | `reads` REST `/markets`; `reads` `state.sqlite:open_orders` for `Q_me`; returns `R_capped_per_epoch` |
| **DecisionEngine** | `brain` module | Python | EV cancel rule lives with the models — one function away from each input. Backtest and paper reuse the exact same call site. | `calls` `FillModel`, `LossModel`, `RewardShareModel`; `emits-event` `DECISION` (PLACE/HOLD/CANCEL); `depends-on-config` the knob tree |
| **CircuitBreakers** | `brain` module | Python | Cross-cutting, **holds kill authority**. Runs on every `MARKET_TICK` and every `brain↔hands` event. When it fires, it preempts `DecisionEngine` and emits `CANCEL_ALL` or `CLOSE_ALL_AT_MARKET` directly. | `reads` margin trajectory, oracle `fTime`, CLO thresholds, fill rate; `emits-event` `KILL` cmd that bypasses `DecisionEngine` |
| **MerkleClaimScheduler** | `brain` module | Python | Low-frequency (weekly), trigger-based; lives in the Python process so it's covered by the same RUN_MANIFEST. | `reads` Arbitrum RPC for Merkle root event; `emits-event` `CLAIM` cmd |
| **RunManifest writer** | `brain` module | Python | Must own the ULID and the knob tree snapshot. Cross-cutting: every emitter of a log line reads `run_id` from here. | `writes` `state.sqlite:run_manifests`; `writes` `logs/<run_id>.manifest.json` |
| **StructuredLogger** | `brain` module | Python | Single NDJSON writer so line ordering is preserved. `hands` events arrive via ZMQ and are logged by `brain` — one writer, no interleaving bugs. | Consumed by humans + analysis notebooks |
| **BacktestReplayEngine** | `brain` CLI subcommand | Python | Same process type; different entrypoint. Imports `DecisionEngine`, `FillModel`, `LossModel` directly. The "hands" half is replaced by an in-process mock matching engine. | `reads` `parquet/*`; `writes` `logs/<run_id>.ndjson` tagged `mode=backtest` |
| **PaperMode** | `brain` CLI subcommand | Python | Same `brain` process, but `hands` commands are routed to a no-op stub that logs them instead of sending to Send-Txs-Bot. WebSocket feeds are live. | Identical code path to live except the dispatcher |
| **CommandListener** | `hands` | TypeScript | Receives `brain` commands over ZMQ. Stateless per-command. | ZMQ PULL on `ipc:///tmp/boros.cmd` |
| **OrderExecutor** | `hands` module | TypeScript | Pendle SDK (`@pendle/sdk-boros`) is TS-only. Place/cancel via `exchange.placeOrders` / `exchange.cancelOrders`. | `calls` Boros REST `/calldata/*`; `writes` `PreSignedCancelCache` on every `PLACE` |
| **PreSignedCancelCache** | `hands` module | TypeScript | **In-memory** `Map<orderId, signedCancelCalldata>`. On `FILL_DETECTED` the cancel is a sync map lookup + tx submit — no network roundtrip to generate calldata. | Written by `OrderExecutor`, read by `WsFillListener` |
| **WsFillListener** | `hands` | TypeScript | Socket.IO subscription + 1 s REST poll of `/accounts/limit-orders` as a belt-and-suspenders diff to catch the case where the public WS doesn't surface our fill. On fill, fires pre-signed cancel + emits `FILL_DETECTED` event to `brain`. | `subscribes-to` `orderbook:{marketId}:full:update`; `reads` REST; `writes` `state.sqlite:open_orders`; `emits-event` to `brain` |
| **SendTxsBotClient** | `hands` module | TypeScript | Dispatches pre-signed calldata. One place to manage agent-wallet nonces and gas. | `calls` Send-Txs-Bot v2; `writes` `state.sqlite:tx_receipts` |
| **MerkleClaimExecutor** | `hands` module | TypeScript | Claim tx is on-chain directly (MultiTokenMerkleDistributor), uses root wallet via a manual confirmation gate — not via Send-Txs-Bot agent, since it's a one-off and not latency-sensitive. | `calls` Arbitrum RPC |
| **EventPublisher** | `hands` module | TypeScript | Fans out `FILL_DETECTED`, `ORDER_PLACED`, `PURGE_DETECTED`, `CANCEL_CONFIRMED`, `TX_FAILED`. | ZMQ PUB on `ipc:///tmp/boros.events` |
| **Dependency diagram lint** | pre-commit hook | Python (parses YAML) | `docs/architecture.yml` is the machine-readable source of truth. Lint fails if code defines a module/function/knob not present in YAML, or vice-versa. | Enforces Protocol 2 |

### Edge type legend (aligned with PROJECT.md Protocol 2)

- `calls` — synchronous function/method call in-process
- `reads` / `writes` — reads or writes persistent state (SQLite row, file, REST)
- `emits-event` / `subscribes-to` — ZMQ PUB/SUB or in-process pub/sub
- `depends-on-config` — reads a named knob from the run manifest
- `dispatches` — submits a blockchain transaction

---

## 3. Data flow — five concrete traces

All five flows assume `mode=live`. In `mode=paper` the last TS→chain step is stubbed; in `mode=backtest` the entire `hands` half is replaced by a deterministic in-process mock matching engine.

### Flow 1 — Order book update → P(fill) recomputed → cancel decision

```
(Boros WS) orderbook:{mid}:full:update
      │  (socket.io message, ~100 ms after event)
      ▼
hands:WsFillListener  (subscribes-to WS)
      │  emits-event ORDER_BOOK_TICK over ZMQ PUB (book delta only)
      ▼
brain:MarketDataLoop  (consumes ORDER_BOOK_TICK)
      │  merges with hourly raw snapshot anchor
      ▼
brain:QueuePositionTracker.apply_delta()
      │  updates queue_position for our orderId(s)
      │  writes state.sqlite:queue_positions
      ▼
brain:FillModel.score(δ, t, features)
      │  returns P(fill) per active order
      ▼
brain:DecisionEngine.evaluate()
      │  EV_hold = R_share × P(no_fill) − E[loss] × P(fill) − cancel_cost × P(purge)
      │  if EV_hold < 0 → emit CANCEL cmd
      ▼
ZMQ PUSH cmd → hands:CommandListener
      ▼
hands:OrderExecutor.cancelOrders({orderIds})
      │  uses cached pre-signed calldata if available, else generates
      ▼
hands:SendTxsBotClient.submit()
      ▼
Arbitrum tx inclusion (~250 ms)
      │  emits CANCEL_CONFIRMED back to brain
      ▼
brain:StructuredLogger writes NDJSON with run_id
```

**Latency budget:** WS delta → ZMQ → model → decision → ZMQ → SDK call → RPC submit. Target **< 2 s** soft (brain evaluates at 1 Hz; ZMQ IPC < 1 ms; SDK/REST 200–500 ms; tx submit 100–300 ms). Chain inclusion is outside the bot's control.

### Flow 2 — WebSocket fill detected → pre-signed close fires → retrigger analytics

This is the **critical latency path**. Must stay in TS end-to-end.

```
(Boros WS or 1 s REST diff) fill on our orderId detected
      │
      ▼
hands:WsFillListener.onFill(orderId)  (TypeScript, single-threaded)
      │  STEP 1 (same tick, no await on IPC):
      │    calldata = PreSignedCancelCache.get(orderId)  // Map lookup, ~1 μs
      │    SendTxsBotClient.submit(calldata)              // async, fire-and-log
      │  STEP 2 (in parallel):
      │    EventPublisher.emit(FILL_DETECTED, {orderId, fillRate, fillSize})
      │  STEP 3 (also in parallel, for closing the opposite leg if needed):
      │    if strategy.close_on_fill == "market":
      │        OrderExecutor.placeMarketClose({side: opposite, size: filledSize})
      ▼
ZMQ PUB → brain:DecisionEngine + brain:CircuitBreakers
      │
      ▼
brain:CircuitBreakers.on_fill()
      │  increment fill counter; if > K/hour → emit KILL cmd
      ▼
brain:StructuredLogger writes fill record with full context
      ▼
brain:LossModel.record_realized_loss(orderId, close_rate)
      │  feeds the empirical cross-check of OU
```

**Latency budget:** WS event → TS dispatch. Target **< 500 ms** of software latency. Critical constraint: **no IPC hop between fill detection and cancel submission.** If that constraint were violated (e.g., Python-owned listener), the 2–5 s end-to-end budget would be at risk.

### Flow 3 — CLO range shift detected → cancel all → recalibrate → repost

```
brain:MarketDataLoop (every 5 s, or accelerated on config change)
      │  reads REST /markets, compares cloLower/cloUpper to last tick
      ▼
brain:CircuitBreakers.check_clo_shift()
      │  if |Δclo| > N ticks → emit CLO_SHIFTED event + CANCEL_ALL cmd
      │  (NOT a DecisionEngine path — CircuitBreakers bypass EV logic)
      ▼
ZMQ PUSH CANCEL_ALL → hands:CommandListener
      ▼
hands:OrderExecutor.cancelOrders({cancelAll: true, marketId})
      │  uses single bulk cancel (SDK supports it)
      │  invalidates entire PreSignedCancelCache for this market
      ▼
await CANCEL_CONFIRMED events for all open orders
      ▼
brain:MarketDataLoop.recalibrate()
      │  recompute CLO→APR→tick using new fIndex
      │  this is why CLO calibration (SCALE, S) is per-market config, loaded once at startup
      │  but the APR↔tick math is pure, runs on every MarketDataLoop tick
      ▼
brain:DecisionEngine.initial_placement()
      │  computes new tick levels, desired Q_me per side
      ▼
ZMQ PUSH PLACE → hands:CommandListener
      ▼
hands:OrderExecutor.placeOrders(...)
      │  for each placed order, generate+cache pre-signed cancel calldata
      ▼
emit ORDER_PLACED → brain (populates state.sqlite:open_orders)
```

### Flow 4 — Hourly raw book snapshot → trade-tape replayer updates queue → feeds FillModel

```
external: new raw/ snapshot file lands (every 3600 s, confirmed by plan_comparison.md)
      │
      ▼
brain:MarketDataLoop.on_snapshot_available()
      │  loads snapshot → parquet
      ▼
brain:QueuePositionTracker.rebuild_anchor()
      │  sets exact queue position for our orders at snapshot time
      │  uses eventIndex for intra-block ordering (Arbitrum 250 ms blocks)
      ▼
brain:QueuePositionTracker.replay_to_now()
      │  replays every trade since snapshot, decrementing our queue position
      │  subtracts AMM share from combined_{tickSize} to avoid double-counting
      ▼
queue_position written to state.sqlite
      ▼
next MarketDataLoop tick → FillModel picks up corrected queue_position
```

**Key correctness note:** This flow runs in the background at low priority. It is **not** in the hot path. `FillModel` always reads the *latest* queue estimate; if reconciliation is stale by < 1 hour the drift is bounded and conservative (overstates our queue protection slightly, per plan).

### Flow 5 — Margin trajectory → predictive circuit breaker → emergency close all

```
brain:MarketDataLoop (every 1 s, fast cycle)
      │  reads REST /accounts/active-positions
      │  computes dNetBalance/dt over last 30 s
      ▼
brain:CircuitBreakers.margin_trajectory()
      │  if (net_balance - maintenance) / |dNetBalance/dt| < 30 s → PANIC
      ▼
emits EMERGENCY_CLOSE cmd (preempts DecisionEngine entirely)
      ▼
ZMQ PUSH EMERGENCY_CLOSE → hands:CommandListener
      ▼
hands:OrderExecutor (priority queue — preempts any pending cmds):
      │  1. cancelAll (bulk cancel, one tx)
      │  2. for each active position: placeMarketClose at current mark
      │  3. emit CIRCUIT_BREAKER_TRIGGERED event with cause=margin_trajectory
      ▼
brain:DecisionEngine enters `suspended` state, requires manual resume
      ▼
StructuredLogger writes every step with run_id + cause
```

**Authority model:** `CircuitBreakers` is the only component allowed to emit `EMERGENCY_CLOSE` or `KILL`. `DecisionEngine` can only emit `PLACE`, `HOLD`, `CANCEL` for specific orderIds. `CommandListener` in `hands` enforces this at the command level — `KILL` commands have a priority queue slot; everything else is FIFO.

---

## 4. The Python/TS boundary — decided

**Decision: Split-brain.** Python and TS are each a long-lived process. They communicate over ZMQ IPC sockets with SQLite as the persistence backstop.

### What lives in Python (brain)

- All model code (fill, loss, reward-share)
- The decision clock (`asyncio` main loop at 1 Hz)
- Market data fetch (REST + eth_call — we use Python's `httpx` + `web3.py`, no SDK needed for reads)
- Queue position tracking and trade-tape replay
- Circuit breakers (kill authority)
- Run manifest + structured logger
- Backtest replay engine
- Paper mode (same code as live, `hands` is stubbed)
- Merkle claim scheduling (weekly trigger; the actual tx is in `hands`)

### What lives in TypeScript (hands)

- **Everything touching `@pendle/sdk-boros`.** Pre-signed calldata generation, `exchange.placeOrders`, `exchange.cancelOrders`, `exchange.bulkCancelOrders`.
- **WebSocket fill listener.** Socket.IO client subscribes to `orderbook:{marketId}:full:update` for our markets; additionally polls `/accounts/limit-orders` at 1 Hz as a belt-and-suspenders fill-diff detector (since the public Socket.IO feed does not surface per-account fill events directly — confirmed against Pendle SDK docs, 2026-04 snapshot).
- **Pre-signed cancel calldata cache.** `Map<orderId, signedCalldata>` in memory; populated on every successful `PLACE`; read on fill or cancel-cmd receipt.
- **Send-Txs-Bot dispatcher.** Nonce management and retry-on-failure for the agent wallet only.
- **Merkle claim tx executor.** Lives here because `ethers`/`viem` are in-process; the *trigger* is in Python.

### Why this choice beats the alternatives

| Alternative | Why rejected |
|---|---|
| **TS monolith with Python subprocess for inference** | Every decision cycle (1 Hz) forks or IPC-calls into Python for model inference. Cold-path latency isn't the issue; the problem is that **the clock lives in TS but the brains live in Python**, which inverts dependency direction — `DecisionEngine` (Python) is no longer in charge of its own cycle, it's a callback. Makes backtesting hard (backtest is Python-driven, but live would be TS-driven → two code paths for the same logic). Same-codebase-runs-all-three-modes requirement dies. |
| **Python monolith with TS shim over HTTP** | Acceptable IPC-wise, but *adds* latency to Flow 2 (WS fill → cancel dispatch) because the fill event has to traverse TS-listener → HTTP POST → Python-decider → HTTP POST back → TS-dispatcher. The decision-on-fill is not meaningful (fill already happened; we just need to cancel siblings and close at market). Keeping the fill-reaction purely in TS saves one roundtrip on the hottest path. |
| **Monolith in Python with TS SDK called via `child_process` per action** | Fork+exec latency (~200–500 ms on macOS) per action. Cancel-after-fill latency explodes. |
| **Redis / NATS event bus** | Extra daemon to install/launch/monitor. Pays operational tax for capacity (multi-consumer broadcast, durability) we don't need at two processes. Use ZMQ IPC. |
| **SQLite alone as IPC (no ZMQ)** | Polling SQLite for new commands is either slow (1 Hz poll → 1 s added to Flow 1) or expensive (100 Hz → CPU burn). ZMQ + SQLite-for-persistence is strictly better. |

### IPC topology (concrete)

```
ipc:///tmp/boros.cmd     brain PUSH  →  hands PULL
  Messages: {cmd_id: ULID, type: "PLACE"|"CANCEL"|"CANCEL_ALL"|"CLOSE_AT_MARKET"|"CLAIM"|"KILL",
             payload: {...}, deadline_ts: int, priority: 0|1|9}
  Priority 9 = KILL/EMERGENCY_CLOSE, preempts.

ipc:///tmp/boros.events  hands PUB   →  brain SUB
  Topics: FILL_DETECTED, ORDER_PLACED, PURGE_DETECTED, CANCEL_CONFIRMED,
          TX_FAILED, ORDER_BOOK_TICK, WS_DISCONNECTED, WS_RECONNECTED
  Each message carries run_id so brain can stamp it on the unified log.

Heartbeat: both sides PUB a heartbeat topic every 5 s. If brain misses 3 consecutive
heartbeats from hands, brain enters "no-dispatch" state (reads only, does not
enqueue new PLACE cmds, does enqueue CANCEL_ALL if oracle is stale).
Conversely: if hands misses 3 heartbeats from brain, hands cancels all
open orders (it has the pre-signed calldata; it can do this without brain's help).
```

This is the **operator-restart-one-side** requirement from PROJECT.md: ZMQ sockets auto-reconnect, SQLite persists state across restart, and each side has a one-page "I lost my sibling" protocol.

---

## 5. State ownership map

Single-writer-per-table, explicit. No shared mutable state without a named owner.

| State | Owner (writer) | Readers | Format | Lifetime | Notes |
|---|---|---|---|---|---|
| `open_orders` | `hands:OrderExecutor` (writes on PLACE/CANCEL_CONFIRMED/PURGE) | `brain:DecisionEngine`, `brain:RewardShareModel`, `brain:CircuitBreakers` | SQLite table | live run + persisted across restarts | Source of truth is chain state; row has `last_reconciled_at` column — `hands` reconciles with REST every 10 s |
| `tx_receipts` | `hands:SendTxsBotClient` | `brain:StructuredLogger` | SQLite table + NDJSON mirror | forever (audit) | One row per submitted tx, including failures |
| `queue_positions` | `brain:QueuePositionTracker` | `brain:FillModel` | SQLite table | rebuilt on every hourly snapshot, reset on restart | Rebuild anchor from last snapshot on startup; not persisted long-term |
| `tick_data` | `brain:MarketDataLoop` | `brain:*`, `brain:BacktestReplayEngine` | SQLite rolling window (last 24 h) + parquet long-term | 24 h hot, rest archived | Every REST poll + WS update appended |
| `features` | `brain:MarketDataLoop` (derived from `tick_data`) | `brain:FillModel`, `brain:LossModel` | In-memory `pandas.DataFrame` per market | cycle-scoped | Recomputed every tick; cached between decision-engine scoring calls |
| `active_config_knobs` | `brain:RunManifest` (loaded once at startup) | `brain:*` | Pydantic model in RAM + `logs/<run_id>.manifest.json` | run lifetime; **no hot reload in v0.5** | Any config change requires restart → new run_id with parent_run_id link. Hot-reload introduces silent drift risk and is explicitly deferred. |
| `reward_accumulation` | `brain:RewardShareModel` | `brain:DecisionEngine`, operator notebooks | SQLite `epoch_rewards` table | forever | Tracks per-epoch capture estimate; reconciled weekly against Merkle claim amounts |
| `run_manifests` | `brain:RunManifest` | analysis tools, `brain:StructuredLogger` | SQLite + `logs/<run_id>.manifest.json` | forever | First line of every run log |
| `decisions` | `brain:DecisionEngine` | paper-mode reviewer, backtest calibration plots | SQLite + NDJSON | forever | Every cancel/hold/place decision with the inputs that produced it |
| `pre_signed_cancel_calldata` | `hands:OrderExecutor` | `hands:WsFillListener`, `hands:CommandListener` | **RAM only** (`Map<orderId, bytes>`) | process lifetime | Rebuilt on hands restart by regenerating from REST `/v2/accounts/all-limit-orders` — costs one REST call burst per restart, acceptable |
| `ws_subscription_state` | `hands:WsFillListener` | — | RAM | process lifetime | Rebuilt on reconnect |
| `historical trades + books` | (data pipeline, not bot runtime) | `brain:BacktestReplayEngine`, `brain:QueuePositionTracker` | parquet + DuckDB view | forever | Written by Phase 1 ingestion; read-only at runtime |

**Why SQLite, not just NDJSON:** NDJSON is great for append-only event streams (it's the format for `logs/<run_id>.ndjson`). But "what are my current open orders" is a question NDJSON answers slowly (scan + reduce). SQLite gives us O(1) lookup with row upserts. The two coexist: NDJSON is the audit log (write-once), SQLite is the live state (read-heavy, write-upsert).

**Why not DuckDB as live state:** DuckDB excels at OLAP scans of parquet files — we use it for backtest replay (read-only joins across months of trade data). DuckDB doesn't do single-row updates well and is not designed as a live application store. Use the right tool per workload: SQLite for state, DuckDB on top of parquet + SQLite (DuckDB reads SQLite natively via `sqlite_scanner`) for analysis.

**Anti-pattern explicitly avoided:** A shared in-memory object passed by reference between processes. There's no such thing in a split-brain design; every piece of cross-process state goes through SQLite (for durability) or ZMQ (for events). Enforced by the dependency diagram — `calls` edges never cross a process boundary.

---

## 6. Deployment surfaces (v0.5 minimum)

### Launching

```bash
# From the project root, reading the active run config
make run-live    # → launches brain + hands, both foreground, via overmind or foreman
make run-paper   # → same launcher, mode=paper (hands stubs Send-Txs-Bot)
make run-backtest # → brain only, hands entirely replaced by BacktestReplayEngine
```

Under the hood this is just:

```
# Procfile
brain:  python -m boros.brain.main --mode=${MODE} --config=config/${MARKET}.yaml
hands:  node --enable-source-maps dist/hands/main.js --mode=${MODE}
```

Running both under a single process manager (`overmind`, 100 lines of Go, no daemons) is the macOS-native answer. No `launchd` plist in v0.5 — the operator is at the keyboard; if they close the terminal the bot should stop, that's a feature. Auto-respawn is deferred to v1.0 when the bot has proven itself.

**One-process-restart requirement:** Because each side is a separate foreground process under `overmind`, `overmind restart hands` restarts TS only; `brain` keeps driving the cycle and will reconnect once `hands` comes back up. Same for `overmind restart brain` — `hands` holds its open orders and its pre-signed cancel cache, and will safely cancel-all if it misses brain heartbeats for 15 s.

### Health / liveness

A trading bot's liveness probe is not "process is running." It's "process is **doing the thing it's supposed to be doing**." Define three health tiers:

| Tier | Check | Action on fail |
|---|---|---|
| **Heartbeat** | Both processes write a `heartbeat_at` column every 5 s | `overmind` or operator restarts side that stopped |
| **Cycle liveness** | `brain` wrote a `tick_data` row in the last 10 s | Alert operator; `hands` should enter no-dispatch mode (protocol 4 above) |
| **Decision freshness** | Last `DECISION` row is < 60 s old, **and** its run_id matches the current manifest | Alert operator — silent drift between config and logs means the manifest reader is broken, which per Protocol 3 means logs are "unreadable by design" |
| **Order drift** | `state.sqlite:open_orders` matches REST `/v2/accounts/all-limit-orders` within tolerance (1 order, 5 s old) | Hard stop, manual reconciliation required |
| **Oracle freshness** | `fTime > 0.7 × maxUpdateDelay` | Cancel-all (from CircuitBreakers, Phase 6) |
| **Margin headroom** | `(net_balance − maintenance_margin) / |dBalance/dt| > 30 s` | Emergency close (Flow 5) |

A CLI command `boros health` runs all of these against the SQLite file in < 200 ms. Operator runs it before closing their laptop.

### Upgrades

**The bot can't be down during a reward epoch** — the strategy is time-weighted, every minute absent is a minute of lost reward accrual. Concrete upgrade protocol for v0.5:

1. During epoch, the bot keeps running.
2. To upgrade, operator stops `brain` first (keep `hands` running).
3. Pull new `brain` code; run migrations (`alembic upgrade head`); smoke-test against SQLite snapshot.
4. Start new `brain`. It reads `state.sqlite`, reconstructs open_orders, emits a new RUN_MANIFEST with `parent_run_id = <prev_run_id>`.
5. Then repeat (2–4) for `hands` if TS changed. `hands` is stateless (ex-RAM pre-signed cache), so this is safe.
6. If the upgrade touches both brain and hands simultaneously (ZMQ message schema change), that's a structured migration: stop both, cancel-all orders first, upgrade, restart, re-place.

**Why this works:** Open orders on-chain survive the bot being offline. They just stop accumulating *decisions* — not reward time-weight (which accrues passively). The only real risk during an upgrade is a fill happening while `hands` is down and no one is listening for it. Keeping `hands` up through `brain` upgrades is the policy. Keeping upgrades scheduled for Thursday 23:00 UTC (end of reward epoch) when the next epoch's budget hasn't started yet is the operator discipline.

### Observability

Where the operator looks during the day, in priority order:

1. **`var/logs/<run_id>.ndjson`, tailed with `jq`:** `tail -f var/logs/$(cat var/current_run_id).ndjson | jq 'select(.level=="warn" or .level=="error" or .event=="DECISION")'`
2. **`boros status`:** CLI that prints the current RUN_MANIFEST header + last 10 decisions + current open orders + current P&L estimate. Think `git status` for a trading bot.
3. **Notebook dashboard (`analysis/live.ipynb`):** reads SQLite + NDJSON, plots P(fill) vs realized, cumulative rewards, queue position over time. Auto-refresh every 30 s.
4. **Discord/Telegram webhook:** circuit-breaker fires only. No noise.

No web UI in v0.5 (see PROJECT.md Out of Scope). The logs + manifest are the interface.

---

## 7. Project structure (concrete folder layout)

```
boros/
├── brain/                          # Python package, the decision layer
│   ├── pyproject.toml
│   ├── src/boros_brain/
│   │   ├── __init__.py
│   │   ├── main.py                 # entrypoint: --mode=live|paper|backtest
│   │   ├── config/
│   │   │   ├── schema.py           # Pydantic: THE knob inventory (Protocol 3)
│   │   │   └── loader.py
│   │   ├── manifest.py             # RUN_MANIFEST writer, ULID, run_id propagation
│   │   ├── logger.py               # structured NDJSON + SQLite mirror
│   │   ├── data/
│   │   │   ├── market_loop.py      # MarketDataLoop
│   │   │   ├── rest_client.py      # httpx-based, no SDK needed for reads
│   │   │   ├── rpc_client.py       # web3.py, fIndexOracle decoder
│   │   │   └── book_snapshots.py   # hourly raw/ ingestion
│   │   ├── models/
│   │   │   ├── fill/
│   │   │   │   ├── base.py         # ArrivalProcess ABC
│   │   │   │   ├── nhpp.py         # v0.5 default
│   │   │   │   ├── hawkes.py       # v1.0, CV > 1.5
│   │   │   │   └── renewal.py      # v1.0, CV < 0.7
│   │   │   ├── loss/
│   │   │   │   ├── ou_basis.py     # parametric OU on basis
│   │   │   │   └── empirical.py    # post-fill replay cross-check
│   │   │   ├── reward_share.py
│   │   │   └── queue.py            # QueuePositionTracker
│   │   ├── decision/
│   │   │   ├── engine.py           # EV cancel rule
│   │   │   └── circuit_breakers.py # kill authority
│   │   ├── execution/
│   │   │   ├── bus.py              # ZMQ PUSH/SUB client
│   │   │   ├── commands.py         # Pydantic message schemas (shared with hands)
│   │   │   └── merkle_scheduler.py
│   │   ├── modes/
│   │   │   ├── live.py
│   │   │   ├── paper.py            # lives-as-module, same DecisionEngine, stub bus
│   │   │   └── backtest.py         # replay engine
│   │   └── state/
│   │       ├── db.py               # SQLite schema + migrations (alembic)
│   │       └── schemas.sql
│   └── tests/
│       ├── test_fill_nhpp.py
│       ├── test_ev_decision.py     # property tests on EV rule
│       └── test_circuit_breakers.py
├── hands/                          # TypeScript package, the execution layer
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── main.ts                 # entrypoint
│   │   ├── config.ts
│   │   ├── bus/
│   │   │   ├── commandListener.ts  # ZMQ PULL
│   │   │   ├── eventPublisher.ts   # ZMQ PUB
│   │   │   └── messageSchemas.ts   # mirrors brain/commands.py (Zod)
│   │   ├── execution/
│   │   │   ├── orderExecutor.ts    # @pendle/sdk-boros wrapper
│   │   │   ├── preSignedCache.ts   # Map<orderId, calldata>
│   │   │   └── sendTxsClient.ts    # Send-Txs-Bot HTTP client
│   │   ├── ws/
│   │   │   ├── fillListener.ts     # Socket.IO + REST diff
│   │   │   └── reconnect.ts
│   │   ├── onchain/
│   │   │   └── merkleClaim.ts      # ethers/viem, root-wallet path
│   │   └── state/
│   │       └── sqliteWriter.ts     # better-sqlite3, upserts only
│   └── tests/
│       ├── orderExecutor.spec.ts
│       └── fillListener.spec.ts
├── config/                         # per-market YAML — CALIBRATION, not strategy
│   ├── ETHUSDT-29MAY2026.yaml      # SCALE, S, cloLower, cloUpper, tickStep, fIndexOracle
│   └── BTCUSDT-29MAY2026.yaml
├── strategy/                       # strategy knob tree — THE knob inventory
│   ├── v0.5-default.yaml           # voluntary_cancel_forfeits_accumulated, target_share, etc.
│   └── v1.0-permarket.yaml
├── data/                           # historical, read-only
│   ├── market-trades/              # NDJSON, monthly
│   ├── order-book/{market}/raw/
│   ├── order-book/{market}/combined_*/
│   ├── underlying-apr/
│   └── parquet/                    # converted for fast DuckDB scans
├── docs/
│   ├── ARCHITECTURE.md             # ← THE living diagram (Protocol 2)
│   ├── architecture.yml            # ← machine-readable, pre-commit hook parses
│   └── runbook.md
├── analysis/
│   ├── live.ipynb
│   ├── backtest_calibration.ipynb
│   └── reward_apr_sweep.ipynb
├── var/                            # runtime, gitignored
│   ├── state.sqlite
│   ├── logs/<run_id>.ndjson
│   ├── logs/<run_id>.manifest.json
│   └── current_run_id              # symlink-like pointer file
├── scripts/
│   ├── dep_lint.py                 # Protocol 2 enforcement: code ↔ architecture.yml
│   └── manifest_diff.py            # diff two run manifests to see knob drift
├── Procfile                        # overmind/foreman: brain + hands
├── Makefile                        # run-live, run-paper, run-backtest, health, check
└── .pre-commit-config.yaml         # runs dep_lint, ruff, eslint, mypy, manifest_diff
```

### Structure rationale

- **`brain/` and `hands/` as sibling packages,** not nested, because they ship independently. Shared schemas (`commands.py` ↔ `messageSchemas.ts`) are the one duplication we accept — a codegen step from a single JSON schema is v1.0 polish, not v0.5 table stakes.
- **`strategy/` separated from `config/`** because `config/` holds *platform calibration* (SCALE, S, fIndexOracle addresses — change when Boros changes something) while `strategy/` holds *the knobs* (target_share, voluntary_cancel_forfeits_accumulated, cancel_latency_assumed — change when we change our mind). RUN_MANIFEST stamps both. The distinction maps to Protocol 3's "full knob tree."
- **`modes/` inside `brain/`** is the "same codebase runs all three modes" requirement. `live.py` and `paper.py` differ only in which bus they attach (real ZMQ vs stub logger); `backtest.py` replaces the bus with the replay engine. `DecisionEngine`, `FillModel`, `LossModel`, `RewardShareModel` are imported unmodified across all three.
- **`docs/architecture.yml` in the repo root `docs/`**, parsed by `scripts/dep_lint.py`, is the ground truth for Protocol 2. Every commit is gated on the diagram matching the code.

---

## 8. Suggested build order — endorsed ordering, one change

The consolidated plan's Phase 0 → Phase 10 ordering is sound for the *modeling* workstream. But the *infrastructure* workstream (SQLite schema, ZMQ bus, RUN_MANIFEST, dependency lint) is cross-cutting and needs to exist **before** any of Phases 2–5 can log anything usable.

### Recommended sequencing

**Phase 0 — Prerequisites** (unchanged)
Answer cancel-behavior and minimum-order-size questions from Boros docs/Discord. Gate subsequent engineering.

**Phase 1 — Data + Infrastructure** (split from consolidated plan; infra was implicit)
- 1a. Data pipeline + market screener (as consolidated plan)
- 1b. **NEW:** Wiki seeding (turn `boros_bot_guide.md`, `boros_consolidated_plan.md`, `plan_comparison.md` into wiki pages — Protocol 1 obligation)
- 1c. **NEW:** `docs/ARCHITECTURE.md` + `architecture.yml` seeded from this research file — Protocol 2 obligation, MUST exist before any code
- 1d. **NEW:** SQLite schema + alembic migrations; RUN_MANIFEST writer; StructuredLogger; `dep_lint.py` pre-commit hook — Protocol 3 obligation
- 1e. **NEW:** ZMQ bus skeleton with echo test between a dummy `brain` and dummy `hands` — proves the boundary works before any model code goes in
- 1f. Reward-share economics gate (Phase 1d in consolidated plan — kept here, uses infra from 1d/1e)

**Why this matters:** Shipping Phase 2 (fill model) without the manifest/logger means we produce NDJSON logs we can't join against the strategy version that produced them. Per Protocol 3, "a log without its manifest sidecar is unreadable by design." Building models before the manifest is building readable-for-today logs that become garbage for tomorrow's postmortem.

**Phase 2 — Fill model (v0.5 NHPP)** — unchanged. Runs as a Python module, testable offline against the parquet data from 1a.

**Phase 3 — Conditional loss model** — unchanged. Same setup.

**Phase 4 — Reward share model** — unchanged. Now wired through the infra.

**Phase 5 — Decision engine (EV rule)** — unchanged. First end-to-end point where `brain`-side code actually produces DECISION rows in the log. Run in `backtest` mode to validate.

**Phase 6 — Circuit breakers** — unchanged. Python-side, same process as DecisionEngine. Can be exercised with mock chain state in tests.

**Phase 7 — Backtest engine** — unchanged. At this point, `brain` is end-to-end self-sufficient in `mode=backtest`.

**Phase 8 — Execution (`hands` process)** — unchanged BUT this is where the ZMQ bus goes from echo-test to real. `hands` wraps `@pendle/sdk-boros` for place/cancel, implements `PreSignedCancelCache`, wires Send-Txs-Bot. WebSocket listener in this phase.

**Phase 9 — Paper trading** — unchanged. `brain` runs `mode=paper`, `hands` runs with Send-Txs-Bot dispatch disabled (logs "would have dispatched X"). Two Procfile modes, same binaries.

**Phase 10 — Live** — unchanged.

### Why endorse the plan's ordering otherwise

The dependency chain `data → models → decision → execution → paper → live` is correct. Execution-before-decision would mean building a hand without a brain; models-before-data would mean fitting on nothing. The two insertions (infra + wiki + ARCHITECTURE.md as Phase 1 prerequisites) are the only structural change.

### Build order, dependencies, and blast radius

| Phase deliverable | Depends on | Blast radius if changed |
|---|---|---|
| SQLite schema (1d) | nothing | Everything that writes state (brain:StructuredLogger, hands:OrderExecutor); migrations needed |
| RUN_MANIFEST knob tree (1d) | `strategy/*.yaml` schema | Every log line; every analysis tool; Protocol 3 contract |
| ZMQ message schemas (1e) | nothing | Both brain and hands; must codegen or manually keep in sync |
| FillModel interface (2) | tick_data schema (1d) | DecisionEngine (5); BacktestReplayEngine (7); paper mode (9) |
| DecisionEngine EV formula (5) | FillModel (2), LossModel (3), RewardShareModel (4) | Every placement/cancel decision; backtest output; paper output |
| PreSignedCancelCache (8) | ZMQ schema (1e), OrderExecutor (8) | Flow 2 latency; fill safety |
| WsFillListener fill-detection logic (8) | PreSignedCancelCache (8) | Flow 2 correctness; paper-vs-live divergence |
| CircuitBreakers kill authority (6) | ZMQ priority lanes (1e) | All fail-closed behavior; any breaker bug is existentially bad |

Anything in the right column that appears in multiple rows is a high-blast-radius node — changes to those nodes require the full Protocol 2 review.

---

## 9. Anti-patterns — what NOT to do here

### Anti-pattern 1: Python driving execution via subprocess calls to a TS CLI

**What people do:** Python `DecisionEngine` emits `subprocess.run(["node", "cancel.js", orderId])` per cancel.
**Why it's wrong:** ~200–500 ms fork+exec tax per action. Hot path (Flow 2) budget annihilated. Nonce/wallet state is per-invocation, which forces re-reading from REST every time — adds another 200 ms.
**Do instead:** Long-lived `hands` process with ZMQ, as above. One warm TS runtime, stateful in-RAM cache.

### Anti-pattern 2: Sharing a mutable `open_orders` dict via a pickle file or shared memory

**What people do:** "It's just two processes on the same machine, let's mmap a file."
**Why it's wrong:** Two writers without locking → corruption. Two writers with locking → 200 ms-ish pauses because neither language has great cross-process lock ergonomics on macOS.
**Do instead:** SQLite as the shared state with single-writer-per-table. WAL mode; concurrent readers; one writer uses `UPSERT` atomically.

### Anti-pattern 3: Hot-reloading the knob tree mid-run

**What people do:** Watch `strategy/*.yaml`, reload on change without restarting.
**Why it's wrong:** Protocol 3 says a RUN_MANIFEST is immutable per run; knob changes require a new run_id. Hot reload makes logs ambiguous ("was target_share 0.05 or 0.08 at 14:23:17?"). Silent parameter drift is exactly what Protocol 3 forbids.
**Do instead:** Config change → `SIGTERM brain` → new process → new RUN_MANIFEST with `parent_run_id` pointer. Operator pays a 5 s interruption to preserve analyzability.

### Anti-pattern 4: Computing `E_liq_per_epoch` once at startup, caching forever

**What people do:** Read `/markets` once, stash the per-side emission rate.
**Why it's wrong:** Consolidated plan §Phase 0 explicitly: "per-side budgets likely rebalance dynamically." Caching stale budgets → `R_share` is fiction → EV rule makes wrong decisions → bot loses money to invisible economics.
**Do instead:** Poll every decision cycle (1 Hz). `RewardShareModel` reads `/markets` and computes from live numbers.

### Anti-pattern 5: "Kill authority" shared between DecisionEngine and CircuitBreakers

**What people do:** Both components can emit CANCEL. Bug: DecisionEngine cancels an order at the exact moment CircuitBreakers tries to EMERGENCY_CLOSE the same order → Send-Txs-Bot sees two conflicting cmds → undefined behavior.
**Why it's wrong:** No single authority = no audit trail for why a cancel happened.
**Do instead:** `CircuitBreakers` is the only component that can emit `EMERGENCY_CLOSE`, `KILL`, or `CANCEL_ALL`. `DecisionEngine` can only emit per-order `PLACE`, `CANCEL`, `HOLD`. The ZMQ `CommandListener` enforces this with priority: a priority-9 KILL preempts pending priority-1 per-order cmds.

### Anti-pattern 6: Treating `mode=paper` as a separate code path

**What people do:** Fork the decision logic into `live_decision.py` and `paper_decision.py`.
**Why it's wrong:** Two code paths means two places for bugs, and paper→live divergence (Phase 9's gating check) is now partly a code-path-difference artifact, not a real-world observation.
**Do instead:** Paper mode is *the same brain code* pointed at a stub `hands`. The only difference is what the ZMQ PUSH socket is connected to. Backtest mode is the same brain code with `BacktestReplayEngine` replacing MarketDataLoop and a stub bus. One `DecisionEngine`. Three entrypoints.

### Anti-pattern 7: Using WebSocket fill events as the only fill-detection channel

**What people do:** Subscribe to the public Socket.IO channel, trust it.
**Why it's wrong:** The public Boros WS (`orderbook:{marketId}:full:update`) broadcasts aggregate book state, not per-account fills. A fill of our specific order is only visible by diffing our order state. If we rely solely on `orderbook:...:update` we'll detect "a fill happened at our tick" but may miss whether it was *our* order filled. False negatives on fill-detection = pre-signed cancel doesn't fire = we hold an IRS position we didn't want.
**Do instead:** Belt-and-suspenders. The public Socket.IO feed gives us the fast signal (book delta within 100 ms). At the same time, 1 Hz REST poll of `/v2/accounts/all-limit-orders` diffs our order state definitively. Any order that disappears or has its `remainingSize` drop is a fill (or a purge — distinguish via the endpoint's status field). This is MEDIUM confidence — verify the exact event surface with Pendle Discord in Phase 0 and update the wiki.

### Anti-pattern 8: Inflating the diagram until it's unmaintainable

**What people do:** Add every class, every function, every private method to `architecture.yml`. 1,500 nodes. Nobody reads it.
**Why it's wrong:** Defeats Protocol 2's purpose — the diagram should be readable in one glance. Too much detail = operator stops consulting it before changes.
**Do instead:** Node granularity = module, public function, CLI command, long-lived task, external dependency, named config knob. **Not** private helpers, not every data-class field. The lint tool enforces the whitelist — private helpers not allowed in the graph. If a helper is important enough to graph, it should be public.

---

## 10. Integration points — external services

| Service | Integration | Process | Rate limits / gotchas |
|---|---|---|---|
| Boros REST (`api.boros.finance/open-api/v1/`) | `httpx` (Python, reads) + `@pendle/sdk-boros` (TS, writes) | brain for reads, hands for writes | Per PROJECT.md, no hard rate limit documented; self-impose 1 Hz on account endpoints, 0.2 Hz on `/markets` |
| Boros Send-Txs-Bot (`api.boros.finance/send-txs-bot/v2/`) | `@pendle/sdk-boros` Exchange | hands only | Agent-wallet scoped; gas balance must be monitored; use `/accounts/gas-balance` in MarketDataLoop |
| Boros WebSocket (`wss://secrettune.io/pendle-dapp-v3`, Socket.IO) | `socket.io-client` | hands only | Reconnection required; channel is public book+trades, not per-account fills (see Anti-pattern 7) |
| Arbitrum RPC (`arb1.arbitrum.io/rpc`) | `web3.py` (Python) + `viem` (TS, for Merkle claim) | brain reads fIndexOracle, hands dispatches Merkle claim tx | Consider operator-owned RPC (e.g., Alchemy free tier) for reliability; public Arbitrum RPC has bursty rate limiting |
| MultiTokenMerkleDistributor contract | `viem` direct call | hands only | Claim once per epoch; uses root wallet signed manually (not Send-Txs-Bot) — this is explicit operator action, not bot autonomy |
| Historical data (`historical-data.boros.finance`) | HTTPS download, offline | data pipeline (not runtime) | Used only for backtest/screening — not in live path |

### Internal boundaries

| Boundary | Communication | Format | Notes |
|---|---|---|---|
| `brain ↔ hands` commands | ZMQ PUSH/PULL on `ipc:///tmp/boros.cmd` | Pydantic/Zod-validated JSON, mirrored schemas | Priority queue: 9=KILL preempts |
| `hands → brain` events | ZMQ PUB/SUB on `ipc:///tmp/boros.events` | JSON with run_id stamped | brain aggregates all events to unified NDJSON log |
| `brain module ↔ brain module` | Direct async function call | Pydantic dataclass | FillModel, LossModel, RewardShareModel are pure functions called by DecisionEngine in-process |
| `hands module ↔ hands module` | Direct function call | TypeScript interfaces | OrderExecutor writes PreSignedCancelCache; WsFillListener reads it |
| brain → SQLite | `sqlite3` std lib + `alembic` for migrations | Typed rows (SQL schema is source of truth) | Single-writer per table |
| hands → SQLite | `better-sqlite3` (sync API, same file, WAL mode) | Typed rows | Single-writer per table |
| logs audit path | NDJSON append-only | One object per line, `run_id` mandatory | Read by analysis notebooks, not the runtime |

---

## 11. Scaling considerations

This is a **single-operator, single-wallet** bot by PROJECT.md constraint. "Scaling" here means **more markets**, not more users.

| Scope | Architecture adjustment |
|---|---|
| 1 market, 1 side ($100, v0.5) | Current design. 1 MarketDataLoop instance, 1 fill model, 1 `hands` process handling 2 open orders at most. Resource usage: tens of MB RAM, < 5% CPU. |
| 2–4 markets (v1.0 shortlist) | Single `brain` process with market-per-task (asyncio tasks). Still one `hands` process — SDK is market-agnostic per call. `PreSignedCancelCache` keyed by `(marketId, orderId)`. Per-market config files stay separate. |
| 4+ markets | Still a single pair of processes. Bottleneck is REST polling — solved by increasing poll interval for less-active markets. WebSocket subscriptions scale freely. |
| "Sharding" (not applicable) | A multi-wallet or multi-user variant is explicitly **out of scope** per PROJECT.md. If it ever came up, the sharding unit is a full bot instance per wallet, each with its own `brain` + `hands` + SQLite. Do not share state across wallets. |

### First bottlenecks

1. **REST polling rate on `/markets` and `/v2/accounts/all-limit-orders`** — at ~5 markets polled every 5 s, 120 REST calls/min. Fix: batch where endpoint supports it, stagger polls, subscribe to WS for order book so REST is only used for account state.
2. **SQLite WAL growth** — NDJSON logs are the real audit trail; SQLite is live state. Keep SQLite trimmed (delete tick_data older than 24 h; archive to parquet nightly).
3. **Python decision latency on 4+ markets** — NHPP is fast (< 5 ms per market). Hawkes with full self-excitation history is slower (~50 ms). Budget is 1 Hz / 1000 ms per cycle; 4 × 50 ms = 200 ms, comfortable. If v1.0 Hawkes gets slow, cache the self-excitation integral between ticks.

Gas/tx throughput is not a bottleneck at this scale — Arbitrum confirms in ~250 ms and we submit < 10 tx/hour steady-state.

---

## 12. Confidence & gaps

| Claim | Confidence | Basis |
|---|---|---|
| Python for brains, TS for hands split is correct | HIGH | Direct constraint from PROJECT.md; Pendle SDK is TS-only (verified via Context7 `/pendle-finance/sdk-boros-public`); quant stack is Python-only |
| Split-brain over ZMQ (vs subprocess, vs Redis) | HIGH | ZMQ IPC sub-ms latency verified via PyZMQ docs (Context7 `/zeromq/pyzmq`); fork+exec on macOS is ~200–500 ms, publicly measured |
| SQLite for shared state, DuckDB read-only for analytics | HIGH | Well-established pattern; DuckDB's `sqlite_scanner` is official; WAL concurrency is documented |
| Pre-signed cancel calldata must live in TS (colocated with WS listener) | HIGH | Latency math: crossing IPC per fill adds 1+ ms but more importantly requires synchronous brain response, which at 1 Hz cycle isn't guaranteed. Keeping it local in TS removes that dependency entirely |
| Public Boros WebSocket does NOT surface per-account fills | MEDIUM | Context7 SDK docs only describe `orderbook:`, `market-trade:`, `statistics:` channels. The consolidated plan says "WebSocket-driven fill detection" but does not show the channel. **Phase 0 action:** confirm with Pendle Discord whether a private channel exists. If yes, use it as primary and REST diff as fallback. If no, REST diff at 1 Hz is the primary path. |
| `E_liq_per_epoch` shifts dynamically and must be polled | HIGH | Consolidated plan explicit; cap-saturation anchor (957% APR Short side) is the concrete example |
| Overmind/Procfile launcher is right for v0.5 | MEDIUM | Defensible for macOS-local; `launchd` would be appropriate if v1.0 ever wants "always on," but v0.5's "operator at the keyboard" model fits Procfile |
| Hot-reload of knobs is a bad idea | HIGH | Directly follows from PROJECT.md Protocol 3 — "No silent drift" |

### Open questions surfaced by this research

1. **Per-account WebSocket channel existence.** Resolve in Phase 0 alongside cancel-behavior. Doesn't block this architecture — design is sound either way — but changes `WsFillListener` implementation detail.
2. **ZMQ message schema codegen.** v0.5 manually mirrors Pydantic ↔ Zod. Is that tolerable? It's ~20 message types. Yes, but add a schema-diff unit test that catches accidental drift (`pytest` test in brain parses the Zod file, `vitest` test in hands parses the Pydantic JSON schema).
3. **Which SQLite migrations library.** `alembic` is the Python-native choice; TS writes via `better-sqlite3` which doesn't manage migrations. Python owns the schema; TS is a consumer. OK.
4. **Crash recovery test protocol.** Before Phase 10 live, write a test that kills `-9` each side mid-tx and verifies order state reconciles within 30 s. Not designed here, but should be a Phase 9 deliverable.

---

## 13. Summary for the roadmap

**Component boundaries** (what becomes code nodes in `docs/architecture.yml`):
- 2 processes (`brain` Python, `hands` TS)
- 16 internal modules listed in §2, plus external deps (Boros REST, WS, Send-Txs-Bot, Arbitrum RPC, Merkle distributor)
- 2 cross-cutting responsibilities with named owners: **CircuitBreakers owns kill authority**, **RunManifest owns knob-tree provenance**

**Python/TS boundary** (single decision, not tradeoff matrix):
- **Split-brain over ZMQ IPC, Python drives the clock, TS owns the chain-touching hot path, SQLite is the shared state spine.**

**State ownership** (§5 map, 11 rows, no unowned shared state)

**Build order implication** (one change to consolidated plan):
- **Expand Phase 1 to include SQLite schema, RUN_MANIFEST writer, StructuredLogger, ZMQ bus skeleton, wiki seed, and `docs/ARCHITECTURE.md` seed *before* any model code.** Phases 2–10 otherwise unchanged.

**Critical hot-path invariant:**
- Flow 2 (WS fill → pre-signed cancel) is TS-only. No Python hop. Enforced by putting `PreSignedCancelCache` inside `hands` process memory and `WsFillListener` in the same process.

**Critical fail-safe invariant:**
- `CircuitBreakers` in `brain` has exclusive authority for `EMERGENCY_CLOSE`, `KILL`, `CANCEL_ALL`. `CommandListener` in `hands` also honors a watchdog: if it loses `brain` heartbeat for 15 s, it cancels all on its own authority using cached calldata. Bot fails closed.

**Mermaid diagram** (§1): first-pass seed for `docs/ARCHITECTURE.md`. Phase 1 turns this into the living diagram with matching `docs/architecture.yml`.

---

## 14. Sources

- PROJECT.md — `/Users/macbookair/Documents/project/test/rerun7/boros/.planning/PROJECT.md` (Engineering Protocols 1–3, constraints, tech stack decision)
- boros_consolidated_plan.md — phase sequencing, EV rule, per-market model selection, circuit-breaker triggers, reward-share cap binding
- boros_bot_guide.md §Bot Architecture (L423-470) — the original component sketch this architecture critiques and replaces
- `../LLM Wiki/workspaces/boros/wiki/index.md` — empty, but seeding plan consulted per Protocol 1
- Context7: `/pendle-finance/sdk-boros-public` — confirmed `exchange.cancelOrders`, `bulkCancelOrders`, `/v3/calldata/cancel-order`, Socket.IO endpoints and channel names
- Context7: `/zeromq/pyzmq` — confirmed REQ/REP + PUB/SUB + asyncio support, IPC transport for localhost sub-ms latency
- macOS `fork+exec` latency (~200–500 ms on M-series laptops) — operational knowledge; drives rejection of subprocess-per-action anti-pattern

---

## 15. Wiki write-back obligations (Protocol 1)

This research file seeds the following wiki pages to be created in Phase 1 under `workspaces/boros/wiki/`:

- `[[Architecture decision — split brain Python TS]]` — Section 4's rationale, Status: `Current`
- `[[ZMQ message schema]]` — command/event taxonomy, Status: `Current`
- `[[State ownership map]]` — §5 table, Status: `Current`
- `[[CircuitBreakers kill authority]]` — §9 Anti-pattern 5 enforcement, Status: `Current`
- `[[Pre-signed cancel cache]]` — Flow 2 criticality, Status: `Current`
- `[[WS fill detection — belt and suspenders]]` — §9 Anti-pattern 7, Status: `Current — pending Phase 0 Discord confirmation`
- `[[v0.5 deployment — Overmind Procfile]]` — §6, Status: `Current`

---

*Architecture research for: Boros reward-farming bot, local Python+TS split-brain design*
*Researched: 2026-04-23*
