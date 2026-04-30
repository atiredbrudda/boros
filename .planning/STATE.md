---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: milestone
status: ready_to_execute
stopped_at: Phase 05.3 plan drafted; execution to start in fresh session (2026-04-30)
last_updated: "2026-04-30T13:00:00.000Z"
last_activity: 2026-04-30 — Phase 05.3 plan drafted (fill-path repair); ROADMAP + STATE updated; awaiting fresh-session execution start
progress:
  total_phases: 12
  completed_phases: 6
  total_plans: 51
  completed_plans: 48
  percent: 94
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-24)

**Core value:** Earn net-positive yield on $100 collateral from the Boros Limit Order Liquidity Rewards pool that beats stablecoin alternatives, after gas and fill-loss — on a live, single-market deployment. If -EV, detect cheaply and kill; do not limp.
**Current focus:** Phase 05.3 — Fill-Path Repair (drafted; ready to execute)

## Current Position

Phase: 05.3 — READY TO EXECUTE
Plan: 05.3-01 (single-plan phase)
Status: Plan drafted and committed; T1 (RED tests) is the next action when execution starts in a fresh session.
Last activity: 2026-04-30 — Phase 05.3 plan drafted; Phase 05.2 Bug #6 fix landed in commit `cad821f`; W5 verdict (970.6% USD-APR) invalidated — gross-of-fills only; Bug #7/#8/#9 routed to Phase 05.3.

Progress: [██████████░] 94%

## Phase 05.3 Resume Notes

**Why halted from 05.2:** Phase 05.2's Wave 5 binding ship-gate produced `p5 = 9.706` (970.6% USD-APR), 2.34× the falsifiable ~415% prediction. Operator review surfaced two distinct issue regions:
  1. **Reward leg (Bug #6):** calibration reader was not `effective_at_utc`-keyed; current-epoch `long_side_split = 0.760` was retroactively applied to a 26-day historical window where the real-world split was the prior-epoch ~0.327. Fixed in commit `cad821f` (Phase 05.2 trailing edge).
  2. **Fill leg (Bugs #7/#8/#9):** simulator cannot detect fills at all. `size_wei = NULL` across the binding-market parquet kills the trade handler; CLO thresholds treated as ticks via a `/10_000` rescale (they're fIndex display units); inter-event rate-crossing detection gated on `queue_ahead_wei == 0` which only the dead trade handler can clear. The W0 audit's `sim_bug_under_counting` verdict is still open. Routed to Phase 05.3.

**Decisions locked for Phase 05.3** (see `05.3-01-PLAN.md`):
  - **D1**: YU unit convention throughout the fill path (rename `queue_ahead_wei` → `queue_ahead_yu`; consume `size_float` directly).
  - **D2**: Lift `_clo_findex_to_tick` to a shared module; both screener and replay import the same helper.
  - **D3**: Decouple inter-event rate-crossing from the queue gate; queue uncertainty lives in `p_fill`, not as a simulator hard-gate.

**Two parallel tracks:**
  - **Plan 01 (engineering, `05.3-01-PLAN.md`)**: fill-path repair. T1–T7. Blocking for verdict.
  - **Plan 02 (research, `05.3-02-PLAN.md`)**: source Pendle's LO reward formula (closes W0 E5), reconcile dapp's 489% LONG APR vs our model, derive an expected-verdict band as `var/reports/expected_verdict_band_2026-04-30.json` consumed by Plan 01 T7. Read-only; no engine code changes; runnable entirely in parallel with Plan 01 T1–T5. Resolves the open question of whether our reward formula is even the right shape — if T1 surfaces a discrepancy, that's a category-different problem requiring a follow-up plan.

**Resume signal for fresh session:** start Plan 01 at T1 (RED tests) and Plan 02 at T1 (formula source) in parallel. Plan 01's task ordering is T1 → T2 → T3 → T4 → T5, then pause for operator before T6 (the ~4h binding re-run). Plan 02 must complete before Plan 01 T7 (verdict classification) so the verdict can be classified against the band, not a single-point guess. Halt remains `halted_pending_phase_05_2` until Phase 05.3 produces a clean verdict.

## Performance Metrics

**Velocity:**

- Total plans completed: 49
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 12 | - | - |
| 02 | 4 | - | - |
| 03 | 4 | - | - |
| 04 | 8 | - | - |
| 05 | 9 | - | - |
| 05.1 | 6 | - | - |

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
| Phase 05-event-driven-backtest-ship-gate P04 | 7 | 4 tasks | 9 files |
| Phase 05-event-driven-backtest-ship-gate P05 | 5 | 3 tasks | 5 files |
| Phase 05-event-driven-backtest-ship-gate P06 | 4 | 3 tasks | 4 files |
| Phase 05-event-driven-backtest-ship-gate P07 | 5 | 4 tasks | 5 files |
| Phase 05-event-driven-backtest-ship-gate P09 | 35 | 7 tasks | 10 files |
| Phase 05.1 P01 | 0 | 5 tasks | 8 files |

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
- Architecture update co-committed with Task 1/2 code (PROTOCOL 2 pre-commit enforcement): Wave 1 nodes (brain.backtest.config/schemas/synthetic_orders/cancel_latency/replay) + Wave 2 nodes (sweeps.cancel_latency, sweeps.competition) registered in docs/architecture.yml
- [2026-04-26 05-04] BACK-03/04 sweep dispatchers: run_cancel_latency_sweep + run_competition_sweep each produce N rows (operator-overridable grid); central-finite-difference dP&L/dL < 0 on always-fills synthetic; each child run gets fresh manifest with parent_run_id (PROTO-01 D2 guard)
- Hive partition layout: parquet_root/run_id=<ulid>/sweep_axis=<...>/[sweep_value=<...>/]results.parquet — base axis omits sweep_value dir (BACK-05)
- Path-traversal guard test uses white-box _ensure_under_root call — avoids OS-dependent depth counting (how many ../ escape a tmp_path)
- P0-01 LOCKED: voluntary_cancel_forfeits_accumulated=False by default; BACK-06 sweep is a sanity check (not a blocker); forfeit_branch_load_bearing signals material divergence without auto-failing ship-gate
- ulid.ULID.from_str() not ulid.from_str() — python-ulid exposes from_str as a class method on ULID, not a module-level function; corrected in bootstrap.py
- BotConfig + RunManifest imported at module top of cli.py — enables mypy type-checking without type:ignore on attribute accesses
- config.backtest.* knobs appear as depends-on-config edge targets in architecture.yml but not as explicit config_knob node declarations — architecture tests check edges, not nodes
- Path traversal guard in emit_backtest_manifest uses CWD-relative Path(var/backtest).resolve() — tests must use same root pattern
- [2026-04-27 05.1-W0 probe] **Boros historical-data archive layout LOCKED** ([[boros-historical-data-archive-layout]]): `https://historical-data.boros.finance/files.json` is the master manifest (JSON array of `{path, size}`, 2466 entries / ~217 KB / ~169 MB total compressed). Files served as static `${origin}/${URI-encoded-path}` GET. Folder-as-ZIP is client-side JSZip glue, NOT a server endpoint — fetcher iterates manifest + per-file GET. Order-book has BOTH `raw/` (1 file/market-month, ~400 KB compressed) and `combined_{0.0001,0.001,0.01,0.1}/` per-tick aggregations. `underlying-apr/` is FLAT (no per-month split) — one file per `Exchange-Asset` pair. ETag + Last-Modified support idempotent re-fetch. Cloudflare-fronted, HTTP/2, no auth, no observed rate-limit. Last archive update 2026-04-26 15:44 UTC.
- [2026-04-27 05.1-W0 probe] **Market-ID format DIVERGENCE flagged**: archive uses `{N}-{EXCHANGE}-{ASSET}-{MATURITY}` (numeric on-chain ID prefix); local `clo_history.market_id` uses just `{EXCHANGE}-{ASSET}-{MATURITY}`. Same human name maps to multiple numeric IDs (re-deployments, e.g. `108-` and `109-HYPERLIQUID-BTC-29MAY2026` are distinct on-chain markets). Phase 5.1 Wave 1 must resolve via `Boros GET /markets` cross-reference and persist a `{symbol→marketId}` mapping (`var/fetcher/market_id_mapping.json`) before bulk fetch. Recommendation: backtest the highest-numeric-ID variant (most recent deployment) per human name; emit a wiki note when multiple variants exist.
- [2026-04-27 05.1-W0 probe] **Estimated Wave 1 fetch budget**: ~70 MB compressed for 25 pre-filtered markets × 60d × 6 kinds. Trivial; fetch completes in minutes at modest bandwidth. Whole-archive fetch is bounded at ~169 MB.
- [2026-04-27 05.1-01] Wave 0 complete: alembic head 0007; fetcher scaffold + 7 tests GREEN; URL pattern locked to Branch A (files.json master manifest + per-file static GET) per [[boros-historical-data-archive-url-pattern]]; pre-filter list at [[markets-pre-filter-2026-04-26]] (25 markets); test-residue docs/kill-report-20260426.md deleted; architecture delta committed (PROTO-02).
- [2026-04-27 05.1-02] Wave 1 complete: fetcher _run_fetch_loop GREEN (Branch A URL template, ThreadPoolExecutor concurrency=6, --resolve DNS workaround for broken local resolver); bulk fetch produced 172 NDJSON files (61 MB on disk, 172 manifest entries) across 25 markets × 6 kinds × up to 3 months; bulk ingest produced parquet for 75 surviving market_id= partitions (141/141 jobs OK, 0 AMM violations, 0 IngesterSchemaViolation); 419 pytest PASS.
- [2026-04-27 05.1-W1.5 hardening] Wave 1.5 hardening pass landed (commit 7a6e689) before Wave 2 could run: order_book schemas described flat per-tick rows but real archive NDJSON is nested per-snapshot arrays — polars silently produced 271 rows × all-null per market. Fixed schemas + ingester (_explode_raw, _explode_combined) + 6 fixtures + 9 tests; re-ingested 25 markets (240k combined + 695k raw rows of valid data). screener/metrics.py: replaced log-return realized_vol with rate-difference std (APR oscillates through zero → log undefined). screener/filter.py: added CLO scale-defaults (SCALE/S/TICK_SIZE) for two-point calibration fallback on single-observation markets. backfill_reward_budget_history.py: synthetic_current backfill (25 rows) bridging the LOCKED D-01 r_apr_potential migration gap. 4 debug sessions filed under .planning/debug/ — order-book-combined-null, realized-vol-on-boros-rates, reward-budget-history-empty, screener-marketid-maturity.
- [2026-04-27 05.1-03] Wave 2 PASS via deviation: DATA-08 screener over 25 real-data markets passed 6 (top-4 shortlist = BINANCE-ETHUSDT-{25SEP,26JUN,29MAY}2026 + HYPERLIQUID-ETH-29MAY2026; 19 fail zero_depth_at_clo, 1 fail insufficient_reversals). DATA-09 economics gate raised ProjectHalt with empty Per-Market Evaluation table — false positive caused by LOCKED D-01 plan defect (gate expects r_apr_potential from market_reward_calibration which Wave 3 populates; Wave 2 has no calibration rows so every passer's r_apr_potential is null and the gate skip-branch fires for all). Soft-PASS branch taken: kill report deleted (empty rows = self-evidently a non-event), shortlist.json + shortlist_previous.json overwritten with the 4 DATA-08 passers (DATA-10 baseline seeded), economics_gate.json kept as informational audit trail (`{threshold:0.07, rows:[], shortlist:[]}`). Binding economics check deferred to Wave 4 backtest (BACK-07 ship-gate threshold = alt_yield + all_fees, same intent as DATA-09). Plan defect documented in [[phase-05-1-economics-gate-verdict]] for future plan revision. See [[phase-05-1-screener-verdict]] + [[phase-05-1-economics-gate-verdict]]. Deviations: local DNS broken (socket.getaddrinfo fails for historical-data.boros.finance) — resolved via --resolve IP override; underlying-apr archive uses Binance-ETH format (not BINANCE-ETHUSDT), xyz-prefix markets mapped via alias table; settlement parquet has null market_id (schema mismatch between archive format and ingester SETTLEMENT_SCHEMA — tracked as known issue). See [[phase-05-1-bulk-fetch-runbook]] + [[phase-05-1-bulk-ingest-runbook]].
- [2026-04-28 05.1-04] Wave 3 complete: per-shortlist-market reward calibration written (4 operator rows, 0 BLOCKED); fill-model fit GREEN for all 8 (market, side) pairs; strategy/v0.5-phase05.1-shortlist.yaml committed; FILL-06 degraded count = 0; fill_model.cli extended with --market single-market override + absolute parquet_root/sqlite_path resolution (CWD-independent). Ready for Wave 4. See [[market-reward-calibration-2026-04-26]] + [[phase-05-1-fill-model-fit-summary]].
- [2026-04-28 05.1-04b] Engine-completeness fix: _aggregate_daily_pnl now composes (reward_accrual − fill_loss) per UTC day. Prior version captured only FILL_REALIZED pnl_pendle, making the bootstrapped p5 unconditionally ≤ 0 for any reward-driven strategy — guaranteeing a false-negative FAIL on Wave 4's binding ship-gate. Fix integrates r_share_per_epoch_pendle from decision_log via config.reward_share_model.epoch_days + config.decision.decision_loop_interval_s (PROTO-04 SSoT, no hard-coded constants). 5/5 tests GREEN (3 existing + 2 new regression tests: reward-only produces strictly positive daily_pnl; full-epoch integration reproduces r_share within 1e-6 rel). Commit 26bac74. Wiki [[backtest-daily-pnl-aggregation-v05]] filed Status: Current.
- [2026-04-29 05.1-05 FAIL] Phase 05.1 ship-gate FAILED on real data: market=BINANCE-ETHUSDT-25SEP2026 side=long; p5_annualized_pnl=0.004897 vs threshold=0.0600 (delta=−0.05510); run_id=01KQB9CPQAQS31P2ZSY14DHYH6; PROJECT HALTED. Real kill report at docs/kill-report-20260429.md (real ULID, real markets, no fixture leaks). Two engine-completeness gaps documented (sparse-event tick under-counting, loss_model SQL column mismatch) — neither closes the 5.51 ppt gap. See [[ship-gate-verdict-20260429]] Status: Current — Phase 5 ship-gate FAIL, project halted.
- [2026-04-29 re-run FAIL] Phase 05.1 ship-gate re-run (corrected stale inputs): p5=0.0244 (2.44% APR) vs threshold=0.0600; delta=−0.0356 (−3.56 ppt); run_id=01KQDMC1DC3JW07VG2VMKKXM6T. Input fixes: pendle_price_usd 7.0→1.35 (+4.98× reward lift), loss_model SQL corrected (246 fill rows vs 0), pyarrow workaround (.fetchall() path). Still FAIL — residual gap dominated by sparse-event tick under-counting (structural engine gap, unfixed). Real kill report at docs/kill-report-20260429-rerun.md. See [[ship-gate-verdict-20260429-rerun]].
- URL pattern Branch A: files.json master manifest + per-file static GET (no server-side folder ZIP); market-ID numeric-prefix divergence requires Wave 1 GET /markets cross-reference
- data.ndjson declared as new storage node in architecture.yml; Wave 1 plan adds reads edges from ingester
- scripts/__init__.py + pythonpath='..' added so python/tests can import scripts.fetch_historical_data as a package

### Roadmap Evolution

- Phase 05.1 inserted after Phase 5: Ship-Gate Execution — Historical Data Fetch + Ingest + Screener + Economics Gate + Backtest Run (URGENT — Phase 5 engineering verified green but ship-gate decision never run on real ingested data; only synthetic tests + 41-row UAT clo_history snapshot exist; historical NDJSON fetcher missing from codebase. Source identified: `https://historical-data.boros.finance` (public ZIP/NDJSON, no auth, updated every 2-3 days). Local alembic head = 0002, behind Phase-4's 0007.)

### Pending Todos

None yet.

### Blockers/Concerns

- **[2026-04-30 HALT — pending Phase 05.2 fix] Phase 05.1 FAIL caused by 5 engine bugs** (not strategy non-viability). Forensic audit on 2026-04-30 via dapp UI probing surfaced: (1) `notional_per_yu_usd = 90,000` placeholder hardcoded to BTC value, semantically should be `margin_per_yu_usd ≈ $18.30` for binding market — ~5,000× APR suppression; (2) `long_side_split = 0.784` should be 0.327 (operator entered backward) — 2.4×; (3) `competition_history` empty in backtest sqlite → `sigma_others = 0` via silent bare-except — 330,000× inflation; (4) sparse-tick under-counting (already documented) — 10,000× suppression; (5) units bug — 22× inflation, **fixed in commit 9625c93**. Net of (3)+(4)+(5) ≈ cancel. Bug (1) alone explains the 5,000× APR suppression that produced the FAIL. **Predicted verdict at $100 collateral on binding market with all 5 bugs fixed: ~415% USD-APR PASS.** Phase 05.2 directory created with full audit context — see `.planning/phases/05.2-sizer-replay-reconcile-to-production/05.2-CONTEXT.md`. Next session: `/gsd-plan-phase 05.2` to formalize.
- ~~Phase 0 P0-02 (minimum order size) is existential~~ **Resolved 2026-04-23** — no protocol minimum. Existential halt-condition is off the table.
- ~~Phase 0 P0-01 (voluntary-cancel forfeit behavior) may drive material divergence in Phase 5 backtest sensitivity; if so, Phase 7 paper is blocked until P0-01 is resolved.~~ **Resolved 2026-04-23** — `voluntary_cancel_forfeits_accumulated = False`; sensitivity row demoted to sanity check, no longer a blocker.
- ~~P0-04 PARTIAL~~ **Resolved 2026-04-23** — Send Txs Bot is the mandatory submission lane; direct-submit ruled out. Latency budget closes on ~1–3s typical, <5s worst, with pre-signed calldata + Send Txs Bot. [[Sign-only cancel primitive]], [[Send Txs Bot integration]].
- Nautilus-adapter vs hand-rolled backtest is a Phase-5 day-1 bailout decision (2-day budget to bail).

## Session Continuity

Last session: 2026-04-30T04:55:25.058Z
Stopped at: context exhaustion at 90% (2026-04-30)
Resume file: None

**Next action:** In a fresh session, run `/gsd-plan-phase 05.2` to formalize the wave-decomposition (Wave 0 evidence → Wave 1 sizer schema → Wave 2 calibration refresh + n_fills audit → Wave 3 sigma_others-from-parquet → Wave 4 sparse-tick synthesis → Wave 5 re-run binding ship-gate). The CONTEXT.md is the single input the planner agent needs.

**Planned Phase:** 05.2 (sizer-replay-reconcile-to-production) — 7 plans — 2026-04-30T03:25:45.376Z
