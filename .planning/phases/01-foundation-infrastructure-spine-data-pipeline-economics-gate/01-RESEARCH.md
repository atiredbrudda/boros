# Phase 1: Foundation (Infrastructure Spine + Data Pipeline + Economics Gate) — Research

**Researched:** 2026-04-23
**Domain:** Load-bearing infrastructure + data pipeline for Pendle Boros LO-liquidity-reward farming bot. Python+TS split, local macOS, Engineering Protocols installed here.
**Confidence:** HIGH on stack/patterns (inherits verified STACK.md + ARCHITECTURE.md + PITFALLS.md plus 8 LLM-Wiki pages from Phase 0). MEDIUM on a handful of Boros-API shapes still to be observed empirically on day 1 (WS Socket.IO heartbeat/reconnect behavior, exact `/markets` response schema, historical `E_liq_per_epoch` reconstruction feasibility). LOW on no material claims — everything in the LOW row is flagged and deferred to empirical spikes inside the phase.
**Wiki pages consulted (Protocol #1):** `[[Voluntary cancel reward behavior]]`, `[[Minimum order size]]`, `[[Boros WebSocket API]]`, `[[Sign-only cancel primitive]]`, `[[Send Txs Bot integration]]`, `[[Market entry cap and auto-exit pattern]]`, `[[eventIndex coverage]]`, `[[Boros fee schedule]]` + index.

---

## Summary

Phase 1 installs the *irreversible spine* for the whole project: every downstream log, plot, postmortem, and live-trading decision is invalid if the manifest writer, the architecture lint, or the wiki-cite hook isn't live. The phase has three workstreams that can be built in parallel once their shared dependencies land: (A) **Infrastructure** — monorepo, Pydantic v2 `BotConfig`, SQLite WAL spine, DuckDB read-only, ZMQ bus, RUN_MANIFEST, structlog/pino, architecture diagram + lint, wiki seed + cite-hook, dotenvx + Keychain, launchd plists, chain-time monitor; (B) **Data pipeline** — NDJSON ingester for trades/books/underlying/settlement, AMM conservation assertion, live `/markets` poller, fIndexOracle reader, market screener, economics kill-switch, daily re-screen, E_liq polling; (C) **Protocols (PROTO-01..05)** — the cross-cutting enforcement that closes the loop.

The **second kill gate** lives in workstream (B): DATA-09's `R_apr_on_collateral > alt_yield + estimated_fill_loss_rate` filter. An empty shortlist halts the project with a written report — no model code, no Phase 2.

**Primary recommendation:** *Build workstream A's "tracer bullet" first (Wave 0: repo + Pydantic schema + SQLite + ZMQ echo + manifest writer + structlog + architecture lint + wiki seed + cite-hook), gated so nothing else merges until `brain` can emit a manifest-stamped log line and a commit without an arch-yml update fails pre-commit. Then fork workstream B (data pipeline) and the remaining A items (dotenvx, launchd, NTP monitor) in parallel waves.* This ordering is enforced by the fact that every other task's verification references a manifest'd log line or an architecture.yml node.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

**No CONTEXT.md exists for Phase 1** — discuss-phase was skipped (per `discuss_mode: "discuss"` config but no transcript in the phase directory). The "constraints" below are extracted from CLAUDE.md, PROJECT.md Key Decisions, the roadmap entry for Phase 1, and the Phase 0 resolutions locked 2026-04-23. The planner should treat these with the same authority as locked decisions from a discuss-phase.

### Locked decisions (from Phase 0 and CLAUDE.md — do NOT re-derive alternatives)

- **Python brain + TypeScript hands split** over ZMQ IPC. (PROJECT.md Key Decisions)
- **IPC transport: ZMQ** on `ipc:///tmp/boros.cmd` (PUSH/PULL with KILL priority lane) and `ipc:///tmp/boros.events` (PUB/SUB), with 5s heartbeat both directions. *(INFRA-05)* — overrides `stdin/stdout JSON Lines` suggested in STACK.md §IPC-Boundary; ARCHITECTURE.md already reflects the ZMQ choice and so does CLAUDE.md. **Research uses ZMQ.**
- **Shared state: SQLite WAL** with single-writer-per-table discipline, **DuckDB read-only on top** of parquet + SQLite for analytical reads. *(INFRA-03, INFRA-04)*
- **Secrets: dotenvx encrypted `.env.vault`, `.env.keys` in macOS Keychain**, gitignored. *(INFRA-12)*
- **Supervision: launchd LaunchAgent plists** for `brain` and `hands` (separate), `KeepAlive`, `ThrottleInterval=30`, logs to `logs/supervisor/`. *(INFRA-13)* — overrides `overmind`/Procfile suggested in ARCHITECTURE.md §6.
- **Pydantic v2 `BotConfig`** is the single source of truth for every knob (`extra='forbid'`, frozen). Manifest generator uses Pydantic reflection. *(INFRA-02, INFRA-06, PROTO-04)*
- **RUN_MANIFEST** is first log record + sidecar JSON, with ULID `run_id`, `git_sha`, `git_dirty`, `strategy_version`, `market_id`, `side`, `wallet_address_hash`, full knob tree. Mid-run knob change → new `run_id` with `parent_run_id`. *(INFRA-06, PROTO-01)*
- **`voluntary_cancel_forfeits_accumulated = False`** (benign branch) locked in Phase 1 `BotConfig` schema per [[Voluntary cancel reward behavior]].
- **Boros WebSocket is Socket.IO, not raw WS** — TS stack uses `socket.io-client 4.x` (NOT `ws 8.20`). Per-account fill channel `account-updates:ROOT` exists. Per [[Boros WebSocket API]]. *(Stack change landed in Phase 1 scope — does not change this phase's delivery but the WS listener is a Phase 6 deliverable, not Phase 1.)*
- **Send Txs Bot is the mandatory submission lane** (`POST /v2/agent/bulk-direct-call` + `/v2/agent/direct-call`, v2 only). Direct-to-chain ruled out; `submission_path` knob is gone. Per [[Sign-only cancel primitive]] + [[Send Txs Bot integration]]. *(Not a Phase 1 deliverable per se, but the config schema must NOT include a `submission_path` knob.)*
- **No protocol minimum order size** — per [[Minimum order size]]. Economic floor via fees/gas handled by DATA-09.
- **`eventIndex` is the intra-block ordering primitive** (NOT `blockTimestamp`) — per [[eventIndex coverage]]. DATA-01 ingester asserts presence on every row.
- **Fee schedule locked**: maker 0, taker 0.05% (`MarketConfig.takerFee`), settlement `|Size|×Rate×Period`, entrance ~$1/market, no cancel fee. Per [[Boros fee schedule]]. Gas measured empirically per DECIDE-03 (Phase 4 task, but Phase 1's economics gate uses a **conservative gas estimate** from pulled Arbiscan tx samples — see "Economics kill-switch math" section below).

### Claude's discretion (research recommends, planner decides)

- **Monorepo layout detail** — `python/` vs `brain/` as top-level name; split of `configs/` vs `strategy/` YAML files; tests-layout. ARCHITECTURE.md §7 proposes one concrete tree; Phase 1 planner may adapt but must preserve: one `BotConfig` schema file, one `architecture.yml` at a known path, one wiki-cite hook config.
- **SQLite ORM vs raw SQL** — unchosen. Research recommends **raw SQL + `sqlite3` stdlib (Python) / `better-sqlite3` (TS)** with Alembic for migrations and no ORM. Rationale below.
- **Migrations tool** — research recommends **Alembic** for Python-side, with TS reading through `better-sqlite3` in read-only-or-single-table mode. Alternative: the lighter-weight `yoyo-migrations`. Planner may pick either.
- **Architecture lint implementation** — pure Python AST walk vs Tree-sitter vs `pyan3` library. Research recommends **pure Python `ast` module** for the Python side (stdlib, zero deps) and **`ts-morph`** for TS side if needed for Phase 1 scope (likely deferred to when `hands` code is non-trivial, Phase 6).
- **NDJSON sources** — the Boros historical-data.boros.finance bucket is the primary; stitching live WS + REST has been considered but is **out of scope for Phase 1** (ingester is batch / daily).
- **ZMQ schema codegen** — Research recommends hand-mirrored Pydantic (Python) + Zod (TS) for v0.5 (~20 message types) with a schema-diff unit test as the drift-detector. A single JSON schema + codegen is v1.0 polish.

### Deferred ideas (OUT OF SCOPE)

- **`submission_path` knob** — ruled out per P0-04. Do NOT add to `BotConfig`.
- **Hot-reload of knobs mid-run** — explicit anti-pattern (PITFALLS §D2/D4 + ARCHITECTURE.md §9 Anti-pattern 3).
- **Multi-market / multi-wallet** — v0.5 is single-market single-side. Schema allows list but validation in v0.5 caps length to 1.
- **VPS / private RPC** — LIVE-07 (Phase 8). Phase 1 uses public Arbitrum RPC for the fIndexOracle reader.
- **Web UI / dashboard** — logs + Jupyter notebooks only.
- **Historical reward-budget reconstruction from distributor events** — if infeasible (likely, given pipeline age), budget-time-series is "forward-only" from pipeline go-live. Pre-pipeline backtest marked "current-budget synthetic." *(B6 concession — scoped here because DATA-11 is the polling-forward layer; the reconstruction attempt is one spike inside DATA-11, with an explicit fallback.)*
- **Session-key wallet / multi-sig** — Phase 8 concern.
- **Nonce model** — Phase 6 decision (C1 pitfall); Phase 1 schema MUST NOT pre-bake a nonce strategy.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **INFRA-01** | Monorepo `python/` + `ts/` + `configs/` + `docs/` layout; `uv` + `pnpm` | Recommended file tree in §Project Structure. Inherits STACK.md (uv/pnpm verified live on registries 2026-04-23). |
| **INFRA-02** | Single Pydantic v2 `BotConfig`, `extra='forbid'`, frozen, round-trip test | §Pydantic BotConfig schema sketch + round-trip test skeleton. |
| **INFRA-03** | SQLite WAL, 8 tables, single-writer-per-table discipline, linted | §SQLite Table Schemas (all 8 tables) + §Single-writer enforcement pattern. |
| **INFRA-04** | DuckDB read-only over parquet + SQLite | §DuckDB read-only wiring. |
| **INFRA-05** | ZMQ IPC cmd PUSH/PULL w/ KILL priority + events PUB/SUB + 5s heartbeat + lost-sibling protocol | §ZMQ topology + priority-lane pattern + lost-sibling protocol. |
| **INFRA-06** | RUN_MANIFEST writer via Pydantic reflection, ULID `run_id`, full knob tree, `parent_run_id` | §RUN_MANIFEST writer + reflection recipe + parent_run_id chain pattern. |
| **INFRA-07** | structlog JSON + pino mirror, contextvars-bound `run_id`, logs/<YYYY-MM-DD>/<run_id>.log.jsonl | §Structured log contract (Python+TS shared schema) + §contextvars-across-async. |
| **INFRA-08** | `docs/ARCHITECTURE.md` (Mermaid) + `docs/architecture.yml` (machine-readable) | §architecture.yml schema draft + §Mermaid seed already exists in ARCHITECTURE.md §1. |
| **INFRA-09** | `scripts/architecture_lint.py` pre-commit hook that parses source tree, fails commits on drift | §Architecture lint approach (Python AST walk) + §Granularity rules. |
| **INFRA-10** | LLM Wiki seeded with `Status:` flags, index thematic + alphabetical populated | §Wiki seeding scope (existing Phase-0 pages + new Phase-1 pages). |
| **INFRA-11** | Wiki-cite pre-commit hook blocking research/decisions/postmortem markdown without `[[wiki-link]]` | §Wiki-cite hook script sketch. |
| **INFRA-12** | `dotenvx` encrypted `.env.vault` + `.env.keys` in macOS Keychain | §dotenvx + Keychain wiring (concrete pattern). |
| **INFRA-13** | `launchd` LaunchAgent plists for brain + hands | §launchd plist template + known gotchas. |
| **INFRA-14** | NTP/chain-time drift monitor, `chain_time` cache, >5s warn / >30s halt | §Chain-time cache pattern. |
| **DATA-01** | NDJSON ingester for `market-trades/`, `eventIndex`/`blockTimestamp`/`rate`/`side`/`size`/`txHash`, wei→float explicit | §Ingester patterns + §Schema assertions (every row has `eventIndex`). |
| **DATA-02** | NDJSON ingester for `order-book/{market}/raw/` hourly + `combined_{tickSize}/` | §Hourly snapshot ingestion + `combined` semantics. |
| **DATA-03** | NDJSON ingester for `underlying-apr/` | §Underlying-APR schema (CEX funding rate series). |
| **DATA-04** | NDJSON ingester for `settlement/` + `market-data/` | §Market-data table schema. |
| **DATA-05** | AMM conservation assertion: `combined_size(δ) − raw_book_size(δ) ≥ 0` per tick | §AMM conservation check + B3 pitfall prevention. |
| **DATA-06** | `GET /markets` ~30s poller writes timestamped `clo_history` rows | §`clo_history` table + polling cadence. |
| **DATA-07** | `fIndexOracle.getLatestFIndex()` reader decodes packed `bytes26 → bytes32`; `latestAnnualizedRate()` spot reader; ≤1s cache | §fIndexOracle decode with selector + decode math + known addresses. |
| **DATA-08** | Market screener (60d trades, CV, realized vol, depth, maturity, clo bounds) → 2–4 market shortlist | §Market screener inputs + outputs + absorbed A8 outside-range-wall flag. |
| **DATA-09** | Reward-share economics kill-switch: `R_apr_on_collateral > alt_yield + estimated_fill_loss_rate` | §Economics kill-switch math + §Alt-yield benchmark (Aave USDC Arbitrum) + §Phase-1 fill-loss coarse bound. |
| **DATA-10** | Daily automated re-screen | §Daily re-screen job pattern (launchd CalendarInterval). |
| **DATA-11** | Live `E_liq_per_epoch` + Long/Short split polling every 1–5s → `reward_budget_history` | §`reward_budget_history` table + polling cadence + B6 fallback (forward-only logging). |
| **PROTO-01** | RUN_MANIFEST + `run_id` on every log line | Inherits INFRA-06 + INFRA-07. |
| **PROTO-02** | Every code-touching commit updates `architecture.yml` + Mermaid | Inherits INFRA-09. |
| **PROTO-03** | Every research/decisions/postmortem commit cites `[[wiki-link]]` | Inherits INFRA-11. |
| **PROTO-04** | Every knob in Pydantic schema | Inherits INFRA-02 + reflection manifest. |
| **PROTO-05** | Supersedence discipline — new wiki finding → update stale pages in same commit | §Supersedence pre-commit check. |
</phase_requirements>

---

## Architectural Responsibility Map

Each Phase 1 capability is mapped to its architectural tier. This prevents mis-assignment at plan time (e.g., putting a data-pipeline ingester in the `hands` process, or putting the manifest writer in `hands`).

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Monorepo layout (INFRA-01) | Repo root | — | Shared skeleton for both tiers |
| Pydantic `BotConfig` (INFRA-02) | `brain` (Python) | `hands` reads via JSON export | Python is source-of-truth; TS consumes via generated JSON schema or mirror |
| SQLite WAL spine (INFRA-03) | `brain` (primary writer) | `hands` (writes to `tx_receipts`, `open_orders`) | Single-writer-per-table: brain owns analytical tables, hands owns execution tables |
| DuckDB read-only (INFRA-04) | `brain` / analysis notebooks | — | Analytical layer only; never on the live/hot path |
| ZMQ IPC (INFRA-05) | Cross-process glue | Both tiers | Python PUSH ↔ TS PULL on cmd; TS PUB ↔ Python SUB on events |
| RUN_MANIFEST writer (INFRA-06) | `brain` (Python) | `hands` echoes `run_id` on every log line | Manifest is Python-authored; `hands` stamps `run_id` received via ZMQ or env var at startup |
| structlog / pino (INFRA-07) | Both tiers | — | Same JSON shape, both sides write to `logs/<YYYY-MM-DD>/<run_id>.log.jsonl` (separate files `brain.jsonl`/`hands.jsonl` per run_id recommended to avoid interleave) |
| ARCHITECTURE.md + architecture.yml (INFRA-08) | Repo root `docs/` | — | Read by pre-commit lint; humans read Mermaid |
| architecture_lint.py (INFRA-09) | Pre-commit hook (Python) | — | Walks both `python/` and `ts/` source trees |
| LLM Wiki seed (INFRA-10) | External workspace (`../LLM Wiki/workspaces/boros/`) | — | Cross-repo; not in bot source tree |
| wiki-cite hook (INFRA-11) | Pre-commit hook (Python) | — | Greps `[[wiki-link]]` in research/decisions/postmortem markdown |
| dotenvx + Keychain (INFRA-12) | Shell / launchd env (pre-process) | Both tiers read decrypted env at startup | Keychain lookup happens in plist's `EnvironmentVariables` or wrapper script |
| launchd plists (INFRA-13) | OS layer (macOS) | — | `brain` plist + `hands` plist in `~/Library/LaunchAgents/` |
| Chain-time drift monitor (INFRA-14) | `brain` (Python, web3.py cache) | — | Single source-of-truth clock; `hands` can read via ZMQ event if needed |
| NDJSON ingester DATA-01..04 | `brain` / offline jobs | — | Batch jobs, not hot path; launchd CalendarInterval for daily runs |
| AMM conservation check (DATA-05) | `brain` ingester step | — | Inline with DATA-02 |
| `/markets` poller (DATA-06) | `brain` background task (asyncio) | — | Low-frequency (~30s); writes `clo_history` |
| fIndexOracle reader (DATA-07) | `brain` (web3.py) | — | `hands` does not need `fIndex` for Phase 1 |
| Market screener (DATA-08) | `brain` offline job | — | Runs against parquet via DuckDB; outputs shortlist YAML |
| Economics kill-switch (DATA-09) | `brain` offline job | — | Halts project if empty shortlist; writes kill report |
| Daily re-screen (DATA-10) | launchd CalendarInterval job | — | Reuses DATA-08 + DATA-09 machinery |
| E_liq polling (DATA-11) | `brain` background task | — | 1–5s cadence; writes `reward_budget_history` |
| PROTO-01..05 | Cross-cutting (all tiers + repo root) | — | Hooks + schema-reflection + discipline |

---

## Standard Stack

Phase 1 inherits the full stack verified in STACK.md and tightened by Phase 0 resolutions. All versions verified on PyPI/npm on 2026-04-23 (same-day cutover as STACK.md research). **Deltas from STACK.md are called out explicitly below; the original table is authoritative otherwise.**

### Core — Python (`brain`)

| Library | Version | Purpose | Phase 1 role | Source |
|---|---|---|---|---|
| CPython | 3.12.x | Runtime | Everything | STACK.md [VERIFIED 2026-04-23, PyPI wheel support] |
| `pydantic` | 2.13.3 | `BotConfig` single source of truth; `model_fields` reflection for RUN_MANIFEST | INFRA-02, INFRA-06, PROTO-04 | STACK.md [VERIFIED] + [CITED: docs.pydantic.dev/latest/concepts/models/] |
| `structlog` | 25.5.0 | JSON logger with `contextvars.bind_contextvars(run_id=...)` across async tasks | INFRA-07 | STACK.md [VERIFIED] + [CITED: structlog.org/en/stable/contextvars.html] |
| `orjson` | 3.10.x | Faster JSON for hot log path (structlog JSONRenderer shim) | INFRA-07 performance | STACK.md |
| `python-ulid` | 3.0.x | `run_id` generation (lexicographically sortable by time) | INFRA-06 | STACK.md |
| `polars` | 1.40.1 | NDJSON ingestion (`pl.scan_ndjson` with column pruning) + partitioned parquet writes | DATA-01..04 | STACK.md [VERIFIED] |
| `duckdb` | 1.5.0 | Read-only analytical layer over parquet + SQLite (via `sqlite_scanner`) | INFRA-04, DATA-08 screener | STACK.md [VERIFIED] |
| `web3.py` | 7.15.0 | Arbitrum RPC reads (`fIndexOracle`, chain time, gas histogram for DATA-09) | DATA-07, INFRA-14 | STACK.md [VERIFIED] |
| `httpx` | 0.27.x | Async REST client for Boros `/markets`, `/v2/accounts/all-limit-orders` | DATA-06, DATA-11 | STACK.md |
| `pyzmq` | 26.x | ZMQ Python bindings for `brain` side of the bus | INFRA-05 | [CITED: pyzmq.readthedocs.io; ARCHITECTURE.md §4 verified IPC sub-ms] |
| `alembic` | 1.14+ | SQLite schema migrations | INFRA-03 | [ASSUMED — standard 2026 pick; planner may substitute `yoyo-migrations`] |
| `python-dotenv` | 1.0.x | Read decrypted env at startup (dotenvx runs wrapper) | INFRA-12 | STACK.md |

### Core — TypeScript (`hands`)

(Phase 1 writes to SQLite + emits/consumes ZMQ but does NOT yet ship fill-listening or execution — those are Phase 6. Phase 1 ships the `hands` skeleton + log contract + ZMQ echo + SQLite writer for `tx_receipts` schema test.)

| Library | Version | Purpose | Phase 1 role | Source |
|---|---|---|---|---|
| Node.js | 24.15.x LTS | Runtime (NOT 22 — exits active support Apr 2026) | Everything | STACK.md [VERIFIED: endoflife.date/nodejs] |
| `@pendle/sdk-boros` | 1.1.44 | (installed for dependency consistency; not used in Phase 1 beyond type imports) | Placeholder for Phase 6 | STACK.md [VERIFIED] |
| `viem` | 2.44.4 | (match SDK pin exactly, caret-less) | Placeholder | STACK.md |
| `socket.io-client` | 4.x | **Stack change per P0-03**: replaces `ws 8.20` | Placeholder for Phase 6 WS listener | [[Boros WebSocket API]] [CITED] |
| `pino` | 9.x | JSON logger mirror of structlog schema | INFRA-07 | STACK.md [VERIFIED] |
| `ulid` | 2.3.x | `run_id` (same lib semantics as Python side) | Reads `run_id` from env at startup | STACK.md |
| `zeromq` (zeromq.js) | 6.x | ZMQ TypeScript bindings | INFRA-05 | [CITED: zeromq.org/languages/nodejs/] |
| `better-sqlite3` | 11.x | Synchronous SQLite (WAL mode) for `hands` writes | INFRA-03 tx_receipts/open_orders | [ASSUMED — standard 2026 Node SQLite, version verified common] |
| `zod` | 3.23.x | Runtime schema validation of ZMQ message payloads | INFRA-05 schema mirror | STACK.md |

### Supporting / tooling

| Tool | Version | Purpose | Phase 1 role |
|---|---|---|---|
| `uv` (astral-sh) | 0.5+ | Python packaging + venv + lockfile | INFRA-01 |
| `pnpm` | 9.x | TS package manager | INFRA-01 |
| `ruff` | 0.7+ | Python linter + formatter | Pre-commit hook |
| `mypy` | 1.13+ | Python type check (strict) | Pre-commit hook |
| `@biomejs/biome` | 1.9+ | TS lint + format (faster than ESLint+Prettier) | Pre-commit hook |
| `pre-commit` | 4.x | Git hook runner | Hosts architecture_lint, wiki-cite, ruff, mypy, biome, config-schema round-trip |
| `pytest` | 8.x | Python tests | INFRA-02 round-trip, INFRA-06 manifest-contains-all-knobs |
| `vitest` | 2.x | TS tests | `hands` schema-mirror-diff test |
| `dotenvx` | latest (CLI) | Encrypted `.env.vault` + `.env.keys` | INFRA-12 |

### Alternatives considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| ZMQ | stdin/stdout JSON Lines (STACK.md's original recommendation) | Locked to ZMQ per CLAUDE.md + INFRA-05 — no reconsideration |
| launchd plist | overmind/foreman Procfile (ARCHITECTURE.md §6 original) | Locked to launchd per INFRA-13 |
| SQLite raw SQL | An ORM (SQLAlchemy) | Raw SQL is faster to write for a fixed 8-table schema, easier to reason about WAL transaction boundaries, and integrates cleanly with DuckDB's `sqlite_scanner`. No ORM. |
| Alembic migrations | `yoyo-migrations` (lighter) | Alembic is the 2026 default for Python + SQLite; `yoyo` is fine too. Planner's choice. |
| Python `ast` for arch lint | `pyan3` library, `tree-sitter`, `ts-morph` | Pure `ast` has zero dependencies and handles Python 3.12 directly. TS parsing (Phase 6+) will need `ts-morph` or `typescript-eslint` but NOT for Phase 1 since TS source is minimal. |
| `socket.io-client 4.x` | `ws 8.20` | Stack change locked by P0-03 — Boros is Socket.IO, not raw WS. |
| `better-sqlite3` (TS) | `sqlite3` (async, Node native) | `better-sqlite3` is synchronous — simpler reasoning about transaction boundaries, 3× faster for our workload, WAL mode works identically. The Python and TS sides thus have different sync models on the same file; that's fine because our single-writer-per-table discipline prevents contention. |

**Installation:**

```bash
# Python side
uv init boros-brain --python 3.12
uv add pydantic==2.13.3 structlog==25.5.0 orjson python-ulid polars==1.40.1 \
        duckdb==1.5.0 web3==7.15.0 httpx pyzmq==26.2.0 alembic python-dotenv
uv add --dev pytest pytest-asyncio hypothesis ruff mypy pre-commit jupyterlab

# TS side
pnpm init
pnpm add @pendle/sdk-boros@1.1.44 viem@2.44.4 socket.io-client@4 \
         pino ulid zeromq@6 better-sqlite3 zod dotenv
pnpm add -D typescript@5.6 tsx@4.21 vitest@2 @biomejs/biome

# Secrets wrapper (one-time operator install)
npm i -g @dotenvx/dotenvx
```

**Version verification** (all spot-checked against registries on 2026-04-23 by STACK.md research + this research): every version above was released within the past 30 days on its registry except `ulid` (2.3.x, stable), `python-ulid` (3.0.x, stable), `alembic` (1.14, stable), `zeromq.js` 6 (stable), `better-sqlite3` (11.x, stable), `zod` (3.23.x, stable). The fast-moving picks (`pydantic` 2.13.3 Apr-20, `polars` 1.40.1 Apr-22, `structlog` 25.5.0 Oct-27, `@pendle/sdk-boros` 1.1.44 ~13h pre-research, `viem` 2.44.4 SDK-pinned) are [VERIFIED: registry] as of the research date. Planner should spot-check again at execution start — for a phase this load-bearing, a 3-week registry delta is worth the 30 seconds.

---

## Architecture Patterns

### System Architecture Diagram

The master diagram lives in ARCHITECTURE.md §1 (Mermaid). For Phase 1 specifically, the relevant subset — what must actually be built + wired in this phase — is:

```
                   ┌─────────────────────────────────────────────────┐
                   │              RUN_MANIFEST (brain)               │
                   │   ULID run_id + git_sha + Pydantic knob tree    │
                   └────────────────────────┬────────────────────────┘
                                            │ stamps run_id on every log line
      ┌─────────────────────────────────────┼──────────────────────────────────┐
      │                                     │                                  │
      ▼                                     ▼                                  ▼
┌───────────────┐                    ┌─────────────────┐                ┌──────────────┐
│ Data ingester │                    │   brain skel    │                │ hands skel   │
│ (polars)      │                    │  (asyncio)      │◀──ZMQ cmd────▶│  (node)      │
│ market-trades │                    │                 │    PUSH/PULL   │              │
│ order-books   │                    │  - MDL poll /m  │    KILL prio   │  - ZMQ echo  │
│ underlying    │────writes parquet──▶│  - fIndex read  │◀──events────▶│  - pino log  │
│ settlement    │                    │  - E_liq poll   │    PUB/SUB     │  - SQLite    │
└───────────────┘                    │  - heartbeat 5s │                │    writer    │
       │                             │  - structlog    │                └──────┬───────┘
       │ DATA-05 AMM check           └────────┬────────┘                       │
       ▼                                      │                                │
┌───────────────┐                             │ writes                         │
│ DuckDB        │◀─────read-only──────────────┤                                │
│ sqlite_scanner│                             │                                │
│ over parquet+ │                             ▼                                │
│ sqlite        │                    ┌─────────────────┐                       │
└───────┬───────┘                    │ state.sqlite    │◀─writes (tx_receipts,─┘
        │                            │ WAL mode        │          open_orders)
        ▼                            │                 │
┌───────────────┐                    │  8 tables       │
│ Market        │───writes shortlist─▶│  + migrations   │
│ screener      │   YAML to config/   │                 │
│ (DATA-08/09)  │                    └─────────────────┘
└───────────────┘                             ▲
        │                                     │
        ▼ (kill report if empty)              │
    ┌──────────┐                              │
    │ PROJECT  │                              │
    │  HALT    │                              │
    └──────────┘                              │
                                              │ reads
                           ┌──────────────────┴──────────────┐
                           │ analysis notebooks (Jupyter)    │
                           │ DuckDB over parquet + SQLite    │
                           └─────────────────────────────────┘

External data flows (Phase 1 scope only):
- historical-data.boros.finance  →  data ingester  (DATA-01..04)
- api.boros.finance/open-api/v1/markets  →  /markets poller  (DATA-06)
- api.boros.finance/open-api/v1/markets  →  E_liq poller  (DATA-11)
- Arbitrum RPC                    →  fIndexOracle reader + chain-time  (DATA-07, INFRA-14)
- Aave USDC Arbitrum (one-off for DATA-09 alt-yield benchmark — not a polled feed)
```

### Recommended Project Structure

Based on ARCHITECTURE.md §7, tightened for Phase 1's specific deliverables:

```
boros/
├── python/                            # ← monorepo python side (INFRA-01)
│   ├── pyproject.toml                 # uv / pip project
│   ├── uv.lock
│   └── src/boros_brain/
│       ├── __init__.py
│       ├── main.py                    # entrypoint — --mode=live|paper|backtest|ingest|screen
│       ├── config/
│       │   ├── schema.py              # ← THE Pydantic BotConfig (INFRA-02) — SINGLE SOURCE OF TRUTH
│       │   └── loader.py              # load YAML → BotConfig with extra='forbid'
│       ├── manifest/
│       │   ├── writer.py              # RUN_MANIFEST writer (INFRA-06) via Pydantic reflection
│       │   └── schema.py              # RunManifest Pydantic model (fields listed below)
│       ├── logging/
│       │   ├── structlog_setup.py     # contextvars-bound run_id, JSONRenderer, file rotation
│       │   └── schema.py              # LogRecord Pydantic model (shared with TS via JSON schema export)
│       ├── bus/
│       │   ├── cmd.py                 # ZMQ PUSH (brain → hands) with priority
│       │   ├── events.py              # ZMQ SUB (brain listens to hands)
│       │   ├── heartbeat.py           # 5s both directions, lost-sibling protocol
│       │   └── messages.py            # Pydantic message schemas (mirrored in TS Zod)
│       ├── state/
│       │   ├── db.py                  # sqlite3 WAL connection; single-writer discipline
│       │   ├── schemas.sql            # 8-table DDL
│       │   ├── migrations/            # Alembic
│       │   └── writers/               # one module per table, enforces single-writer
│       │       ├── open_orders.py     # owned by hands (used only in TS; Python has read-only helpers)
│       │       ├── decisions.py       # owned by brain
│       │       ├── tx_receipts.py     # owned by hands
│       │       ├── queue_positions.py # owned by brain
│       │       ├── run_manifests.py   # owned by brain
│       │       ├── epoch_rewards.py   # owned by brain
│       │       ├── clo_history.py     # owned by brain
│       │       └── reward_budget_history.py  # owned by brain
│       ├── data/
│       │   ├── rest_client.py         # httpx wrapper for Boros /open-api/v1/*
│       │   ├── rpc_client.py          # web3.py AsyncHTTPProvider, fIndexOracle reader (DATA-07)
│       │   ├── ingester/
│       │   │   ├── market_trades.py   # DATA-01 (preserves eventIndex, asserts presence)
│       │   │   ├── order_book.py      # DATA-02 (raw + combined + AMM conservation)
│       │   │   ├── underlying_apr.py  # DATA-03
│       │   │   └── settlement_md.py   # DATA-04
│       │   ├── poller/
│       │   │   ├── markets_poller.py  # DATA-06 — clo_history
│       │   │   └── e_liq_poller.py    # DATA-11 — reward_budget_history
│       │   └── chain_time.py          # INFRA-14 chain-time cache + drift monitor
│       ├── screener/
│       │   ├── metrics.py             # CV, realized vol, depth, reversal count (DATA-08)
│       │   ├── economics_gate.py      # DATA-09 — R_apr vs alt-yield + fill-loss
│       │   └── report.py              # shortlist YAML + kill report writer
│       ├── duckdb_layer/
│       │   └── views.sql              # register SQLite as attached DB, define parquet views
│       └── tests/
│           ├── test_config_round_trip.py       # INFRA-02
│           ├── test_manifest_contains_all_knobs.py # D2 prevention
│           ├── test_zmq_schema_mirror.py       # TS↔Python schema diff
│           ├── test_sqlite_single_writer.py    # single-writer-per-table discipline
│           ├── test_amm_conservation.py        # DATA-05
│           └── test_economics_kill_switch.py   # DATA-09 math
├── ts/                                # ← monorepo TS side (INFRA-01)
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   └── src/boros_hands/
│       ├── main.ts                    # entrypoint — reads run_id from env, opens ZMQ bus
│       ├── config.ts                  # loads BotConfig JSON (exported from Python)
│       ├── logger.ts                  # pino with same record shape as structlog
│       ├── bus/
│       │   ├── cmd_listener.ts        # ZMQ PULL
│       │   ├── event_publisher.ts    # ZMQ PUB
│       │   ├── heartbeat.ts           # 5s both directions
│       │   └── messages.ts            # Zod schemas (mirror python/.../bus/messages.py)
│       └── state/
│           └── sqlite_writer.ts       # better-sqlite3 WAL, only tx_receipts + open_orders
├── configs/                           # ← per-market CALIBRATION (SCALE, S, fIndexOracle) — NOT strategy
│   ├── ETHUSDT-29MAY2026.yaml
│   ├── BTCUSDT-29MAY2026.yaml
│   └── shortlist.yaml                 # DATA-08 output — selected markets
├── strategy/                          # ← the KNOB tree YAML — parsed into BotConfig
│   └── v0.5-default.yaml
├── docs/
│   ├── ARCHITECTURE.md                # ← Mermaid (INFRA-08) — human-readable
│   └── architecture.yml               # ← machine-readable (INFRA-08/09) — lint parses
├── data/                              # ← gitignored; populated by ingester
│   ├── raw/                           # NDJSON downloads
│   │   ├── market-trades/{market}/*.ndjson
│   │   ├── order-book/{market}/raw/*.ndjson
│   │   ├── order-book/{market}/combined_{tickSize}/*.ndjson
│   │   ├── underlying-apr/*.ndjson
│   │   └── settlement/*.ndjson
│   └── parquet/                       # partitioned parquet — DuckDB reads
│       ├── market_trades/market=ETHUSDT-29MAY2026/month=2025-08/*.parquet
│       ├── order_book_raw/market=.../snapshot_ts=.../tick=.../*.parquet
│       └── ...
├── var/                               # ← gitignored runtime state
│   ├── state.sqlite                   # WAL mode
│   ├── state.sqlite-wal
│   ├── state.sqlite-shm
│   └── logs/
│       └── <YYYY-MM-DD>/
│           ├── <run_id>.manifest.json
│           ├── <run_id>.brain.log.jsonl
│           └── <run_id>.hands.log.jsonl
├── scripts/
│   ├── architecture_lint.py           # INFRA-09 — parses Python AST + architecture.yml
│   ├── wiki_cite_lint.py              # INFRA-11 — greps for [[wiki-link]] in research/decisions/postmortem
│   ├── supersedence_lint.py           # PROTO-05 — warns on stale Status:Current pages
│   └── launchd/
│       ├── com.boros.brain.plist      # INFRA-13
│       └── com.boros.hands.plist      # INFRA-13
├── .pre-commit-config.yaml            # hosts all lints + tests
├── .env.vault                         # ← committed (dotenvx encrypted) — INFRA-12
├── .gitignore                         # ← must include .env.keys, var/, data/parquet/, data/raw/
├── .envrc                             # ← direnv, sets DOTENV_PRIVATE_KEY from Keychain
├── Makefile                           # run-brain, run-hands, screen, ingest, health
└── CLAUDE.md / README.md              # already present
```

### Pattern 1: Pydantic v2 `BotConfig` — schema-driven manifest (INFRA-02, INFRA-06, PROTO-04)

**What:** A single nested Pydantic v2 model is the authoritative knob inventory. `model_fields` reflection generates the `RUN_MANIFEST` knob tree. Adding a knob in code without adding it to the schema is impossible — the `extra='forbid'` + `frozen=True` + pre-commit round-trip test catches it.

**When to use:** Once. The schema is the project's strategy-knob source-of-truth for its entire lifetime.

**Example** (sketch — planner refines field-by-field):

```python
# python/src/boros_brain/config/schema.py
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class StrictBase(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

class StrategyConfig(StrictBase):
    voluntary_cancel_forfeits_accumulated: bool = False  # [[Voluntary cancel reward behavior]]
    target_share: float = Field(0.05, ge=0.01, le=1.0)
    # ... decision-engine knobs go here, added by Phase 4

class ExecutionConfig(StrictBase):
    # Phase 6 knobs — placed here now so manifest surfaces them as defaults
    cancel_latency_budget_s: float = 5.0
    require_success_default: bool = True  # [[Send Txs Bot integration]]
    agent_wallet_gas_warn_multiples: int = 50
    agent_wallet_gas_halt_multiples: int = 20
    agent_wallet_gas_emergency_multiples: int = 5
    # NO submission_path knob — ruled out per P0-04

class DataConfig(StrictBase):
    markets_poll_interval_s: float = 30.0             # DATA-06
    e_liq_poll_interval_s: float = 5.0                # DATA-11
    chain_time_cache_ttl_s: float = 1.0               # DATA-07
    rpc_url_arbitrum: str                              # no default — must come from env/yaml
    boros_rest_base: str = "https://api.boros.finance/open-api/v1"

class InfraConfig(StrictBase):
    sqlite_path: str = "var/state.sqlite"
    logs_dir: str = "var/logs"
    zmq_cmd_endpoint: str = "ipc:///tmp/boros.cmd"
    zmq_events_endpoint: str = "ipc:///tmp/boros.events"
    heartbeat_interval_s: float = 5.0
    heartbeat_timeout_misses: int = 3
    chain_drift_warn_s: float = 5.0
    chain_drift_halt_s: float = 30.0

class ScreenerConfig(StrictBase):
    min_time_to_maturity_days: int = 30
    trades_window_days: int = 60
    realized_vol_window_days: int = 14
    reversal_count_window_days: int = 3
    # alt_yield: baseline APR that R_apr_on_collateral must beat — PLANNER: resolve unit (decimal fraction 0.05 not 5.0)
    alt_yield: float = Field(0.05, description="alt-yield floor, decimal fraction; default = Aave USDC Arbitrum p50 proxy 2026-04")
    fill_loss_coarse_bound: float = Field(0.02, description="pre-deploy coarse fill-loss rate floor; refined in Phase 3")

class MarketCalibration(StrictBase):
    market_id: str
    scale: float               # e.g. 5.591e12 per ETHUSDT calibration
    s: float
    clo_lower_thresh: float
    clo_upper_thresh: float
    fIndex_oracle_address: str  # 0x... per boros_bot_guide.md §Oracle addresses
    maturity_ts: int            # unix ts

class BotConfig(StrictBase):
    mode: Literal['live', 'paper', 'backtest', 'ingest', 'screen']
    strategy_version: str       # semver; stamped into manifest
    market_id: str
    side: Literal['long', 'short']
    root_wallet_address: str    # for wallet_address_hash in manifest
    agent_wallet_address: str

    strategy: StrategyConfig
    execution: ExecutionConfig
    data: DataConfig
    infra: InfraConfig
    screener: ScreenerConfig
    markets: list[MarketCalibration] = Field(default_factory=list, max_length=1)  # v0.5 cap
```

**Reflection-based manifest writer (INFRA-06):**

```python
# python/src/boros_brain/manifest/writer.py
import json, hashlib, subprocess
from pathlib import Path
from ulid import ULID
from datetime import datetime, timezone
from ..config.schema import BotConfig

def build_run_manifest(
    config: BotConfig,
    parent_run_id: str | None = None,
) -> dict:
    git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
    # `git diff --quiet` → 0 means clean, 1 means dirty
    git_dirty = subprocess.call(['git', 'diff', '--quiet']) != 0

    # Reflection: model_dump(mode='json') walks every nested StrictBase recursively.
    # Because every sub-model also has extra='forbid', adding a knob is a schema change
    # → schema round-trip test fails → pre-commit rejects the commit if knob isn't in schema.
    knob_tree = config.model_dump(mode='json')

    return {
        "run_id": str(ULID()),
        "parent_run_id": parent_run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": config.mode,
        "strategy_version": config.strategy_version,
        "git_sha": git_sha,
        "git_dirty": git_dirty,
        "market_id": config.market_id,
        "side": config.side,
        "wallet_address_hash": hashlib.sha256(
            config.root_wallet_address.lower().encode()
        ).hexdigest()[:16],
        "config": knob_tree,        # ← full knob tree via reflection
        "chain_time_drift_at_start_seconds": None,  # populated by INFRA-14 before first log
        "agent_wallet_gas_balance_at_start": None,  # populated in Phase 6, field reserved here
    }
```

**Round-trip test (INFRA-02) — skeleton:**

```python
# python/tests/test_config_round_trip.py
def test_config_round_trip_idempotent(tmp_path):
    # 1. Load strategy/v0.5-default.yaml → BotConfig
    # 2. model_dump(mode='json') → write temp YAML
    # 3. Load temp YAML → BotConfig2
    # 4. Assert BotConfig == BotConfig2 (frozen + extra=forbid → exact equality)
    ...

def test_unknown_key_raises():
    with pytest.raises(ValidationError):
        BotConfig.model_validate({"unknown_key": "x", ...})

def test_manifest_contains_all_knobs():
    cfg = load_test_config()
    manifest = build_run_manifest(cfg)
    # Assert every field in cfg.model_fields is reachable in manifest["config"]
    ...
```

### Pattern 2: SQLite WAL + single-writer-per-table (INFRA-03)

**What:** SQLite with `PRAGMA journal_mode=WAL;` allows many concurrent readers + one writer. Across two processes (Python brain + TS hands) both writing the same file, serialization is at the file-level, not table-level — SQLite has no table-level locking primitive in vanilla builds. The "single-writer-per-table" discipline is therefore **an application-level convention enforced by code review + lint**, not a hardware lock.

**When to use:** Every table must have an explicit owner. Planner assigns an owner to each of the 8 tables; writer modules are the only place `INSERT`/`UPDATE`/`UPSERT` live.

**How it's enforced (concrete):**

1. **Directory discipline:** `python/src/boros_brain/state/writers/{table}.py` contains ALL write paths for that table. Any other Python module that tries `INSERT INTO <table>` fails a lint check.
2. **Lint rule:** a custom pre-commit check `scripts/sqlite_writer_lint.py` greps for `"INSERT INTO "` / `"UPDATE "` / `"ON CONFLICT"` outside the designated writer module for each table name. Violations fail commit.
3. **TS side:** `ts/src/boros_hands/state/sqlite_writer.ts` is the ONLY TS file that contains write SQL, and only for the two tables it owns (`tx_receipts`, `open_orders`).
4. **Run-time reality:** SQLite WAL serializes writers at the file lock. "Single-writer-per-table" is about code clarity / audit — not concurrency. The hardware side is: one writer at a time gets `BEGIN IMMEDIATE`, others retry.

**Why not an ORM:** ORMs add a layer of implicit query construction that defeats grep-for-`INSERT`-in-wrong-module lint. Raw SQL is loud, grep-able, and the whole schema is ~200 lines.

**Source:** [VERIFIED: sqlite.org/wal.html — WAL allows one writer + many readers]; [CITED: oldmoe.blog/2024/07/08/the-write-stuff — confirmed WAL single-writer serialization].

### Pattern 3: ZMQ priority-lane KILL + 5s heartbeat + lost-sibling protocol (INFRA-05)

**What:** A separate ZMQ PUSH/PULL socket carries per-order commands; a ZMQ PUB/SUB carries events. **Priority in ZMQ is a message-attribute convention, not a socket feature** — ZMQ does NOT have native priority queues. The KILL lane is implemented as either (a) a *second* PUSH/PULL socket solely for KILL/EMERGENCY_CLOSE messages that `hands` polls first on every event loop tick, or (b) an explicit priority field on every message with `hands` draining priority=9 first. Research recommends **(a) — a separate socket**, because it gives ZMQ's own FIFO behavior per socket + guarantees KILL isn't buried behind queued PLACE cmds.

**5s heartbeat both directions:** Python `PUB`s `heartbeat:brain` every 5s; TS `SUB`s it and tracks `last_heartbeat_at`. Same in reverse. If 3 consecutive misses (15s elapsed without heartbeat) → "lost sibling."

**Lost-sibling protocol (concrete):**

| Scenario | Brain action | Hands action |
|---|---|---|
| `brain` lost `hands` heartbeat (≥15s) | Enter `no-dispatch` state: stop emitting PLACE cmds. If oracle is stale during the outage, emit CANCEL_ALL on the KILL lane (which hands *may* still receive if it's just a PUB hiccup). Write a `LOST_SIBLING` event to NDJSON log. Surface alert. | (doesn't know brain is gone from hands's perspective) |
| `hands` lost `brain` heartbeat (≥15s) | — | Enter `self-preserve` mode: on the next WS fill, fire the pre-signed cancel from cache **without waiting for brain authorization**. After 30s still no brain heartbeat → emit CANCEL_ALL using pre-signed cache (defense against unsupervised fills). Log `LOST_SIBLING`. |
| Heartbeat recovers | Exit `no-dispatch` | Exit `self-preserve` |
| Both sides restarted by launchd | Each side reconnects to the IPC endpoint (ZMQ auto-reconnects). Reconcile state via SQLite + REST poll of `/v2/accounts/all-limit-orders`. | Same |

**KILL priority lane implementation sketch:**

```python
# python/src/boros_brain/bus/cmd.py
class CmdBus:
    def __init__(self, cfg):
        self.ctx = zmq.asyncio.Context()
        # Main cmd socket — normal-priority PLACE/CANCEL/CLAIM
        self.cmd = self.ctx.socket(zmq.PUSH)
        self.cmd.bind(cfg.zmq_cmd_endpoint)
        # Separate KILL lane — brain PUSHes emergency cmds here
        self.kill = self.ctx.socket(zmq.PUSH)
        self.kill.bind(cfg.zmq_cmd_endpoint + ".kill")  # ipc:///tmp/boros.cmd.kill

    async def send_cmd(self, msg): await self.cmd.send_json(msg)
    async def send_kill(self, msg): await self.kill.send_json(msg)
```

```typescript
// ts/src/boros_hands/bus/cmd_listener.ts
// Poll KILL lane first on every event loop tick, then drain normal cmd lane
const killSock = await new zmq.Pull({ receiveHighWaterMark: 1000 });
await killSock.connect("ipc:///tmp/boros.cmd.kill");
const cmdSock = await new zmq.Pull();
await cmdSock.connect("ipc:///tmp/boros.cmd");

// Drain loop: KILL first, then CMD
while (running) {
  for await (const [msg] of killSock) { await handleKill(msg); }   // never blocks
  for await (const [msg] of cmdSock) { await handleCmd(msg); }
}
```

**Heartbeat implementation — use ZMQ's own `ZMQ_HEARTBEAT_IVL` / `ZMQ_HEARTBEAT_TIMEOUT` socket options for transport-level keepalive, PLUS an application-level heartbeat message on the events PUB/SUB topic for logical liveness.** ZMQ-level heartbeats detect broken connections (ZMTP 3.1 ping); app-level detects a process that's stuck but connected. You need both.

**Source:** [CITED: api.zeromq.org/4-2:zmq-setsockopt — ZMQ_HEARTBEAT_IVL/TIMEOUT verified]; [CITED: learning-0mq-with-pyzmq.readthedocs.io — PUSH/PULL basics]; [ASSUMED: priority-lane as separate socket — this is a common pattern not uniquely documented; alternative is ZMQ ROUTER/DEALER + message priority which is heavier].

### Pattern 4: structlog + pino log contract (INFRA-07)

**What:** Both tiers emit NDJSON log records with the **same field names and types**, so `jq 'select(.run_id=="…")' var/logs/*/*.jsonl` returns the union across both processes. `run_id` is propagated via `contextvars` on the Python side (survives `asyncio.create_task` automatically; critical PITFALLS D2 requirement); on the TS side via a shared `pino.child({ run_id })` logger plus `AsyncLocalStorage` for request-scoped propagation.

**Shared record schema (minimum fields):**

```json
{
  "ts": "2026-04-23T14:23:17.123456+00:00",
  "level": "info",
  "event": "MARKET_TICK",
  "run_id": "01HXXABC...",
  "tier": "brain",                    // "brain" or "hands"
  "logger": "boros_brain.data.market_loop",
  "module": "market_loop",
  "function": "on_tick",
  "pid": 12345,
  "thread": "MainThread",
  // event-specific keys:
  "market_id": "ETHUSDT-29MAY2026",
  "mid_rate_bps": 1234.5,
  ...
}
```

**Python side (structlog):**

```python
# python/src/boros_brain/logging/structlog_setup.py
import structlog, orjson, logging
from structlog.contextvars import bind_contextvars, clear_contextvars

def configure_logging(run_id: str, tier: str = "brain") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # ← pulls run_id + any request-scoped context
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.PROCESS,
                    structlog.processors.CallsiteParameter.THREAD_NAME,
                ]
            ),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(serializer=orjson.dumps),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(
            file=open(f"var/logs/{today}/{run_id}.brain.log.jsonl", "ab", buffering=0)
        ),
        cache_logger_on_first_use=True,
    )
    bind_contextvars(run_id=run_id, tier=tier)
```

**TS side (pino) — same record shape:**

```typescript
// ts/src/boros_hands/logger.ts
import pino from 'pino';
import { AsyncLocalStorage } from 'node:async_hooks';

export const ctxStore = new AsyncLocalStorage<{ run_id: string }>();

const base = pino({
  level: 'info',
  timestamp: () => `,"ts":"${new Date().toISOString()}"`,
  formatters: {
    level: (label) => ({ level: label }),   // matches structlog's "level" field name
    bindings: (b) => ({ pid: b.pid, tier: 'hands', logger: b.name }),
  },
  mixin: () => {
    const ctx = ctxStore.getStore();
    return ctx ? { run_id: ctx.run_id } : {};
  },
},
pino.destination({
  dest: `var/logs/${today}/${run_id}.hands.log.jsonl`,
  sync: false,
}));
export const log = base;
```

**Gotcha:** `asyncio.create_task` **does** copy `contextvars` by default in Python 3.7+ — so `run_id` propagates to child tasks automatically. `asyncio.to_thread` also carries context. `asyncio.run_coroutine_threadsafe` does NOT — flag in `brain` code reviews. [CITED: structlog.org/en/stable/contextvars.html — Python docs confirm asyncio task-local behavior via `contextvars`.]

**Source:** STACK.md + [CITED: structlog.org/en/stable/contextvars.html]; [CITED: github.com/pinojs/pino — child logger + mixin pattern verified]; [CITED: nodejs.org/api/async_context.html — AsyncLocalStorage verified].

### Pattern 5: Architecture YAML + Mermaid + drift lint (INFRA-08, INFRA-09, PROTO-02)

**What:** `docs/architecture.yml` is the machine-readable manifest; `docs/ARCHITECTURE.md` contains the Mermaid diagram seeded from ARCHITECTURE.md §1 + §2. The lint script parses Python source via `ast`, extracts the declared module/function/CLI-command inventory, diffs against `architecture.yml`, and fails commit on drift.

**`architecture.yml` schema draft (concrete — planner refines):**

```yaml
# docs/architecture.yml
version: 1
nodes:
  # process nodes
  - id: brain
    type: process
    language: python
    entrypoint: python/src/boros_brain/main.py
  - id: hands
    type: process
    language: typescript
    entrypoint: ts/src/boros_hands/main.ts
  # module nodes
  - id: brain.data.market_loop
    type: module
    process: brain
    path: python/src/boros_brain/data/market_loop.py
    public_functions:
      - on_tick
      - start_loop
  - id: brain.data.rpc_client.get_latest_fIndex
    type: function
    process: brain
    path: python/src/boros_brain/data/rpc_client.py
    line_hint: 42
  # cli command
  - id: cli.screen
    type: cli_command
    process: brain
    entry: "boros-brain screen"
    module: brain.screener.economics_gate
  # config knob — every Pydantic field is a node
  - id: config.strategy.voluntary_cancel_forfeits_accumulated
    type: config_knob
    pydantic_path: BotConfig.strategy.voluntary_cancel_forfeits_accumulated
    default: false
    referenced_by: [brain.decision.engine]     # ← code paths that read the knob
  # external dependency
  - id: ext.boros_rest
    type: external
    url: "https://api.boros.finance/open-api/v1"
  - id: ext.arbitrum_rpc
    type: external
    url: "https://arb1.arbitrum.io/rpc"

edges:
  - from: brain.data.market_loop
    to: ext.boros_rest
    type: reads
    notes: "DATA-06: /markets poller; DATA-11: E_liq poller"
  - from: brain.data.rpc_client
    to: ext.arbitrum_rpc
    type: calls
    notes: "DATA-07: fIndexOracle.getLatestFIndex + latestAnnualizedRate"
  - from: brain.data.market_loop
    to: state.clo_history
    type: writes
  - from: brain.decision.engine
    to: config.strategy.voluntary_cancel_forfeits_accumulated
    type: depends-on-config
```

**Lint script approach (INFRA-09):**

```python
# scripts/architecture_lint.py
import ast, sys, yaml
from pathlib import Path

def extract_code_inventory(src_root: Path) -> dict:
    """Walk every *.py file, AST-parse, collect:
       - Module definitions (every file in boros_brain/)
       - Public functions (names not starting with '_') at module scope
       - Import edges (to detect 'calls' between modules)
       - Pydantic BaseModel fields (to detect config_knob nodes)
    """
    inventory = {"modules": set(), "functions": set(), "edges": set(), "config_knobs": set()}
    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        # ... walk AST, populate inventory
    return inventory

def compare(inventory: dict, yml: dict) -> list[str]:
    violations = []
    declared_modules = {n['id'] for n in yml['nodes'] if n['type'] == 'module'}
    code_modules = inventory['modules']
    for m in code_modules - declared_modules:
        violations.append(f"Code defines module '{m}' not in architecture.yml")
    for m in declared_modules - code_modules:
        violations.append(f"architecture.yml declares module '{m}' not found in code")
    # ... repeat for functions, knobs, edges
    return violations

if __name__ == "__main__":
    inv = extract_code_inventory(Path("python/src/boros_brain"))
    yml = yaml.safe_load(Path("docs/architecture.yml").read_text())
    vs = compare(inv, yml)
    if vs:
        print("\n".join(vs), file=sys.stderr)
        sys.exit(1)
```

**Granularity rule** (per ARCHITECTURE.md §9 Anti-pattern 8): nodes are modules + public functions + CLI commands + named config knobs + external dependencies. **NOT** private helpers, not every dataclass field. Keeps diagram readable.

**Source:** [CITED: Python `ast` stdlib — verified pattern]; [CITED: python docs for `ast.walk`]; [ASSUMED: custom-built, no off-the-shelf tool catches Pydantic-knob-in-YAML matching precisely; `pyan3` and others are call-graph-only].

### Pattern 6: dotenvx + macOS Keychain (INFRA-12)

**What:** `.env.vault` is committed (AES-256 encrypted); `.env.keys` contains `DOTENV_PRIVATE_KEY_PRODUCTION` (or `_LIVE`, etc. per dotenvx convention) and is gitignored. Under launchd (headless), the private key is stored in macOS Keychain under the operator's login keychain. A wrapper script fetches the key via `security find-generic-password` before invoking the bot.

**Concrete pattern:**

```bash
# One-time operator setup (run once, interactive)
# 1. Generate .env.vault from plaintext .env
dotenvx encrypt
# → writes .env.vault (commit) and .env.keys (gitignore)

# 2. Store the private key in Keychain
security add-generic-password \
    -s "boros-bot-dotenvx-key" \
    -a "$USER" \
    -w "$(grep DOTENV_PRIVATE_KEY_PRODUCTION .env.keys | cut -d'=' -f2 | tr -d '\"')"
# ← password only prompted once; marked accessible to launchd jobs of this user
```

**launchd plist invokes a wrapper script that resolves the key:**

```bash
# scripts/boros-brain-wrapper.sh
#!/bin/bash
set -euo pipefail
cd "$HOME/projects/boros"
export DOTENV_PRIVATE_KEY_PRODUCTION="$(security find-generic-password \
    -s 'boros-bot-dotenvx-key' -a "$USER" -w)"
exec dotenvx run -- uv run python -m boros_brain.main --mode=live
```

**Plist references the wrapper, not `dotenvx` directly:**

```xml
<key>ProgramArguments</key>
<array>
    <string>/bin/bash</string>
    <string>/Users/USER/projects/boros/scripts/boros-brain-wrapper.sh</string>
</array>
```

**Known gotchas (verified):**

1. **Keychain ACL under launchd**: items created via `security add-generic-password` are by default restricted to the creating app (terminal). For launchd-spawned processes, add `-A` flag to allow all apps ("access any application") OR use the launch agent's `UserName` matching the keychain owner — headless launchd agents of the same UID can access items without extra ACLs if `-A` is set. Use `-A` (the threat model is "someone with local access to my laptop" — already worse than Keychain compromise anyway).
2. **`security` CLI blocks on GUI prompt** if the keychain is locked. For headless laptop reboots, either ensure keychain is unlocked at login, or switch to the `/Library/Keychains/System.keychain` with a different ACL model (v2 consideration, not worth the complexity at $100 scale).
3. **`dotenvx decrypt`** is for debugging only — never in production launchd wrapper.

**Source:** [CITED: dotenvx.com/docs/quickstart/encryption — encryption model]; [CITED: dotenvx.com/docs/advanced/decrypt — decrypt mechanics]; [CITED: `security add-generic-password -A` flag — Apple developer docs]; [CITED: github.com/sorah/envchain — pattern for OS-keychain env injection, alternative approach]; [ASSUMED: launchd-Keychain interaction — pattern is widely used by macOS dev teams but not in dotenvx official docs directly].

### Pattern 7: launchd LaunchAgent plists (INFRA-13)

**Plist template** (one per process — `com.boros.brain.plist`, `com.boros.hands.plist`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.boros.brain</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/USER/projects/boros/scripts/boros-brain-wrapper.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/USER/projects/boros</string>

    <key>RunAtLoad</key>
    <true/>

    <!-- KeepAlive: restart on any exit EXCEPT clean exit 0 -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <!-- ThrottleInterval: min seconds between restarts (default 10; raise to 30 to avoid fork storms) -->
    <key>ThrottleInterval</key>
    <integer>30</integer>

    <!-- Capture stdout/stderr into structured log directory; structlog writes JSON lines too,
         but anything that escapes structlog (uncaught stack traces etc.) lands here -->
    <key>StandardOutPath</key>
    <string>/Users/USER/projects/boros/var/logs/supervisor/brain.stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/USER/projects/boros/var/logs/supervisor/brain.stderr.log</string>

    <!-- Environment: minimal; secrets resolved by wrapper via Keychain -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>/Users/USER</string>
    </dict>
</dict>
</plist>
```

**Install:**

```bash
cp scripts/launchd/com.boros.brain.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.boros.brain.plist
launchctl enable gui/$(id -u)/com.boros.brain
launchctl kickstart -k gui/$(id -u)/com.boros.brain  # start immediately
```

**Known gotchas (all verified):**

1. **Exit code 78 (`EX_CONFIG`)** disables KeepAlive permanently — launchd interprets it as "operator misconfigured, don't loop." Never exit with 78 from user code. Reserve for "config schema invalid, cannot proceed." [CITED: github.com/NousResearch/hermes-agent/issues/5589]
2. **Clean exit 0 does NOT trigger KeepAlive restart** when `SuccessfulExit=false`. If the bot should always restart (including after clean shutdown), use `<key>KeepAlive</key><true/>` instead of the dict form. For our case, clean shutdown means operator intentionally stopped — do NOT restart. Keep the dict form. [CITED: launchd.info + medium.com/@chetcorcos]
3. **ThrottleInterval default is 10s** — if the bot crashes immediately on startup (bad config), launchd would spin up 6 processes/min. Setting to 30 gives the operator time to notice and fix. [CITED: manpagez.com/man/5/launchd.plist]
4. **Working directory not preserved across `launchctl` invocations** — must set `WorkingDirectory` explicitly. [CITED: discussions.apple.com/thread/2755309]
5. **Agent (user) vs Daemon (system) distinction**: `LaunchAgents/` under `~/Library/` runs as the logged-in user and is active only while that user is logged in. `LaunchDaemons/` under `/Library/` runs as root at boot. For a personal bot on operator's laptop, LaunchAgent is correct.
6. **SIGTERM signal handling**: launchd sends SIGTERM on stop. Both Python and Node processes must install handlers to flush logs, close ZMQ sockets, and commit SQLite transactions before exiting. Otherwise the final NDJSON buffers + in-flight SQLite transactions are lost.
7. **`launchctl` (user-facing CLI) vs `launchd` (the daemon)**: always use `launchctl`; never invoke `launchd` directly. The `bootstrap` / `bootout` commands replace the older `load` / `unload` since macOS 10.11 — use `bootstrap` for newer macOS. [CITED: keith.github.io/xcode-man-pages/launchd.plist.5.html]

**Source:** [CITED: launchd.info]; [CITED: medium.com/@chetcorcos/a-simple-launchd-tutorial]; [CITED: github.com/tjluoma/launchd-keepalive]; [CITED: manpagez.com/man/5/launchd.plist]; [VERIFIED: Apple's own `launchd.plist(5)` manpage]; Launch-code-78 gotcha [CITED: github.com/NousResearch/hermes-agent/issues/5589].

### Pattern 8: fIndexOracle decoding (DATA-07)

**Source of truth:** `boros_bot_guide.md` §fIndex Oracle L187-217 (verified 2026-04-23 during this research via grep).

**Known addresses** (per boros_bot_guide.md L486-489):

| Market | fIndexOracle address |
|---|---|
| Binance ETHUSDT 29-May-2026 | `0x1950dc94e3063267049482f075af72107eb79352` |
| Binance ETHUSDT 26-Jun-2026 | `0x9dd097e8e7b18a79ac86ddac72d0cdf72017198c` |
| Binance ETHUSDT 25-Sep-2026 | `0x7fe191632c66ddbd14d6fbe1e331744b894a2b7b` |
| BTCUSDT 29-May-2026 | (from `/markets` API response — `fIndexOracle` field on each market object) |

**ABI & selectors** (per boros_bot_guide.md L216-217):

```
getLatestFIndex()      selector = 0xbd63342e  →  returns (bytes26 packed into bytes32)
latestAnnualizedRate() selector = 0x972b365a  →  returns (int256, 1e18 precision)
```

**Decoding the bytes26 packed payload** (per boros_bot_guide.md L202-213):

```
val208 = int(payload[-26:], 16)   # the bottom 26 bytes (208 bits) of the returned bytes32

fTime        = (val208 >> 176) & ((1 << 32) - 1)     # top 32 bits: unix timestamp
floatingIndex = (val208 >>  64) & ((1 << 112) - 1)  # middle 112 bits, signed int112 — 1e18 precision
if floatingIndex >= (1 << 111):
    floatingIndex -= (1 << 112)                      # sign extension
feeIndex     = val208 & ((1 << 64) - 1)              # bottom 64 bits, uint64
```

**web3.py concrete implementation:**

```python
# python/src/boros_brain/data/rpc_client.py
from web3 import AsyncWeb3
from web3.providers.rpc import AsyncHTTPProvider

FINDEX_ABI = [
    {"name": "getLatestFIndex",      "inputs": [], "outputs": [{"type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"name": "latestAnnualizedRate", "inputs": [], "outputs": [{"type": "int256"}],   "stateMutability": "view", "type": "function"},
]

class FIndexReader:
    def __init__(self, w3: AsyncWeb3, oracle_address: str):
        self.oracle = w3.eth.contract(address=oracle_address, abi=FINDEX_ABI)
        self._cache = {"value": None, "ts": 0.0}
        self._ttl = 1.0

    async def get_latest_fIndex(self) -> dict:
        now = time.time()
        if self._cache["value"] and now - self._cache["ts"] < self._ttl:
            return self._cache["value"]
        raw = await self.oracle.functions.getLatestFIndex().call()  # bytes32
        val208 = int.from_bytes(raw[-26:], "big")
        fTime = (val208 >> 176) & ((1 << 32) - 1)
        floatingIndex = (val208 >> 64) & ((1 << 112) - 1)
        if floatingIndex >= (1 << 111):
            floatingIndex -= (1 << 112)
        feeIndex = val208 & ((1 << 64) - 1)
        result = {"fTime": fTime, "floatingIndex": floatingIndex, "feeIndex": feeIndex}
        self._cache = {"value": result, "ts": now}
        return result

    async def latest_annualized_rate(self) -> int:
        # 1e18-precision signed int — convert to APR float as: val / 1e18
        return await self.oracle.functions.latestAnnualizedRate().call()
```

**fIndex_display conversion** (per boros_bot_guide.md L175-178):

```
fIndex_display = 10000 + floatingIndex_raw / SCALE
```

For Binance ETHUSDT 29-May-2026, `SCALE ≈ 5.591e12` (calibrated per market — verify per market type by grepping boros_bot_guide.md or deriving from two `cloLowerThresh`/`cloUpperThresh` + fIndex pairs).

**Source:** [VERIFIED: boros_bot_guide.md L187-217 grep 2026-04-23]. [ASSUMED: ABI exactly as stated — planner should verify by loading the contract at one of the known addresses on Arbiscan and fetching the verified contract code; boros_bot_guide.md is project-internal documentation, not protocol-authored.]

### Pattern 9: NDJSON ingester → partitioned parquet → DuckDB read (DATA-01..05)

**Polars ingester** writes partitioned parquet; DuckDB reads both parquet partitions and live SQLite tables through `sqlite_scanner`.

```python
# python/src/boros_brain/data/ingester/market_trades.py
import polars as pl

SCHEMA = pl.Schema({
    "eventIndex": pl.UInt64,
    "blockTimestamp": pl.UInt64,
    "datetime": pl.Datetime("us", "UTC"),
    "rate": pl.Float64,
    "side": pl.Enum(["long", "short"]),
    "size": pl.Utf8,       # wei string — cast to UInt128 below
    "txHash": pl.Utf8,
})

def ingest_market_trades(ndjson_path: Path, market_id: str, out_root: Path) -> None:
    lf = pl.scan_ndjson(ndjson_path, schema=SCHEMA)
    # DATA-01 assertions
    df = lf.collect()
    assert df["eventIndex"].is_not_null().all(), f"eventIndex missing rows in {ndjson_path}"
    # wei→float explicit (size field is wei string per plan_comparison.md)
    df = df.with_columns(
        pl.col("size").cast(pl.UInt128).alias("size_wei"),
        (pl.col("size").cast(pl.UInt128).cast(pl.Float64) / 1e18).alias("size_float"),
    ).drop("size")
    # Partition by market + year-month for DuckDB efficiency
    df.write_parquet(
        out_root,
        use_pyarrow=True,
        pyarrow_options={"partition_cols": ["market_id", "year_month"]},
    )
```

**DuckDB wires parquet + SQLite** (read-only analytical layer):

```python
# python/src/boros_brain/duckdb_layer/setup.py
import duckdb

def open_analytical_conn(sqlite_path: str, parquet_root: str):
    con = duckdb.connect(":memory:", read_only=False)  # memory conn; extensions need write
    con.install_extension("sqlite_scanner")
    con.load_extension("sqlite_scanner")
    con.execute(f"CALL sqlite_attach('{sqlite_path}', overwrite=true)")
    # parquet views
    con.execute(f"""
        CREATE VIEW market_trades AS
        SELECT * FROM read_parquet('{parquet_root}/market_trades/**/*.parquet', hive_partitioning=true)
    """)
    return con
```

**AMM conservation assertion (DATA-05) — inline in `order_book.py` ingester:**

```python
def assert_amm_conservation(raw: pl.DataFrame, combined: pl.DataFrame) -> None:
    """For every (snapshot_ts, tick), combined_size - raw_size >= 0.
       Violations indicate snapshot time-skew or tick-aggregation mismatch (PITFALLS B3)."""
    joined = raw.join(combined, on=["snapshot_ts", "tick"], how="outer", coalesce=True, suffix="_combined")
    neg = joined.filter(pl.col("size_combined") - pl.col("size") < 0)
    if neg.height > 0:
        # Fail loud, don't silently absorb
        raise AmmConservationViolation(
            f"AMM conservation violated on {neg.height} tick-rows; first 5: {neg.head(5).to_dicts()}"
        )
```

**Source:** STACK.md §polars [VERIFIED]; [CITED: docs.pola.rs/api/python/dev/reference/api/polars.DataFrame.write_parquet.html]; [CITED: duckdb.org/docs/stable/guides/python/polars — integration]; [CITED: duckdb.org/docs/current/data/partitioning/partitioned_writes]; AMM conservation is project-specific, no external source.

### Pattern 10: Economics kill-switch math (DATA-09)

The goal is a **conservative** per-market filter: drop markets whose reward APR on collateral doesn't beat `alt_yield + estimated_fill_loss_rate`. The math is stated in roadmap L71 as:

```
R_apr_on_collateral = R_share_per_epoch × epochs_per_year / required_collateral
```

**Where does each input come from?**

| Input | Phase-1 source | Confidence |
|---|---|---|
| `R_share_per_epoch` | Computed per-market from `E_liq_per_epoch × side_split × (Q_me × t_frac) / (Σ_others + Q_me × t_frac)` with `Q_me = protocol_min` and `t_frac = 1.0` (assume bot posts the full epoch) | HIGH — `E_liq_per_epoch` + side-split are polled from `/markets` per DATA-11; `Σ_others` from `/v2/accounts/all-limit-orders` or order-book aggregation |
| `epochs_per_year` | Constant = 52 (weekly epochs, Fri 00:00 UTC → Thu 23:59 UTC per PROJECT.md L63) | HIGH |
| `required_collateral` | $100 (per $100-collateral premise) OR the `Q_min` × maintenance-margin requirement — whichever is larger; screener uses $100 as floor since $100 is the operator commitment | HIGH |
| `alt_yield` | **Aave USDC on Arbitrum supply APY, 2026-04** ≈ 3–7% decimal (0.03–0.07). Recommend default `0.05` (5%) as conservative mid-range per web search on 2026-04-23. | MEDIUM — alternatives in same ballpark: Morpho USDC ≈ similar; Arbitrum-native stablecoin pools 4–8%. `0.05` is a defensible floor. |
| `estimated_fill_loss_rate` | Phase 1 **coarse bound** (Phase 3's LossModel produces the real number). Coarse bound: `P(fill per epoch) × E[loss\|fill]_coarse`. Without Phase 2/3 fit, use worst-case heuristic: assume `P(fill per epoch) ≤ 0.10` (no market should qualify if > 10% weekly fill rate at CLO edge — if it does, rewards can't compensate), `E[loss\|fill]_coarse ≈ 0.05` (5% of notional, based on basis volatility bounds in plan_comparison data). Product ≈ 0.005 = 0.5%. Add taker fee 0.05% + settlement fee bound + $1 one-time entrance fee amortization = **round up to `0.02` (2%) as Phase 1 coarse bound.** Planner adjusts based on observed data. | LOW — assumption to be refined in Phase 3; documented in LossModel scaffold. |

**Kill condition:**

```
drop(market) iff R_apr_on_collateral < alt_yield + fill_loss_coarse_bound
         = 0.05 + 0.02 = 0.07 (7% APR decimal)
```

**Empty-shortlist halt behavior:**

```python
# python/src/boros_brain/screener/economics_gate.py
def run_economics_gate(candidates: list[MarketCalibration], alt_yield: float, fill_loss_bound: float) -> list[str]:
    shortlist = []
    report_rows = []
    for m in candidates:
        r_apr = compute_r_apr_on_collateral(m)
        passes = r_apr > alt_yield + fill_loss_bound
        report_rows.append({"market_id": m.market_id, "R_apr": r_apr, "threshold": alt_yield + fill_loss_bound, "pass": passes})
        if passes:
            shortlist.append(m.market_id)
    write_kill_report(report_rows, out="var/reports/economics_gate.json")
    if not shortlist:
        raise ProjectHalt(
            "Empty shortlist after economics gate. "
            f"No market has R_apr > {alt_yield + fill_loss_bound:.3f}. "
            "Project halts. See var/reports/economics_gate.json"
        )
    return shortlist
```

**Output:** `configs/shortlist.yaml` (the 2–4 market shortlist that passes both DATA-08 screener + DATA-09 economics gate) OR a written kill report that halts Phase 2.

**Source:** Math per roadmap L71 + PROJECT.md L63 (weekly epochs). Aave benchmark [CITED: aave.com/markets; aavescan.com; confirmed USDC Arbitrum supply 3-7% in 2026-04 via web search]. Fill-loss coarse bound is [ASSUMED] — documented as a knob for Phase 3 refinement; flagged as A1 in the Assumptions Log.

### Anti-Patterns to Avoid (Phase 1-specific, inherited from PITFALLS)

- **Hot-reloading config mid-run** (PITFALLS §D4 / ARCHITECTURE.md §9 Anti-pattern 3). Schema reload = new `run_id` with `parent_run_id`, no exception.
- **Hand-maintained RUN_MANIFEST schema** (PITFALLS §D2). Reflection from Pydantic is mandatory.
- **Caching `E_liq_per_epoch` across polls** (ARCHITECTURE.md §9 Anti-pattern 4 / PITFALLS §A2). Every decision cycle polls live.
- **Shared mutable state via pickle / shared memory** (ARCHITECTURE.md §9 Anti-pattern 2). Everything cross-process goes through SQLite or ZMQ.
- **Using `orderbook:{marketId}:full:update` as fill-detection** (ARCHITECTURE.md §9 Anti-pattern 7). Per-account channel `account-updates:ROOT` is primary — but this is a Phase 6 concern; for Phase 1 the `/v2/accounts/all-limit-orders` REST poll is the fallback/reconciliation path and is already specified in ingester scope.
- **Single `Config` class per mode** (PITFALLS §D4). ONE BotConfig with mode-specific sections.
- **Ingester assuming `combined_size ≥ raw_size`** without the assertion (PITFALLS §B3). Loud fail.
- **Treating `eventIndex` as optional** (PITFALLS §B2). Every row is asserted; missing `eventIndex` market drops from shortlist.
- **Skipping the daily re-screen** (PITFALLS §A5). DATA-10 runs while Phase 2+ are building.

---

## Don't Hand-Roll

Phase 1 has a LOT of pre-built components that look small but are expensive to get right. Build them from libraries — don't hand-roll.

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Structured JSON logging with context propagation across async tasks | Custom `logging` wrapper + dict merging | `structlog` with `contextvars.merge_contextvars` processor (Python) + `pino` with `AsyncLocalStorage` + `mixin` (Node) | contextvar propagation across `asyncio.create_task` + `asyncio.gather` is NOT trivial; structlog already handles it and is ~2.6× faster than thread-local patterns [CITED: structlog docs]. Same story for pino. |
| ULID generation | Hand-coded encoder | `python-ulid` 3.x (Python) + `ulid` 2.x (Node) | 26-char Crockford base32 + monotonicity guard + 48-bit timestamp — library is ~30 lines used correctly, ~300 lines reimplemented poorly. |
| Encrypted env file | Plaintext `.env` + "rotate periodically" | `dotenvx` CLI (AES-256 + Secp256k1-protected key) | Rolling your own AES + KDF at the $100 scale is an anti-pattern; dotenvx is project-standard [CITED: dotenvx.com]. |
| SQLite migrations | Hand-written `ALTER TABLE` scripts | Alembic (Python) | Down-migrations, revision graph, safe concurrent dev — Alembic ships it. |
| ZMQ Python bindings + async integration | `socket` module with raw ZMQ frames | `pyzmq` with `zmq.asyncio.Context` | ZMQ frame format, identity frames, LINGER semantics are non-trivial; pyzmq integrates with asyncio directly. |
| ZMQ Node bindings | native C++ wrapper | `zeromq.js` 6.x | Same reasoning. |
| Arbitrum RPC call with retry + block-ID handling | httpx + hand-rolled JSON-RPC | `web3.py` 7.15 AsyncWeb3 + AsyncHTTPProvider | Retry, connection pooling, ABI encoding/decoding, block-identifier handling — all free. |
| NDJSON parsing at 72K+ rows/market | `json.loads` in a for loop | `polars.scan_ndjson` with column pruning + predicate pushdown | Lazy streaming + Arrow-backed = 5–10× faster, ~10× less memory for our shape. |
| Parquet partitioning | Hand-written directory tree | `polars.DataFrame.write_parquet(pyarrow_options={"partition_cols": [...]})` | Hive-style partitioning gets DuckDB predicate pushdown for free. |
| Analytical SQL over parquet + SQLite | Load NDJSON → pandas → pd.read_sql | `duckdb` with `sqlite_scanner` + `read_parquet` | Single SQL surface over both; pushdown; memory-efficient. |
| Pre-commit hook runner | Hand-rolled Git hook | `pre-commit` 4.x | Hooks-per-file-type, repository-local config, auto-install. |
| Python linter | separate flake8 + isort + black | `ruff` with `select = ["ALL"]` | Single tool, 10× faster, replaces 3. |
| Config file parsing | Hand-rolled YAML loader | Pydantic v2 `model_validate` on PyYAML-parsed dict | Typed, validated, defaulted, round-trippable. Zero loops. |
| Running bot under supervision | `nohup &` + cron check | launchd LaunchAgent plist | Native macOS supervision, survives reboots, KeepAlive + throttle built-in. |
| Chain time / NTP drift | `time.time()` + `ntpdate` shell call | web3.py `eth_getBlockByNumber("latest").timestamp` + 1s cache | The only time we care about is chain time (per PITFALLS §C7); stop comparing to NTP, compare to chain. |

**Key insight:** The Phase 1 temptation is to "just build a simple X." Every "simple X" is a footgun that compounds across the 8 remaining phases — e.g., a slightly wrong manifest schema makes every backtest result from Phase 5 un-reconcilable (PITFALLS §D2). Use the libraries; spend the saved time on the project-unique parts (economics-gate math, architecture lint rules, single-writer-per-table enforcement).

---

## Runtime State Inventory

**Not applicable.** Phase 1 is a *greenfield* phase — there is no prior runtime state to migrate, rename, or reconcile. The LLM Wiki seed (INFRA-10) has ~8 pages from Phase 0 that need to be added to the index but that's text assembly, not runtime state.

(Skipping the 5-category table — no prior system to inventory.)

---

## Common Pitfalls

Phase 1 is explicitly the phase that **absorbs** the most Engineering-Protocol pitfalls from PITFALLS.md. The list below is the subset the planner must verify is addressed by the end of Phase 1; every pitfall has a concrete prevention step already embedded in the requirements above.

### Pitfall 1: RUN_MANIFEST missing fields → analysis fabricates conclusions (PITFALLS §D2)

**What goes wrong:** A knob is added in code but forgotten in the manifest schema. Later, backtest vs paper divergence is analyzed against identical-looking manifests, engineer chases a ghost.
**How to avoid:** Pydantic `model_dump(mode='json')` reflection + a pre-commit test that initializes a dummy `BotConfig`, generates a manifest, and asserts `every field in BotConfig.model_fields appears in the manifest JSON`. If the assertion fails, the commit fails.
**Warning signs:** Manifest JSON field count < grep for `Config\.` references.
**Warning-sign test:** `test_manifest_contains_all_knobs.py` in the pre-commit suite.

### Pitfall 2: Dependency diagram drift (PITFALLS §D3)

**What goes wrong:** Code changes ship without `architecture.yml` updates; blast-radius review becomes fiction.
**How to avoid:** `scripts/architecture_lint.py` runs in pre-commit, diffs Python AST vs YAML, fails commits on drift.
**Warning signs:** `git log docs/ARCHITECTURE.md` commit count < `git log src/` commit count.
**Phase 1 verification:** deliberately add a new module in a test PR without touching `architecture.yml`; confirm the hook rejects.

### Pitfall 3: Config schema drift across backtest/paper/live (PITFALLS §D4)

**What goes wrong:** Three `Config` classes in three places; `max_position_size` means different things in each; live deploys with 100% size.
**How to avoid:** ONE `BotConfig` class; `mode: Literal[...]` field + mode-specific sub-models; `--mode live-dry-run` gate at Phase 8 re-uses the same schema.
**Warning signs:** Multiple `Config` classes in the codebase; similarly-named knobs appearing in multiple modules.
**Verification:** Phase 1 has exactly ONE `schema.py` in `python/src/boros_brain/config/`; grep for `class.*Config.*BaseModel` outside that file is a fail.

### Pitfall 4: Wiki decay — write-back skipped under time pressure (PITFALLS §D5)

**What goes wrong:** Agent finds something surprising during work, merges PR, never files wiki page. 10 sessions later, same edge case rediscovered.
**How to avoid:** `scripts/wiki_cite_lint.py` — any new file in `research/`, `decisions/`, `postmortem/` without a `[[wiki-link]]` fails commit.
**Warning signs:** Ratio of merged PRs to new/updated wiki pages > 3:1.
**Verification:** pre-commit hook test that creates a dummy `research/foo.md` with no link → hook rejects; with a link → passes.

### Pitfall 5: AMM conservation silently violated (PITFALLS §B3)

**What goes wrong:** `raw/` and `combined_{tickSize}/` snapshots from different timestamps produce negative AMM shares → replay engine miscounts fills.
**How to avoid:** Every combined snapshot runs the `combined_size(δ) − raw_book_size(δ) ≥ 0` assertion at ingest time. Violations raise `AmmConservationViolation`, ingest stops loud.
**Warning signs:** Any negative AMM share anywhere in the parquet output.
**Verification:** deliberately inject a mis-aligned snapshot in a test; assert the ingester refuses it.

### Pitfall 6: `eventIndex` missing on some markets (PITFALLS §B2)

**What goes wrong:** ETHUSDT has `eventIndex`; some other market may not. CV calculation is wrong; model class is wrong.
**How to avoid:** Ingester asserts `eventIndex` present + non-null on every `market-trades/` row for every market. Markets failing assertion are flagged and either excluded from shortlist or processed with a documented tied-timestamp inflation factor.
**Warning signs:** Any market's NDJSON batch has rows with `eventIndex` null or missing.
**Verification:** schema assertion in DATA-01 with an explicit fail path; Phase 1 exit gate requires cross-market probe to have run at least once.

### Pitfall 7: Historical reward-budget bias (PITFALLS §B6)

**What goes wrong:** Backtest uses current `E_liq_per_epoch` against historical trades → over-predicts P&L because protocol emission was probably lower historically.
**How to avoid:** DATA-11 polls forward and persists every reading to `reward_budget_history`. If historical reconstruction via distributor events is infeasible (likely), pre-pipeline data is explicitly marked `current_budget_synthetic=true` in the backtest output rows (Phase 5 concern, but the flag column exists in Phase 1 schema).
**Warning signs:** Paper claim amounts systematically lower than backtest-predicted claims.
**Verification:** `reward_budget_history` schema has a `data_source ENUM('polled', 'synthetic_current')` column from day one.

### Pitfall 8: Competition crowding in during engineering window (PITFALLS §A5)

**What goes wrong:** Shortlist passes economics gate on day 1; 3 months of engineering later, competitors have crowded in; shortlist has collapsed to 0 markets.
**How to avoid:** DATA-10 daily re-screen runs under launchd CalendarInterval. Operator sees shortlist changes within 24h, not at Phase 7 start.
**Warning signs:** `Q_total_in_range` on the shortlisted market has doubled since initial screening.
**Verification:** DATA-10 job is scheduled and observed to run on day 1.

### Pitfall 9: Outside-range wall (PITFALLS §A8)

**What goes wrong:** Participants park size just outside the CLO range for Maker Volume rewards, shielding our incentivized posts.
**How to avoid:** DATA-08 screener computes `depth_at_clo_edge` vs `depth_one_tick_outside_clo_edge`; ratio > 2 flags the market as "outside-range wall" for Phase 2 covariate inclusion.
**Warning signs:** Market has persistently higher depth one tick outside CLO edges than at edges.
**Verification:** screener output includes this ratio as a column in `var/reports/screener_metrics.json`.

### Pitfall 10: Clock drift (PITFALLS §C7)

**What goes wrong:** macOS sleep-wake leaves `time.time()` behind chain time; oracle-staleness breaker fires wrong.
**How to avoid:** INFRA-14 cache `chain_time` via `eth.get_block('latest').timestamp` with 1s TTL. All chain-relevant comparisons use cache, not `time.time()`. Startup check refuses to start if `|time.time() - chain_time| > 5s`.
**Warning signs:** Any log line comparing `time.time()` directly to a chain timestamp.
**Verification:** grep for `time.time()` in `brain/decision/`, `brain/data/`; any hit is a lint fail.

---

## Code Examples

(Most code examples live inline in the Architecture Patterns section above. This section repeats the load-bearing ones for quick reference in a planner.)

### Example 1: Pydantic manifest via reflection

See Pattern 1 above for the `build_run_manifest()` function. Key line:

```python
knob_tree = config.model_dump(mode='json')   # walks every nested StrictBase recursively
```

Source: [CITED: docs.pydantic.dev/latest/api/base_model/#pydantic.main.BaseModel.model_dump] — confirmed nested `BaseModel` recurses to dicts when `mode='json'`.

### Example 2: structlog with contextvars

See Pattern 4 above. Critical two lines:

```python
structlog.contextvars.merge_contextvars,   # ← processor that pulls contextvar-bound keys into every record
bind_contextvars(run_id=run_id, tier=tier)  # ← called once at startup; survives asyncio.create_task
```

Source: [CITED: structlog.org/en/stable/contextvars.html].

### Example 3: fIndexOracle bytes26 decoding

See Pattern 8 above. Critical decoding:

```python
val208 = int.from_bytes(raw[-26:], "big")
fTime = (val208 >> 176) & ((1 << 32) - 1)
floatingIndex = (val208 >> 64) & ((1 << 112) - 1)
if floatingIndex >= (1 << 111): floatingIndex -= (1 << 112)  # sign-extend int112
feeIndex = val208 & ((1 << 64) - 1)
```

Source: [VERIFIED: boros_bot_guide.md L202-213 grep 2026-04-23].

### Example 4: AMM conservation assertion

See Pattern 9 above. Inline in DATA-02 ingester step.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `pandas` for DataFrames | `polars` + `duckdb` split | 2024 mainstream shift | 5–10× speedup on our NDJSON + partitioned parquet shape. STACK.md verified. |
| `stdlib logging` + `python-json-logger` | `structlog` with `contextvars.merge_contextvars` | 2025 (structlog 25.x) | Zero-copy contextvars across async; automatic run_id propagation across `asyncio.create_task` |
| `ts-node` for Node TS | `tsx` (dev) + `tsc → dist/` (prod) | 2024 | ~25× faster startup; simpler production path |
| Hand-maintained JSON/YAML config | Pydantic v2 with `extra='forbid'` + `frozen=True` | Pydantic v2 (2023+) | Single-source schema; round-trip safe; reflection enables RUN_MANIFEST |
| `ws` 8.20 for Node WebSockets to Boros | `socket.io-client 4.x` | 2026-04-23 (P0-03 resolution) | Boros WS is Socket.IO, not raw WS — stack-change locked |
| Direct-to-chain tx submit | Send Txs Bot `/v2/agent/bulk-direct-call` + `/v2/agent/direct-call` | 2026-04-23 (P0-04) | Mandatory submission path; `submission_path` knob dropped |
| `blockTimestamp` for trade ordering | `eventIndex` | Pendle Boros launch (plan-verified) | Intra-block resolution; Arbitrum blocks are ~250ms so `blockTimestamp` ties |
| `nohup &` + cron health check | `launchd` LaunchAgent with KeepAlive + ThrottleInterval | macOS native | Survives reboots; automatic restart; no daemon to manage |
| Plaintext `.env` | `dotenvx` encrypted `.env.vault` + macOS Keychain | 2024 emerging standard | Safe to commit `.env.vault`; secrets still protected |

**Deprecated / outdated:**

- `pm2` for a single-process personal bot on macOS — launchd is lighter and native.
- `winston` for Node JSON logging — pino is faster and simpler.
- `ws 8.20` for Boros — not Socket.IO-compatible.
- `hawkeslib` — deprecated by author; use `tick`.
- `ethers` v6 on the TS side of this project — pins to viem per SDK.

---

## Validation Architecture

(Including per config — `workflow.nyquist_validation: true`.)

### Test Framework

| Property | Value |
|---|---|
| Framework (Python) | `pytest` 8.x with `pytest-asyncio` |
| Framework (TS) | `vitest` 2.x |
| Config file (Python) | `python/pyproject.toml` — `[tool.pytest.ini_options]` — CREATE in Wave 0 |
| Config file (TS) | `ts/vitest.config.ts` — CREATE in Wave 0 |
| Quick run command | `uv run pytest python/tests -x --tb=short` and `pnpm -C ts test --run` |
| Full suite command | `uv run pytest python/tests --cov=boros_brain` and `pnpm -C ts test --coverage` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| INFRA-02 | BotConfig round-trip YAML → model → YAML → model equal | unit | `uv run pytest python/tests/test_config_round_trip.py -x` | ❌ Wave 0 |
| INFRA-02 | Unknown key raises `ValidationError` | unit | `uv run pytest python/tests/test_config_round_trip.py::test_unknown_key_raises -x` | ❌ Wave 0 |
| INFRA-03 | SQLite WAL enabled + 8 tables created by migrations | integration | `uv run pytest python/tests/test_sqlite_migrations.py -x` | ❌ Wave 0 |
| INFRA-03 | Single-writer lint: `INSERT INTO decisions` only in `writers/decisions.py` | lint | `python scripts/sqlite_writer_lint.py` | ❌ Wave 0 |
| INFRA-04 | DuckDB `sqlite_scanner` attaches + reads `clo_history` | integration | `uv run pytest python/tests/test_duckdb_layer.py -x` | ❌ Wave 0 |
| INFRA-05 | ZMQ echo round-trip brain→hands→brain < 10ms | integration | `uv run pytest python/tests/test_zmq_echo.py -x` | ❌ Wave 0 |
| INFRA-05 | KILL lane preempts normal cmd | integration | `uv run pytest python/tests/test_zmq_kill_priority.py -x` | ❌ Wave 0 |
| INFRA-05 | 5s heartbeat + 15s lost-sibling transition | integration | `uv run pytest python/tests/test_heartbeat_lost_sibling.py -x --timeout 30` | ❌ Wave 0 |
| INFRA-06 | Manifest contains all `BotConfig` fields (reflection test) | unit | `uv run pytest python/tests/test_manifest_contains_all_knobs.py -x` | ❌ Wave 0 |
| INFRA-06 | Parent_run_id chain on knob change | integration | `uv run pytest python/tests/test_parent_run_id_chain.py -x` | ❌ Wave 0 |
| INFRA-07 | structlog JSON line contains `run_id` after `asyncio.create_task` | unit | `uv run pytest python/tests/test_structlog_contextvars.py -x` | ❌ Wave 0 |
| INFRA-07 | pino record shape == structlog record shape for same event | integration | `pnpm -C ts test src/logger.test.ts` | ❌ Wave 0 |
| INFRA-08 | `architecture.yml` parses as valid YAML matching schema | unit | `uv run pytest python/tests/test_architecture_yml_schema.py -x` | ❌ Wave 0 |
| INFRA-09 | Architecture lint rejects PR missing a module in yml | integration | `python scripts/architecture_lint.py --check-only` (fails in negative test) | ❌ Wave 0 |
| INFRA-10 | Wiki index.md contains all seeded pages in thematic + alphabetical | manual | operator reads `../LLM Wiki/workspaces/boros/wiki/index.md` | n/a |
| INFRA-11 | Wiki-cite hook rejects `research/foo.md` without `[[link]]` | integration | `uv run pytest python/tests/test_wiki_cite_lint.py -x` | ❌ Wave 0 |
| INFRA-12 | dotenvx decrypts `.env.vault` at startup via Keychain-fetched key | integration | `uv run pytest python/tests/test_dotenvx_keychain.py -x --skip-ci` | ❌ Wave 0 (operator-local) |
| INFRA-13 | `launchctl kickstart com.boros.brain` starts brain; `launchctl stop` stops cleanly | manual | operator runs + `launchctl print gui/$(id -u)/com.boros.brain` | n/a |
| INFRA-14 | Chain-time drift > 5s triggers warn log; > 30s halts | integration | `uv run pytest python/tests/test_chain_time_drift.py -x` | ❌ Wave 0 |
| DATA-01 | Ingester asserts `eventIndex` present on every row | unit | `uv run pytest python/tests/test_ingester_market_trades.py -x` | ❌ Wave 0 |
| DATA-02 | Hourly raw snapshots partitioned correctly | integration | `uv run pytest python/tests/test_ingester_order_book.py -x` | ❌ Wave 0 |
| DATA-05 | AMM conservation raises on negative share | unit | `uv run pytest python/tests/test_amm_conservation.py -x` | ❌ Wave 0 |
| DATA-06 | `/markets` poller writes `clo_history` row per change | integration | `uv run pytest python/tests/test_markets_poller.py -x` | ❌ Wave 0 |
| DATA-07 | fIndexOracle bytes26 decode matches expected `fTime/floatingIndex/feeIndex` | unit | `uv run pytest python/tests/test_fIndex_decode.py -x` | ❌ Wave 0 |
| DATA-08 | Screener produces shortlist YAML with ≥1 market or empty | integration | `uv run pytest python/tests/test_screener.py -x` | ❌ Wave 0 |
| DATA-09 | Economics gate halts with empty shortlist, passes with non-empty | unit | `uv run pytest python/tests/test_economics_kill_switch.py -x` | ❌ Wave 0 |
| DATA-10 | Daily re-screen job runs via launchd CalendarInterval (manual verify) | manual | operator observes next-day run in logs | n/a |
| DATA-11 | E_liq poller writes `reward_budget_history` row per cycle | integration | `uv run pytest python/tests/test_e_liq_poller.py -x` | ❌ Wave 0 |
| PROTO-01..04 | Covered by INFRA tests above | — | — | ❌ Wave 0 |
| PROTO-05 | Supersedence grep: any wiki page with stale finding fails lint | integration | `uv run pytest python/tests/test_supersedence_lint.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest python/tests -x --tb=short -k <affected_area>` (quick, <30s typical)
- **Per wave merge:** `uv run pytest python/tests --cov=boros_brain && pnpm -C ts test --coverage` (full suite, <5min expected)
- **Phase gate:** Full suite green + `pre-commit run --all-files` green before `/gsd-verify-work`

### Wave 0 Gaps

Phase 1 is greenfield — every test file listed above must be created in Wave 0 alongside its target module. The planner's Wave 0 should include:

- [ ] `python/pyproject.toml` with pytest config — covers framework install
- [ ] `python/tests/conftest.py` with shared fixtures (tmp SQLite path, dummy BotConfig, ZMQ test harness)
- [ ] `ts/vitest.config.ts` with minimal TS test config
- [ ] Every test file listed in the Req→Test table above — one per task, co-located with the module under test
- [ ] `scripts/architecture_lint.py` + test `test_architecture_lint.py`
- [ ] `scripts/wiki_cite_lint.py` + test `test_wiki_cite_lint.py`
- [ ] `scripts/sqlite_writer_lint.py` + test `test_sqlite_writer_lint.py`
- [ ] `scripts/supersedence_lint.py` + test `test_supersedence_lint.py`

Framework install:
- `uv sync` from `python/pyproject.toml` (installs pytest + pytest-asyncio + ruff + mypy)
- `pnpm -C ts install` (installs vitest + biome)

---

## Security Domain

(Included per `security_enforcement: absent → enabled by default`.)

### Applicable ASVS categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | **no** (single-operator, no multi-user) | — |
| V3 Session Management | **no** | — |
| V4 Access Control | **minimal** — single user, no ACL model | Keychain ACL on dotenvx private key |
| V5 Input Validation | **yes** — Pydantic `extra='forbid'` on BotConfig; Zod on ZMQ messages; polars schema on NDJSON | Pydantic v2 (Python) + Zod 3 (TS) |
| V6 Cryptography | **yes, limited to secret-at-rest** — never hand-roll | dotenvx AES-256 + Secp256k1-protected KEK |
| V7 Error Handling & Logging | **yes** — structured logs, no plaintext secrets in logs | structlog processor chain + regex redaction on sensitive keys |
| V9 Communication Security | **yes** — HTTPS for Boros REST, WSS for WS, TLS cert verify on | Default-on in httpx, viem, socket.io-client |
| V10 Malicious Code / Supply Chain | **yes** — dep pins + lockfiles | uv.lock + pnpm-lock.yaml committed; Dependabot / Renovate v2 concern; regular `uv sync --upgrade` audited by operator |
| V12 File and Resources | **yes** — SQLite file permissions | `chmod 600 var/state.sqlite` at creation |

### Known threat patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| Agent private key in plaintext env or committed file | Information Disclosure | dotenvx + Keychain (INFRA-12); `scripts/no_plain_keys.py` pre-commit hook greps for `^0x[a-fA-F0-9]{64}$` patterns in staged files |
| RPC URL with API key logged inadvertently | Information Disclosure | structlog redaction processor on keys matching `/api[-_]?key|token|secret/i`; URL query-string stripped before logging |
| SQLite file world-readable | Information Disclosure | `os.chmod(db_path, 0o600)` at DB creation + pre-commit test |
| ZMQ IPC socket under `/tmp/` readable by any local user | Information Disclosure | `ipc:///tmp/boros.cmd` — any local user on the machine can connect. Mitigation: set socket file permissions via `ZMQ_IPC_FILTER_UID`/`ZMQ_IPC_FILTER_PID` (ZMQ 4.1+), OR use a path under `~/` instead of `/tmp/` with `0700` directory perms. Recommend **move IPC sockets to `~/.boros/run/` with `chmod 700`**. |
| Plaintext keys in test fixtures committed to repo | Information Disclosure | Pre-commit `.gitleaks` scan on staged files; test fixtures use `FAKE_KEY_FOR_TESTS = "0x" + "0"*64`-style synthetic values |
| Malicious dependency in Python/TS supply chain | Tampering | `uv.lock` + `pnpm-lock.yaml` pinned; `uv audit` / `pnpm audit` in CI; root wallet never in bot process (C3 mitigation) |
| Pre-signed calldata leaked in logs | Information Disclosure (limited — nonce-bound) | structlog redaction; never log the full signed payload, log `tx_hash` + `intent` only (Phase 6 concern, but Phase 1 log schema pre-allocates redaction pattern) |

**Phase 1 security-relevant deliverables:**

- INFRA-12: dotenvx + Keychain.
- `scripts/no_plain_keys.py` pre-commit hook — greps staged diffs for 64-hex-char strings and `BEGIN PRIVATE KEY`.
- Log redaction processor in `structlog_setup.py` — redacts `password`, `api_key`, `private_key`, `secret`, `DOTENV_PRIVATE_KEY*` keys before JSONRender.
- `chmod 700` on `~/.boros/run/` for IPC sockets; `chmod 600` on `var/state.sqlite`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Python 3.12 | Everything Python | Assumed present on operator macOS | — | uv can install via `uv python install 3.12` |
| Node 24 LTS | Everything TS | Assumed present (operator installs) | — | `nvm install 24` |
| `uv` | Python project | To install one-time | — | `pip install uv` as fallback; `brew install uv` |
| `pnpm` | TS project | To install one-time | — | `brew install pnpm` or `corepack enable` |
| `git` | Everything | Assumed present on macOS | — | — |
| `dotenvx` CLI | INFRA-12 secrets | Install one-time via `npm i -g @dotenvx/dotenvx` | — | — |
| `pre-commit` | All lint hooks | `uv add pre-commit` | — | — |
| `launchctl` | INFRA-13 supervision | Native macOS | — | — |
| `security` CLI (Keychain) | INFRA-12 | Native macOS | — | — |
| Arbitrum public RPC (`https://arb1.arbitrum.io/rpc`) | DATA-07, INFRA-14 | Public, no key required | — | Alchemy free tier (1M req/mo) as backup if public rate-limits |
| Boros REST `/open-api/v1/` | DATA-06, DATA-11 | Public, no key | — | — |
| Boros `historical-data.boros.finance` NDJSON bucket | DATA-01..04 | Public (per plan) | — | — |
| LLM Wiki tooling (`../LLM Wiki/src/`) | INFRA-10 | **Sibling repo must be checked out at `../LLM Wiki/`** | — | Planner verifies sibling exists in Wave 0 |
| Aave USDC Arbitrum supply rate reference | DATA-09 alt_yield default | External data (one-off lookup, not polled) | — | Operator may override `alt_yield` in strategy yaml |

**Missing dependencies with no fallback:** **None** — every external piece is either trivially installable on macOS, publicly accessible, or operator-controlled. The only judgement call is the sibling `LLM Wiki` repo — research assumes it's already checked out per CLAUDE.md referencing `../LLM Wiki/workspaces/boros/wiki/`. Planner should add a Wave 0 sanity-check step: "verify `../LLM Wiki/workspaces/boros/wiki/index.md` exists, else STOP."

**Missing dependencies with fallback:** Alchemy-key Arbitrum RPC if public rate-limits during ingester runs (Phase 1 ingester is batch, rate limits unlikely but documented).

---

## Project Constraints (from CLAUDE.md)

CLAUDE.md directives that apply to Phase 1 and any plan/task must honor:

1. **Every commit touching `python/` or `ts/` source MUST also update `docs/architecture.yml` + `docs/ARCHITECTURE.md`.** Pre-commit hook enforces; this is INFRA-09 itself. The requirement is circular in Wave 0 (the first commit that creates the architecture.yml file is exempt, but every subsequent source-touching commit is not).
2. **Every research/decisions/postmortem commit MUST cite at least one `[[wiki-link]]`.** Pre-commit hook enforces; this is INFRA-11.
3. **New config knob MUST be added to the Pydantic schema in the same commit as the code that uses it.** PROTO-04; the round-trip test enforces.
4. **Use `gsd-sdk query commit "<message>" <files...>` for planning-doc commits.** Operational, not source-level.
5. **Commit planning docs to git.** `commit_docs=true` in config.json.
6. **LLM Wiki: check-first, write-back.** Already verified — all 8 wiki pages from Phase 0 were consulted for this research. The research itself will be written back as a wiki page `[[Phase 1 research plan]]` after commit.
7. **No hot-reload of knobs.** Prevention: explicit anti-pattern, documented in BotConfig schema comments + ARCHITECTURE.md.
8. **`submission_path` knob does not exist.** Prevention: absent from BotConfig schema; any attempt to add it in future fails the code review.
9. **Fills are bad; immediate market close on fill.** Not a Phase 1 deliverable but the `require_success_default: true` knob is pre-configured for Phase 6.
10. **`eventIndex` is the intra-block ordering primitive (not `blockTimestamp`).** DATA-01 asserts this for every row.
11. **OU on the basis (Implied − Underlying)** — Phase 3 concern; not Phase 1. Schema reserves space.
12. **Pre-signed cancel calldata at placement time.** Phase 6; Phase 1 schema does not bake this in, just reserves `execution.*` section.
13. **Single Pydantic `BotConfig` class is the single source of truth for all knobs.** INFRA-02 + PROTO-04.

---

## Assumptions Log

All claims in this research tagged `[ASSUMED]` above are collected here for planner / discuss-phase attention. The planner should verify each before a task commits.

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | `estimated_fill_loss_rate` coarse bound of `0.02` (2% APR decimal) is conservative enough for DATA-09 | §Pattern 10 economics kill-switch math | If too loose: markets pass the gate that shouldn't; Phase 2/3 discovers -EV; Phase 2/3 was built on dud data. Mitigation: Phase 3 refines and DATA-10's daily re-screen catches shifts; worst case is 1-2 weeks of wasted Phase-2 effort. If too tight: screener kills a viable market early; mitigation: the threshold is a knob (`fill_loss_coarse_bound`), operator can adjust. |
| A2 | `alt_yield = 0.05` (5%) is the right default (Aave USDC Arbitrum p50 2026-04) | §Pattern 10, §DataConfig | If significantly off (e.g., stable rates spike to 10%): screener drops a market that's still -EV; operator overrides knob. Low risk — the value is knob, not hardcoded. |
| A3 | launchd Keychain ACL works for dotenvx under LaunchAgent without GUI prompt when `-A` flag is set on `security add-generic-password` | §Pattern 6 dotenvx+Keychain | If wrong: bot fails to start headless after reboot. Mitigation: Wave 0 adds a "headless launchd smoke test" manual step — operator runs the plist, reboots, verifies brain+hands come up. If ACL fails, fallback to storing key in a launchd-owned system keychain or switching to a file under `~/.boros/` with `chmod 600`. |
| A4 | ZMQ separate-socket KILL lane is the right priority pattern (vs ROUTER/DEALER + message priority) | §Pattern 3 ZMQ | If a single shared socket ends up having KILL buried behind PLACE: cancel-all latency extends beyond 5s budget. Mitigation: Phase 6 adds instrumentation to measure; if latency is observed > 500ms for KILL, switch patterns. |
| A5 | Boros `/markets` endpoint response shape is consistent across all markets and contains `fIndexOracle`, `cloLowerThresh`, `cloUpperThresh`, `takerFee` (per `MarketConfig`), and `E_liq_per_epoch` with Long/Short split. Field names/types not verified against live API; openapi docs fetch returned empty content. | §DATA-06, §DATA-11 | If field names differ: first empirical hit fails; ingester logs a schema-mismatch, operator fixes. Low-to-medium risk. Mitigation: Wave 0 task "fetch one sample `/markets` response with `curl` and reconcile schema" happens before writing the poller. |
| A6 | Historical `E_liq_per_epoch` reconstruction from distributor events is infeasible; `reward_budget_history` is forward-only from pipeline go-live | §DATA-11 / PITFALLS B6 | If infeasible is wrong: we could reconstruct historical budgets and tighten Phase 5 backtest. Mitigation: Phase 1 includes one research spike (`scripts/probe_historical_budget.py`) to confirm; if feasible, reconstruction is a bonus task. |
| A7 | `python-ast` module is sufficient for INFRA-09 architecture lint (no need for tree-sitter or ts-morph) | §Pattern 5 architecture lint | If insufficient: TS side won't lint in Phase 6+; but Phase 1's TS code is minimal so this is a Phase 6 problem. Mitigation: defer TS AST parsing to Phase 6 when `hands` has real code. |
| A8 | `SCALE ≈ 5.591e12` for ETHUSDT; per-market variance is handled by re-calibrating from two (clo, fIndex) pairs | §Pattern 8 fIndexOracle decode | If SCALE varies unpredictably: Phase 1 screener for non-ETH markets produces wrong APR conversions. Mitigation: DATA-08 screener runs the calibration per market and logs SCALE/S; operator checks outliers. |
| A9 | Alembic is the right migration tool (vs yoyo-migrations or raw SQL versioning) | §Alembic section | Minor. Swapping is cheap. |
| A10 | Pydantic v2 `model_dump(mode='json')` recursively walks nested `StrictBase` models including `list[StrictBase]` fields and correctly serializes Decimal/datetime/enum without extra config | §Pattern 1 reflection manifest | High-confidence per [CITED: docs.pydantic.dev], but edge cases like `bytes` fields may need explicit serializers. Mitigation: round-trip test catches any non-serializable field. |
| A11 | The `historical-data.boros.finance` bucket is still publicly available and schema-stable for ingester use | §DATA-01..04 | If not available: Phase 1 halts until operator gets access. Mitigation: Wave 0 smoke-test "`curl -I historical-data.boros.finance/market-trades/ETHUSDT-26SEP2025/sample.ndjson`" as a first step. |

**If planner decides a claim requires user confirmation before execution:** open a discuss-phase or add a task-level decision hook before the dependent task is started.

---

## Open Questions

Phase-0 closed the existential questions. The following are Phase 1 execution-time unknowns, each with a mitigation path so none block the plan:

1. **Exact Boros `/markets` response schema** (A5)
   - What we know: endpoint exists, returns market objects with CLO thresholds, fIndexOracle, MarketConfig.takerFee per [[Send Txs Bot integration]] and [[Boros fee schedule]].
   - What's unclear: exact JSON field names/types/units for `E_liq_per_epoch`, Long/Short budget split, entrance fees, `maxUpdateDelay`, etc.
   - Recommendation: Wave 0 task "curl + pretty-print one `/markets` response" before writing the poller; update schema in `data/rest_client.py` to match; flag any discrepancies in PR description.

2. **Socket.IO heartbeat / reconnect replay semantics** (TBD per [[Boros WebSocket API]])
   - What we know: Socket.IO 4.x client-side defaults are `pingInterval=25s`, `pingTimeout=20s`; reconnect logic configurable.
   - What's unclear: whether the server replays missed events on reconnect, or the client must reconcile via REST.
   - Recommendation: NOT a Phase 1 problem (WS listener is Phase 6). Phase 1's REST poll is the only Boros-API interaction; WS can be verified in Phase 6 Wave 0.

3. **Historical `E_liq_per_epoch` reconstruction from distributor events** (A6)
   - What we know: distributor emits events on-chain; ABI likely available via Arbiscan.
   - What's unclear: whether the emission rate per market is reconstructible from events alone, or requires reading a protocol state variable.
   - Recommendation: single spike `scripts/probe_historical_budget.py` inside DATA-11 task. If infeasible in <1 day, fall back to forward-only logging and document in wiki as `[[Historical reward budget reconstruction — infeasible, forward-only logging]]`.

4. **launchd + Keychain + dotenvx headless wake-up** (A3)
   - What we know: pattern is documented; `security -A` flag is the intended mechanism.
   - What's unclear: macOS version-specific behavior; whether login keychain is unlocked before LaunchAgent starts at boot.
   - Recommendation: Wave-end manual test step: reboot operator machine, confirm both `brain` and `hands` come up under launchd without prompts. If fails, fallback to keeping `DOTENV_PRIVATE_KEY_PRODUCTION` in `/etc/boros.env` with `chmod 600` (lower security but works headless).

5. **Per-market SCALE value derivation** (A8)
   - What we know: boros_bot_guide.md shows one calibrated value for ETHUSDT 29-May.
   - What's unclear: whether BTC, SOL, other markets have the same or different SCALE constant.
   - Recommendation: DATA-08 screener derives SCALE per market from two observed (clo, fIndex) pairs during initial ingestion; log SCALE/S per market; alert if a market's SCALE changes over observation window.

---

## Sources

### Primary (HIGH confidence)

- `/Users/macbookair/Documents/project/test/rerun7/boros/.planning/research/STACK.md` — full stack research from 2026-04-23 (versions verified)
- `/Users/macbookair/Documents/project/test/rerun7/boros/.planning/research/ARCHITECTURE.md` — split-brain design, ZMQ topology, state ownership map
- `/Users/macbookair/Documents/project/test/rerun7/boros/.planning/research/PITFALLS.md` — 29 failure modes with phase mapping
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/voluntary-cancel-reward-behavior.md` — [[Voluntary cancel reward behavior]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/minimum-order-size.md` — [[Minimum order size]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/websocket-api.md` — [[Boros WebSocket API]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/sign-only-cancel-primitive.md` — [[Sign-only cancel primitive]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/send-txs-bot-integration.md` — [[Send Txs Bot integration]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/eventindex-coverage.md` — [[eventIndex coverage]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/fee-schedule.md` — [[Boros fee schedule]]
- `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/market-entry-cap.md` — [[Market entry cap and auto-exit pattern]]
- `/Users/macbookair/Documents/project/test/rerun7/boros/boros_bot_guide.md` (L160-217 fIndexOracle decoding, L486-489 oracle addresses, L505 SCALE/S calibration anchor)

### Secondary (HIGH/MEDIUM confidence — verified via web search + official docs)

- [Pydantic v2 Models — docs.pydantic.dev](https://docs.pydantic.dev/latest/concepts/models/) — reflection behavior of `model_dump(mode='json')` on nested `BaseModel`
- [Pydantic v2 Serialization — docs.pydantic.dev](https://docs.pydantic.dev/latest/concepts/serialization/) — nested model recursion
- [structlog contextvars — structlog.org](https://www.structlog.org/en/stable/contextvars.html) — async-task-local propagation
- [Pino — github.com/pinojs/pino](https://github.com/pinojs/pino) — child logger + mixin pattern
- [pyzmq Push/Pull — learning-0mq-with-pyzmq.readthedocs.io](https://learning-0mq-with-pyzmq.readthedocs.io/en/latest/pyzmq/patterns/pushpull.html)
- [ZMQ heartbeat options — api.zeromq.org/4-2:zmq-setsockopt](http://api.zeromq.org/4-2:zmq-setsockopt) — `ZMQ_HEARTBEAT_IVL`, `ZMQ_HEARTBEAT_TIMEOUT` verified
- [SQLite WAL — sqlite.org/wal.html](https://sqlite.org/wal.html) — single-writer serialization verified
- [The Write Stuff — oldmoe.blog](https://oldmoe.blog/2024/07/08/the-write-stuff-concurrent-write-transactions-in-sqlite/) — SQLite concurrent write discussion
- [polars write_parquet — docs.pola.rs](https://docs.pola.rs/api/python/dev/reference/api/polars.DataFrame.write_parquet.html)
- [DuckDB + Polars integration — duckdb.org](https://duckdb.org/docs/stable/guides/python/polars)
- [DuckDB partitioned writes — duckdb.org](https://duckdb.org/docs/current/data/partitioning/partitioned_writes)
- [launchd.info — full reference](https://www.launchd.info/)
- [launchd.plist(5) manpage — keith.github.io](https://keith.github.io/xcode-man-pages/launchd.plist.5.html)
- [A Simple Launchd Tutorial — medium.com/@chetcorcos](https://medium.com/@chetcorcos/a-simple-launchd-tutorial-9fecfcf2dbb3)
- [launchd-keepalive patterns — github.com/tjluoma](https://github.com/tjluoma/launchd-keepalive)
- [dotenvx encryption — dotenvx.com/docs/quickstart/encryption](https://dotenvx.com/docs/quickstart/encryption)
- [dotenvx — dotenvx.com](https://dotenvx.com/)
- [envchain — github.com/sorah](https://github.com/sorah/envchain) — alternative Keychain env pattern
- [Aave Arbitrum USDC supply rate reference — aavescan.com](https://aavescan.com/) + [aave.com/markets](https://app.aave.com/markets/) — alt-yield benchmark 2026-04
- [Boros fee schedule — docs.pendle.finance/boros-dev/Mechanics/Fees](https://docs.pendle.finance/boros-dev/Mechanics/Fees) — MarketConfig.takerFee
- [Boros WebSocket — docs.pendle.finance/boros-dev/Backend/websocket](https://docs.pendle.finance/boros-dev/Backend/websocket) — Socket.IO protocol
- [Boros best-practices — docs.pendle.finance/boros-dev/Backend/best-practices](https://docs.pendle.finance/boros-dev/Backend/best-practices) — Send Txs Bot endpoints

### Tertiary (LOW confidence — to verify at execution)

- Exact field names in Boros `/markets` response (A5 — flagged; Wave-0 curl verifies)
- Headless launchd+Keychain ACL behavior (A3 — flagged; Wave-end reboot smoke test verifies)
- Historical reward-budget reconstruction feasibility (A6 — flagged; <1-day spike decides)

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH (inherited from STACK.md verified 2026-04-23; all versions registry-checked; 4 small Phase-0 stack-deltas integrated: socket.io-client instead of ws, launchd instead of overmind, ZMQ instead of stdin/stdout JSON, no submission_path knob)
- Architecture: HIGH (ARCHITECTURE.md §1-§15 adopted; Phase-1-specific subset extracted and tied to requirement IDs; responsibility map explicit)
- Pitfalls: HIGH (every pitfall tagged in Phase 1 scope is mapped to a concrete requirement, with tests verifying its prevention)
- Economics kill-switch math: MEDIUM-HIGH on structure (inputs traced to source), MEDIUM on the `fill_loss_coarse_bound = 0.02` assumption (A1)
- launchd/Keychain: MEDIUM (well-documented pattern, but A3 flagged — headless wake-up behavior deserves a manual reboot smoke test)
- Boros REST schema: MEDIUM (structure known, exact field names TBD via single Wave-0 `curl`)
- WS Socket.IO heartbeat: LOW priority (not Phase 1 scope; flagged for Phase 6)

**Research date:** 2026-04-23
**Valid until:** 2026-05-23 (30-day window for stable stack choices; earlier if Boros API shape changes materially)

**Wiki write-back plan (Protocol #1):** This research file seeds one wiki page to file after commit:

- `[[Phase 1 research plan]]` — meta page linking to this file, Status: `Current`. Updates `../LLM Wiki/workspaces/boros/wiki/index.md` under "Operations" reading path.

Additional wiki pages the Phase 1 execution will produce (not research's job to file — planner's task set):

- `[[Pydantic BotConfig schema v0.5]]` — after INFRA-02 ships
- `[[SQLite state spine v0.5]]` — after INFRA-03 ships
- `[[ZMQ bus topology v0.5]]` — after INFRA-05 ships
- `[[RUN_MANIFEST writer]]` — after INFRA-06 ships
- `[[Log contract structlog-pino]]` — after INFRA-07 ships
- `[[Architecture YAML + lint]]` — after INFRA-08/09 ships
- `[[dotenvx + Keychain + launchd]]` — after INFRA-12/13 ships
- `[[NDJSON ingester v0.5]]` — after DATA-01..05 ships
- `[[Economics kill-switch v0.5]]` — after DATA-08/09 ships
- `[[Historical reward-budget reconstruction — infeasible fallback]]` — after DATA-11 spike (status depends on A6 outcome)

---

*Phase 1 research for: Boros Reward Farming Bot — Infrastructure Spine + Data Pipeline + Economics Gate*
*Researched: 2026-04-23*
*Next: planner consumes this, emits `PLAN.md`s grouped by wave; plan-check verifies all 30 requirement IDs are addressed; execute-phase schedules waves.*
