# Stack Research — Boros Reward-Farming Bot

**Domain:** Personal DeFi market-making bot (Pendle Boros IRS on Arbitrum, passive Limit-Order-Liquidity-Rewards farming)
**Researched:** 2026-04-23
**Overall confidence:** HIGH on tooling choices (widely documented, current versions verified on PyPI/npm). MEDIUM on Boros-SDK edges (WebSocket feed presence, exact v1.1.44 surface) — some answers need Phase-0 empirical verification against the live SDK.
**Wiki check (Protocol #1):** `../LLM Wiki/workspaces/boros/wiki/index.md` read; zero pages filed yet (wiki was seeded empty 2026-04-23). No prior stack findings exist. Every claim here must be written back to the wiki as pages when Phase 0/1 executes (candidate pages enumerated at end of doc).

---

## TL;DR — the final picks

**Python side:** CPython 3.12 · `tick` 0.8.0.1 (Hawkes + NHPP) · hand-rolled OU MLE on `scipy.optimize` · `nautilus_trader` 1.225 for the event-driven backtest · `pydantic` 2.13 for the knob-tree config · `structlog` 25.5 for JSON logs · `polars` 1.40 for NDJSON bulk + `duckdb` 1.5 for ad-hoc SQL · `web3.py` 7.15 (async) for on-chain reads.

**TypeScript side:** Node.js **24 LTS** (not 22 — 22 exits active support April 2026) · `@pendle/sdk-boros` 1.1.44 · **viem** 2.47 (match what the SDK already pins) · native `ws` 8.20 for the Boros WebSocket · `tsx` 4.21 for dev, `tsc` to `dist/` for long-running bot.

**IPC boundary:** **stdin/stdout JSON Lines** between a single long-running TS process (the "executor") and a Python "brain" subprocess it spawns. No HTTP, no ZeroMQ, no shared files. Single machine, single operator, one cold-start per run — this is the minimum-dependency choice.

**Supervision:** `launchd` LaunchAgent with a plist under `~/Library/LaunchAgents/`. Not `pm2` (Node-specific, adds an 83 MB daemon to supervise a 150 MB bot — not worth it for a personal 1-process setup).

**Secrets:** `.env` via `python-dotenv` + `dotenvx` CLI wrapper for at-rest encryption. The root wallet key never sees the bot process; the agent-wallet key is stored encrypted and decrypted at startup only.

**Log inspection:** `jq` as the primary, `lnav` as the secondary. Every line carries `run_id`, so `jq 'select(.run_id=="01HXX…")'` is the base operation.

---

## Python Side

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **CPython** | 3.12.x | Language runtime | All target libs (tick 0.8, polars 1.40, nautilus 1.225, pydantic 2.13) publish wheels for 3.12. 3.13 works too but NumPy-heavy wheels are more settled on 3.12 at the April-2026 cutover. Don't use 3.11 — `tick` 0.8.0.1 requires `>=3.11` but the wheels' best path is 3.12; don't use 3.14 — too new, some scientific wheels lag. |
| **tick** | 0.8.0.1 | Hawkes / non-homogeneous Poisson arrival-process fitting | Actively maintained (0.8.0 and 0.8.0.1 released Apr 18 and Apr 20, 2026 — 3 days before this research) with a full rewrite to scikit-build-core + pybind11. Publishes CPython 3.11/3.12/3.13 wheels. This library is the reason the plan's per-market model selection (Hawkes for CV>1.5, NHPP for 0.7≤CV≤1.5) is a 1-week implementation and not a 1-month research project. It covers `HawkesExpKern`, `HawkesSumExpKern`, and `HawkesEM` plus marked/non-homogeneous Poisson. High confidence — verified on PyPI on the day of this research. |
| **scipy** | 1.14.x | OU MLE on the basis, minimization backbone | `scipy.optimize.minimize` with `method='L-BFGS-B'` is the right tool for hand-rolled OU parameter estimation on `B(t) = Implied − Underlying` (plan Phase 3a). There is no production-quality OU library on PyPI that is worth adopting — the `ornstein-uhlenbeck` package on GitHub (felix-clark) is a 300-line reference, not a dependency, and `statsmodels` does not ship an OU MLE (confirmed via their issue #7883, still open 2026). The closed-form OU log-likelihood on discrete samples is 15 lines of code; write it, do Yu (2012) / Tang-Chen bias correction by hand, and test it against a simulated OU trajectory. Do not take a library dependency for what is essentially a textbook formula. |
| **numpy** | 2.1.x | Array math | Required transitively by tick, scipy, polars; pin to 2.1+ because 2.0 introduced ABI breaks for C-extensions and all of our deps have caught up. |
| **pandas** | 2.2.x | Compat shim only | Some libs emit pandas objects. Do NOT use pandas as the primary data layer — polars is faster, has a proper query optimizer, and its NDJSON reader `pl.read_ndjson` streams cleanly. |
| **polars** | 1.40.1 | Primary DataFrame layer; NDJSON ingestion | Released 2026-04-22. Core reason: `pl.scan_ndjson()` can lazy-stream the `market-trades/` NDJSON files (~72k rows/market but compressing to millions across the shortlist) with column pruning and predicate pushdown. On the benchmarks in the 2026 comparison, polars beats pandas 5–10× on filter/aggregate for our shape. The plan verification doc already shows we handle size-as-wei-string conversions; polars `cast()` + `.map_elements(int)` handles this cleanly. |
| **duckdb** | 1.5.0 | Ad-hoc SQL over the NDJSON / parquet cache | Released 2026-03-09. Not a replacement for polars; a complement. The notebook workflow wants "give me all trades between T1 and T2 where size > X grouped by hour" as one SQL string. DuckDB's `read_ndjson_auto()` handles the Boros schema directly, no ETL step. Keep it for the market screener (Phase 1b) and the backtest cross-checks; don't try to use it as the runtime data path. |
| **pydantic** | 2.13.3 | Config schema = single source of truth for knobs | Released 2026-04-20. Engineering Protocol #3 mandates that every config knob appears in `RUN_MANIFEST`. The authoritative way to enforce this is one nested Pydantic `BaseModel` (e.g. `StrategyConfig(markets: list[MarketConfig], fill_model: FillModelConfig, decision: DecisionConfig, ...)`). `model_dump(mode='json')` produces the exact manifest payload. Use `model_config = ConfigDict(extra='forbid', frozen=True)` — any unknown key is a bug, not a feature. |
| **structlog** | 25.5.0 | JSON structured logging with context-bound `run_id` | Released 2025-10-27. `structlog.contextvars.bind_contextvars(run_id=...)` propagates `run_id` across every log call including async tasks and thread pools — critical for Engineering Protocol #3 (every line carries `run_id`). Use `structlog.processors.JSONRenderer()` as the final processor; one line = one JSON object = one `jq` match. Don't use stdlib `logging` alone + `python-json-logger` — you'd have to hand-wire contextvars and it's already done for you in structlog. |
| **web3.py** | 7.15.0 | Arbitrum on-chain reads (fIndex oracle, Merkle distributor) | Released 2026-04-02. Use `AsyncWeb3` + `WebSocketProvider` or `AsyncHTTPProvider` (v7 introduced the graduated WebSocketProvider). The bot's on-chain reads are cheap (`getLatestFIndex()`, `latestAnnualizedRate()`, Merkle claim polling) and don't justify a second library. Don't use `eth-account` as the primary lib — it's a dependency of web3.py anyway, not an alternative; you need it only for raw signing, which we delegate to TS (viem) for trading. **One explicit rule:** all block reads must use `block_identifier='latest'` and never trust a returned block number without sanity check — Arbitrum block time is ~250ms and stale reads are a real risk. |
| **nautilus_trader** | 1.225.0 | Event-driven backtest engine | Released 2026-04-06. The plan's Phase 7 backtest requirements (nanosecond-resolution event replay, custom L2 order book, queue-position tracking, AMM merged book, cancel-latency sweep) are exactly what Nautilus was designed for. It's Rust-native under the hood, deterministic, and ships a custom-adapter SDK for exactly the situation we have: we will NOT use a live venue, only historical replay of our own NDJSON → Nautilus parquet. See "Alternative backtest frameworks considered" below for why nothing else fits. |

### Supporting Python Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `orjson` | 3.10.x | Faster JSON than stdlib for the hot log path | Drop-in for structlog's JSON renderer. ~5× faster serialization; matters because every decision cycle emits several log records. |
| `httpx` | 0.27.x | Async REST client for Boros REST endpoints | Python side uses Boros REST for market metadata polls (`GET /markets`, `GET /v2/accounts/all-limit-orders` for the competition tracker) — not for order placement (that's the TS side via the SDK). `httpx` has proper async, retries, and HTTP/2. Don't use `requests` — blocking and decades-old architecture. |
| `python-ulid` | 3.0.x | `run_id` generation (ULID, not UUID) | Engineering Protocol #3 requires `run_id`. ULIDs sort lexicographically by time, so `ls -la logs/` is already in chronological order and directory listing matches log order. |
| `python-dotenv` | 1.0.x | Read `.env` at startup | For non-secret config (RPC URL, market shortlist, Discord webhook). Secret management layer sits on top (see "Secrets" below). |
| `pytest` | 8.x | Unit + integration tests | Standard. Pair with `pytest-asyncio` for the async web3.py paths and `hypothesis` for fuzzing the tick↔APR conversion math (easy to introduce off-by-one bugs). |
| `hypothesis` | 6.x | Property-based testing of numeric code | The `apr_to_tick` / `tick_to_apr` round-trip and the OU log-likelihood are exactly the kind of numeric code that Hypothesis catches bugs in that unit tests miss. |
| `rich` | 13.x | CLI output for ops commands | Only for CLI commands the operator runs manually (`boros-bot status`, `boros-bot dry-run`). Do NOT use rich inside the bot's main event loop — the log format must be JSON (Protocol #3). |
| `jupyterlab` | 4.x | Notebook workflow for Phase 1 screening, Phase 3 OU fitting, calibration plots | Per PROJECT.md, "Jupyter-friendly workflow" is explicit in the constraints. Notebooks only read logs / parquet caches — they don't touch the bot's live state. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` (astral-sh) | Python packaging + venv + lockfile | The 2026 default for new Python projects. Faster than poetry/pip/pip-tools, produces a lockfile (`uv.lock`), handles the full venv + requirement-resolution lifecycle. Run everything through `uv run …`. |
| `ruff` 0.7+ | Linter + formatter | Replaces flake8/isort/black/pyupgrade in one tool. Set `select = ["ALL"]`, disable the rules you don't want. Required in pre-commit hook. |
| `mypy` 1.13+ | Type checker, strict mode | Catches manifest-schema drift against the Pydantic model. Run in CI + pre-commit. |
| `pre-commit` 4.x | Git hook runner | Host the architecture-manifest lint (`docs/architecture.yml` check — Protocol #2) and `ruff`/`mypy` here. |

---

## TypeScript Side

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Node.js** | **24 LTS** (24.15.x as of Apr 2026) | JS runtime | **Not 22.** Node 22 LTS exits active support April 2026 — it goes into maintenance-only mode the same month this research is being done. Node 24 is LTS since Oct 2025, with active support through Oct 2027 and maintenance to Apr 2028. For a bot that should run for months+ without a runtime upgrade, 24 is the correct pick. Node 24 also ships native TypeScript stripping (`--experimental-strip-types`) but we don't rely on it — we build to JS for production (see `tsc` below). |
| **@pendle/sdk-boros** | 1.1.44 | Pendle Boros trading SDK | Latest release on npm (published ~13h before this research; that's the live release cadence). Exposes `Exchange` class with `placeOrder`, `bulkPlaceOrdersV5`, `cancelOrders`, `approveAgent`, `getCollaterals`, `deposit`/`withdraw`. Under the hood it pulls in `@pendle/boros-core` 1.0.4, `@pendle/boros-offchain-math` 1.0.6, and **pins viem 2.44.4 directly** — this is the decisive reason viem wins on the TS side. **Known gotchas surfaced from the repo:** (a) agent approval is valid 7 days — a 7-day-interval scheduler is a Phase 8 requirement, not optional; (b) the `Exchange` constructor takes a viem `WalletClient`, RPC URLs, and an `Agent` — the `Agent` object must be constructed and approved before any `placeOrder` succeeds; (c) no WebSocket helper in the SDK itself — the SDK is REST-only (confirmed by inspection of `boros-api-examples`), so fill-detection WebSocket is a hand-rolled `ws` client against the documented `/ws` URL (the Boros docs reference a WS feed but the exact URL needs Phase-0 verification against the live docs). |
| **viem** | 2.47.12 | EVM client (signing, calldata, tx construction) | Released ~2 days before this research. **Choose viem over ethers v6 for three reasons, any one of which would be decisive:** (1) the Pendle SDK is already pinned to viem 2.44.4 — using ethers would mean carrying both libraries, duplicating wallet state, and reconciling two code paths; (2) pre-signed calldata generation is trivial and cheap in viem — `walletClient.signTransaction({ … })` returns the signed raw tx, ready to hold in memory and fire through `publicClient.sendRawTransaction()` on fill-detection (this is the Phase 8 "pre-sign cancel calldata at placement time" critical-path optimization — Plan §8); (3) bundle size (27 KB vs 130 KB) matters not for deployment but for startup time and memory footprint of the long-running bot. One minor caveat: the SDK pins `viem: 2.44.4` (no caret) which means we align on 2.44.x and let the SDK dictate the minor. Upgrade only when the SDK does. |
| **ws** | 8.20.0 | WebSocket client for Boros fill/account feeds | Released 25 days before this research. The canonical Node WebSocket lib. Use it directly; do NOT add `reconnecting-websocket` or `ws-reconnect` — those wrappers hide connection-state transitions we need to see (a silent reconnect that misses a fill event is how you lose real money). Instead: hand-roll a 30-line reconnect loop with exponential backoff, explicit `open`/`close`/`error` logging (stamped with `run_id`), and heartbeat via `ws.ping()` every 20s with a 10s pong timeout. Browser-style `WebSocket` (native in Node 22+) is tempting but lacks the per-frame hooks needed for heartbeat and backpressure. |
| **tsx** | 4.21.0 | TypeScript runtime for dev + scripts | Development loop only (`tsx watch src/bot.ts`). ~25× faster startup than `ts-node`. No type-checking (we use `tsc --noEmit` for that). Do NOT run the production bot under `tsx` — for a multi-day process, an esbuild-transpiled `dist/` directory run under bare `node` has fewer moving parts. |
| **typescript** | 5.6.x | Compiler (type-check only) + production build | `tsc --noEmit` for type-check (lint gate). `tsc` to `dist/` for the production bundle loaded by `node`. Don't use `tsup` / `esbuild` bundler — there's no reason to bundle a Node-side bot into a single file; let Node's module resolver do its job. |
| **ethers** | *— not used —* | | Explicitly rejected. See "What NOT to use" below for the full reasoning. |

### Supporting TypeScript Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `zod` | 3.23.x | Runtime schema validation of incoming WebSocket / REST payloads | Pendle Boros REST/WS schemas can change; `zod` parses every payload into a validated typed object or throws. Put a zod validator on every external boundary. Do NOT trust TypeScript types alone for external data. |
| `pino` | 9.x | JSON logging (mirror of Python structlog) | Same `run_id`-carrying contract. `pino` has ~1 µs per log, emits NDJSON natively. Wire `pino.child({ run_id })` at bot start. Do NOT use `winston` — heavier, slower, less ergonomic for structured output. |
| `dotenv` | 16.x | Read `.env` at startup | Same purpose as python-dotenv on the other side; shared `.env` file. |
| `ulid` | 2.3.x | `run_id` generation matching the Python side | Same ULID library semantics on both sides so IDs collide-check consistently if both processes mint them. |
| `p-queue` | 8.x | Order-placement rate limiter | Boros REST has rate limits (check docs Phase 0); `p-queue` serializes bursts without drops. |
| `abitype` | 1.x | Compile-time ABI typing | Already a peer of viem; we get it for free. Useful when we hand-craft a contract call to the Merkle distributor. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pnpm` | Package manager | Faster than npm, produces a proper lockfile, saves disk via the store. The Pendle SDK examples use Yarn but pnpm is the 2026 default. |
| `@biomejs/biome` | Lint + format (TS side) | Faster than ESLint + Prettier. Optional — ESLint 9 (flat config) is fine too. |
| `tsc --noEmit` in CI | Type-check gate | |
| `vitest` 2.x | Unit + integration tests | Faster than `jest`, ESM-native, TypeScript-first. The default 2026 pick for TS test runners. |

---

## Cross-Cutting Layer

### IPC Boundary: Python ↔ TypeScript — **stdin/stdout JSON Lines**

| Choice | Decision |
|--------|----------|
| **stdin/stdout JSON Lines** (chosen) | TS is the parent process. It spawns Python as `child_process.spawn('uv', ['run', 'python', '-m', 'boros.brain'])` on startup. TS writes decision requests as `{"req_id": "…", "market": "…", "book_snapshot": {…}, "rate": …}\n`. Python reads line-by-line, computes the EV, writes back `{"req_id": "…", "action": "hold"|"cancel"|"replace", "reasoning": {…}}\n`. Python must `sys.stdout.flush()` after every line; TS's `readline` on the child's stdout handles framing. |
| Why this, not HTTP localhost | (a) One less port-bind. No "is something already listening on 7123?" failure mode. (b) No TCP stack / no serialization overhead. (c) The child process lifetime is coupled to the parent's — when the bot is killed, the Python brain dies too, no orphan process to hunt. (d) Zero auth: the pipe is only readable by the parent process. HTTP would need loopback-only binding + some token. |
| Why not ZeroMQ | Overkill. ZeroMQ excels at many-publisher / many-subscriber / complex patterns. We have one parent ↔ one child, one request-reply pattern. Adding `pyzmq` + `zeromq.js` is two deps and an extra `ipc://` socket to manage for no capability gain. ZeroMQ's `ipc://` also has Windows limitations (not relevant for local macOS, but the complexity tax is). |
| Why not shared filesystem state | Race conditions on writes, `fsync` cost, plus you then need a watcher or a poll loop — you've reinvented IPC poorly. |
| Why not bidirectional WebSocket | Same overhead as HTTP plus framing; WebSockets make sense only when you have multiple simultaneous subscribers/publishers. |
| **Throughput reality check** | Decision cycle runs ~1 Hz (every few seconds, per plan). Serializing one JSON object per cycle is sub-millisecond. JSON Lines over a pipe is faster than any network loop by an order of magnitude for this workload. |
| **Lifecycle rules** | (1) On Python side crash, TS logs the crash, kills any live orders via a cold-wallet-signed fallback? No — policy is: TS cancels all orders it has pre-signed calldata for, then exits. Supervisor restarts both. (2) Python sends a `{"type": "ready"}\n` line at startup; TS waits for this before submitting the first decision request. (3) Heartbeat every 5s: TS sends `{"type": "ping"}\n`, Python replies `{"type": "pong"}\n`. Missed pong → same as crash. |

### Secrets: Hot Agent Wallet Key

| Layer | Choice | Rationale |
|-------|--------|-----------|
| At-rest encryption | `dotenvx` CLI wrapper (AES-256 with Secp256k1-protected key) | The operator runs `dotenvx run -- node dist/bot.js` (or similar); the `.env.vault` file on disk is encrypted, the private-key material for decryption lives in `~/.dotenvx/` (or an env var the operator pastes once per session). Defensible against "someone took a copy of my repo" but NOT against a local-machine compromise — which is correct-scope for a $100 starting-capital personal bot. |
| Scope | Agent wallet only | The root wallet key is never loaded into any bot process. It's in the operator's hardware wallet / encrypted keystore file; it signs deposits/withdrawals/agent-approvals manually. |
| Rotation | Manual, Phase-10 scale-up gate | Current scale ($100) does not warrant automated rotation. If/when live scales, HashiCorp Vault / AWS KMS become appropriate. Noted as a v2 concern. |
| What NOT to do | Don't commit `.env` (git-ignored), don't use plain `python-dotenv` / `dotenv` for the wallet key (plaintext on disk = auditable but unprotected — OK for RPC URLs, not for trading keys). Don't use the `keyring` Python package on macOS — Keychain access prompts during long-running operation is the opposite of what we want. |

### Process Supervision (macOS)

| Choice | Decision |
|--------|----------|
| **launchd LaunchAgent** (chosen) | One `com.boros-bot.plist` in `~/Library/LaunchAgents/`. Keys: `RunAtLoad=true`, `KeepAlive=<SuccessfulExit=false>`, `ThrottleInterval=30`, `StandardOutPath` / `StandardErrorPath` → log files, `EnvironmentVariables` for the minimal non-secret env (secrets loaded by dotenvx at process start). `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.boros-bot.plist` to activate. Native to macOS, zero extra dependencies, survives laptop reboots. |
| Why not pm2 | `pm2` is a Node-specific process manager that adds an 83 MB daemon to supervise our ~150 MB bot. It's the right tool for "one machine hosting 10 Node apps." We have one bot on a personal laptop. launchd does this with a 15-line plist and no running daemon we didn't put there. |
| Why not supervisord | Pythonic, well-designed, but also a daemon we'd have to manage. launchd is already running. |
| Why not `nohup &` + a script | Doesn't survive laptop reboot without manual intervention. launchd does. |
| What NOT to do | Don't cron the bot. Don't write your own supervisor. Don't rely on terminal-open process lifetime — if the operator's screen locks / terminal dies, the bot should not. |

### Structured-Log Inspection

| Tool | Usage | Notes |
|------|-------|-------|
| **`jq`** (primary) | `cat logs/2026-04-23.ndjson \| jq 'select(.run_id=="01HXX…")'` — base op. Add filters (`.level=="error"`, `.market=="…"`) inline. | Every operator already has it. Works on NDJSON out of the box. |
| **`lnav`** (secondary) | Interactive deep-dive (SQL over NDJSON, highlighting, time-based navigation): `lnav logs/2026-04-23.ndjson`. | Use when a bug is suspected and you want to pivot across fields. lnav 0.14+ auto-detects JSON-line format; if not, a format file is 20 lines. |
| **Notebook analysis** | `polars.read_ndjson("logs/*.ndjson").filter(pl.col("run_id")=="…")` → DataFrame. | For calibration plots and P&L reconciliation, which the plan's Phase 9 paper-trading gate requires. |
| Why not `logdy` | A web UI for logs. Real-time dashboard fits a team workflow. We are one operator with `jq`. Extra surface, no gain. |
| Why not cloud log services (Datadog, etc.) | Out-of-scope for a local-only $100-collateral bot. Re-evaluate at scale-up. |

---

## Installation

```bash
# ----- Python side (single uv project) -----
# uv sync will respect pyproject.toml's [project] dependencies
uv init boros-brain --python 3.12
cd boros-brain
uv add tick==0.8.0.1
uv add scipy numpy pandas
uv add polars==1.40.1 duckdb==1.5.0
uv add pydantic==2.13.3
uv add structlog==25.5.0 orjson
uv add web3==7.15.0 httpx python-ulid python-dotenv
uv add nautilus_trader==1.225.0
uv add --dev pytest pytest-asyncio hypothesis ruff mypy pre-commit jupyterlab

# ----- TypeScript side -----
pnpm init
pnpm add @pendle/sdk-boros@1.1.44
pnpm add viem@2.44.4         # match the SDK's exact pin
pnpm add ws@8.20.0
pnpm add zod pino dotenv ulid p-queue
pnpm add -D typescript@5.6 tsx@4.21 vitest@2 @biomejs/biome

# ----- Secrets wrapper -----
# one-time: npm i -g @dotenvx/dotenvx
# then: dotenvx encrypt   (creates .env.vault)
# run the bot via: dotenvx run -- node dist/bot.js

# ----- Supervisor -----
# Phase 8 work: hand-roll ~/Library/LaunchAgents/com.boros-bot.plist
# launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.boros-bot.plist
```

---

## Alternatives Considered (per layer)

### Hawkes / arrival-process library

| Recommended | Alternative | When / Why the alternative would win |
|-------------|-------------|---------------------------------------|
| **`tick` 0.8.0.1** | hand-rolled MLE on scipy | Only if tick's wheel doesn't build on our target Python version (it does, 3.11–3.13 confirmed April 2026) or if we need a very custom self-excitation kernel not in the exp-kernel family. For the plan's `exp` / `sumexp` kernels, tick is strictly the better tool. |
| `tick` | `pyhawkes` (slinderman) | `pyhawkes` targets Bayesian inference over network-structured Hawkes. Neat, but we don't need latent networks — we need one fast MLE fit per market. Wrong shape. |
| `tick` | `hawkeslib` (canerturkmen) | **Explicitly deprecated by its author** — the README says "I'm no longer able to develop/support this library, check out tick or pyhawkes." Don't pick up an abandoned dep for the core model of a strategy. |
| `tick` | `py-hawkes` (ragoragino) | Niche, less documentation, smaller community. Might work, but the support cost is higher. |

### OU parameter estimation

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|---------------------------------------|
| **Hand-rolled `scipy.optimize.minimize` + closed-form OU log-likelihood + Tang-Chen bias correction** (~40 lines) | `ornstein-uhlenbeck` (felix-clark) | It's a reference implementation, not a maintained dependency. Copy the formulas into our code, test against it, don't depend on it. |
| hand-rolled | `statsmodels` OU | Doesn't exist — confirmed via open issue #7883 (2021, still open in 2026). |
| hand-rolled | Bayesian via `pymc` or `pyro` | Overkill for a stationary 2-parameter process on 14-day rolling windows. Bayesian OU would be correct for a v2 strategy that propagates parameter uncertainty into the EV equation; we don't need it at v0.5. |

### Event-driven backtest

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|---------------------------------------|
| **`nautilus_trader` 1.225** | `vectorbtpro` | Vectorbt is vectorized, not event-driven. You can't model queue position and AMM consumption in a vectorized sweep of prices — the whole point of the plan's Phase 7 is that naive vectorized backtest overstates P&L. Hard no. |
| `nautilus_trader` | `zipline` | Equities-shaped, single daily-bar orientation, not maintained in 2026 in the same way. No custom-venue CLOB. Wrong tool. |
| `nautilus_trader` | `backtrader` | Old, single-threaded, poor documentation. Nautilus superseded it. |
| `nautilus_trader` | `bt` | Portfolio-rebalancing framework. Not an event-driven L2-aware engine. |
| `nautilus_trader` | **hand-rolled** | A real alternative. A bespoke replay engine is ~1500 LoC if we're disciplined; Nautilus's adapter surface is ~400 LoC. Hand-rolled wins only if we find Nautilus's custom-venue adapter fights our AMM-merged-book replay. **Default to Nautilus; fall back to hand-rolled if Phase 7 day-1 feels like we're working around the framework.** This is an explicit callout in the "what might fail" section — budget 2 days to bail out if needed. |

### IPC boundary

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|---------------------------------------|
| **stdin/stdout JSON Lines** | HTTP localhost (FastAPI/Express) | If we later need to support multiple concurrent bot processes sharing a brain, HTTP makes that trivial. We don't — one operator, one wallet pair, one bot. |
| stdin/stdout | ZeroMQ (`pyzmq` + `zeromq.js`) | If we later need pub/sub for tee'ing decisions to a logger / dashboard separate from the executor, ZeroMQ is the right tool. Phase 10 scale-up question. |
| stdin/stdout | Shared file (SQLite WAL, parquet) | Never the right pick for real-time IPC. |

### TypeScript EVM library

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|---------------------------------------|
| **viem 2.44.4** | ethers v6.16 | Never on this project. The Pendle SDK pins viem directly; using ethers means carrying two libs and reconciling two wallet-state surfaces. ethers v6 is fine for projects NOT tied to viem-based SDKs. |

### Node runtime

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|---------------------------------------|
| **Node 24 LTS** | Node 22 LTS | Only for a short-lived project shipping in April 2026 that will be mothballed in a month. We intend to run for months+. 22 exits active support April 2026. |
| Node 24 LTS | Bun | Bun is fast and compatible but has no formal LTS, ships minor versions every 2–4 weeks, and the `ws` native module we need is tested against Node, not Bun. For a multi-day bot, Node's 15-year stability track record wins. Re-evaluate for v2. |
| Node 24 LTS | Deno | Fewer ecosystem libraries supported, and the Pendle SDK is Node-targeted. Not worth the integration friction. |

### Process supervision

| Recommended | Alternative | When the alternative would win |
|-------------|-------------|---------------------------------------|
| **launchd** | pm2 | If we later run multiple Node processes (dashboard, paper-traders, etc.), pm2's ecosystem view helps. For one process, launchd wins. |
| launchd | supervisord | If we later deploy to Linux VPS, supervisord/systemd applies. For local macOS, launchd is native. |
| launchd | Docker Compose | Docker-izes our deployment at the cost of filesystem / networking complexity. Not worth it at v0.5. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pandas` as the primary data layer | 2–10× slower than polars on our ops; no query optimizer; single-threaded; memory-heavy on NDJSON | `polars` (primary) + `duckdb` (ad-hoc SQL) |
| `requests` (Python) | Blocking; no async; forces threading for concurrent I/O | `httpx` (async, HTTP/2, modern) |
| `stdlib logging` alone | Not structured by default; contextvar integration is manual; JSON output requires extra plumbing | `structlog` with `JSONRenderer` |
| `statsmodels` for OU | Doesn't have OU; issue #7883 open since 2021, still open 2026 | Hand-rolled MLE on `scipy.optimize` |
| `ethers` v6 on the TS side | Duplicates viem (which the Pendle SDK already pins); two wallet-state surfaces to reconcile; bigger bundle | `viem` — pinned to the SDK's version |
| `ts-node` | 25× slower startup than tsx; outdated; Node's own `--strip-types` or `tsx` replaces it | `tsx` for dev, `tsc` → `dist/` for prod |
| `winston` (JS logger) | Heavier, slower, less ergonomic for structured NDJSON output than pino | `pino` |
| `reconnecting-websocket` / `ws-reconnect` wrappers | Hide connection-state transitions that we NEED visibility into (silent reconnect = missed fill = lost money) | Native `ws` + hand-rolled 30-line reconnect loop with explicit state logging |
| `pm2` for a single-process personal bot | 83 MB daemon to supervise one process; native alternative is free | `launchd` with a plist |
| `cron` for bot supervision | Not a supervisor; doesn't restart on crash; no stdout/stderr capture | `launchd` (macOS) |
| `hawkeslib` | Author deprecated it | `tick` 0.8 |
| `vectorbt` / `vectorbtpro` for backtest | Vectorized; cannot model queue position or AMM consumption; price-touch-only | `nautilus_trader` |
| `zipline` / `backtrader` / `bt` | Equities-shaped, no custom CLOB venue, low recent activity | `nautilus_trader` |
| `python-dotenv` alone for the agent-wallet private key | Plaintext on disk | `dotenvx` encrypted `.env.vault` |
| `tsx` for the production long-running bot | Fine for dev, but we want fewer moving parts in a multi-day process | `tsc` → `dist/` + bare `node` |
| `keyring` / macOS Keychain for the agent key in a long-running bot | Interactive unlock prompts during operation | `dotenvx` |

---

## Stack Patterns by Variant

**If v0.5 (non-homogeneous Poisson only, one market):**
- Use **only** tick's `SimuInhomogeneousPoisson` + a hand-rolled NHPP MLE with covariates on scipy.
- Skip `nautilus_trader` entirely if the backtest is genuinely one-market, one-strategy — a 1500-LoC hand-rolled event replay may ship faster than learning Nautilus's adapter surface. **Decision point in Phase 7 day 1.**
- `duckdb` alone for data screening (Phase 1); defer `polars` if our ops fit in SQL.

**If v1.0 (per-market Hawkes/NHPP/renewal, shortlist of 2–4 markets):**
- Full stack as recommended above.
- `nautilus_trader` becomes essential — the multi-market, multi-strategy, calibration-sweep workload justifies its adapter surface.
- `polars` becomes essential — NDJSON streams across 2–4 markets push the dataset into the millions of rows.

**If scaling to live > $1k collateral:**
- Move agent-wallet secrets to HashiCorp Vault or AWS KMS (away from `dotenvx`).
- Consider VPS deployment with lower-latency RPC and replace `launchd` with `systemd`.
- Add Prometheus + Grafana sidecar for live monitoring (log-only analysis doesn't scale past "I'll eyeball it").
- Re-evaluate IPC: if the brain needs to serve multiple bots, move to ZeroMQ or HTTP localhost with auth.

---

## Version Compatibility Matrix

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `tick` 0.8.0.1 | Python 3.11 / 3.12 / 3.13 | Wheels published for CPython only. Don't use PyPy. Don't use 3.14 until tick republishes. |
| `tick` 0.8.0.1 | `numpy >= 2.0` | Rebuilt on scikit-build-core + pybind11 against modern NumPy ABI. Older tick 0.6 had NumPy-1 constraints — don't accidentally install 0.6 from a cached index. |
| `nautilus_trader` 1.225 | Python `>=3.12, <3.15` | Explicit range per PyPI metadata. Matches our 3.12 pick. |
| `polars` 1.40.1 | Python `>=3.10` | 3.12 works; our choice. |
| `pydantic` 2.13 | Python `>=3.9` | Comfortably compatible. |
| `@pendle/sdk-boros` 1.1.44 | `viem@2.44.4` (direct pin) | The caret-less pin is intentional. We match it. |
| `@pendle/sdk-boros` 1.1.44 | Node `>= 20` (peer) | Node 24 satisfies this. |
| `web3.py` 7.15 | Python `>=3.8, <4` | Compatible with 3.12. `WebSocketProvider` graduated in v7 — must be on v7+ for the async WS path. |
| `viem` 2.44.4 | Node 18+ | Node 24 is fine. |
| `ws` 8.20 | Node 10+ | Universally compatible. |

---

## Confidence Levels (per recommendation)

| Recommendation | Confidence | Reason |
|----------------|------------|--------|
| CPython 3.12 | HIGH | Universally supported by all picks; verified on each package's PyPI page. |
| `tick` 0.8.0.1 for Hawkes/NHPP | HIGH | Verified release 3 days before research (Apr 20 2026); wheels for 3.11–3.13 confirmed on PyPI. |
| Hand-rolled OU on scipy | HIGH | No production OU library exists (statsmodels issue #7883 confirmed still open 2026). This is textbook code; reference impls exist. |
| `nautilus_trader` for backtest | MEDIUM | Release 1.225 verified (Apr 6 2026, 3 weeks ago). The claim "custom CLOB venue + AMM adapter fits our shape" is based on doc patterns (Polymarket integration is the closest analog), not a proof-of-concept. **Phase 7 day-1 bailout clause is the risk mitigation.** |
| `polars` 1.40 / `duckdb` 1.5 | HIGH | Verified on PyPI Apr 22 / Mar 9, 2026. Both are mainstream 2026 choices. |
| `pydantic` 2.13.3 | HIGH | Released Apr 20 2026, stable. |
| `structlog` 25.5 | HIGH | Oct 2025 release, still the standard in 2026 per the search results. |
| `web3.py` 7.15 async | HIGH | Verified on PyPI Apr 2 2026. WebSocketProvider graduated in v7. |
| Node 24 LTS (not 22) | HIGH | Verified from multiple sources — Node 22 exits active support April 2026 (i.e., this month), Node 24 LTS active through Oct 2027. Non-negotiable. |
| `@pendle/sdk-boros` 1.1.44 | HIGH | Verified on npm 13h before research; `boros-api-examples` repo + package.json inspected. |
| viem 2.44.4 on TS side | HIGH | Based on the SDK's pinned dependency. |
| `ws` 8.20 native (no reconnect wrapper) | MEDIUM | The "don't use reconnect wrappers" is an opinion backed by the operational concern (silent reconnect = missed fill). Defensible; not a library-version claim. |
| stdin/stdout JSON Lines for IPC | HIGH | Well-documented pattern; the reasoning about dependency minimality is straightforward. |
| `dotenvx` for the agent-wallet key | MEDIUM | Works as described; the "acceptable at $100 scale" qualifier is a judgment call, not a library claim. |
| `launchd` vs `pm2` | HIGH | launchd is native macOS; pm2 is a Node-ecosystem daemon. Choice is clear at one-process scale. |
| `jq` + `lnav` for log inspection | HIGH | Operator-friendly tooling, matches Protocol #3's "grep by `run_id`" directly. |
| Boros WebSocket endpoint exact URL | LOW | The bot guide references a WS feed but the exact `/ws` URL isn't in the scraped public docs. **Phase 0 task: verify the WebSocket URL and subscription payload against the live Boros API docs (or Discord if docs are incomplete).** This doesn't change the recommended library (`ws`), just the endpoint. |

---

## Gaps / Phase-0 Verifications Needed

These are not stack choices — they're facts that must be pinned down before Phase 1 engineering starts:

1. **Exact Boros WebSocket URL and subscription message schema.** The bot guide mentions it; the public SDK doesn't expose a WS helper. Needs one manual session reading `https://api.boros.finance/open-api/docs` or a Discord ping.
2. **`@pendle/sdk-boros` 1.1.44 exact `Exchange` constructor shape.** The README in the public repo doesn't show a full TypeScript example with viem `WalletClient` wired in. One hour of SDK exploration at the start of Phase 8.
3. **Does the SDK expose pre-sign-transaction (sign but don't send)?** Phase 8's killer feature depends on it. If the SDK only exposes `placeOrder` (which signs AND sends), we must compose the lower-level calldata-getting endpoint (`POST /calldata/cancel-order`) with viem's `signTransaction` manually. That's doable but changes the implementation shape; verify at the start of Phase 8.
4. **Actual protocol minimum order size** (plan Phase 0 open item). Not a stack question but a go/no-go on the $100 starting-capital premise.

---

## Wiki Write-Back Plan (Protocol #1)

When this research lands in a PR, the following pages MUST be filed in `../LLM Wiki/workspaces/boros/wiki/` (candidate titles):

- `[[Python stack v0.5]]` — distilled form of the Python section above, Status: Current
- `[[TypeScript stack v0.5]]` — distilled form of the TS section above, Status: Current
- `[[IPC boundary — stdin JSON Lines]]` — the decision and its alternatives, Status: Current
- `[[Secrets handling v0.5]]` — dotenvx at $100 scale, scale-up path noted, Status: Current — v0.5 scale
- `[[launchd supervisor plist]]` — template plist once Phase 8 writes it, Status: Current (pending Phase 8)
- `[[Alternatives rejected — ethers, pandas, pm2, vectorbt, ...]]` — the "what NOT to use" table, Status: Current

These pages supersede the informal notes in this STACK.md. Once filed, the index gets updated with the new thematic links, and subsequent phase plans cite `[[Python stack v0.5]]` instead of re-deriving the choice.

---

## Sources

- [Context7 equivalent — PyPI direct inspection] `tick` 0.8.0.1 — verified Apr 20 2026, Python 3.11/3.12/3.13 wheels
- [Context7 equivalent — PyPI] [`pydantic`](https://pypi.org/project/pydantic/) 2.13.3 — Apr 20 2026
- [Context7 equivalent — PyPI] [`structlog`](https://pypi.org/project/structlog/) 25.5.0 — Oct 27 2025
- [Context7 equivalent — PyPI] [`polars`](https://pypi.org/project/polars/) 1.40.1 — Apr 22 2026
- [Context7 equivalent — PyPI] [`web3.py`](https://pypi.org/project/web3/) 7.15.0 — Apr 2 2026
- [PyPI] [`nautilus_trader`](https://pypi.org/project/nautilus_trader/) 1.225.0 — Apr 6 2026
- [PyPI] [`duckdb`](https://pypi.org/project/duckdb/) 1.5.0 — Mar 9 2026
- [GitHub] [`X-DataInitiative/tick`](https://github.com/X-DataInitiative/tick) — 0.8.0 migration to scikit-build-core + pybind11
- [npm] [`@pendle/sdk-boros`](https://www.npmjs.com/package/@pendle/sdk-boros) 1.1.44 — latest release, 13h old at research time
- [GitHub] [`pendle-finance/sdk-boros-public`](https://github.com/pendle-finance/sdk-boros-public) package.json — confirms viem 2.44.4 pin
- [GitHub] [`pendle-finance/boros-api-examples`](https://github.com/pendle-finance/boros-api-examples) — confirms REST-only SDK (no WebSocket helper)
- [npm] ethers 6.16.0 (rejected)
- [npm] viem 2.47.12 (we use 2.44.4 to match SDK pin)
- [npm] `ws` 8.20.0 — 25 days before research
- [npm] `tsx` 4.21.0 — Nov 30 2025
- [Node.js release schedule] [endoflife.date/nodejs](https://endoflife.date/nodejs) — Node 22 active support ends Apr 2026, Node 24 active Oct 2025 → Oct 2027
- [dotenvx.com](https://dotenvx.com/) — AES-256 + Secp256k1-key-protected `.env.vault` model
- [statsmodels issue #7883](https://github.com/statsmodels/statsmodels/issues/7883) — confirms no OU fit in statsmodels, still open 2026
- Pendle docs: [docs.pendle.finance/boros-dev](https://docs.pendle.finance/boros-dev), [api.boros.finance/open-api/docs](https://api.boros.finance/open-api/docs)
- Verification confidence: all package versions spot-checked on PyPI/npm on 2026-04-23; any stated "Apr 2026 release" dates come from vendor registry metadata, not secondary blog posts.

---

*Stack research for: Boros reward-farming bot (Python + TypeScript split, local macOS deployment, v0.5 → v1.0)*
*Researched: 2026-04-23*
*Next: STACK.md gets turned into wiki pages at Phase 1 kickoff (per Engineering Protocol #1).*
