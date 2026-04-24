# Boros Reward Farming Bot — Claude Guide

This is the project-local guide. Read this before touching code in this repo.

## What this project is

A personal, single-user Python + TypeScript bot that captures **Pendle Boros Limit Order Liquidity Rewards** on Arbitrum by resting limit orders at the outer edges of each market's incentivized CLO range — deliberately avoiding fills so capital earns time-weighted PENDLE rewards without taking unwanted IRS exposure. Runs locally. Starts with $100 collateral. v0.5 first (NHPP + one market), v1.0 later (per-market model selection across a shortlist).

**Authoritative project context:** `.planning/PROJECT.md`
**Active scope:** `.planning/REQUIREMENTS.md`
**Phase plan:** `.planning/ROADMAP.md`
**State:** `.planning/STATE.md`
**Research:** `.planning/research/` (SUMMARY.md, STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md)
**Legacy planning (source material):** `boros_consolidated_plan.md` (canonical spec), `boros_bot_guide.md` (platform reference), `plan_comparison.md` (synthesis + data verification)

## GSD workflow

Use the Get-Shit-Done skills to drive any multi-step work:

- `/gsd-plan-phase <N>` — create the detailed plan for phase N (auto-runs research + plan check per config)
- `/gsd-execute-phase <N>` — execute all plans in phase N in wave-based parallel order
- `/gsd-progress` — check where the project is, route to the next logical step
- `/gsd-next` — advance to the next phase automatically
- `/gsd-discuss-phase <N>` — pre-plan clarifying discussion for the next phase
- `/gsd-verify-work <N>` — validate the phase satisfied its success criteria

**Config:** YOLO auto-approve, standard granularity, parallel execution, all verification agents on (research, plan-check, verifier), **quality** model profile (Opus on planning agents, Sonnet on execution agents).

## Engineering Protocols (enforcement, not suggestion)

Every phase, every plan, every code change obeys three protocols. Skipping them produces broken work.

### 1. LLM Wiki — check first, write back

- **Workspace:** `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/` (skeleton seeded 2026-04-23).
- **Tools:** the shared `LLM Wiki/src/` pipeline (`python src/ingest/url_fetcher.py … -w boros`, `python src/process/wiki_generator.py … -w boros`, `python -m src.lint.lint_engine -w boros --no-external`). See `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/CLAUDE.md` for the full tooling contract.
- **Before any research task** (phase research, spike, debug, design question): read `workspaces/boros/wiki/index.md` and any pages keyed by the topic. Cite pages as `[[page-name]]` in answers/plans.
- **Before closing any task** with a decision, discovery, surprise, failed hypothesis, or calibrated number: file a wiki page (or append to an existing one) with a `**Status:**` field (`Current` / `Current — <condition>` / `Historical — <reason>`).
- **Supersedence:** when a new finding invalidates an older one, grep the wiki and update every stale page in the same commit with `Status: Historical — superseded by [[new-page]]`. Stale claims in forgotten pages are worse than gaps.

### 2. Dependency / state-chain diagram — consult before change, update atomically

- **Location (once Phase 1 lands it):** `docs/ARCHITECTURE.md` (Mermaid — human-facing) + `docs/architecture.yml` (machine-readable — what the pre-commit hook parses).
- **Before any code change:** open `docs/ARCHITECTURE.md`, trace upstream (what feeds this node) and downstream (what this feeds) to enumerate the blast radius. List the affected nodes in the plan or PR description.
- **In the same commit as the code change:** update both the Mermaid diagram and `architecture.yml`. The pre-commit hook `scripts/architecture_lint.py` fails commits with drift.
- **Node granularity:** module, public function, CLI command, long-lived background task, external dependency (Boros REST, Arbitrum RPC, Send Txs Bot, Merkle distributor), every named config knob or env var.
- **Edge types:** `calls`, `reads`, `writes`, `emits-event`, `subscribes-to`, `depends-on-config`.

### 3. RUN_MANIFEST — strategy + knobs stamped into every log

- Every bot run (backtest, paper, live) emits `RUN_MANIFEST` as the first log record + sidecar `<run_id>.manifest.json`.
- Manifest fields: `run_id` (ULID), `started_at`, `mode` (backtest/paper/live), `git_sha`, `git_dirty`, `strategy_version`, `market_id`, `side`, `wallet_address_hash`, and **the full config tree of knobs with active values** (nothing elided).
- Every log line carries the active `run_id` (structured JSON; grep/join on `run_id`).
- Mid-run knob change or strategy-version bump → new `RUN_MANIFEST` with new `run_id` and `parent_run_id` pointer. No silent drift.
- The Pydantic config schema is the single source of truth for the knob list. Adding a knob without adding it to the schema is a bug.
- Any tool that analyzes logs (P&L plot, calibration chart, postmortem) loads the manifest first and surfaces the strategy version + key knobs alongside the analysis.

## Stack

- **Python (brain):** CPython 3.12 · `tick` 0.8.0.1 (Hawkes/NHPP) · `scipy` (OU MLE hand-rolled) · `nautilus_trader` (with hand-rolled fallback decision on Phase 5 day-1) · `polars` + `duckdb` + partitioned parquet · `pydantic` v2 (single `BotConfig` class) · `structlog` (JSON logs, `run_id` via `contextvars`) · `web3.py` for on-chain reads · `asyncio` clock, 1 Hz decision loop.
- **TypeScript (hands):** Node 24 LTS · `@pendle/sdk-boros` 1.1.44 · `viem` 2.44.4 (NOT ethers — SDK pins viem) · `ws` 8.20 · `tsx` 4.21 · `pino` (same log contract as Python).
- **IPC:** ZMQ — `ipc:///tmp/boros.cmd` (PUSH/PULL with KILL priority lane) + `ipc:///tmp/boros.events` (PUB/SUB). 5s heartbeat both directions.
- **Shared state:** SQLite WAL (single-writer-per-table discipline, linted). DuckDB read-only on top for analysis.
- **Secrets:** `dotenvx` encrypted envs. `.env.vault` committed, `.env.keys` in macOS Keychain, gitignored.
- **Process supervision:** `launchd` LaunchAgent plists (`brain` and `hands` each auto-restart on crash).
- **Hot path (WS fill → pre-signed cancel):** stays entirely inside the TypeScript `hands` process — no IPC hop — to protect the 2–5s end-to-end latency budget.

## Strategy non-negotiables

These are load-bearing; don't "fix" them without discussion:

- Target only the **Limit Order Liquidity Rewards** pool. Ignore the Maker Volume pool — it pays on fills, which this strategy avoids by design.
- **Fills are bad.** Any fill that slips through is closed immediately at market (accept the taker fee as insurance). No holding for reversion.
- **EV-based cancel rule, no threshold dials.** `EV_hold = R_share × P(no_fill) − E[loss|fill] × P(fill) − cancel_cost × P(purge)`. Cancel iff `EV_hold < 0`.
- **`eventIndex`** (not `blockTimestamp`) for intra-block ordering. Arbitrum blocks are ~250ms; `blockTimestamp` ties at the second.
- **OU on the basis `Implied − Underlying`** for `E[loss|fill]` — NOT on raw implied APR for fill probability. CLOB price is a step function; continuous diffusion is the wrong primitive for fills.
- **Pre-signed cancel calldata at placement time.** Biggest leverage point on fill avoidance — removes HTTP roundtrip from the critical path.
- **Single Pydantic `BotConfig` class** is the single source of truth for all knobs. Knobs used in code but missing from the schema are bugs.

## Phase 0 open questions (block engineering past Phase 1)

1. **Voluntary cancel behavior** — does a voluntary cancel forfeit already-accumulated reward-time-weight for the epoch? Build with `voluntary_cancel_forfeits_accumulated` flag; Phase 5 backtest runs both branches.
2. **Actual protocol minimum order size** — working assumption $100 collateral-equivalent. Existentially critical at $100 starting capital. If true minimum > $100, project halts at Phase 0.
3. **Boros WebSocket URL + subscription schema + per-account fill channel existence** — if no per-account fill channel, 1 Hz REST diff poll is promoted from backup to primary.
4. **`@pendle/sdk-boros` sign-only primitive** — needed for pre-signed cancel calldata. If absent, compose via `POST /calldata/cancel-order` + `viem.signTransaction` manually.
5. **`eventIndex` coverage** across all candidate markets.
6. **Full fee schedule** per candidate market (maker/taker/settlement/entrance/gas).

## Commit hygiene

- Commit planning docs to git (config says yes).
- Use `gsd-sdk query commit "<message>" <files...>` for planning-doc commits.
- Any commit that touches `python/` or `ts/` source also updates `docs/architecture.yml` + `docs/ARCHITECTURE.md`. The pre-commit hook (once installed in Phase 1) blocks drift.
- Any commit adding a `research/`, `decisions/`, or `postmortem/` markdown must cite at least one `[[wiki-link]]`. Pre-commit hook blocks omissions.
- New config knob → schema update in same commit.

## Where to look first

- **Something isn't working:** check `.planning/research/PITFALLS.md` — 29 failure modes already documented with phase-mapped prevention.
- **Wondering why a decision was made:** check `.planning/PROJECT.md` Key Decisions table, then the LLM Wiki pages under `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/`.
- **Wondering what's next:** `/gsd-progress` or `.planning/STATE.md`.
- **Wondering what's in scope:** `.planning/REQUIREMENTS.md` (v1 = this milestone; v2 = deferred to v1.0; Out of Scope = never).

## Non-negotiable

If you find yourself about to skip one of the Engineering Protocols "just this once" — stop. The point of the protocols is that they catch the drift *you* don't notice. A wiki page that's not filed, a diagram that's one commit behind, a log without a manifest are each small at the moment but compound into unreadable history. Don't start that slide.
