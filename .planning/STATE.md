---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: milestone
status: executing
stopped_at: Completed 01-03-PLAN.md — RUN_MANIFEST writer + structlog/pino contract + ZMQ bus (INFRA-05/06/07 + PROTO-01)
last_updated: "2026-04-24T00:32:30.109Z"
last_activity: 2026-04-24
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 12
  completed_plans: 3
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-23)

**Core value:** Earn net-positive yield on $100 collateral from the Boros Limit Order Liquidity Rewards pool that beats stablecoin alternatives, after gas and fill-loss — on a live, single-market deployment. If -EV, detect cheaply and kill; do not limp.
**Current focus:** Phase 01 — foundation-infrastructure-spine-data-pipeline-economics-gate

## Current Position

Phase: 01 (foundation-infrastructure-spine-data-pipeline-economics-gate) — EXECUTING
Plan: 3 of 12
Status: Ready to execute
Last activity: 2026-04-24

Progress: [███░░░░░░░] 25%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01-01 | 41 | 2 tasks | 28 files |
| Phase 01 P01-02 | 16 | 2 tasks | 23 files |
| Phase 01 P01-03 | 38 | 2 tasks | 17 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Recent decisions affecting current work:

- [Init]: Target only Limit Order Liquidity Rewards pool; ignore Maker Volume.
- [Init]: Python brain (models/backtest) + TypeScript hands (SDK/execution) split over ZMQ IPC.
- [Init]: EV-based cancel rule (no threshold dials); `voluntary_cancel_forfeits_accumulated` flag present until P0-01 confirmed.
- [Init]: Build engine with both branches; Phase 5 backtest reports sensitivity to both A1 branches.
- [2026-04-23] **P0-01 resolved**: Boros official team — "LO incentives are calculated per block, so accumulated rewards won't go to zero even if users cancel the order." → `voluntary_cancel_forfeits_accumulated = False` (benign, forward-looking cancel rule). Wiki page [[Voluntary cancel reward behavior]]. Evidence tier: official team statement, not contract-traced. Side-finding: per-block reward granularity (~250ms on Arbitrum).
- [2026-04-23] **P0-02 resolved**: docs state "No minimum order size requirement" and "No lot size restrictions." $100-collateral premise safe at the protocol level. [[Minimum order size]].
- [2026-04-23] **P0-03 resolved**: Per-account fill channel exists — `account-updates:ROOT_ADDRESS` → `order-update` event (`efs` fill-size + `os` status). REST 1 Hz poll stays as reconciliation backup, not primary. **Stack change:** `ws 8.20` → `socket.io-client 4.x` in TS `hands` (Boros endpoint is Socket.IO, not raw WS). [[Boros WebSocket API]].
- [2026-04-23] **P0-04 resolved** (tightened after /Backend/best-practices): Send Txs Bot is the mandatory submission lane — `POST /v2/agent/bulk-direct-call` and `/v2/agent/direct-call`, v2 only (v3 browser-session-only). Pre-signing the cancel *calldata* at placement time still saves one hot-path roundtrip. Direct-to-chain submit ruled out; `submission_path` knob dropped from Phase 6. Bundled fill-response ([close_position, cancel_siblings] with `requireSuccess=true`) eliminates partial-state outcomes. [[Sign-only cancel primitive]], [[Send Txs Bot integration]].
- [2026-04-23] **Market entry cap**: max 10 markets per account; `autoExitMarket=true` returns variable-length calldata array — never assume `calldatas[0]`. v0.5 single-market is trivially under the cap; v2 2–4 market shortlist is also well under. [[Market entry cap and auto-exit pattern]].
- [2026-04-23] **EXEC-11 added**: API error-shape discriminated union (Open API `errorCode` vs Send Txs Bot/Stop Orders `statusCode`). Total v1 requirements 95 → 96.
- [2026-04-23] **P0-05 spot-confirmed**: `eventIndex` present on ETHUSDT sample + WS `order-update` field `ei`. Cross-market probe deferred to Phase 1 ingester. [[eventIndex coverage]].
- [2026-04-23] **P0-06 mostly resolved**: fee schedule extracted from docs (maker 0, taker ~0.05%, settlement per-period, entrance ~$1/market, no cancel fee). Gas measured empirically per DECIDE-03. [[Boros fee schedule]].
- [Roadmap]: Phase 0 is a hard kill-gate — project halts if protocol minimum order size exceeds $100 on every candidate market (P0-02).
- [Roadmap]: Engineering Protocols (wiki, architecture diagram, RUN_MANIFEST) anchor in Phase 1 as cross-cutting infrastructure; apply to every subsequent phase.
- [Roadmap]: Merged Phase 3 (loss model) + Phase 4 (reward-share/sizing) into a single Phase 3 — both are small EV-input producers; kept Paper (Phase 7) and Live (Phase 8) distinct per deliverable-type rule.
- [2026-04-23 01-01] Pydantic v2 BotConfig locked as PROTO-04 SSoT: extra='forbid' + frozen=True on every StrictBase sub-model, markets list capped max_length=1 (v0.5), voluntary_cancel_forfeits_accumulated=False default (D-01 / P0-01), zero submission_path occurrences anywhere (P0-04 regression guard via test_submission_path_not_in_schema).
- [2026-04-23 01-01] Monorepo tree committed: python/ + ts/ + configs/ + strategy/ + docs/ + scripts/ + state/ + logs/ + data/parquet/; uv sync --locked + pnpm --frozen-lockfile both clean; socket.io-client@^4 replaces raw ws (P0-03 stack change).
- [2026-04-23 01-01] pnpm 10.33.2 installed via 'corepack enable pnpm' — documented as declarative dependency in ts/package.json packageManager field; plan's 'pnpm install --frozen-lockfile --dry-run' command adjusted to drop --dry-run (flag removed in pnpm 10); same semantic via --frozen-lockfile alone.
- [2026-04-24 01-02] PROTO-02 mechanized: scripts/sqlite_writer_lint.py grep-enforces single-writer-per-table across python/src + ts/src with TEST_ONLY=True literal exception for Python-side hands writers (open_orders.py, tx_receipts.py); injected-drift behavioral test proves it catches INSERT INTO <table> outside the owner module.
- [2026-04-24 01-02] SQLite WAL spine invariants: open_connection() clamps journal_mode=WAL + synchronous=NORMAL + foreign_keys=ON + chmod 600 on every open (covering .sqlite + -wal + -shm siblings); not one-time-at-creation. T-02-02/03 mitigations baked in.
- [2026-04-24 01-02] B6 pitfall guard lands as schema CHECK + Python ValueError: reward_budget_history.data_source accepts only 'polled' | 'synthetic_current'; Phase-5 backtest MUST filter by data_source='polled' to avoid current-budget-synthetic leakage.
- [2026-04-24 01-02] scripts/apply_alembic_migration.py replaces alembic CLI for TS tests (alembic -x does NOT override sqlalchemy.url — documented limitation). Helper uses cfg.set_main_option() programmatically and accepts arbitrary sqlite:/// URLs.
- [2026-04-24 01-03] MANIFEST-FIRST invariant installed: RUN_MANIFEST = first log line + sidecar JSON + run_manifests SQLite row, all three identical content. Manifest built via config.model_dump(mode='json') reflection — adding a BotConfig knob mechanically surfaces in the manifest (PITFALLS D2 / T-03-01 mechanized).
- [2026-04-24 01-03] Cross-tier run_id propagation via contextvars (structlog) + AsyncLocalStorage (pino); minimum shared field set = {ts, level, event, run_id, tier, logger, pid}; structlog WriteLoggerFactory requires text-mode file + str serializer (orjson.dumps(...).decode()) — bytes mode fails with TypeError on the '\\n' concat.
- [2026-04-24 01-03] ZMQ KILL lane = second PUSH/PULL socket (not a priority field); hands drains kill + cmd as independent async iterators so KILL never queues behind PLACE. Two-endpoint PUB/SUB events topology — each tier binds its own PUB + SUBs the peer's (no string-mangling). Measured ipc echo: median 0.126ms / p95 0.173ms (N=1000), well inside 10ms budget.
- [2026-04-24 01-03] HeartbeatMonitor fire-once LostSibling — emits exactly one event after 3 missed intervals; recovery (record_peer_heartbeat within window) resets flag for re-fire. 5s default interval / 15s threshold per BotConfig; test compresses to 0.1s / 0.3s. PUB/SUB slow-joiner settle time = 0.3s (tests) — production 5s interval is well past that.
- [2026-04-24 01-03] Cross-language schema mirror = hand-written Pydantic + Zod with a round-trip test (test_zmq_schema_mirror) that invokes Python's model_dump(mode='json') via subprocess and Zod-parses every message type — T-03-03 drift guard. Code-gen (Pydantic → Zod) deferred to v1.0 if hand-mirror drift recurs.
- [2026-04-24 01-03] ipc_dir pytest fixture = /tmp-rooted short path under macOS's 103-byte sockaddr_un.sun_path limit — pytest's default tmp_path under /private/var/folders/… overflows and breaks ZMQ ipc:// binds. Added to conftest for all future ZMQ tests.

### Pending Todos

None yet.

### Blockers/Concerns

- ~~Phase 0 P0-02 (minimum order size) is existential~~ **Resolved 2026-04-23** — no protocol minimum. Existential halt-condition is off the table.
- ~~Phase 0 P0-01 (voluntary-cancel forfeit behavior) may drive material divergence in Phase 5 backtest sensitivity; if so, Phase 7 paper is blocked until P0-01 is resolved.~~ **Resolved 2026-04-23** — `voluntary_cancel_forfeits_accumulated = False`; sensitivity row demoted to sanity check, no longer a blocker.
- ~~P0-04 PARTIAL~~ **Resolved 2026-04-23** — Send Txs Bot is the mandatory submission lane; direct-submit ruled out. Latency budget closes on ~1–3s typical, <5s worst, with pre-signed calldata + Send Txs Bot. [[Sign-only cancel primitive]], [[Send Txs Bot integration]].
- Nautilus-adapter vs hand-rolled backtest is a Phase-5 day-1 bailout decision (2-day budget to bail).

## Session Continuity

Last session: 2026-04-24T00:32:30.103Z
Stopped at: Completed 01-03-PLAN.md — RUN_MANIFEST writer + structlog/pino contract + ZMQ bus (INFRA-05/06/07 + PROTO-01)
Resume file: None

**Planned Phase:** 01 (Foundation (Infrastructure Spine + Data Pipeline + Economics Gate)) — 12 plans — 2026-04-23T20:08:16.743Z
