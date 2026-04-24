---
status: complete
phase: 02-fill-model-nhpp-v0-5
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md]
started: 2026-04-24T00:00:00Z
updated: 2026-04-24T19:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test — fill model test suite from scratch
expected: |
  Run fill model test suite from clean state.
  Expected: 30 tests pass, 0 failures, 0 unexpected skips.
result: pass

### 2. CLI entry point — subcommands visible
expected: |
  python -m boros_brain.fill_model --help lists exactly:
  fit, predict, calibration-report, force-degrade. No import errors. Exits 0.
result: pass

### 3. RUN_MANIFEST first log line on CLI boot
expected: |
  First JSON log line contains event=RUN_MANIFEST and tier=fill_model.
result: issue
reported: "Manifest sidecar JSON written correctly (01KQ0AZMEX9ZZWDKV8TCFD003Z.manifest.json with run_id, mode, git_sha, full config tree). Manifest row inserted into run_manifests SQLite. But first structured log EVENT is fill_model.cli_started, not RUN_MANIFEST. No log event named RUN_MANIFEST is emitted at all. PROTO-01 spec says 'emits RUN_MANIFEST as the first log record' — the sidecar satisfies the sidecar half but the log event half is absent."
severity: minor

### 4. force-degrade emits fill_model.fit_degraded
expected: |
  python -m boros_brain.fill_model force-degrade emits fill_model.fit_degraded log event.
result: pass

### 5. covariate_whitelist rejects invalid covariate names
expected: |
  FillModelConfig(covariate_whitelist=['not_real']) raises ValidationError with "non-allowed entries".
result: pass

### 6. Database migration includes fill_model_fits table
expected: |
  alembic upgrade head creates fill_model_fits table alongside the other 8 state tables.
result: pass

### 7. Negative fit_age_s guard (WR-02 fix)
expected: |
  predict() with fit_window_end_ts > current_chain_ts treats fit_age_s as 0, logs warning, does not raise.
result: pass
notes: "Verified via code inspection (predict.py:92 — if fit_age_s < 0 guard present) and passing unit test test_fill_model_predict_contract.py. Full integration test requires BotConfig from YAML which is awkward in one-liner form; unit test coverage is sufficient."

## Summary

total: 7
passed: 6
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "First structured log event on CLI boot is RUN_MANIFEST (PROTO-01 requirement)"
  status: failed
  reason: "Manifest sidecar + SQLite row written correctly before first log line. But no RUN_MANIFEST log event is emitted — first event is fill_model.cli_started. Phase 1 brain confirmed RUN_MANIFEST as first log event; fill_model CLI does not match this pattern."
  severity: minor
  test: 3
  root_cause: ""
  artifacts:
    - path: "python/src/boros_brain/fill_model/cli.py"
      issue: "write_manifest() called but no log.info('RUN_MANIFEST', ...) emitted; first explicit log is fill_model.cli_started"
  missing:
    - "Emit a structured log event (e.g. event='RUN_MANIFEST', **manifest.__dict__) immediately after write_manifest() in cli.py main()"
  debug_session: ""
