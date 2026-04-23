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
| 01-06-T1 | 01-06 | 1 | INFRA-13 | T-01-06-03, T-01-06-04 | Plists parse via plutil; never embed DOTENV_PRIVATE_KEY or raw 0x-hex; ThrottleInterval=30; KeepAlive={SuccessfulExit=false} | unit (plistlib) + plutil lint | `uv run --directory python pytest python/tests/test_launchd_plist_schema.py -x && plutil -lint scripts/launchd/com.boros.brain.plist scripts/launchd/com.boros.hands.plist` | ❌ task | ⬜ pending |
| 01-06-T2 | 01-06 | 1 | INFRA-12 | T-01-06-01, T-01-06-02 | no_plain_keys hook rejects 0x<64-hex> + PEM blocks; structlog redacts api_key/token/secret/*PRIVATE_KEY*; runbook has A3 fallback section | unit + lint + markdown-section-count | `uv run --directory python pytest python/tests/test_no_plain_keys.py python/tests/test_log_redaction.py -x && grep -c '^## ' docs/runbook-secrets.md \| awk '$1 >= 6'` | ❌ task | ⬜ pending |
| 01-06-T3 | 01-06 | 1 | INFRA-13 (A3) | — | Reboot smoke test — both launchd agents start headlessly without Keychain GUI; first log line is RUN_MANIFEST | manual (reboot) | (operator reboots + inspects `launchctl list \| grep boros` + tails `var/logs/<today>/*.brain.log.jsonl`) | ❌ task | ⬜ pending |
| 01-07-T1 | 01-07 | 1 | INFRA-14 | T-01-07-01, T-01-07-03 | Startup halts on drift>5s; runtime warn@5s / halt@30s; 1s TTL cache; no_time_time_lint rejects direct time.time() in brain/{decision,data,screener}/ | unit + hook lint | `uv run --directory python pytest python/tests/test_chain_time_drift.py python/tests/test_no_time_time_in_hotpath.py -x && python scripts/no_time_time_lint.py` | ❌ task | ⬜ pending |
| 01-07-T2 | 01-07 | 1 | INFRA-04 | T-01-07-02 | DuckDB attaches SQLite READ_ONLY (INSERT raises); parquet views stubbed gracefully on empty root; duckdb_layer not imported from hot path | unit + grep | `uv run --directory python pytest python/tests/test_duckdb_layer.py -x` | ❌ task | ⬜ pending |
| 01-08-T1 | 01-08 | 1 | DATA-01 | T-01-08-01, T-01-08-02 | eventIndex hard-fail on null/missing (PITFALL B2); wei→float explicit (both wei-string and JSON-number paths); Hive partition shape matches duckdb views.sql | unit | `uv run --directory python pytest python/tests/test_ingester_base.py python/tests/test_ingester_market_trades.py -x` | ❌ task | ⬜ pending |
| 01-08-T2 | 01-08 | 1 | DATA-02 | T-01-08-03 | raw + combined share (market_id, snapshot_ts, tick) join key for Wave-2 DATA-05; wei→float for sz + sz_combined | unit + polars-join | `uv run --directory python pytest python/tests/test_ingester_order_book.py -x` | ❌ task | ⬜ pending |
| 01-08-T3 | 01-08 | 1 | DATA-03, DATA-04 | — | underlying_apr partitioned by exchange+year_month; settlement + market_data partitioned by market_id+year_month; CLI writes RUN_MANIFEST per run | unit + CLI subprocess | `uv run --directory python pytest python/tests/test_ingester_underlying_apr.py python/tests/test_ingester_settlement_md.py -x && uv run --directory python python -m boros_brain.data.ingester.cli --kind market_trades --src python/tests/fixtures/sample_market_trades.ndjson --market-id ETH --out /tmp/parquet_smoke` | ❌ task | ⬜ pending |
| 01-09-T1 | 01-09 | 1 | DATA-06 (A5 reconcile) | — | Real /markets JSON captured; schema-notes enumerates every field with resolved decision (parse/log/ignore) | manual (operator) / automated curl | (executor attempts curl; else operator) `test -s docs/samples/markets-response.json && test -s docs/samples/markets-schema-notes.md` | ❌ task | ⬜ pending |
| 01-09-T2 | 01-09 | 1 | DATA-06 | T-01-09-01, T-01-09-03 | Pydantic schema validated against captured response; clo_history written only on change; exponential backoff on 5xx; run_id stamped on every row | unit + integration | `uv run --directory python pytest python/tests/test_markets_response_schema.py python/tests/test_markets_poller.py -x` | ❌ task | ⬜ pending |
| 01-09-T3 | 01-09 | 1 | DATA-07 | T-01-09-02 | bytes26 decode + int112 sign extension per research §Pattern 8 verbatim; bounds check |floatingIndex|<2^110; 1s TTL cache; live-RPC smoke test passes on operator machine | pure-unit + skip-on-CI live-RPC | `uv run --directory python pytest python/tests/test_findex_decode.py python/tests/test_findex_reader.py -x` | ❌ task | ⬜ pending |
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
| `launchd` cold-boot under reboot | INFRA-13, absorbs A3 (plan 01-06 Task 3) | Requires macOS reboot — automated test impossible without CI-in-VM | 1. Reboot the MacBook; 2. After login, run `launchctl list \| grep boros`; 3. Expect both `boros.brain` and `boros.hands` in RunAtLoad state with exit code 0; 4. Inspect `logs/YYYY-MM-DD/<run_id>.log.jsonl` — first line MUST be a `RUN_MANIFEST` record |
| `dotenvx` + Keychain headless decrypt | INFRA-12, absorbs C3 (plan 01-06 Task 3) | Keychain ACL requires interactive approval; `-A` flag must be verified under launchd context | 1. Re-lock Keychain; 2. Reboot; 3. After login, confirm `brain` starts WITHOUT prompting (Keychain trust to `launchd` binary must be persistent); 4. If prompted, document and fall back to file-env with chmod 600 + runbook note |
| `RUN_MANIFEST` sidecar JSON written correctly | INFRA-06, PROTO-01 | Easy to assert file exists but semantic correctness across mid-run knob change needs operator validation of `parent_run_id` chain | 1. Start `brain`; 2. Change one knob via config reload signal; 3. Expect NEW `run_id` with `parent_run_id` pointing to prior `run_id`; 4. Manually `jq .parent_run_id logs/.../<new_run_id>.manifest.json` and trace chain |
| /markets response schema reconcile | DATA-06 (plan 01-09 Task 1) | Executor may not have network; even if it does, operator spot-checks the captured JSON for surprises | 1. Either executor curls or operator curls `https://api.boros.finance/open-api/v1/markets` into `docs/samples/markets-response.json`; 2. `jq 'keys' ...` to enumerate fields; 3. Commit schema-notes.md with parse/log/ignore decisions per field |
| fIndexOracle live decode | DATA-07 (plan 01-09 Task 3) | Requires reachable Arbitrum RPC — CI may not have it | Operator runs `CI= uv run pytest python/tests/test_findex_reader.py::test_findex_decode_from_live_rpc -x` on their machine once; expects fTime within 1 hour of now, feeIndex > 0, abs(floatingIndex) < 2^110 |
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
