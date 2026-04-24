---
phase: 03-loss-reward-share-models-sizing
plan: 04
subsystem: wiring_phase_gate
tags: [wiring, architecture, main_py, supersedence, proto1, proto2, proto4, proto5, wave-3, phase_gate]
requires:
  - phase: 03
    plan: 01
    provides: [LossModel + replay + refit_loop + ou_parametric scaffold]
  - phase: 03
    plan: 02
    provides: [RewardShareModel + CompetitionTracker + LOCKED-D-01 calibrate + BotConfig schema delta]
  - phase: 03
    plan: 03
    provides: [Sizer + SizerConfig attached to BotConfig]
provides:
  modules:
    - brain.main (extended — spawns 3 Phase-3 async tasks + cancel-on-shutdown)
    - main.py adapters (_CompetitionRestAdapter + _TopicEventPubAdapter — keep 03-02 signature stable)
  schema:
    - architecture.yml — 24 new module nodes + 4 storage nodes + 34 config_knob nodes + ~40 edges
  contracts:
    - replay_historical_fills now sources pendle_price_usd from config.pricing
    - build_per_fill_pnl_from_frame pendle_price_usd kwarg defaults to None
      (resolves from config.pricing.pendle_price_usd) — tests may override
affects:
  - python/src/boros_brain/main.py (spawn block + cancel tuple + adapter classes)
  - python/src/boros_brain/loss_model/replay.py (PricingConfig wiring)
  - scripts/no_time_time_lint.py (3 new banned dirs)
  - python/tests/test_manifest_contains_all_knobs.py (test_phase3_leaves_surfaced)
  - python/tests/test_sqlite_single_writer.py (test_phase3_tables_have_single_writer)
  - docs/architecture.yml (Phase-3 manifest delta — atomic Plan 03-04 commit)
  - docs/ARCHITECTURE.md (Phase-3 Mermaid subgraph)
tech_stack:
  patterns:
    - thin REST/event-pub adapters in main.py (avoid touching 03-02 signature)
    - reflection-based knob count test (>=34 Phase-3 leaves)
    - PROTO-05 supersedence in single atomic edit (3 flipped + 1 promoted + 1 narrowed + 1 new)
key_files:
  modified:
    - python/src/boros_brain/main.py
    - python/src/boros_brain/loss_model/replay.py
    - scripts/no_time_time_lint.py
    - python/tests/test_manifest_contains_all_knobs.py
    - python/tests/test_sqlite_single_writer.py
    - docs/architecture.yml
    - docs/ARCHITECTURE.md
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/fill-loss-coarse-bound-v05.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/economics-kill-switch-v05.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/economics-kill-switch-usd-variant-v10.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/historical-reward-budget-reconstruction-infeasible.md"
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/live-e-liq-polling-data-11.md"
  created:
    - "/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/unit-consistency-pendle-units-v05.md"
decisions:
  - "main.py adapters (_CompetitionRestAdapter + _TopicEventPubAdapter) chosen over refactoring 03-02 signature — keeps the CompetitionTracker contract stable, isolates wiring concerns to main.py."
  - "Phase-3 manifest leaf count is 34 (not 35 as plan-prose stated) — 11 LossModelConfig + 8 FeesConfig + 5 RewardShareModelConfig + 4 PricingConfig + 6 SizerConfig. The `fees` field on LossModelConfig is itself a sub-model so does NOT count as a leaf. Test threshold set to >=34. (Rule 1 - Bug, plan-prose off-by-one.)"
  - "build_per_fill_pnl_from_frame pendle_price_usd kwarg flipped to default None (with config-fallback) instead of removed entirely — preserves the test-injection seam from Plan 03-01 while satisfying Plan 03-04 acceptance criterion §3 (grep returns 0)."
  - "Wiki pages live at /Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/ — external to the repo, so the Protocol-5 supersedences are not part of the in-repo git commits but ARE part of this plan's atomic delivery (matches Plan 03-01/02/03 Task-3 precedent)."
metrics:
  duration_min: 35
  tasks_completed: 3
  files_created: 1   # unit-consistency-pendle-units-v05.md
  files_modified: 12  # 7 in-repo + 5 wiki
  total_tests_added: 2  # test_phase3_leaves_surfaced + test_phase3_tables_have_single_writer
  tests_pass: 247  # full suite minus pre-existing screener_filter (pre-Plan 03-01)
  tests_skip: 1
  completed: "2026-04-24"
---

# Phase 3 Plan 04: Wiring + Architecture + Protocol-5 Supersedence Summary

Phase-3 ship-gate: brain.main.run() spawns the loss-model refit loop +
CompetitionTracker alongside the existing fill-model refit loop with
cancel-on-shutdown discipline; loss_model/replay.py wires
`pendle_price_usd` from `config.pricing` (resolves Plan 03-01 TODO);
`scripts/no_time_time_lint.py` extends to `loss_model/`, `reward_model/`,
`sizer/` (clean baseline confirmed); `docs/architecture.yml` +
`docs/ARCHITECTURE.md` carry the full ~24-module + 34-knob + ~40-edge
Phase-3 delta atomically; 3 wiki Protocol-5 supersedences + 1 promotion +
1 in-place narrowing + 1 new unit-consistency page filed.

## Core Deliverables

### 1. `brain.main.run()` — three Phase-3 async tasks + cancel tuple

`python/src/boros_brain/main.py` extended:
- Synchronous initial loss-model fit at boot (pattern matches existing
  fill-model: `await loss_refit_once(cfg, run_id)` blocks ~15-30s on a warm
  market so `expected_loss()` has an artifact before Phase-4's 1 Hz hot path
  starts).
- `loss_refit_task = asyncio.create_task(run_loss_model_refit_loop(...))` —
  same `(cfg, run_id)` signature as `fill_model.refit_loop`, no extra
  plumbing.
- `comp_task = asyncio.create_task(run_competition_tracker_loop(...))` — the
  competition tracker requires `(conn, rest, event_pub)` per Plan 03-02;
  main.py constructs thin **`_CompetitionRestAdapter`** + **`_TopicEventPubAdapter`**
  classes inline (not in 03-02's tracker code) so the tracker signature stays
  stable.
- Shutdown cancel tuple extended:
  `for t in (send_task, monitor_task, ingest_task, fill_refit_task, loss_refit_task, comp_task)`
  — all three new tasks join the existing `t.cancel(); with contextlib.suppress(asyncio.CancelledError): await t` loop. Side resources
  (`comp_http`, `comp_conn`) are torn down via `contextlib.suppress(Exception)`.

The original `refit_task` was renamed to `fill_refit_task` for clarity.
T-03-11 mitigation (orphan async tasks on shutdown) is enforced by the
extended tuple.

### 2. `loss_model/replay.py` — PricingConfig wiring (Plan 03-01 TODO resolved)

`replay_historical_fills` no longer takes `pendle_price_usd` as a kwarg —
sources it from `config.pricing.pendle_price_usd` (PricingConfig sub-model
attached to BotConfig in Plan 03-02). The TODO comment that Plan 03-01
deferred is removed.

`build_per_fill_pnl_from_frame` (the test-injection seam) keeps the kwarg
but its default is now `None`, falling back to `config.pricing.pendle_price_usd`
when omitted — preserves the test seam without leaving a hard-coded `1.0`
default in the codebase. Plan 03-04 acceptance criterion §3 grep
(`pendle_price_usd: float = 1.0`) returns 0 and `config.pricing.pendle_price_usd`
returns 3 (one in `replay_historical_fills`, one in
`build_per_fill_pnl_from_frame` fallback, plus the docstring reference).

### 3. `scripts/no_time_time_lint.py` — Phase-3 directories added

`_BANNED_DIRS` tuple extended with three new entries:

```python
"python/src/boros_brain/loss_model/",     # Phase 3 Plan 03-04
"python/src/boros_brain/reward_model/",   # Phase 3 Plan 03-04
"python/src/boros_brain/sizer/",          # Phase 3 Plan 03-04
```

Module docstring updated. `python scripts/no_time_time_lint.py` exits 0 —
all three directories are clean (Plans 03-01/02/03 already followed
INFRA-14 discipline pre-emptively per their `<read_first>` references).

### 4. `docs/architecture.yml` — full Phase-3 manifest delta atomically

Single commit (`a392735`) lands:
- **24 new module nodes** — `brain.loss_model.{config,schemas,replay,fit,
  expected_loss,artifact,refit_loop,ou_parametric,cli}` (9) +
  `brain.reward_model.{config,schemas,competition_tracker,r_capped,q_cap,
  calibrate,cli}` (7) + `brain.sizer.{config,schemas,optimizer,cli}` (4) +
  `brain.pricing.config` (1) + 3 state.writers
  (loss_grid_artifacts, competition_history, market_reward_calibration).
- **4 new storage nodes** — `state.loss_grid_artifacts`,
  `state.competition_history`, `state.market_reward_calibration` (with
  LOCKED D-01 note), `parquet.loss_grid_artifacts`.
- **34 new config_knob nodes** — 19 LossModelConfig leaves (incl. 8
  nested fees) + 5 RewardShareModelConfig + 4 PricingConfig + 6 SizerConfig.
- **~40 new edges** — Loss Model wiring (replay → market_trades reads,
  fit → artifact → writer, expected_loss → writer reads, refit_loop →
  chain_time, cli → manifest.writer, main → refit_loop), Reward Model
  wiring (CompetitionTracker → REST + parquet.order_book_raw + state.clo_history;
  calibrate → market_reward_calibration; cli wiring; main → tracker loop),
  Sizer wiring (optimizer → fill_model.predict + loss_model.expected_loss
  + r_capped + q_cap + 6 config_knob `depends-on-config`), and Pricing
  pseudo-edges (config.schema → 4 sub-model configs).

`scripts/architecture_lint.py` exits clean — no drift between code and
manifest.

### 5. `docs/ARCHITECTURE.md` — Phase-3 Mermaid subgraph

New `subgraph phase3` block shows the LossModel / RewardShareModel / Sizer
composition with single-USD-boundary discipline (PricingConfig as the
gateway). Cross-subgraph edges hook `parquet.market_trades →
loss_replay` (DuckDB no-look-ahead replay), `state.clo_history →
comp_tracker` (latest CLO bounds), `parquet.order_book_raw →
comp_tracker` (T-03-06 AMM exclude), `state.open_orders → comp_tracker`
(REST-degraded fallback), `PredictMod → sizer_opt` (Phase-2 LOCKED
contract), and `brain_main → loss_refit + comp_tracker` (Plan 03-04
spawn-points). A Phase-4 placeholder edge (`sizer_opt -.-> brain_main`)
notes the upcoming DecisionEngine consumer.

A new "Phase 3 EV inputs + Sizer (Plans 03-01 / 03-02 / 03-03 / 03-04)"
prose section narrates the wiring and links 10 wiki pages including the
new `[[unit-consistency-pendle-units-v05]]`.

### 6. Test additions — `test_phase3_leaves_surfaced` + `test_phase3_tables_have_single_writer`

`tests/test_manifest_contains_all_knobs.py::test_phase3_leaves_surfaced`
asserts ≥34 Phase-3 leaves total (≥12 loss_model incl. fees, ≥5
reward_share_model, ≥4 pricing, ≥6 sizer) plus 11 spot-checks of
specific critical knobs (`loss_model.depth_bucket_edges`,
`loss_model.fees.taker_fee_rate`, `loss_model.fees.gas_price_gwei`,
`reward_share_model.competition_poll_interval_s`,
`reward_share_model.cap_apr_multiple`, `pricing.pendle_price_usd`,
`pricing.price_source`, `sizer.collateral_usd`, `sizer.q_min_pendle`,
`sizer.notional_per_yu_usd`).

`tests/test_sqlite_single_writer.py::test_phase3_tables_have_single_writer`
asserts the three Phase-3 tables each have exactly one writer module on
disk with the expected `def insert_*(` and `def get_latest_*(` definitions.

### 7. Protocol-5 wiki supersedences (single atomic edit)

| Action | Page | Resulting Status |
|--------|------|------------------|
| Flip Historical | `[[fill-loss-coarse-bound-v05]]` | `Historical — superseded by [[empirical-loss-grid-v05]]` |
| Flip Historical | `[[economics-kill-switch-v05]]` | `Historical — superseded by [[economics-kill-switch-usd-variant-v10]]` |
| Promote Current | `[[economics-kill-switch-usd-variant-v10]]` | `Current` (was `Current — deferred to Phase 3`); +60 lines of promotion content |
| Flip Historical | `[[historical-reward-budget-reconstruction-infeasible]]` | `Historical — superseded by [[e-liq-per-epoch-source-decision]]` |
| In-place narrow | `[[live-e-liq-polling-data-11]]` | `Current — narrowed scope` (E_liq numerator superseded; reward_budget_history lineage retained) |
| New page | `[[unit-consistency-pendle-units-v05]]` | `Current — v0.5 regime` — ~115 lines + 9 wiki cross-references |

Each superseded page has a `> **2026-04-24 SUPERSESSION (Phase 3, Plan
03-04):**` banner immediately below the Status line; original content is
preserved below the banner (renamed to "Historical context" headers) so
historical decision-trail is not lost.

## Phase 3 Ship-Gate Verification

ROADMAP Success Criteria #1-#4:

- [x] **#1 LossModel.expected_loss covers grid with sparse-cell fallback** —
  Plan 03-01 (PASS).
- [x] **#2 RewardShareModel sub_cap at \$100, cap_binding at \$5k** —
  Plan 03-02 (PASS).
- [x] **#3 Sizer Q_me_target returns Q_min at \$100, Q_me < Q_cap at
  \$5k** — Plan 03-03 (PASS).
- [x] **#4 OU scaffold with failing stub** — Plan 03-01 (PASS).

Plan 03-04 mechanical verification:

- [x] `brain.main.run()` spawns 3 Phase-3 async tasks; all join cancel
  tuple — verified by reading main.py + grep.
- [x] `scripts/no_time_time_lint.py` exits 0 with 3 new dirs banned —
  verified by `uv --project python run python scripts/no_time_time_lint.py`.
- [x] `scripts/sqlite_writer_lint.py` exits 0 — verified.
- [x] `scripts/architecture_lint.py` exits 0 — verified.
- [x] `docs/architecture.yml` + `docs/ARCHITECTURE.md` carry the full
  Phase-3 delta atomically (single commit `a392735`).
- [x] `test_phase3_leaves_surfaced` PASS (34 leaves).
- [x] `test_phase3_tables_have_single_writer` PASS.
- [x] Full pytest suite green except pre-existing screener_filter
  failures (documented in Plan 03-01 SUMMARY as out-of-scope).
- [x] Protocol-5 supersedences applied atomically (3 flipped + 1
  promoted + 1 narrowed + 1 new).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan-prose Phase-3 leaf count off by one (35 → 34)**

- **Found during:** Task 1 (`test_phase3_leaves_surfaced` initial run failed
  with "expected >=35 total Phase-3 leaves, got 34").
- **Issue:** Plan 03-04 plan-prose stated "≥35 Phase-3 knob leaves
  (loss_model.* (20 incl. fees.* nested) + reward_share_model.* (5) +
  pricing.* (4) + sizer.* (6)) = ~35 minimum". Actual count is 34: 11
  LossModelConfig leaves (the `fees` field on LossModelConfig is itself
  a StrictBase sub-model so does NOT count as a leaf; `_collect_leaf_paths`
  recurses INTO it) + 8 FeesConfig nested leaves = 19 loss_model leaves,
  + 5 reward_share_model + 4 pricing + 6 sizer = 34 total.
- **Fix:** Set the aggregate threshold in `test_phase3_leaves_surfaced`
  to `>= 34` with an inline comment explaining the off-by-one. Per-sub-model
  thresholds (≥12, ≥5, ≥4, ≥6) preserved as plan-spec wrote them.
- **Files modified:** `python/tests/test_manifest_contains_all_knobs.py`.
- **Commit:** 71f79f3.

**2. [Rule 1 - Bug] `build_per_fill_pnl_from_frame` retained `pendle_price_usd: float = 1.0` default**

- **Found during:** Task 1 self-check on plan acceptance criterion §3
  (`grep -c 'pendle_price_usd: float = 1.0' replay.py == 0`).
- **Issue:** The plan instructed "Remove the `*, pendle_price_usd: float = 1.0`
  kwarg." from `replay_historical_fills` — done. But the test-injection seam
  helper `build_per_fill_pnl_from_frame` ALSO had the same default; the plan
  acceptance criterion is a literal grep over the full file, so even the
  helper-default trips it.
- **Fix:** Flipped helper kwarg to `pendle_price_usd: float | None = None`
  with config-fallback (`config.pricing.pendle_price_usd` when omitted).
  Tests that pass an explicit value still work; tests that don't get the
  config value via fallback. Grep now returns 0.
- **Files modified:** `python/src/boros_brain/loss_model/replay.py`.
- **Commit:** ab733c4.

**3. [Plan-aligned] CompetitionTracker REST + event_pub adapter pattern (executor's call)**

- **Found during:** Task 1 main.py wiring.
- **Issue:** Plan offered two options for resolving CompetitionTracker's
  `(conn, rest, event_pub)` signature mismatch with main.py's existing
  constructs: (a) instantiate REST inside the loop, (b) refactor 03-02's
  signature. Plan said "Executor's call".
- **Fix:** Chose option (c) — thin adapter classes (`_CompetitionRestAdapter`,
  `_TopicEventPubAdapter`) inline in main.py. Keeps the tracker's signature
  stable (no edits to 03-02's competition_tracker.py), isolates wiring
  concerns to main.py, and makes the event-pub semantics explicit (degraded
  events surface as structured WARNING log lines bound to run_id via
  contextvars rather than ZMQ messages — they are rare operator-facing
  signals, not cross-process events).
- **Files modified:** `python/src/boros_brain/main.py`.
- **Commit:** 71f79f3.

### No Rule-4 (architectural) checkpoints encountered.

## Auth Gates

None. The plan is pure wiring + lint extension + test additions + wiki
edits — no network endpoints requiring auth, no operator-only secrets.

## Known Stubs / Open TODOs

These are explicitly deferred to Phase 4 — they are NOT bugs:

| TODO | File | Plan that closes it |
|------|------|---------------------|
| DecisionEngine wiring of `q_me_target` into the 1 Hz loop | `python/src/boros_brain/main.py` | Phase 4 |
| SAFE-09 breaker pattern for CompetitionTracker staleness | TBD (Phase 4) | Phase 4 |
| OU empirical implementation (replaces NotImplementedError scaffold) | `loss_model/ou_parametric.py:fit_ou_basis` | v1.0 |
| Chainlink/Pyth price oracle (replaces operator-manual) | `pricing/config.py` + new oracle module | v1.0 |
| Merkle-delta historical reward budget reconstruction | TBD | v1.0 (Phase 8 live operation) |

## Threat Flags

None. The plan's `<threat_model>` enumerated 3 threats (T-03-11 orphan
async tasks, T-03-12 architecture.yml drift, T-03-13 wiki supersedence
content loss) — all mitigated:

- T-03-11: cancel tuple extended to include `loss_refit_task` + `comp_task`;
  main.py also tears down `comp_http` (httpx AsyncClient) +
  `comp_conn` (SQLite connection) via `contextlib.suppress(Exception)`
  after the cancel-loop.
- T-03-12: `scripts/architecture_lint.py` exits 0 — no drift remains.
  `test_architecture_lint_clean` passes.
- T-03-13: every superseded page preserves its original content below the
  new banner under a renamed "Historical context" header; file sizes
  expanded (not shrank) after edits, confirmed manually.

No NEW threat-relevant surface beyond what the plan enumerated. The
adapter classes in main.py are pure-function-equivalent shims (one
`async post_all_limit_orders` + one `async publish`); they do not
introduce new auth boundaries or cross-process surfaces.

## Deferred / Out-of-Scope Test Failures

**Pre-existing, NOT caused by Plan 03-04** (documented in Plans
03-01/02/03 SUMMARY too):

- `tests/test_screener_filter.py::test_all_six_filters_applied` —
  `_duckdb.BinderException: size_float not found`.
- `tests/test_screener_filter.py::test_shortlist_capped_at_four` — same
  root cause.
- `tests/test_screener_filter.py::test_r_apr_potential_ranking` — same
  root cause.

These pre-date Phase 3 (verified by reading Plan 03-01 SUMMARY's
`## Deferred / Out-of-Scope Test Failures` section). Routed to
`.planning/phases/03-loss-reward-share-models-sizing/deferred-items.md` if
absent there; not blocking Phase 3 ship.

Full pytest suite (excluding pre-existing failures): **247 PASS + 1
SKIP** (the 1 skip is the Phase-5 backtest integration placeholder from
Plan 03-01).

## TDD Gate Compliance

Plan-level type is `execute` (not `tdd`); each task's `tdd="true"` was
honored: tests written alongside implementation, landing in the same
commits as the code they exercise.

Per-task commit hashes:

- Task 1 (`71f79f3`): main.py spawn-block + loss_model/replay.py wiring +
  no_time_time_lint extension + 2 new tests (test_phase3_leaves_surfaced
  + test_phase3_tables_have_single_writer).
- Task 1 follow-up (`ab733c4`): drop `pendle_price_usd: float = 1.0`
  from `build_per_fill_pnl_from_frame` — satisfies acceptance criterion
  §3 literal grep.
- Task 2 (`a392735`): docs/architecture.yml + docs/ARCHITECTURE.md
  Phase-3 delta atomic.
- Task 3 (no in-repo commit): wiki pages live at
  `/Users/macbookair/Documents/project/test/rerun7/LLM Wiki/workspaces/boros/wiki/`
  per CLAUDE.md Engineering Protocol 1 — same convention as Plan
  03-01/02/03 Task-3.

## Self-Check: PASSED

**Files modified (in-repo) — verified via Read tool + grep:**
- `python/src/boros_brain/main.py` — FOUND
  (`grep -c 'run_loss_model_refit_loop' main.py` = 2;
  `grep -c 'run_competition_tracker_loop' main.py` = 2;
  `loss_refit_task` + `comp_task` in cancel-tuple)
- `python/src/boros_brain/loss_model/replay.py` — FOUND
  (`grep -c 'pendle_price_usd: float = 1.0'` = 0;
  `grep -c 'config.pricing.pendle_price_usd'` = 3)
- `scripts/no_time_time_lint.py` — FOUND
  (`grep -c '"python/src/boros_brain/loss_model/"'` = 1;
  `grep -c '"python/src/boros_brain/reward_model/"'` = 1;
  `grep -c '"python/src/boros_brain/sizer/"'` = 1)
- `python/tests/test_manifest_contains_all_knobs.py` — FOUND
  (`test_phase3_leaves_surfaced` defined; PASSES)
- `python/tests/test_sqlite_single_writer.py` — FOUND
  (`test_phase3_tables_have_single_writer` defined; PASSES)
- `docs/architecture.yml` — FOUND
  (44 `brain.loss_model.` refs, 40 `brain.reward_model.` refs, 24
  `brain.sizer.` refs, 9 storage refs, 49 config_knob refs;
  `architecture_lint.py` exits 0)
- `docs/ARCHITECTURE.md` — FOUND (Phase 3 substring count: 5; new
  `subgraph phase3` block + cross-subgraph edges + Phase-3 prose section)

**Files created/modified (LLM Wiki, external) — verified via grep:**
- `fill-loss-coarse-bound-v05.md` — FOUND with `Status: Historical —
  superseded by [[empirical-loss-grid-v05]]`
- `economics-kill-switch-v05.md` — FOUND with `Status: Historical —
  superseded by [[economics-kill-switch-usd-variant-v10]]`
- `economics-kill-switch-usd-variant-v10.md` — FOUND with
  `Status: Current` (no `— deferred` qualifier) + new "Promoted
  2026-04-24 (Phase 3, Plan 03-04)" section
- `historical-reward-budget-reconstruction-infeasible.md` — FOUND with
  `Status: Historical — superseded by [[e-liq-per-epoch-source-decision]]`
- `live-e-liq-polling-data-11.md` — FOUND with `Status: Current —
  narrowed scope` + `SCOPE NARROWING` banner
- `unit-consistency-pendle-units-v05.md` — FOUND (NEW) with
  `Status: Current — v0.5 regime` + 9 `[[wiki-link]]` cross-references

**Commits (in-repo):**
- `71f79f3` — FOUND (Task 1)
- `a392735` — FOUND (Task 2)
- `ab733c4` — FOUND (Task 1 follow-up)
