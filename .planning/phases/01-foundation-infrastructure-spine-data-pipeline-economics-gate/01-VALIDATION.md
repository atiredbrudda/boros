---
phase: 01
slug: foundation-infrastructure-spine-data-pipeline-economics-gate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-23
last_updated: 2026-04-23
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (Python)** | `pytest 8.x` + `pytest-asyncio` (installed in Wave 0 via INFRA-01 monorepo bootstrap) |
| **Framework (TypeScript)** | `vitest 2.x` (installed in Wave 0 via INFRA-01 monorepo bootstrap) |
| **Config file (Python)** | `python/pyproject.toml` (pytest section) — created Wave 0 |
| **Config file (TypeScript)** | `ts/vitest.config.ts` — created Wave 0 |
| **Quick run command** | `cd python && uv run pytest -q --testmon && cd ../ts && pnpm vitest run --changed` |
| **Full suite command** | `cd python && uv run pytest -q && cd ../ts && pnpm vitest run` |
| **Estimated runtime** | ~30s quick / ~3min full at Phase-1 close |

---

## Sampling Rate

- **After every task commit:** Run `{quick run command}` (testmon / --changed keeps this <10s)
- **After every plan wave:** Run `{full suite command}` plus `scripts/architecture_lint.py` + `scripts/wiki_cite_lint.py` (pre-commit already runs these but wave boundary re-asserts)
- **Before `/gsd-verify-work`:** Full suite must be green; architecture + wiki-cite lints must pass; one full `brain`+`hands` cold start under launchd must boot cleanly and emit a `RUN_MANIFEST` as first log line
- **Max feedback latency:** 10s quick / 180s full

---

## Per-Task Verification Map

Plans filled in per-task rows during planner pass. Wave 0 is the tracer-bullet — nothing else merges until it passes.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-10-T1 | 01-10 | 2 | DATA-05 | T-01-10-01 | AMMConservationError raised on combined<raw; no silent absorb | unit + subprocess exit-code | `uv run pytest python/tests/test_amm_conservation.py -x` | ❌ task | ⬜ pending |
| 01-10-T2 | 01-10 | 2 | DATA-11 | T-01-10-02, T-01-10-03 | No E_liq cache across polls; exponential backoff on 503; single-writer-per-table | integration | `uv run pytest python/tests/test_e_liq_poller.py -x && python scripts/sqlite_writer_lint.py` | ❌ task | ⬜ pending |
| 01-10-T3 | 01-10 | 2 | DATA-11 (A6 spike) | — | A6 spike time-boxed; fallback data_source='synthetic_current' documented | smoke | `uv run pytest python/tests/test_probe_historical_budget_smoke.py -x` | ❌ task | ⬜ pending |
| 01-11-T1 | 01-11 | 2 | DATA-08 | T-01-11-01 | eventIndex-ordered CV; gap detection; A8 outside-range-wall ratio | unit | `uv run pytest python/tests/test_screener_metrics.py -x` | ❌ task | ⬜ pending |
| 01-11-T2 | 01-11 | 2 | DATA-08 (A8 SCALE) | T-01-11-02 | Per-market SCALE from 2 pairs ≥ 1 day apart; unstable flag > 1% divergence | unit | `uv run pytest python/tests/test_screener_scale_calibration.py -x` | ❌ task | ⬜ pending |
| 01-11-T3 | 01-11 | 2 | DATA-08 | T-01-11-03 | All 6 filters applied; shortlist cap ≤ 4; ranked by R_apr_potential | integration | `uv run pytest python/tests/test_screener_filter.py -x` | ❌ task | ⬜ pending |
| 01-12-T1 | 01-12 | 2 | DATA-09 | T-01-12-01, T-01-12-02, T-01-12-04 | Fail-loud on missing/unit-confused knobs; kill-report written on empty shortlist | unit + CLI | `uv run pytest python/tests/test_economics_kill_switch.py python/tests/test_kill_report_template.py -x` | ❌ task | ⬜ pending |
| 01-12-T2 | 01-12 | 2 | DATA-10 | T-01-12-03 | Full ingest→screener→gate chain; diff flags new-entrant/dropped; launchd plist valid | integration | `uv run pytest python/tests/test_daily_rescreen.py -x && plutil -lint scripts/launchd/com.boros.rescreen.plist` | ❌ task | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements (tracer-bullet)

Wave 0 must install the frameworks AND the smoke-test scaffolding before any other wave merges:

- [ ] `python/pyproject.toml` — `pytest`, `pytest-asyncio`, `pytest-testmon` as dev deps
- [ ] `ts/package.json` — `vitest`, `@vitest/ui` as dev deps
- [ ] `python/tests/conftest.py` — shared fixtures (isolated tmp SQLite, stubbed ZMQ sockets, frozen `chain_time`)
- [ ] `ts/tests/setup.ts` — shared helpers (viem mock chain, socket.io-client mock)
- [ ] `python/tests/test_tracer_bullet.py` — stubs that exercise RUN_MANIFEST writer + structlog JSON shape + ZMQ echo + SQLite WAL open_orders round-trip (spawned first, MUST be green before non-Wave-0 plans run)
- [ ] `ts/tests/tracer_bullet.test.ts` — stubs that exercise pino JSON shape + ZMQ peer echo + hands startup SIGTERM handler
- [ ] `scripts/architecture_lint.py` — unit tests for the lint script itself (parses fixture YAML, catches injected drift, exits non-zero)
- [ ] `scripts/wiki_cite_lint.py` — unit tests (fixture markdown with/without `[[wiki-link]]`)
- [ ] One `.github/workflows/ci.yml` or equivalent local pre-commit wiring that runs both suites on every commit

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `launchd` cold-boot under reboot | INFRA-13, absorbs A3 | Requires macOS reboot — automated test impossible without CI-in-VM | 1. Reboot the MacBook; 2. After login, run `launchctl list \| grep boros`; 3. Expect both `boros.brain` and `boros.hands` in RunAtLoad state with exit code 0; 4. Inspect `logs/YYYY-MM-DD/<run_id>.log.jsonl` — first line MUST be a `RUN_MANIFEST` record |
| `dotenvx` + Keychain headless decrypt | INFRA-12, absorbs C3 | Keychain ACL requires interactive approval; `-A` flag must be verified under launchd context | 1. Re-lock Keychain; 2. Reboot; 3. After login, confirm `brain` starts WITHOUT prompting (Keychain trust to `launchd` binary must be persistent); 4. If prompted, document and fall back to file-env with chmod 600 + runbook note |
| `RUN_MANIFEST` sidecar JSON written correctly | INFRA-06, PROTO-01 | Easy to assert file exists but semantic correctness across mid-run knob change needs operator validation of `parent_run_id` chain | 1. Start `brain`; 2. Change one knob via config reload signal; 3. Expect NEW `run_id` with `parent_run_id` pointing to prior `run_id`; 4. Manually `jq .parent_run_id logs/.../<new_run_id>.manifest.json` and trace chain |
| Empty-shortlist halt report (DATA-09) | DATA-09 | Adversarial — depends on live market state we can't deterministically stub into "below threshold" | 1. Run `python -m brain.screener --force-halt` with synthetic below-threshold fixture; 2. Verify `docs/kill-report-YYYYMMDD.md` is written; 3. Verify exit code 1; 4. In production, if halted in real run, document the real report as an artifact |
| DATA-10 daily re-screen under launchd | DATA-10 (plan 01-12 Task 2) | launchd CalendarInterval requires a full 24h cycle to verify in production | 1. `launchctl load ~/Library/LaunchAgents/com.boros.rescreen.plist`; 2. Wait until next 03:00 UTC; 3. Confirm `logs/supervisor/com.boros.rescreen.out` has a new entry; 4. Confirm `var/reports/rescreen_diff.json` updated with today's timestamp |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (tracer-bullet tests installed first)
- [ ] No watch-mode flags (tests exit deterministically)
- [ ] Feedback latency < 10s quick / 180s full
- [ ] `nyquist_compliant: true` set in frontmatter once planner fills per-task map

**Approval:** pending
