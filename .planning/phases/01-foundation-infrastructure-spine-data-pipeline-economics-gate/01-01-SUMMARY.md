---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
plan: 01-01
subsystem: infra
tags: [pydantic, pydantic-v2, structlog, polars, duckdb, web3, pyzmq, typescript, pnpm, uv, vitest, pytest, monorepo, configuration, socket.io-client]

requires:
  - phase: 00-bootstrap
    provides: Phase-0 open-question resolutions (P0-01 voluntary-cancel flag lock = False, P0-03 Socket.IO WS stack, P0-04 submission_path dropped) — all consumed as schema defaults + absent-field regression guards

provides:
  - Monorepo skeleton (python/ + ts/ + configs/ + docs/ + scripts/ + state/ + logs/ + data/parquet/) with .gitignore + Makefile
  - Python project (pyproject.toml) with exact-pinned deps — pydantic==2.13.3, structlog==25.5.0, polars==1.40.1, duckdb==1.5.0, web3==7.15.0, pyzmq==26.2.0, orjson / python-ulid / httpx / alembic / python-dotenv / pyyaml; dev deps pytest + pytest-asyncio + pytest-testmon + ruff + mypy + hypothesis + pre-commit
  - TypeScript project (package.json) with exact-pinned deps — @pendle/sdk-boros@1.1.44, viem@2.44.4, socket.io-client@^4 (NOT raw ws), pino@^9, ulid@^2.3, zeromq@^6, better-sqlite3@^11, zod@^3.23, dotenv@^16; dev deps typescript 5.6 / tsx 4.21 / vitest 2 / biome / @types
  - Pydantic v2 BotConfig — the single source of truth for every knob (PROTO-04)
  - YAML loader (config/loader.py) — load_config(path) → BotConfig with extra='forbid' enforcement
  - Seven round-trip / unknown-key / frozen-mutation / voluntary-cancel / markets-max-length / submission_path-absent / rpc_url-required tests (all passing)
  - Wave-0 tracer-bullet test scaffolding (3 Python + 3 TS) stubbed and skip-marked with dependency pointers to 01-02 / 01-03
  - strategy/v0.5-default.yaml — seed default knob tree parseable into BotConfig
  - uv.lock and pnpm-lock.yaml committed; both resolve clean (uv --locked, pnpm --frozen-lockfile)
affects: [01-02, 01-03, 01-04, 01-05, 01-06, 01-07, 01-08, 01-09, 01-10, 01-11, 01-12, all future phases]

tech-stack:
  added: [pydantic==2.13.3, structlog==25.5.0, polars==1.40.1, duckdb==1.5.0, web3==7.15.0, pyzmq==26.2.0, pnpm@10.33.2, @pendle/sdk-boros@1.1.44, viem@2.44.4, socket.io-client@^4, vitest@2, tsx@4.21]
  patterns:
    - "StrictBase pattern (ConfigDict(extra='forbid', frozen=True)) as the base for every BotConfig sub-model — schema drift is mechanically impossible because unknown keys raise ValidationError"
    - "Factory-default pattern on nested config models (Field(default_factory=StrategyConfig)) so top-level BotConfig only needs mode + strategy_version + market_id + side + wallets + data.rpc_url_arbitrum as minimal required input"
    - "Two-endpoint PUB/SUB topology for ZMQ events (zmq_events_brain_endpoint + zmq_events_hands_endpoint) — each tier binds its own PUB endpoint, SUBs the other; no string-mangling in EventBus code (checker issue #07 pre-resolution)"
    - "Wave-0 tracer-bullet scaffolding — tests in dependent downstream plans are stubbed here with skip markers so collection proves wiring; 01-02/01-03 replace skip with concrete assertions"
    - "pythonpath in [tool.pytest.ini_options] as the src-layout import bridge — avoids editable-install friction while keeping hatchling as the wheel builder"

key-files:
  created:
    - "python/pyproject.toml — Python deps + pytest/ruff/mypy config"
    - "python/src/boros_brain/config/schema.py — BotConfig + 6 sub-models (StrictBase, StrategyConfig, ExecutionConfig, DataConfig, InfraConfig, ScreenerConfig, MarketCalibration)"
    - "python/src/boros_brain/config/loader.py — YAML → BotConfig via model_validate"
    - "python/src/boros_brain/main.py — boot-only skeleton entrypoint (mode parse + print)"
    - "python/tests/test_config_round_trip.py — 7 PROTO-04 assertions"
    - "python/tests/test_tracer_bullet.py — 3 skip-marked stubs (wave0_scaffold)"
    - "python/tests/conftest.py — shared fixtures (default_yaml_path, default_config, tmp_sqlite_path, frozen_chain_time)"
    - "ts/package.json — TS deps + vitest scripts"
    - "ts/tsconfig.json — strict ES2022 module config"
    - "ts/vitest.config.ts — vitest setup"
    - "ts/src/boros_hands/main.ts — boot-only skeleton entrypoint (run_id print + SIGTERM handler)"
    - "ts/src/boros_hands/config.ts — placeholder BotConfig type (TODO: codegen from Pydantic)"
    - "ts/tests/tracer_bullet.test.ts — 1 passing + 3 skip stubs"
    - "strategy/v0.5-default.yaml — seed default knob YAML"
    - ".gitignore — excludes state/, logs/, data/parquet/, .env.keys, __pycache__, node_modules, etc."
    - "Makefile — brain/hands/test-python/test-ts/test/lint shortcuts"
  modified: []

key-decisions:
  - "pythonpath=[\"src\"] in pyproject.toml pytest config (workaround for src-layout import without relying on editable-install ordering)"
  - "pnpm 10.33.2 installed via `corepack enable pnpm` — corepack is available on this macOS, no system-wide pnpm needed"
  - "Stayed with socket.io-client@^4 (Socket.IO v4 stable) per P0-03 — NOT pinning exact version because the Boros server version is not yet observed empirically; caret allows patch-level security fixes"
  - "Dropped `readme = ...` from pyproject.toml — no top-level README.md exists yet, and the planning docs are the authoritative description for now"
  - "logs/.gitkeep added via `git add -f` since `logs/` is in .gitignore (this is intentional: we want the directory to exist in fresh clones, but runtime log files themselves must NEVER be committed)"

patterns-established:
  - "PROTO-04 schema-drift guard: every new knob must be added to BotConfig or a sub-model AND to the YAML. Round-trip test catches code-side drift; extra='forbid' catches YAML-side drift. Neither lane can silently add or drop a knob."
  - "Deterministic tracer-bullet scaffolding: downstream plan test modules are stubbed at Wave 0, so pytest/vitest test counts grow monotonically as the project matures — no 'suddenly 50 tests appeared' plan boundaries."

requirements-completed: [INFRA-01, INFRA-02, PROTO-04]

duration: 41min
completed: 2026-04-23
---

# Phase 01 Plan 01-01: Monorepo scaffold + Pydantic v2 BotConfig SSoT Summary

**Pydantic v2 `BotConfig` single-source-of-truth landed with 7 PROTO-04 assertions green; monorepo skeleton (python/ + ts/ + configs/ + strategy/ + docs/ + scripts/ + state/ + logs/ + data/parquet/) and pinned-dep lockfiles committed; zero `submission_path` occurrences in any config file (P0-04 regression guard).**

## Performance

- **Duration:** 41 min
- **Started:** 2026-04-23T21:39:44Z
- **Completed:** 2026-04-23T22:21:33Z
- **Tasks:** 2 (both `type="auto"` with `tdd="true"`; scaffolding task does not follow RED/GREEN cycle because the tests in it are effectively install/build smoke checks)
- **Files created:** 28 (15 in Task 1 + 13 in Task 2)
- **Files modified:** 0 (greenfield plan)

## Accomplishments

- **`BotConfig` is locked down as the PROTO-04 SSoT.** `extra='forbid'` + `frozen=True` on every sub-model; round-trip test proves YAML → model → YAML → model is idempotent; unknown-key and frozen-mutation tests fail loud on any drift attempt.
- **Phase-0 locks hard-coded in the schema.** `voluntary_cancel_forfeits_accumulated: bool = False` default (D-01 / P0-01 lock — [[Voluntary cancel reward behavior]]); `markets: list[MarketCalibration]` capped to `max_length=1` for v0.5; `submission_path` knob is absent from `ExecutionConfig` (P0-04 lock — [[Sign-only cancel primitive]]) and there is a dedicated regression test asserting its absence.
- **Two-tier dep pinning lands clean.** `uv sync --locked --dry-run` → "Would make no changes"; `pnpm install --frozen-lockfile` → no delta. Both lockfiles committed. `socket.io-client@^4` is the only WebSocket client (raw `ws` does not appear in `ts/package.json` — P0-03 stack change from [[Boros WebSocket API]]).
- **Wave-0 tracer-bullet scaffolding wired.** Three Python tests (manifest writer / ZMQ echo / SQLite open-orders) and three TS tests (pino JSON / ZMQ echo / SIGTERM) are committed with explicit `reason="..."` skip markers pointing at 01-02 and 01-03; downstream plans will simply replace `skip` with `xfail`→green.
- **Monorepo tree matches CLAUDE.md §Stack verbatim.** `python/ + ts/ + configs/ + docs/ + scripts/ + state/ + logs/ + data/parquet/` all present; `.gitkeep` files preserve the empty directories through git.

## Task Commits

Each task was committed atomically:

1. **Task 1: Monorepo root scaffold + gitignore + Makefile + package manifests** — `d70601c` (feat)
2. **Task 2: Pydantic v2 BotConfig schema + YAML loader + round-trip tests + Wave-0 test scaffolding** — `770e028` (feat)

_Note: Task 1 is marked `tdd="true"` in the plan but its "tests" are infrastructure smoke checks (`uv sync`, `pnpm install`, `grep` acceptance criteria). The genuine TDD cycle applies to Task 2, where the schema + tests were co-authored rather than strictly RED-then-GREEN — this is the pragmatic limit of applying RED/GREEN to Pydantic model authoring where writing the schema IS the implementation, and the tests merely assert its already-intended invariants. No regression was introduced because the 7 assertions in `test_config_round_trip.py` target observable Pydantic behavior (extra='forbid' validation errors, frozen mutation, JSON-schema shape) that the library itself provides once the StrictBase mixin is in place._

## Files Created/Modified

### Python (brain)
- `python/pyproject.toml` — Pinned deps + pytest/ruff/mypy config; `pythonpath=["src"]` for src-layout import
- `python/uv.lock` — sha256: `6146b7959809ede815c3f1cb6ab06f8435cc64847347d11bf1048b8673b7b0f0`
- `python/src/boros_brain/__init__.py` — `__version__ = "0.0.1"`
- `python/src/boros_brain/main.py` — argparse skeleton (accepts `--mode=live|paper|backtest|ingest|screen`, prints one line, exits 0)
- `python/src/boros_brain/config/__init__.py` — Re-exports BotConfig + sub-models + load_config
- `python/src/boros_brain/config/schema.py` — The schema (112 lines, all seven models with docstrings)
- `python/src/boros_brain/config/loader.py` — `load_config(path)` → `BotConfig.model_validate(yaml.safe_load(...))`
- `python/tests/__init__.py` — empty
- `python/tests/conftest.py` — `default_yaml_path`, `default_config`, `tmp_sqlite_path`, `frozen_chain_time` fixtures
- `python/tests/test_config_round_trip.py` — 7 PROTO-04 assertions (all passing)
- `python/tests/test_tracer_bullet.py` — 3 stubs with `wave0_scaffold` marker and skip reasons pointing at 01-02 / 01-03

### TypeScript (hands)
- `ts/package.json` — Pinned deps + vitest/biome/tsc scripts
- `ts/pnpm-lock.yaml` — sha256: `72b6672380ba195f941ac64b9b2d787f7b8d46f0c45de1597536549999dbc46b`
- `ts/tsconfig.json` — strict ES2022 / ESNext / bundler moduleResolution
- `ts/vitest.config.ts` — setup file + test globs + 10s timeout
- `ts/src/boros_hands/main.ts` — Entrypoint skeleton (reads BOROS_RUN_ID env, SIGTERM/SIGINT handler)
- `ts/src/boros_hands/config.ts` — Placeholder `type BotConfig = Record<string, unknown>` with codegen TODO
- `ts/tests/setup.ts` — empty placeholder
- `ts/tests/tracer_bullet.test.ts` — 1 passing + 3 skip stubs

### Strategy / ops
- `strategy/v0.5-default.yaml` — Seed YAML parseable into BotConfig (`voluntary_cancel_forfeits_accumulated: false` explicit; `rpc_url_arbitrum: "https://arb1.arbitrum.io/rpc"`; wallet fields `"TBD"`)
- `Makefile` — `brain` / `hands` / `test-python` / `test-ts` / `test` / `lint` targets
- `.gitignore` — Excludes runtime state + node_modules + .venv + __pycache__ + .env.keys + .pytest_cache + .mypy_cache + .ruff_cache + dist + .DS_Store

### Empty directory markers
- `configs/.gitkeep`, `docs/.gitkeep`, `scripts/.gitkeep`, `state/.gitkeep`, `logs/.gitkeep` (force-added because `logs/` is gitignored), `data/parquet/.gitkeep`

## BotConfig field inventory (model_fields.keys() — verbatim)

```text
BotConfig          : ['mode', 'strategy_version', 'market_id', 'side', 'root_wallet_address', 'agent_wallet_address', 'strategy', 'execution', 'data', 'infra', 'screener', 'markets']
StrategyConfig     : ['voluntary_cancel_forfeits_accumulated', 'target_share']
ExecutionConfig    : ['cancel_latency_budget_s', 'require_success_default', 'agent_wallet_gas_warn_multiples', 'agent_wallet_gas_halt_multiples', 'agent_wallet_gas_emergency_multiples']
DataConfig         : ['markets_poll_interval_s', 'e_liq_poll_interval_s', 'chain_time_cache_ttl_s', 'rpc_url_arbitrum', 'boros_rest_base']
InfraConfig        : ['sqlite_path', 'logs_dir', 'zmq_cmd_endpoint', 'zmq_events_brain_endpoint', 'zmq_events_hands_endpoint', 'zmq_kill_endpoint', 'heartbeat_interval_s', 'heartbeat_timeout_misses', 'chain_drift_warn_s', 'chain_drift_halt_s']
ScreenerConfig     : ['min_time_to_maturity_days', 'trades_window_days', 'realized_vol_window_days', 'reversal_count_window_days', 'alt_yield', 'fill_loss_coarse_bound']
MarketCalibration  : ['market_id', 'scale', 's', 'clo_lower_thresh', 'clo_upper_thresh', 'fIndex_oracle_address', 'maturity_ts']
```

**Notably absent (by design):** `ExecutionConfig.submission_path` (P0-04 lock). Confirmed by `test_submission_path_not_in_schema` — the assertion itself is the regression guard.

## Monorepo tree (diff vs 01-RESEARCH.md §Recommended Project Structure)

```text
/
├── .gitignore
├── Makefile
├── CLAUDE.md                    (existed pre-plan)
├── .planning/                   (existed pre-plan)
├── configs/
│   └── .gitkeep
├── strategy/
│   └── v0.5-default.yaml
├── docs/
│   └── .gitkeep
├── scripts/
│   └── .gitkeep
├── state/
│   └── .gitkeep
├── logs/
│   └── .gitkeep                 (force-added; logs/ is gitignored)
├── data/
│   └── parquet/
│       └── .gitkeep
├── python/
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── src/boros_brain/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── config/
│   │       ├── __init__.py
│   │       ├── schema.py
│   │       └── loader.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_config_round_trip.py
│       └── test_tracer_bullet.py
└── ts/
    ├── package.json
    ├── pnpm-lock.yaml
    ├── tsconfig.json
    ├── vitest.config.ts
    ├── src/boros_hands/
    │   ├── main.ts
    │   └── config.ts
    └── tests/
        ├── setup.ts
        └── tracer_bullet.test.ts
```

**Adaptations vs RESEARCH §Recommended Project Structure:**
- RESEARCH suggested many more subdirectories under `python/src/boros_brain/` (ipc/, logging/, db/, rpc_client/, duckdb_layer/, etc.) — those are wave-2+ deliverables; 01-01 intentionally creates only `config/` because that's the only sub-package this plan touches. Later plans (01-02, 01-03) will add their own sub-packages.
- Same story on the TS side — `hands/commands/`, `hands/events/`, `hands/tx/` etc. are Phase 6 deliverables; 01-01 creates only the entrypoint and the placeholder config module.
- No `docs/ARCHITECTURE.md` or `docs/architecture.yml` yet — those are created by plan 01-04 (architecture-lint hook). The `docs/.gitkeep` placeholder reserves the directory.

## Lockfile hashes (for reproducibility audit)

- `python/uv.lock` sha256: `6146b7959809ede815c3f1cb6ab06f8435cc64847347d11bf1048b8673b7b0f0`
- `ts/pnpm-lock.yaml` sha256: `72b6672380ba195f941ac64b9b2d787f7b8d46f0c45de1597536549999dbc46b`

Both lockfiles pass their respective freshness checks:
- `cd python && uv sync --locked --dry-run` → `Resolved 87 packages in 2ms. Audited 82 packages in 2ms. Would make no changes.`
- `cd ts && pnpm install --frozen-lockfile` → `Done in 268ms using pnpm v10.33.2` (no changes).

## Verification of plan's <verification> block

| Check | Result |
|-------|--------|
| Both package managers resolve cleanly | `uv --locked` ✓, `pnpm --frozen-lockfile` ✓ |
| `make test` exits 0 | `make test-python` 7 passed + 3 skipped ✓, `make test-ts` 1 passed + 3 skipped ✓ |
| BotConfig schema contains zero `submission_path` references | `grep -l submission_path pyproject.toml ts/package.json strategy/v0.5-default.yaml Makefile .gitignore` → NO MATCHES ✓ |
| `voluntary_cancel_forfeits_accumulated = False` is the hard-coded default | `test_voluntary_cancel_default_is_false` ✓; also verified directly: `load_config('strategy/v0.5-default.yaml').strategy.voluntary_cancel_forfeits_accumulated == False` |
| `markets: max_length=1` rejects 2-element lists | `test_markets_list_max_length_one` ✓ |
| `socket.io-client` is the declared WS client; `"ws":` does not appear | `grep socket.io-client ts/package.json` ✓, `grep '"ws":' ts/package.json` NO MATCH ✓ |
| All Wave-0 tracer-bullet placeholder tests collect in both runners | pytest collects 3 skip-marked, vitest collects 3 skip-marked ✓ |

## Decisions Made

- **`pythonpath=["src"]` in pyproject.toml pytest config.** Pytest needs to find the `boros_brain` package without a `pip install -e .` step on every sync. `pythonpath` in pyproject is the cleanest option and avoids a conftest.py `sys.path.insert` hack.
- **`corepack enable pnpm` as the pnpm install vector.** No system-wide pnpm was present; corepack (shipped with Node) was already installed. This keeps the dev environment declarative and reproducible across operators without adding a system package install step.
- **`socket.io-client@^4` caret pin, not exact pin.** Exact pin would be correct if the Boros server version were observed empirically — it isn't yet. Caret allows patch-level security fixes while constraining to Socket.IO v4 (the major version P0-03 locked). Plan 01-03 / Phase 6 can tighten the pin once `wss://api.boros.finance/pendle-dapp-v3` handshake behavior is probed empirically.
- **Dropped `readme = "../README.md"` from pyproject.toml.** The referenced file does not exist; adding it would make `uv sync` fail. CLAUDE.md and the planning docs are the current authoritative description — a real README.md is a later plan's work if at all (user preference: no documentation files unless requested).
- **`logs/.gitkeep` force-added.** The `logs/` directory is in `.gitignore` (runtime logs must NEVER be committed), but we want the directory to exist in fresh clones so the logger doesn't have to `mkdir -p` on boot. `git add -f logs/.gitkeep` is the smallest intervention that achieves both goals.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `pythonpath=["src"]` added to pytest config**
- **Found during:** Task 2 (first `uv run pytest` attempt)
- **Issue:** Without editable install or path configuration, `uv run pytest` could not import `boros_brain` from the test files — `ModuleNotFoundError: No module named 'boros_brain'`. Plan's acceptance criteria include `uv run pytest -q` exiting 0 which could not hold without this fix.
- **Fix:** Added `pythonpath = ["src"]` to `[tool.pytest.ini_options]` in `python/pyproject.toml`.
- **Files modified:** `python/pyproject.toml`
- **Verification:** `uv run pytest -q` → `7 passed, 3 skipped`.
- **Committed in:** `d70601c` (Task 1 commit — the pyproject.toml update landed together with the rest of the scaffolding).

**2. [Rule 3 - Blocking] Plan's `pnpm install --frozen-lockfile --dry-run` command uses a flag pnpm v10 removed**
- **Found during:** Task 1 acceptance verification (`pnpm install --frozen-lockfile --dry-run` failed with `ERROR Unknown option: 'dry-run'`)
- **Issue:** Plan acceptance criterion specifies `pnpm install --frozen-lockfile --dry-run` but pnpm v10 (current: 10.33.2) does not support `--dry-run` for `install`. The intent (lockfile consistency check) is fully captured by `pnpm install --frozen-lockfile` alone — with node_modules already installed, the command reports "Done" without modifications.
- **Fix:** Used `pnpm install --frozen-lockfile` (without `--dry-run`) as the lockfile consistency check.
- **Files modified:** None — this is a plan-acceptance-command adjustment, not a code change.
- **Verification:** `pnpm install --frozen-lockfile` → `Done in 268ms using pnpm v10.33.2` (zero added/removed/changed packages).
- **Committed in:** N/A — no commit needed.

**3. [Rule 3 - Blocking] Dropped `readme = "../README.md"` from pyproject.toml**
- **Found during:** Task 1 (`uv sync` dry-run)
- **Issue:** pyproject.toml had `readme = "../README.md"` but no `README.md` exists at the repo root. `uv sync` / `hatchling` will fail the build metadata step when the referenced file is missing. The plan's action block didn't specify `readme =` one way or the other; I initially added one reflexively, then dropped it when the file was missing.
- **Fix:** Removed the `readme` line from `[project]` entirely. `description` alone is sufficient for build metadata.
- **Files modified:** `python/pyproject.toml`
- **Verification:** `uv sync` exits 0; the generated `python/boros_brain-0.0.1-*.whl` is built cleanly.
- **Committed in:** `d70601c` (Task 1).

**4. [Rule 3 - Blocking] Corepack-enabled pnpm (10.33.2) vs system pnpm**
- **Found during:** Task 1 start (`pnpm --version` → "pnpm not found")
- **Issue:** Plan assumed `pnpm` was on PATH. It was not on this host — but `corepack` was.
- **Fix:** Ran `corepack enable pnpm`. pnpm 10.33.2 landed on PATH via corepack's shim. Added matching `"packageManager": "pnpm@10.33.2"` to `ts/package.json` so the dev-environment requirement is declarative.
- **Files modified:** `ts/package.json` (added `packageManager` field).
- **Verification:** `pnpm --version` → `10.33.2`; `pnpm install` + `pnpm install --frozen-lockfile` both exit 0.
- **Committed in:** `d70601c` (Task 1).

---

**Total deviations:** 4 auto-fixed (4× Rule 3 blocking, 0× Rule 1 bug, 0× Rule 2 missing critical, 0× Rule 4 architectural)
**Impact on plan:** All four fixes were mechanical blockers for the plan's acceptance criteria to be satisfiable on this host. No scope change, no schema/behavior change, no relaxation of any invariant. The fixes make the plan actually runnable without changing what the plan delivers.

## Issues Encountered

- **Partial pnpm install on first run.** The first `pnpm install` attempt hit `ECONNRESET` partway through downloading tarballs (registry slowness — several "Tarball download average speed 4 KiB/s" warnings). Re-running `pnpm install` completed it cleanly in ~2m39s. No state corruption — pnpm's content-addressable store handles partial downloads correctly.
- **`grep -q submission_path ... schema.py` shows matches in the docstring and regression test.** These are intentional: the schema's module docstring cites the P0-04 lock and the test file asserts the absence. The plan's acceptance grep specifically scopes to `pyproject.toml ts/package.json strategy/v0.5-default.yaml`, which has ZERO matches (as required). The cross-file grep (`grep -rn submission_path python/src python/tests ts/src ts/tests strategy Makefile .gitignore`) shows 7 matches, all in schema.py docstring + test_config_round_trip.py — expected.

## Threat model follow-through

All three STRIDE threats from the plan's `<threat_model>` block are mitigated as designed:

| Threat ID | Mitigation status | Evidence |
|-----------|-------------------|----------|
| T-01-01 (Tampering — unpinned deps) | Mitigated | `pydantic==2.13.3`, `structlog==25.5.0`, `polars==1.40.1`, `duckdb==1.5.0`, `web3==7.15.0`, `pyzmq==26.2.0` all exact-pinned in pyproject.toml. `@pendle/sdk-boros@1.1.44`, `viem@2.44.4` exact-pinned in package.json. `uv sync --locked --dry-run` + `pnpm install --frozen-lockfile` both pass → lockfile drift detector is operational. |
| T-01-02 (Information Disclosure — secrets) | Mitigated (first line of defense) | `.gitignore` explicitly lists `.env`, `.env.keys`, `.env.local`. Second line (`scripts/no_plain_keys.py` pre-commit hook) is plan 01-04 scope. |
| T-01-03 (Repudiation — schema drift) | Mitigated | `extra='forbid'` + `frozen=True` on every StrictBase sub-model; round-trip + unknown-key + frozen-mutation tests in `test_config_round_trip.py` (4/7 tests target T-01-03 directly). `test_submission_path_not_in_schema` specifically guards P0-04 regression. |

## User Setup Required

None — no external service configuration required for this plan. Plans 01-04 (pre-commit hooks), 01-05 (LLM Wiki seed), 01-12 (dotenvx + macOS Keychain) will introduce user-side setup steps.

## Next Phase Readiness

- **Immediate downstream (Wave 1 of phase 01):**
  - 01-02 (SQLite WAL spine) — imports `BotConfig.infra.sqlite_path`; replaces `test_sqlite_open_orders_roundtrip` skip with real assertion.
  - 01-03 (ZMQ bus + structlog + RUN_MANIFEST) — imports every `BotConfig.infra.zmq_*` + `BotConfig.mode` + `BotConfig.strategy_version`; replaces `test_zmq_echo_roundtrip_under_10ms` and `test_manifest_writer_emits_first_line` stubs.
- **Cross-cutting dependencies satisfied:**
  - Every downstream plan that reads a knob now has a single import target: `from boros_brain.config.schema import BotConfig` (or the relevant sub-model).
  - Every downstream plan that writes a knob now has a single modification target: `python/src/boros_brain/config/schema.py`. The plan-check agent for subsequent plans should reject any PLAN.md that proposes a knob not present in the schema as the same commit.
- **Known follow-ups (deferred, tracked):**
  - `BotConfig` does not yet have a `runtime-mode-gate` validator that rejects `root_wallet_address == "TBD"` when `mode == "live"`. That validator is a Phase 8 (live-deploy) scope item per the threat-model boundary note.
  - The `[[Pydantic BotConfig schema v0.5]]` wiki page mentioned in the plan `<output>` block is deferred to plan 01-05 (LLM Wiki seed). The schema docstring and this SUMMARY serve as interim knowledge-base records until 01-05 files the canonical page.

## Self-Check: PASSED

**Files verified existing:**
- FOUND: python/pyproject.toml
- FOUND: python/uv.lock
- FOUND: python/src/boros_brain/__init__.py
- FOUND: python/src/boros_brain/main.py
- FOUND: python/src/boros_brain/config/__init__.py
- FOUND: python/src/boros_brain/config/schema.py
- FOUND: python/src/boros_brain/config/loader.py
- FOUND: python/tests/__init__.py
- FOUND: python/tests/conftest.py
- FOUND: python/tests/test_config_round_trip.py
- FOUND: python/tests/test_tracer_bullet.py
- FOUND: ts/package.json
- FOUND: ts/pnpm-lock.yaml
- FOUND: ts/tsconfig.json
- FOUND: ts/vitest.config.ts
- FOUND: ts/src/boros_hands/main.ts
- FOUND: ts/src/boros_hands/config.ts
- FOUND: ts/tests/setup.ts
- FOUND: ts/tests/tracer_bullet.test.ts
- FOUND: strategy/v0.5-default.yaml
- FOUND: Makefile
- FOUND: .gitignore
- FOUND: configs/.gitkeep, docs/.gitkeep, scripts/.gitkeep, state/.gitkeep, logs/.gitkeep, data/parquet/.gitkeep

**Commits verified via git log:**
- FOUND: d70601c (Task 1 — feat(01-01): monorepo scaffold + pinned dependency manifests)
- FOUND: 770e028 (Task 2 — feat(01-01): Pydantic v2 BotConfig single source of truth + round-trip tests)

---
*Phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate*
*Completed: 2026-04-23*
