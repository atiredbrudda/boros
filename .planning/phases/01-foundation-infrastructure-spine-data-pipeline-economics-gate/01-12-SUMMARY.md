---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
plan: 12
subsystem: screener
tags: [economics-gate, kill-switch, daily-rescreen, launchd, pydantic, structlog]

# Dependency graph
requires:
  - phase: 01-11
    provides: screener filter + MarketScreeningResult + r_apr_potential in screener_metrics.json
  - phase: 01-10
    provides: reward_budget_history table with e_liq_per_epoch
  - phase: 01-06
    provides: load_config + load_raw_yaml + BotConfig.screener knobs
provides:
  - DATA-09 economics kill-switch (compute_r_apr_on_collateral_pendle + run_economics_gate)
  - ProjectHalt halt with docs/kill-report-YYYYMMDD.md written on empty shortlist
  - Fail-loud config validation: missing or out-of-range alt_yield/fill_loss_coarse_bound = ConfigError + exit 2
  - DATA-10 daily re-screen pipeline (ingest -> screener -> economics gate -> diff)
  - var/reports/rescreen_diff.json with new_entrants/dropped/unchanged
  - launchd CalendarInterval plist (com.boros.rescreen) at 03:00 UTC daily
affects:
  - Phase 2+ all plans (shortlist drives which market Phase 2 models are built for)
  - Phase 3 (USD conversion replaces PENDLE-units gate; supersedes [[fill_loss_coarse_bound v0.5]])
  - Phase 5 (backtest compares fill_loss_coarse_bound=0.02 against empirical LossModel)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail-loud kill-switch: raw YAML asserted BEFORE Pydantic validation to prevent silent-default bypass (T-01-12-01)"
    - "Unit-confusion guard: decimal-fraction APR range check (0.0, 0.5) on alt_yield before any market evaluation"
    - "PENDLE-units APR computation: R_apr = R_share_per_epoch * 52 / required_collateral_pendle -- avoids pendle_price_usd knob"
    - "Staged pipeline helper functions (_run_ingest_stage, _run_screener_stage, _run_gate_stage) for mockable TDD"
    - "ProjectHalt inherits SystemExit so bare except Exception cannot swallow it"

key-files:
  created:
    - python/src/boros_brain/screener/economics_gate.py
    - python/src/boros_brain/screener/kill_report.py
    - python/src/boros_brain/screener/rescreen.py
    - scripts/launchd/com.boros.rescreen.plist
    - docs/kill-report-template.md
    - python/tests/test_economics_kill_switch.py
    - python/tests/test_kill_report_template.py
    - python/tests/test_daily_rescreen.py
    - python/tests/fixtures/rescreen_yesterday_shortlist.json
    - python/tests/fixtures/rescreen_today_shortlist.json
  modified:
    - strategy/v0.5-default.yaml
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
    - python/src/boros_brain/screener/cli.py

key-decisions:
  - "R_apr computed in PENDLE-units only (checker issue #06 Option A): avoids pendle_price_usd knob + stale-price risk in Phase 1; USD variant deferred to Phase 3 PricingConfig sub-model"
  - "kill-switch checks raw YAML before Pydantic so operator typo (commented-out knob) = ConfigError exit 2, not silent default acceptance"
  - "fill_loss_coarse_bound=0.02 is A1-flagged coarse bound; documented in strategy YAML and [[fill_loss_coarse_bound v0.5]] wiki page; Phase 3 refines with empirical LossModel"
  - "Daily re-screen runs all three stages (ingest, screener, gate) to prevent stale-data halt decisions (T-01-12-03)"

patterns-established:
  - "Kill-switch halt artifact: write docs/kill-report-YYYYMMDD.md before raising ProjectHalt so operator can reproduce decision weeks later (T-01-12-04)"
  - "Shortlist diff: load yesterday from var/reports/shortlist_previous.json BEFORE running gate so diff is accurate even on empty-shortlist halt"
  - "Stage isolation for testability: each pipeline stage (_run_ingest_stage etc.) is a named function patchable in tests"

requirements-completed: [DATA-09, DATA-10, PROTO-05]

# Metrics
duration: 35min
completed: 2026-04-24
---

# Phase 01 Plan 12: Economics Kill-Switch + Daily Re-Screen Summary

**PENDLE-units economics kill-switch (DATA-09) halts project on empty shortlist with auditable kill-report; launchd daily re-screen (DATA-10) diffs shortlist within 24h to catch crowding-in during Phase 2 engineering**

## Performance

- **Duration:** ~35 min (continuation execution — Task 1 completed in prior run at 894a632)
- **Started:** 2026-04-24 (continuation from Task 1 commit)
- **Completed:** 2026-04-24
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 11

## Accomplishments

- DATA-09 economics kill-switch: `compute_r_apr_on_collateral_pendle()` implements verbatim formula from 01-RESEARCH.md §Pattern 10 with `EPOCHS_PER_YEAR = 52` locked constant; computed in PENDLE-units (no `pendle_price_usd` knob, per checker issue #06)
- Fail-loud config validation: raw YAML asserted before Pydantic runs; missing `alt_yield` or `fill_loss_coarse_bound` = `ConfigError` + exit 2; unit-confusion (e.g. 5.0 instead of 0.05) = `ConfigError` with diagnostic message; both threats T-01-12-01 and T-01-12-02 mitigated with tests
- Empty-shortlist halt: `ProjectHalt` + `docs/kill-report-YYYYMMDD.md` written with per-market R_apr table, knob tree snapshot, and remediation guidance (T-01-12-04)
- DATA-10 daily re-screen: `rescreen.py` pipeline (ingest NDJSON -> screener -> economics gate -> diff); `rescreen_diff.json` with `new_entrants`/`dropped`/`unchanged`; PITFALLS §A5 documented in module + function docstrings
- `com.boros.rescreen.plist`: `StartCalendarInterval` Hour=3 Minute=0, `TZ=UTC`, `KeepAlive=false` — `plutil -lint` passes

## Task Commits

Each task committed atomically with TDD RED/GREEN flow:

1. **Task 1 RED: DATA-09 kill-switch tests** - included in `894a632` (feat — tests + implementation committed together by prior run; TDD gating was done within the executor session)
2. **Task 1 GREEN: DATA-09 economics kill-switch** - `894a632` feat(01-12)
3. **Task 2 RED: DATA-10 daily re-screen tests** - `ab214b7` test(01-12)
4. **Task 2 GREEN: DATA-10 daily re-screen + plist** - `b71b1b5` feat(01-12)

**Plan metadata commit:** (to follow as docs commit)

## Files Created/Modified

- `python/src/boros_brain/screener/economics_gate.py` - DATA-09 kill-switch: formula + ConfigError/ProjectHalt + fail-loud knob validation
- `python/src/boros_brain/screener/kill_report.py` - writes `docs/kill-report-YYYYMMDD.md` on halt
- `python/src/boros_brain/screener/rescreen.py` - DATA-10 daily re-screen pipeline + diff writer
- `scripts/launchd/com.boros.rescreen.plist` - CalendarInterval 03:00 UTC daily, one-shot
- `docs/kill-report-template.md` - Markdown template rendered by `write_kill_report()`
- `strategy/v0.5-default.yaml` - added `alt_yield: 0.05` and `fill_loss_coarse_bound: 0.02` with A1/unit-confusion comments
- `docs/architecture.yml` - 4 new nodes (economics_gate, kill_report, rescreen, launchd.com.boros.rescreen) + 9 new edges
- `docs/ARCHITECTURE.md` - Mermaid mirror updated
- `python/src/boros_brain/screener/cli.py` - `--economics-gate` flag + exit code contract (0/1/2)
- `python/tests/test_economics_kill_switch.py` - 8 test cases for DATA-09
- `python/tests/test_kill_report_template.py` - kill-report template validation
- `python/tests/test_daily_rescreen.py` - 6 test cases for DATA-10
- `python/tests/fixtures/rescreen_{yesterday,today}_shortlist.json` - diff test fixtures

## Decisions Made

- **PENDLE-units only (checker issue #06 Option A):** `R_apr_pendle = R_share_per_epoch_pendle * 52 / required_collateral_pendle` — avoids introducing a `pendle_price_usd` config knob in Phase 1 without a price oracle. USD conversion deferred to Phase 3 `PricingConfig` sub-model. When Phase 3 lands, update `[[fill_loss_coarse_bound v0.5]]` and `[[Economics kill-switch v0.5]]` with `Status: Historical`.
- **fill_loss_coarse_bound=0.02 is an A1 coarse bound:** Documented in `strategy/v0.5-default.yaml` with comment "coarse bound, Phase-3 refines"; also in `[[fill_loss_coarse_bound v0.5]]` wiki page. DO NOT tune below 0.02 until Phase 3 LossModel lands.
- **Default threshold = 7% APR decimal:** `alt_yield (0.05) + fill_loss_coarse_bound (0.02) = 0.07`. Recorded here for Phase 3 comparison when A1 is refined.
- **First-run economics gate: no real data yet available** — `var/reports/screener_metrics.json` only exists after a live screener run against actual parquet data. The kill-switch tests use fixture JSON files; a live halt decision requires first running DATA-08 against ingested data.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff SIM117 in test_halt_propagation**
- **Found during:** Task 2 RED commit (pre-commit hook)
- **Issue:** Nested `with` blocks (`with (patches): with pytest.raises(...)`) flagged by ruff SIM117 — should be single `with` statement
- **Fix:** Merged `pytest.raises(ProjectHalt)` into the outer `with (...)` context manager group
- **Files modified:** `python/tests/test_daily_rescreen.py`
- **Verification:** `ruff` pre-commit passes; test still passes after refactor
- **Committed in:** `ab214b7` (Task 2 RED commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug / lint error)
**Impact on plan:** Trivial cosmetic fix. No logic change.

## Issues Encountered

- **Pre-existing test failure:** `test_no_time_time_in_hotpath.py` 3 tests fail due to `FileNotFoundError: python` — macOS environment has no bare `python` in PATH (only `python3`). Pre-existing before this plan's commits (confirmed by stash test). Out of scope; logged in deferred-items.

## Economics Gate First-Run Assessment

**Did the first-run economics gate halt the project?** Not evaluated yet — no live `screener_metrics.json` exists (requires actual parquet data from ingested NDJSON). The kill-switch is ready; it will run at `launchctl load ~/Library/LaunchAgents/com.boros.rescreen.plist` on first 03:00 UTC after operator loads the plist and drops data into `data/raw/`.

**Threshold used:** `alt_yield (0.05) + fill_loss_coarse_bound (0.02) = 0.07` (7% APR decimal)

**Final shortlist for Phase 2:** Pending first live screener run. Phase 2 engineering can begin in parallel with first data collection.

## Wiki Pages Filed

- `[[Economics kill-switch v0.5]]` — Status: Current — formula, knob locations, PENDLE-units rationale, halt behavior, kill-report contract, Phase-3 supersedence marker
- `[[fill_loss_coarse_bound v0.5]]` — Status: Current — 0.02 coarse bound, A1 landmine label, Phase-3 refinement path
- `[[Daily re-screen scheduler]]` — Status: Current — launchd cadence, diff semantics, A5 competition-crowding rationale

## Architecture Diagram Nodes Added

- `brain.screener.economics_gate` — reads config.screener.alt_yield + fill_loss_coarse_bound, reads screener_metrics.json, calls kill_report, raises ProjectHalt
- `brain.screener.kill_report` — writes docs/kill-report-YYYYMMDD.md, reads kill-report-template.md
- `brain.screener.rescreen` — calls screener CLI + economics gate, writes rescreen_diff.json
- `launchd.com.boros.rescreen` — external, invokes brain.screener.rescreen at 03:00 UTC daily

## Open Follow-ups

1. **A1 Phase-3 refinement:** `fill_loss_coarse_bound=0.02` is explicitly a placeholder. Phase 3 LossModel + NHPP fill probability replaces it. When Phase 3 lands, update both wiki pages with `Status: Historical — superseded by [[Economics kill-switch — USD variant v1.0]]`.
2. **Manual launchd load:** Operator must run `launchctl load ~/Library/LaunchAgents/com.boros.rescreen.plist` after copying the plist. First execution appears in `logs/supervisor/com.boros.rescreen.out` the following 03:00 UTC (documented in `01-VALIDATION.md §Manual-Only Verifications`).
3. **Live shortlist pending:** First `run_daily_rescreen()` against real ingested data will produce the Phase 2 market shortlist (or halt + kill-report if no market clears 7% APR).

## Self-Check

- [x] `python/src/boros_brain/screener/rescreen.py` — FOUND
- [x] `scripts/launchd/com.boros.rescreen.plist` — FOUND
- [x] `python/tests/test_daily_rescreen.py` — FOUND
- [x] Commit `ab214b7` (RED) — FOUND
- [x] Commit `b71b1b5` (GREEN) — FOUND
- [x] Commit `894a632` (Task 1) — FOUND

## Self-Check: PASSED

---
*Phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate*
*Completed: 2026-04-24*
