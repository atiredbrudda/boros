---
gsd_state_version: 1.0
milestone: v0.5
milestone_name: milestone
status: executing
stopped_at: Completed 01-01-PLAN.md — BotConfig + monorepo scaffold landed
last_updated: "2026-04-23T22:25:10.309Z"
last_activity: 2026-04-23
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 12
  completed_plans: 1
  percent: 8
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-23)

**Core value:** Earn net-positive yield on $100 collateral from the Boros Limit Order Liquidity Rewards pool that beats stablecoin alternatives, after gas and fill-loss — on a live, single-market deployment. If -EV, detect cheaply and kill; do not limp.
**Current focus:** Phase 01 — foundation-infrastructure-spine-data-pipeline-economics-gate

## Current Position

Phase: 01 (foundation-infrastructure-spine-data-pipeline-economics-gate) — EXECUTING
Plan: 2 of 12
Status: Ready to execute
Last activity: 2026-04-23

Progress: [█░░░░░░░░░] 8%

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

### Pending Todos

None yet.

### Blockers/Concerns

- ~~Phase 0 P0-02 (minimum order size) is existential~~ **Resolved 2026-04-23** — no protocol minimum. Existential halt-condition is off the table.
- ~~Phase 0 P0-01 (voluntary-cancel forfeit behavior) may drive material divergence in Phase 5 backtest sensitivity; if so, Phase 7 paper is blocked until P0-01 is resolved.~~ **Resolved 2026-04-23** — `voluntary_cancel_forfeits_accumulated = False`; sensitivity row demoted to sanity check, no longer a blocker.
- ~~P0-04 PARTIAL~~ **Resolved 2026-04-23** — Send Txs Bot is the mandatory submission lane; direct-submit ruled out. Latency budget closes on ~1–3s typical, <5s worst, with pre-signed calldata + Send Txs Bot. [[Sign-only cancel primitive]], [[Send Txs Bot integration]].
- Nautilus-adapter vs hand-rolled backtest is a Phase-5 day-1 bailout decision (2-day budget to bail).

## Session Continuity

Last session: 2026-04-23T22:25:10.306Z
Stopped at: Completed 01-01-PLAN.md — BotConfig + monorepo scaffold landed
Resume file: None

**Planned Phase:** 01 (Foundation (Infrastructure Spine + Data Pipeline + Economics Gate)) — 12 plans — 2026-04-23T20:08:16.743Z
