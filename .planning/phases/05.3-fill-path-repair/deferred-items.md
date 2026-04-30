# Phase 05.3 — Deferred items

Pre-existing test failures and out-of-scope discoveries surfaced during Plan
01 execution but explicitly NOT addressed in this plan (per the executor's
scope-boundary rule: only auto-fix issues directly caused by the current
task's changes).

## Pre-existing failures observed during T2 (committed unchanged from HEAD)

Verified via `git stash` of T2 changes — all three fail on HEAD without
T2 modifications.

1. **`tests/test_backtest_run_manifest_first.py::test_backtest_writes_sidecar_json`**
   - Failure: `ValueError: backtest manifest sidecar path traversal blocked:
     /Users/macbookair/boros/python/var/backtest/<ulid> is outside
     /Users/macbookair/boros/var/backtest`.
   - Cause: working directory mismatch — pytest runs in `python/` but the
     guard expects the repo-root `var/backtest`. Pre-existing CWD-dependent
     test.

2. **`tests/test_backtest_run_manifest_sidecar.py::test_sidecar_atomic_write`**
   - Same root cause as (1).

3. **`tests/test_backtest_run_manifest_sidecar.py::test_sidecar_content_matches_manifest_dump`**
   - Same root cause as (1).

4. **`tests/test_screener_filter.py::test_all_six_filters_applied`**
   - Failure: `Market E should pass all filters; failures:
     ['zero_depth_at_clo']`.
   - Cause: the test fixture's order-book data does not have positive depth
     within the converted CLO tick range. Likely a fixture drift after the
     CLO tick-conversion fix in Phase 5.1 W1.5 hardening.

5. **`tests/test_screener_filter.py::test_shortlist_capped_at_four`**
   - Failure: `Expected >= 4 passing markets, got 0`.
   - Same root cause as (4) — fixture's order-book depth doesn't survive
     the `_clo_findex_to_tick` conversion.

## Why these are NOT fixed in Phase 05.3 Plan 01

- (1)/(2)/(3) are CWD-resolution bugs in the test harness — orthogonal to
  the fill-path repair. Fixing requires changing the test or the
  `path_traversal_root` resolution in `run_manifest.py`. Out of scope for
  the fill-path D1/D2/D3 decisions.
- (4)/(5) are screener-fixture issues. T3 lifts `_clo_findex_to_tick` to a
  shared module but does NOT change the conversion math — these tests
  failed before T3 started and remain unchanged. Fixing requires re-seeding
  the fixture's order-book depth into the post-conversion tick range,
  which is a screener-level concern, not fill-path.

## Action

File a Phase-05.4 follow-up to track the screener fixture rebuild and
the manifest-sidecar CWD issue. Do not block Phase 05.3 PASS verdict on
these.
