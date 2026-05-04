# Phase 05.4 — Deferred Items

**Phase status:** in-progress (Plan 04 verdict pending)
**Last updated:** 2026-05-04

---

## Bug B (replay loop terminates at trade #65/237)

- **Disposition:** cascade
- **Investigation budget:** 2 hours (per CONTEXT.md line 108)
- **Time used:** ~0h 25m (forensic analysis of T6 log was conclusive without bisection)
- **Root cause:** Not an independent bug. The T6 baseline replay loop DID process all 237
  trades (full 25.74-day window). The diagnosis of "loop termination at trade #65" was a
  misinterpretation of the decision_log coverage metric:
  - `decision_log` records events only while an order is ACTIVE (placed → filled/cancelled).
  - The initial order was placed at day 0 (2026-03-31T15:22:48Z) and FILLED at day 7.72
    (2026-04-08T08:35:14Z, trade #65 of 237 in the real-event sense but only the 11th
    fill-trigger event across 66,696 decision ticks).
  - After the fill, no new order was placed (Bug A's missing calibration → no EV signal →
    no re-placement). Decision_log stopped because no active order = no decisions.
  - The T6 baseline completed in **3.5 minutes** (baseline_start=13:48:26Z →
    cancel_latency_sweep_start=13:52:10Z per `01KQFABR9VNPMKKQYPTQGRJMDR.backtest-cli.log.jsonl`).
  - The T6 was killed at ~19:02Z DURING THE PERTURBATION GRID, not during the baseline.
- **Last yielded chain_ts (T6 baseline):** inferred ~1775919210 (2026-04-26T09:13:30Z —
  the last market trade timestamp; loop completed normally)
- **Last active-order chain_ts (T6 decision_log):** 1775637314 (2026-04-08T08:35:14Z)
- **Smoke run_id:** 01KQTFK1X7GBNQWS7CBDMKX43F (started 2026-05-04T21:51:27Z, still running
  against Bug-A-fixed engine; estimated 9-10h wall-time due to full calibration computation)
- **Diagnostic log:** `var/phase054-bug-b-bisect.log` (gitignored)
- **Resolution evidence:** T6 log forensic analysis shows the baseline completed; no
  independent replay-loop termination bug existed. Bug B was downstream of Bug A in the
  sense that Bug A's missing calibration caused no post-fill order re-placement, making
  the decision_log appear truncated.
- **Phase 05.5 entry conditions:** N/A (Bug B resolved as cascade/misdiagnosis)

## Bug B: misidentified diagnostic metric — follow-up note

For Phase 05.4-04 binding ship-gate re-run: the decision_log span will again reflect the
ACTIVE ORDER PERIOD only (from initial placement to first fill or replay-end). This is
expected. The correct metric for "full replay coverage" is:
- `grep -c "cancel_latency_sweep_start" backtest-cli.log.jsonl` should return ≥ 1
  (baseline completed before sweep starts)
- NOT the decision_log span alone

## Pre-existing test failures (inherited from Phase 05.3)

The following 5 test failures were documented in `.planning/phases/05.3-fill-path-repair/deferred-items.md`
and remain deferred into Phase 05.4. They are not caused by any 05.4 changes:

1. `tests/test_backtest_run_manifest_first.py::test_backtest_writes_sidecar_json`
2. `tests/test_backtest_run_manifest_sidecar.py::test_sidecar_atomic_write`
3. `tests/test_backtest_run_manifest_sidecar.py::test_sidecar_content_matches_manifest_dump`
4. `tests/test_screener_filter.py::test_all_six_filters_applied`
5. `tests/test_screener_filter.py::test_shortlist_capped_at_four`

Root causes: (1)-(3) CWD-resolution mismatch in manifest sidecar test; (4)-(5) CLO tick
conversion fixture drift (Phase 5.1 W1.5 hardening side effect).

These are out of scope for Phase 05.4 (orthogonal to A/B/C/D bugs). Route to Phase 05.5
or a dedicated screener-fixture-repair plan if they block future work.

## See also

- [[phase-05-3-bugs-discovered-during-t6]] (parent diagnosis)
- [[phase-05-4-bug-a-calibration-migration]] (the prerequisite fix)
- [[phase-05-4-bug-b-investigation]] (this Bug B investigation page)
