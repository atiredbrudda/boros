# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-23)

**Core value:** Earn net-positive yield on $100 collateral from the Boros Limit Order Liquidity Rewards pool that beats stablecoin alternatives, after gas and fill-loss — on a live, single-market deployment. If -EV, detect cheaply and kill; do not limp.
**Current focus:** Phase 0 — Prerequisite Resolution & Kill Gate

## Current Position

Phase: 0 of 8 (Prerequisite Resolution & Kill Gate)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-04-23 — ROADMAP.md created; 95 v1 requirements mapped to 8 phases

Progress: [░░░░░░░░░░] 0%

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

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. Recent decisions affecting current work:

- [Init]: Target only Limit Order Liquidity Rewards pool; ignore Maker Volume.
- [Init]: Python brain (models/backtest) + TypeScript hands (SDK/execution) split over ZMQ IPC.
- [Init]: EV-based cancel rule (no threshold dials); `voluntary_cancel_forfeits_accumulated` flag present until P0-01 confirmed.
- [Init]: Build engine with both branches; Phase 5 backtest reports sensitivity to both A1 branches.
- [Roadmap]: Phase 0 is a hard kill-gate — project halts if protocol minimum order size exceeds $100 on every candidate market (P0-02).
- [Roadmap]: Engineering Protocols (wiki, architecture diagram, RUN_MANIFEST) anchor in Phase 1 as cross-cutting infrastructure; apply to every subsequent phase.
- [Roadmap]: Merged Phase 3 (loss model) + Phase 4 (reward-share/sizing) into a single Phase 3 — both are small EV-input producers; kept Paper (Phase 7) and Live (Phase 8) distinct per deliverable-type rule.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 0 P0-02 (minimum order size) is existential: if > $100-collateral-equivalent on every candidate market, v0.5 halts before any engineering.
- Phase 0 P0-01 (voluntary-cancel forfeit behavior) may drive material divergence in Phase 5 backtest sensitivity; if so, Phase 7 paper is blocked until P0-01 is resolved.
- Nautilus-adapter vs hand-rolled backtest is a Phase-5 day-1 bailout decision (2-day budget to bail).

## Session Continuity

Last session: 2026-04-23
Stopped at: Roadmap created, 95 requirements mapped, ready to plan Phase 0.
Resume file: None
