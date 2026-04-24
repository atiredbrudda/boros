---
status: partial
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
source: [01-VERIFICATION.md]
started: 2026-04-24T05:10:00Z
updated: 2026-04-24T05:10:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Pre-commit hook end-to-end — architecture-lint blocks real commit
expected: Modify a Python source file without updating docs/architecture.yml — commit is blocked by architecture-lint hook; unblocked only by updating architecture.yml or reverting source change
result: [pending]

### 2. launchd supervision lifecycle — KeepAlive + restart on SIGKILL
expected: Load brain+hands plists via `launchctl load`; both processes start, emit RUN_MANIFEST as first log line, survive SIGKILL with auto-restart within ThrottleInterval=30s
result: [pending]

### 3. Live RUN_MANIFEST dry-run against real Arbitrum RPC
expected: chain_time drift at boot ≤5s; sidecar JSON lands under logs/<date>/ and run_manifests SQLite row appears with non-null git_sha; run_id matches in both locations
result: [pending]

### 4. DATA-09 kill report readability — trigger economics gate halt
expected: Run screener CLI with synthetic metrics that produce empty shortlist; docs/kill-report-<today>.md written with per-market R_apr rows, config knob tree, halt reason; report is self-describing to an operator
result: [pending]

### 5. Wiki-cite hook end-to-end — blocks commit without [[wiki-link]]
expected: Create a new research/ markdown file without [[wiki-link]], attempt commit; hook exits non-zero and blocks until link is added
result: [pending]

### 6. Live poller flow ~5 min against Boros REST + Arbitrum RPC
expected: clo_history + reward_budget_history tables accumulate real rows; market_ids match /markets response; f_index_raw populated from on-chain fIndexOracle; no AMM conservation violations
result: [pending]

### 7. LLM Wiki completeness audit — 31 pages with Status flags
expected: ../LLM Wiki/workspaces/boros/wiki/index.md links to all 31 pages; every page has **Status:** field set to Current / Historical / Deferred
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps
