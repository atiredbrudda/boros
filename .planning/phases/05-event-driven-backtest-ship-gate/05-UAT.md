---
status: complete
phase: 05-event-driven-backtest-ship-gate
source: [05-01-SUMMARY.md, 05-02-SUMMARY.md, 05-03-SUMMARY.md, 05-04-SUMMARY.md, 05-05-SUMMARY.md, 05-06-SUMMARY.md, 05-07-SUMMARY.md, 05-08-SUMMARY.md, 05-09-SUMMARY.md]
started: 2026-04-26T00:00:00Z
updated: 2026-04-26T01:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Pytest Suite Green
expected: Run `cd python && pytest -q`. Expect 412 passed, 2 skipped, 0 failed. No --ignore flags needed.
result: issue
reported: "4 failures in test_backtest_2d_contour.py — WR-03 guard (zero-knob) triggered by default config using decision.p_purge_default=0.0"
severity: major
note: Root cause diagnosed and fixed inline — changed default contour_2d_knobs from decision.p_purge_default to screener.alt_yield (commit 09cef41). Re-run: 412 passed, 2 skipped.

### 2. CLI Entrypoint
expected: `python -m boros_brain.backtest --help` shows `run` and `plot` subcommands with `--market`, `--side`, `--config` options.
result: pass

### 3. Architecture Lint
expected: `scripts/architecture_lint.py` exits 0 — all Phase-5 nodes registered, no drift.
result: pass

### 4. RUN_MANIFEST First Log + Sidecar
expected: First structured log event is RUN_MANIFEST with run_id, mode=backtest, git_sha, full config knob tree. Sidecar JSON written to var/backtest/<run_id>/.
result: pass
note: Verified by test_backtest_run_manifest_first_log.py (3 tests) + test_backtest_run_manifest_sidecar.py (3 tests) — all GREEN.

### 5. Ship-Gate Report Written
expected: ship-gate-report.md written with PASSED/FAILED header, threshold components, p5 bootstrapped P&L, manifest excerpt.
result: pass
note: Verified by test_backtest_ship_gate_pass_path.py + test_backtest_ship_gate_fail_path.py — both GREEN.

### 6. Perturbation Sign-Flip Recorded, Not Blocking
expected: Sign-flip rows appended to ship-gate report under ## Perturbation Grid; do NOT auto-fail the verdict.
result: pass
note: Verified by test_backtest_perturbation_sign_flip.py::test_fragile_flag_does_not_auto_fail_ship_gate — GREEN.

### 7. Voluntary-Cancel Branch Divergence Log
expected: Logs forfeit_branch.sanity_check_pass (INFO) or forfeit_branch_load_bearing (WARNING); neither causes a ship-gate fail.
result: pass
note: Verified by test_backtest_voluntary_cancel_sensitivity.py (3 tests) — all GREEN.

### 8. Cancel-Latency Sweep Monotonicity
expected: 6 rows tagged sweep_axis=cancel_latency; unexpected_monotonicity warning if slope reverses, no crash.
result: pass
note: Verified by test_backtest_sweep_cancel_latency.py (3 tests) — all GREEN.

## Summary

total: 8
passed: 7
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "pytest suite runs 412 passed, 2 skipped, 0 failed"
  status: fixed
  reason: "WR-03 zero-knob guard triggered by default contour_2d_knobs containing decision.p_purge_default=0.0"
  severity: major
  test: 1
  root_cause: "BacktestConfig.contour_2d_knobs default included a zero-value knob. The new guard in contour_2d.py correctly rejected it, but the schema default and tests were not updated alongside the guard."
  artifacts:
    - path: "python/src/boros_brain/backtest/config.py"
      issue: "default contour_2d_knobs second element was decision.p_purge_default (default=0.0)"
    - path: "python/tests/test_backtest_2d_contour.py"
      issue: "tests used default_config (zero knob) and operator_override test also used p_purge_default"
  missing:
    - "Changed default second knob to screener.alt_yield (default=0.05)"
    - "Updated test assertions to match new default"
  fix_commit: "09cef41"
