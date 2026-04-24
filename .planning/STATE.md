---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: milestone
status: executing
stopped_at: Phase 01 UAT complete (5/7 PASS, 1 PARTIAL). Ready to plan Phase 02 (Fill Model — NHPP v0.5).
last_updated: "2026-04-24T10:18:59.379Z"
last_activity: 2026-04-24 -- Phase 02 execution started
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 16
  completed_plans: 12
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-23)

**Core value:** Earn net-positive yield on $100 collateral from the Boros Limit Order Liquidity Rewards pool that beats stablecoin alternatives, after gas and fill-loss — on a live, single-market deployment. If -EV, detect cheaply and kill; do not limp.
**Current focus:** Phase 02 — fill-model-nhpp-v0-5

## Current Position

Phase: 02 (fill-model-nhpp-v0-5) — EXECUTING
Plan: 1 of 4
Status: Executing Phase 02
Last activity: 2026-04-24 -- Phase 02 execution started

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 12 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01-01 | 41 | 2 tasks | 28 files |
| Phase 01 P01-02 | 16 | 2 tasks | 23 files |
| Phase 01 P01-03 | 38 | 2 tasks | 17 files |
| Phase 01 P01-04 | 22 | 3 tasks | 82 files |
| Phase 01 P01-05 | 15 | 2 tasks | 27 files |
| Phase 01 P01-06 | 9 | 3 tasks | 17 files |
| Phase 01 P01-07 | 11 | 2 tasks | 13 files |
| Phase 01 P08 | 9 | 3 tasks | 22 files |
| Phase 01 P01-09 | unknown | 3 tasks | 16 files |
| Phase 01 P11 | 35 | 3 tasks | 14 files |
| Phase 01 P12 | 35 | 2 tasks | 11 files |

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
- Bootstrap commit uses --no-verify exactly once for docs/architecture.yml creation (circular dep). Logged in docs/override-log.md with #override: bootstrap tag. Pattern is the approved exception per 01-04 plan.
- architecture_lint skips __init__.py files and migrations/ directory. Catches drift in both directions: undeclared code modules AND orphaned yml declarations AND undeclared public functions.
- pre-commit hooks use python3 (not python) for system-language local hooks — macOS has no bare python in PATH.
- mypy uses --no-warn-unused-ignores to handle Pydantic default_factory type: ignore comments that may or may not trigger depending on pydantic mypy plugin availability.
- Wiki page filenames for v0.5-regime pages use v05 suffix (not v0.5) to match the LLM Wiki lint normalizer which strips dots from filenames
- Pipe alias syntax [[kebab-filename|Human Title]] used for all wiki links where filename differs from normalized human title
- purge-reward-behavior.md stub created to resolve orphaned Purge reward behavior link; Status: Current — PARTIAL (low-confidence bot-guide claim)
- Keychain -A flag mandatory for headless launchd spawn (A3 landmine); without it launchd-spawned processes trigger GUI prompt — documented in docs/runbook-secrets.md
- no_plain_keys.py rewritten to pass_filenames:false (git diff --cached) — hook reads its own staged file list; .env.vault excluded by filename
- launchd plist paths are absolute (launchd does not expand HOME); wrapper scripts use HOME variable (bash does expand it)
- chain_drift thresholds: startup halt = chain_drift_warn_s (5s), runtime halt = chain_drift_halt_s (30s); startup is stricter than runtime halt by design
- sqlite_scanner: CALL sqlite_attach() chosen over ATTACH…USE live — USE live redirects default DDL catalog to read-only attach, breaking CREATE VIEW
- no_time_time_lint: full-tree walk (not git diff --cached fallback) so tests can inject files without staging them
- Used polars pl.PartitionBy + sink_parquet for Hive-partitioned parquet — pyarrow not in project deps; PartitionBy produces identical layout and is streaming-native
- snapshot_ts stored as Utf8 partition col in order_book parquet — PartitionBy requires string partition values; join on (snapshot_ts, tick) consistent across both sides
- CLI manifest fallback: write sidecar JSON when SQLite not yet initialized — enables ingest-first runs before state DB setup
- Use imData.symbol as clo_history.market_id string key (API marketId is int); all poller cache + KNOWN_ORACLES dict use symbol e.g. BINANCE-ETHUSDT-29MAY2026
- decode_findex_bytes uses val>>48 (discard 6-byte lower zero-pad) per boros_bot_guide.md L206 — RESEARCH.md raw[-26:] snippet was wrong direction
- now kwarg on apply_screener_filters: INFRA-14 bans time.time() in screener/; offline batch uses datetime.now(UTC).timestamp() as default; callers with chain_time SHOULD pass chain-time value
- A8 outside_range_wall_flag is a Phase-2 covariate warning, NOT a hard filter — markets with ratio > 2 remain in shortlist
- SCALE calibration non-blocking: InsufficientCalibrationData caught silently, scale=None, market still rankable by 6 metrics
- DATA-09 R_apr computed in PENDLE-units only (checker #06 Option A): avoids pendle_price_usd knob in Phase 1; USD conversion deferred to Phase 3 PricingConfig sub-model
- fill_loss_coarse_bound=0.02 is A1-flagged coarse bound; Phase 3 LossModel refines; documented in strategy YAML and wiki [[fill_loss_coarse_bound v0.5]]; threshold = 0.07 (7% APR decimal) recorded for Phase 3 comparison
- [2026-04-24 UAT] ELiqPoller Assumption A5 unverified: fields liquidityRewardPerEpoch/longBudget/shortBudget absent from live GET /markets response. Only reward-adjacent field is config.liqSettings.{base,slope,feeRate}. ELiqPoller needs full redesign once actual E_liq_per_epoch source identified. Not blocking Phase 2.
- [2026-04-24 UAT] GET /markets returns HYPERLIQUID-BTC-29MAY2026 twice (duplicate symbol). MarketsPoller.tick() now deduplicates by symbol with a warning log; clo_history PK (snapshot_ts, market_id) constraint still enforced.
- [2026-04-24 UAT] DOTENV_PRIVATE_KEY_PRODUCTION was wrong env var name in both wrapper scripts; corrected to DOTENV_PRIVATE_KEY (matches .env.keys naming convention for plain .env file).
- [2026-04-24 UAT] LLM Wiki stays at /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/ — not moved. CLAUDE.md ../LLM Wiki/ references updated to absolute path to match.

### Pending Todos

None yet.

### Blockers/Concerns

- ~~Phase 0 P0-02 (minimum order size) is existential~~ **Resolved 2026-04-23** — no protocol minimum. Existential halt-condition is off the table.
- ~~Phase 0 P0-01 (voluntary-cancel forfeit behavior) may drive material divergence in Phase 5 backtest sensitivity; if so, Phase 7 paper is blocked until P0-01 is resolved.~~ **Resolved 2026-04-23** — `voluntary_cancel_forfeits_accumulated = False`; sensitivity row demoted to sanity check, no longer a blocker.
- ~~P0-04 PARTIAL~~ **Resolved 2026-04-23** — Send Txs Bot is the mandatory submission lane; direct-submit ruled out. Latency budget closes on ~1–3s typical, <5s worst, with pre-signed calldata + Send Txs Bot. [[Sign-only cancel primitive]], [[Send Txs Bot integration]].
- Nautilus-adapter vs hand-rolled backtest is a Phase-5 day-1 bailout decision (2-day budget to bail).

## Session Continuity

Last session: 2026-04-24T09:00:00Z
Stopped at: Phase 01 UAT complete (5/7 PASS, 1 PARTIAL). Ready to plan Phase 02 (Fill Model — NHPP v0.5).
Resume file: None

**Completed this session (2026-04-24 second pass):**

- Fixed wrapper scripts: DOTENV_PRIVATE_KEY_PRODUCTION → DOTENV_PRIVATE_KEY (env var name mismatch with .env.keys)
- Fixed venv editable install: uv sync --locked in python/ updated stale .pth from old path to /Users/macbookair/boros/python/src
- Loaded brain launchd agent: bootstrap + enable + kickstart. Brain running at /Users/macbookair/boros.
- Test 2 PASS: SIGKILL PID 18701 at 07:37:02 → new PID 18896 at 07:37:13 (11s restart). Fresh RUN_MANIFEST confirmed.
- Test 6 PARTIAL: clo_history 41 rows, f_index_raw populated, market_ids correct. MarketsPoller duplicate-symbol fix applied (HYPERLIQUID-BTC-29MAY2026 deduped). reward_budget_history = 0 — ELiqPoller Assumption A5 fields absent from live API.
- LLM Wiki stays at original path. CLAUDE.md updated: ../LLM Wiki/ → absolute /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/.
- ELiqPoller gap documented in UAT file: needs redesign before Phase 3 reward-share model.

**Carried concern:**

- ELiqPoller (DATA-11): fields liquidityRewardPerEpoch/longBudget/shortBudget NOT in GET /markets. Real source of E_liq_per_epoch unknown — candidates: config.liqSettings.{base,slope}, on-chain distributor contract, or separate endpoint. Investigate before Phase 3.

**Next action:**
/clear then `/gsd-plan-phase 2` — Phase 02: Fill Model (NHPP v0.5)

**Planned Phase:** 2 (Fill Model (NHPP v0.5)) — 4 plans — 2026-04-24T09:56:57.583Z
