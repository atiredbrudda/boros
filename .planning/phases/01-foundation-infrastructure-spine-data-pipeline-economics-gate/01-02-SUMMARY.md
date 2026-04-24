---
phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
plan: 01-02
subsystem: state
tags: [sqlite, wal, alembic, state-spine, single-writer, threat-model, chmod, foreign-keys, better-sqlite3, tdd]

requires:
  - phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate
    plan: 01-01
    provides: BotConfig.infra.sqlite_path knob + Wave-0 tracer-bullet test stub pointing at 01-02

provides:
  - "Canonical 8-table SQLite WAL schema (open_orders, decisions, tx_receipts, queue_positions, run_manifests, epoch_rewards, clo_history, reward_budget_history) in python/src/boros_brain/state/schemas.sql"
  - "Alembic migration 0001_initial_8_tables.py that replays schemas.sql (statement-split on top-level semicolons) with a reverse-order downgrade"
  - "python/src/boros_brain/state/db.py: open_connection() context manager that clamps journal_mode=WAL + synchronous=NORMAL + foreign_keys=ON + chmod 600 on every open"
  - "Per-table writer modules (9 total): 6 brain-owned Python writers, 1 hands-owned TS writer (tx_receipts + open_orders), 2 TEST_ONLY-guarded Python writers for hands-owned tables"
  - "scripts/sqlite_writer_lint.py: grep-based single-writer-per-table lint with TEST_ONLY exception for Python-side hands writers"
  - "scripts/apply_alembic_migration.py: helper for TS tests to drive alembic programmatically (bypasses -x / ini-override CLI limitation)"
  - "reward_budget_history.data_source CHECK constraint (B6 pitfall guard) enforced at SQL + Python layers"
  - "run_manifests.parent_run_id self-FK (INFRA-06 mid-run knob-change chain)"
  - "Wave-0 tracer-bullet test test_sqlite_open_orders_roundtrip un-skipped and green (both Python and TS sides)"

affects: [01-03, 01-04, 01-05, 01-06, 01-09, 01-10, 01-11, 01-12, all downstream plans that read/write state]

tech-stack:
  added: []
  patterns:
    - "Canonical-DDL-in-SQL-file + Alembic-replays pattern — schemas.sql is the single source of truth; Alembic migration loads and op.execute()s statement-by-statement; any future column add lands in schemas.sql + a new numbered migration in the same commit."
    - "Single-writer-per-table as greppable convention — scripts/sqlite_writer_lint.py scans python/src + ts/src for INSERT INTO <table> / UPDATE <table> / ON CONFLICT <table> / DELETE FROM <table> outside the designated owner file and exits 1 on violation. Production-grade mechanization of PROTO-02."
    - "TEST_ONLY marker pattern — Python writer modules for hands-owned tables carry a module-scope `TEST_ONLY = True` literal that the lint recognizes as an exception. Any Python file OTHER than the designated TEST_ONLY-exception file is still rejected. This lets tests seed state without violating single-writer, while still catching accidental Python writes elsewhere."
    - "FK enforcement per-connection — SQLite default is `PRAGMA foreign_keys = OFF`; `open_connection()` sets it ON on every open. The run_manifests self-FK (parent_run_id → run_id) is unenforced without this — which would silently break the INFRA-06 mid-run-knob-change chain."
    - "chmod 600 at every open_connection() (not one-time-at-creation) — a crash during WAL truncation can leave fresh -wal / -shm files that a one-time clamp misses; re-clamping on every open covers them."
    - "Programmatic alembic upgrade for cross-language test setup — ts/tests/state/sqlite_writer.test.ts runs `uv run python scripts/apply_alembic_migration.py sqlite:///tmp.sqlite` in beforeEach, bypassing alembic CLI's ini-override limitation. Each test gets a fresh DB in a mkdtempSync workdir."

key-files:
  created:
    - "python/src/boros_brain/state/__init__.py — state package header"
    - "python/src/boros_brain/state/schemas.sql — canonical 8-table DDL (145 lines)"
    - "python/src/boros_brain/state/db.py — open_connection + ensure_permissions_0600 + enable_wal_mode"
    - "python/src/boros_brain/state/migrations/alembic.ini — minimal alembic config"
    - "python/src/boros_brain/state/migrations/env.py — alembic runtime env (offline + online)"
    - "python/src/boros_brain/state/migrations/script.py.mako — alembic revision template"
    - "python/src/boros_brain/state/migrations/versions/0001_initial_8_tables.py — replays schemas.sql"
    - "python/src/boros_brain/state/writers/__init__.py — re-exports all 8 writer modules"
    - "python/src/boros_brain/state/writers/decisions.py — insert_decision (brain-owned)"
    - "python/src/boros_brain/state/writers/queue_positions.py — insert_queue_position (brain-owned)"
    - "python/src/boros_brain/state/writers/run_manifests.py — insert_run_manifest (brain-owned)"
    - "python/src/boros_brain/state/writers/epoch_rewards.py — insert_epoch_reward + mark_claim_tx (brain-owned)"
    - "python/src/boros_brain/state/writers/clo_history.py — insert_clo_snapshot (brain-owned)"
    - "python/src/boros_brain/state/writers/reward_budget_history.py — insert_reward_budget + B6 ValueError guard (brain-owned)"
    - "python/src/boros_brain/state/writers/open_orders.py — TEST_ONLY=True; insert_open_order + update_open_order_status"
    - "python/src/boros_brain/state/writers/tx_receipts.py — TEST_ONLY=True; insert_tx_receipt"
    - "python/tests/test_sqlite_migrations.py — 6 migration + safety tests"
    - "python/tests/test_sqlite_single_writer.py — 8 round-trip + guard tests across all writer modules"
    - "scripts/sqlite_writer_lint.py — single-writer-per-table lint (main entrypoint)"
    - "scripts/apply_alembic_migration.py — CLI helper for arbitrary-url alembic upgrade (used by TS tests)"
    - "scripts/tests/test_sqlite_writer_lint.py — clean-tree-passes + injected-drift-fails"
    - "ts/src/boros_hands/state/sqlite_writer.ts — openHandsDb + upsertOpenOrder + updateOpenOrderStatus + insertTxReceipt + confirmTxReceipt"
    - "ts/tests/state/sqlite_writer.test.ts — open_orders upsert + tx_receipts insert round-trips"
  modified:
    - "python/tests/test_tracer_bullet.py — un-skipped test_sqlite_open_orders_roundtrip; wired to writers.open_orders via TEST_ONLY seeding path"
    - "ts/tests/tracer_bullet.test.ts — new 'sqlite_writer WAL roundtrip works' test (INFRA-03 un-skip); pino/ZMQ/SIGTERM stubs remain it.skip for 01-03"
    - "ts/package.json — added pnpm.onlyBuiltDependencies=['better-sqlite3'] so fresh clones rebuild the native binding"
    - "ts/tsconfig.json — removed rootDir=\"src\" (pre-existing tsconfig bug amplified by new test files; fix scoped to this plan)"

key-decisions:
  - "One-statement-per-semicolon SQL replay in the alembic migration (rather than embedding all 8 CREATE TABLE in Python strings): keeps schemas.sql as the single human-readable source of truth; Mermaid-style schema diffs in future migrations will still live in schemas.sql + a new 000N revision in the same commit."
  - "TEST_ONLY=True module-scope literal as the lint-recognised Python-exception marker: a simple string grep at module top is unambiguous; adding a comment '# TEST_ONLY' would also match grep but the literal assignment ensures the marker is semantically load-bearing (you can `from writers.open_orders import TEST_ONLY` in tests)."
  - "Writers use autocommit (isolation_level=None) + caller owns transactions: batch writers (e.g., trade-tape replay) can wrap N inserts in BEGIN/COMMIT without the writer helper fighting them. For single-row writes the autocommit-per-call cost is negligible."
  - "scripts/apply_alembic_migration.py as a standalone helper (not a pytest fixture): TS tests need a CLI-reachable way to drive the migration with an arbitrary `sqlite:///<tmp>.sqlite` URL. Alembic's CLI -x flag does NOT override sqlalchemy.url (documented Alembic limitation); the helper calls `command.upgrade()` programmatically with `cfg.set_main_option('sqlalchemy.url', …)`."
  - "TS sqlite_writer does NOT clamp chmod 600 (Python-side does): production boot order is brain-first (alembic upgrade runs before hands starts), so the file is always chmod-clamped before the TS side opens it. If that boot-order assumption ever changes, add the TS-side chmod call; for now the constraint is documented in the function docstring."
  - "B6 guard (ValueError before SQL IntegrityError): the DB CHECK constraint would reject invalid data_source values too, but surfacing a ValueError at the Python layer gives callers a clearer stack trace and stops the SQL round-trip earlier on hot paths."

patterns-established:
  - "The PROTO-02 single-writer-per-table pattern is now MECHANICALLY enforced rather than convention-enforced. Any commit that adds `INSERT INTO <table>` outside the designated owner file will fail scripts/sqlite_writer_lint.py (wired into pre-commit by plan 01-04). This permanently closes the 'grep-for-drift-in-code-review' failure mode."
  - "Every Python + TypeScript test that needs persisted state now has a canonical setup path: `open_connection()` → apply_alembic_migration.py (or programmatic command.upgrade) → use the writer module. No test is allowed to reach for raw SQL for setup."

requirements-completed: [INFRA-03]

threat-mitigations-applied:
  - "T-02-01 (Tampering via non-owner write): scripts/sqlite_writer_lint.py catches INSERT INTO / UPDATE / ON CONFLICT / DELETE FROM outside the owner file. Tested via test_injected_insert_in_wrong_module_fails (injects `INSERT INTO decisions` into main.py of a copied repo tree, asserts exit 1 + violation message)."
  - "T-02-02 (Information Disclosure via 0o644 SQLite): ensure_permissions_0600() called from open_connection() clamps .sqlite + -wal + -shm siblings. Tested via test_sqlite_file_chmod_600."
  - "T-02-03 (Repudiation via unenforced FK): enable_wal_mode() sets PRAGMA foreign_keys=ON. Tested via test_run_manifests_parent_run_id_fk (dangling parent raises sqlite3.IntegrityError)."
  - "T-02-04 (B6 backtest pollution): reward_budget_history.data_source CHECK constraint at SQL layer + Python ValueError guard in the writer. Tested via test_reward_budget_history_data_source_check + test_reward_budget_history_rejects_invalid_data_source."

duration: 16min
completed: 2026-04-24
---

# Phase 01 Plan 01-02: SQLite WAL State Spine (INFRA-03) Summary

**The SQLite WAL state spine landed with all 8 tables migrated via Alembic 0001, single-writer-per-table discipline mechanically enforced by `scripts/sqlite_writer_lint.py`, file permissions clamped to 0o600 at every `open_connection()`, `PRAGMA foreign_keys=ON` enforced for the `run_manifests.parent_run_id` chain, and the Wave-0 tracer-bullet `test_sqlite_open_orders_roundtrip` un-skipped and green on both the Python and TypeScript sides.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-04-23T23:50:14Z
- **Completed:** 2026-04-24T00:06:14Z
- **Tasks:** 2 (both `type="auto"` with `tdd="true"`; both followed strict RED → GREEN with visible-failure commits before implementation)
- **Files created:** 23 (7 in Task 1 + 16 in Task 2)
- **Files modified:** 4 (Task 2: test_tracer_bullet.py, tracer_bullet.test.ts, ts/package.json, ts/tsconfig.json)

## Task Commits

Four atomic commits — RED and GREEN gates for each task plus the plan's metadata commit at the end:

1. **Task 1 RED (`fe5295e`)** — `test(01-02): add failing test for SQLite WAL state spine migration` (6 failing assertions on missing `boros_brain.state.db` module).
2. **Task 1 GREEN (`8352379`)** — `feat(01-02): SQLite WAL state spine — 8-table schema + Alembic 0001 + db.py` (schemas.sql + db.py + alembic env.py + 0001 migration; all 6 tests pass).
3. **Task 2 RED (`b7e34ea`)** — `test(01-02): add failing tests for single-writer discipline + TS+Py round-trips` (test_sqlite_single_writer.py + test_sqlite_writer_lint.py + ts/tests/state/sqlite_writer.test.ts + flipped tracer-bullet stubs; 9 failing Python tests).
4. **Task 2 GREEN (`0b5a644`)** — `feat(01-02): per-table writer modules + single-writer lint + TS hands writer` (9 writer modules + lint + TS sqlite_writer + apply_alembic_migration.py; all tests pass, lint catches injected drift).

## 8-table column inventory (from schemas.sql)

### open_orders (hands-owned — TS sqlite_writer.ts is the production writer)
```
order_id       TEXT PRIMARY KEY
market_id      TEXT NOT NULL
side           TEXT NOT NULL CHECK(side IN ('long','short'))
depth_ticks    INTEGER NOT NULL
size_wei       TEXT NOT NULL                              -- 256-bit wei as string
rate           INTEGER NOT NULL
status         TEXT NOT NULL CHECK(status IN ('filling','cancelled','fully_filled','expired','purged'))
placed_at_ts   INTEGER NOT NULL
run_id         TEXT NOT NULL
+ ix_open_orders_run_id(run_id), ix_open_orders_market_status(market_id, status)
```

### decisions (brain-owned)
```
decision_id    TEXT PRIMARY KEY
ts_ms          INTEGER NOT NULL
run_id         TEXT NOT NULL
market_id      TEXT NOT NULL
decision       TEXT NOT NULL CHECK(decision IN ('place','hold','cancel','emergency_cancel','no_action'))
ev_hold        REAL
p_fill         REAL
e_loss         REAL
r_share        REAL
reason         TEXT
+ ix_decisions_run_id_ts(run_id, ts_ms)
```

### tx_receipts (hands-owned)
```
tx_hash           TEXT PRIMARY KEY
run_id            TEXT NOT NULL
submitted_at_ts   INTEGER NOT NULL
confirmed_at_ts   INTEGER
status            TEXT NOT NULL CHECK(status IN ('pending','confirmed','reverted','dropped'))
gas_used          INTEGER
intent            TEXT NOT NULL                           -- 'place'|'cancel'|'close'|'claim'|'approve'|…
related_order_id  TEXT
+ ix_tx_receipts_run_id(run_id)
```

### queue_positions (brain-owned)
```
snapshot_ts           INTEGER NOT NULL
market_id             TEXT NOT NULL
side                  TEXT NOT NULL CHECK(side IN ('long','short'))
tick                  INTEGER NOT NULL
our_order_id          TEXT NOT NULL
queue_ahead_size_wei  TEXT NOT NULL
PRIMARY KEY(snapshot_ts, market_id, side, tick, our_order_id)
```

### run_manifests (brain-owned — INFRA-06 RUN_MANIFEST relational sidecar)
```
run_id                TEXT PRIMARY KEY
parent_run_id         TEXT REFERENCES run_manifests(run_id)    -- self-FK for mid-run knob-change chain
started_at_iso        TEXT NOT NULL
mode                  TEXT NOT NULL CHECK(mode IN ('live','paper','backtest','ingest','screen'))
strategy_version      TEXT NOT NULL
git_sha               TEXT NOT NULL
git_dirty             INTEGER NOT NULL CHECK(git_dirty IN (0,1))
market_id             TEXT NOT NULL
side                  TEXT NOT NULL CHECK(side IN ('long','short'))
wallet_address_hash   TEXT NOT NULL
config_json           TEXT NOT NULL                            -- full BotConfig.model_dump(mode='json')
+ ix_run_manifests_started_at(started_at_iso)
```

### epoch_rewards (brain-owned)
```
epoch_end_ts         INTEGER NOT NULL
market_id            TEXT NOT NULL
our_accrued_pendle   REAL NOT NULL
claimed              INTEGER NOT NULL DEFAULT 0 CHECK(claimed IN (0,1))
claim_tx_hash        TEXT
PRIMARY KEY(epoch_end_ts, market_id)
```

### clo_history (brain-owned — DATA-06 /markets poller)
```
snapshot_ts       INTEGER NOT NULL
market_id         TEXT NOT NULL
clo_lower_thresh  REAL NOT NULL
clo_upper_thresh  REAL NOT NULL
f_index_raw       INTEGER                                       -- nullable; 01-09 populates on every poll
PRIMARY KEY(snapshot_ts, market_id)
```

### reward_budget_history (brain-owned — DATA-11 + B6 pitfall guard)
```
snapshot_ts       INTEGER NOT NULL
market_id         TEXT NOT NULL
e_liq_per_epoch   REAL NOT NULL
long_budget       REAL NOT NULL
short_budget      REAL NOT NULL
data_source       TEXT NOT NULL CHECK(data_source IN ('polled','synthetic_current'))  -- B6 flag
PRIMARY KEY(snapshot_ts, market_id)
```

## Writer modules inventory

| Table                   | Owner         | Production writer                                                          | Python test-seeding writer?            |
| ----------------------- | ------------- | -------------------------------------------------------------------------- | -------------------------------------- |
| `open_orders`           | hands (TS)    | `ts/src/boros_hands/state/sqlite_writer.ts::upsertOpenOrder`               | `state/writers/open_orders.py` (TEST_ONLY=True) |
| `tx_receipts`           | hands (TS)    | `ts/src/boros_hands/state/sqlite_writer.ts::insertTxReceipt`               | `state/writers/tx_receipts.py` (TEST_ONLY=True) |
| `decisions`             | brain (Py)    | `state/writers/decisions.py::insert_decision`                              | —                                      |
| `queue_positions`       | brain (Py)    | `state/writers/queue_positions.py::insert_queue_position`                  | —                                      |
| `run_manifests`         | brain (Py)    | `state/writers/run_manifests.py::insert_run_manifest`                      | —                                      |
| `epoch_rewards`         | brain (Py)    | `state/writers/epoch_rewards.py::insert_epoch_reward` + `mark_claim_tx`    | —                                      |
| `clo_history`           | brain (Py)    | `state/writers/clo_history.py::insert_clo_snapshot`                        | —                                      |
| `reward_budget_history` | brain (Py)    | `state/writers/reward_budget_history.py::insert_reward_budget` (+B6 guard) | —                                      |

Total: **9 writer modules** (6 brain-production + 1 TS-production + 2 TEST_ONLY-guarded Python hands seeders). Ownership grepped and confirmed single-file for every table:

```
$ grep -rl "INSERT INTO decisions" python/src ts/src --include='*.py' --include='*.ts'
python/src/boros_brain/state/writers/decisions.py

$ grep -rl "INSERT INTO open_orders\|UPDATE open_orders" ts/src --include='*.ts'
ts/src/boros_hands/state/sqlite_writer.ts

$ grep -rl "INSERT INTO open_orders" python/src --include='*.py'
python/src/boros_brain/state/writers/open_orders.py       # TEST_ONLY=True guarded

$ grep -rl "INSERT INTO tx_receipts" ts/src --include='*.ts'
ts/src/boros_hands/state/sqlite_writer.ts
```

## Confirmation: `sqlite_writer_lint.py` catches injected drift

Dry-run on the real repo (clean tree):
```
$ cd python && uv run python ../scripts/sqlite_writer_lint.py --root ..
$ echo $?
0
```

Dry-run with `INSERT INTO decisions` injected into `main.py` of a copied repo tree:
```
$ uv run python ../scripts/sqlite_writer_lint.py --root /tmp/boros-lint-demo
sqlite_writer_lint: single-writer violations detected
  python/src/boros_brain/main.py: writes to `decisions` (owner: python/src/boros_brain/state/writers/decisions.py)
$ echo $?
1
```

The behavioral test `scripts/tests/test_sqlite_writer_lint.py::test_injected_insert_in_wrong_module_fails` automates this exact flow on every CI run.

## Confirmation: WAL mode + FK enforcement + 0o600 live on every `open_connection()`

Live smoke-test:
```
$ cd python && uv run python -c "
from boros_brain.state.db import open_connection
from pathlib import Path; import tempfile, os, stat
d = tempfile.mkdtemp()
with open_connection(Path(d)/'test.sqlite') as c:
    print('journal_mode:', c.execute('PRAGMA journal_mode').fetchone()[0])
    print('foreign_keys:', c.execute('PRAGMA foreign_keys').fetchone()[0])
mode = stat.S_IMODE(os.stat(Path(d)/'test.sqlite').st_mode)
print('chmod:', oct(mode))"
journal_mode: wal
foreign_keys: 1
chmod: 0o600
```

`ensure_permissions_0600()` is called unconditionally from `open_connection()` — NOT one-time-at-creation — so a crash during WAL truncation that leaves fresh `-wal` / `-shm` siblings around is covered by the next open. `test_idempotent_reopen` asserts no permission change on repeated opens (both settle at 0o600 and stay there).

## Verification block (plan §verification)

| Check                                                                              | Result                                                                                             |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `cd python && uv run pytest -q` — all migration + single-writer + tracer tests pass | ✓ 22 passed, 2 skipped (manifest + ZMQ pending 01-03)                                              |
| `cd ts && pnpm vitest run` — open_orders + tx_receipts round-trips pass             | ✓ 4 passed, 3 skipped (pino + ZMQ + SIGTERM pending 01-03)                                         |
| `uv run python scripts/sqlite_writer_lint.py --root .` exits 0 on clean tree       | ✓ CLEAN                                                                                            |
| `uv run python scripts/sqlite_writer_lint.py --root <with-drift>` exits 1         | ✓ exit 1, violation message: `main.py: writes to decisions (owner: …writers/decisions.py)`       |
| `grep -c "CREATE TABLE" python/src/boros_brain/state/schemas.sql` returns 8         | ✓ 8                                                                                                |
| 0o600 perms on live SQLite file after open_connection                               | ✓ verified by `test_sqlite_file_chmod_600` and interactive smoke-test                              |
| `PRAGMA foreign_keys = ON` at connection time                                        | ✓ verified by `test_run_manifests_parent_run_id_fk` (dangling FK raises IntegrityError)            |
| B6 CHECK: `data_source` rejects 'invalid'                                            | ✓ verified by `test_reward_budget_history_data_source_check` + writer-level ValueError guard       |

## Decisions Made

- **One-statement-per-semicolon replay in Alembic 0001.** Splitting `schemas.sql` on top-level semicolons and running each as a separate `op.execute()` keeps schemas.sql human-readable (the SQL is not duplicated in Python string literals) and keeps the migration small. Any new column added in a future plan lands in schemas.sql + a new numbered migration in the same commit.

- **`TEST_ONLY = True` as a module-scope literal marker.** The lint recognises this exact string at module top to grant a write exception for Python-side hands writers. A comment (`# TEST_ONLY`) would also grep-match but the literal assignment is semantically load-bearing — tests can `from …writers.open_orders import TEST_ONLY; assert TEST_ONLY is True`, which is how `test_hands_owned_python_writers_are_test_only` validates the guard is in place.

- **Writers use autocommit; caller owns transactions.** `open_connection(isolation_level=None)` means each `INSERT` auto-commits. Batch callers wrap in explicit `BEGIN` / `COMMIT` when needed (e.g., trade-tape replay). For single-row writes the autocommit cost is negligible and the writer code stays slim (no implicit rollback / context swallowing).

- **`scripts/apply_alembic_migration.py` instead of alembic CLI for TS tests.** Alembic's `-x key=value` CLI flag does NOT override `sqlalchemy.url` (documented Alembic behavior — `-x` is for user-defined vars only). The helper script uses `cfg.set_main_option("sqlalchemy.url", url)` programmatically, which TS tests invoke via `execSync('uv run python …apply_alembic_migration.py sqlite:///tmp.sqlite')` in `beforeEach`.

- **TS `openHandsDb` does NOT clamp chmod 600.** Production boot order is brain-first (the launchd plist starts `brain` first, which runs `alembic upgrade head` before `hands` connects). The file is always chmod-clamped before the TS side opens it. If that boot-order assumption changes, add the TS-side chmod call; for now the constraint is documented in the function docstring and mirrored by `ts/src/boros_hands/state/sqlite_writer.ts` source comment.

- **B6 guard as ValueError BEFORE SQL IntegrityError.** The DB CHECK constraint would reject invalid `data_source` values at the SQL layer, but surfacing a `ValueError` at the Python boundary gives callers a clearer stack trace and stops the SQL round-trip earlier on hot paths. The DB CHECK remains the last line of defense.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `better-sqlite3` native binding missing on the host**
- **Found during:** First vitest run of `sqlite_writer.test.ts` — `Error: Could not locate the bindings file`.
- **Issue:** pnpm 10 defaults to NOT running post-install build scripts for untrusted packages (security feature). `better-sqlite3` ships a `node-gyp` build step that never ran, so the `.node` binary was missing for Node 23.11.0.
- **Fix:** Ran `npx --yes prebuild-install` once to materialize `build/Release/better_sqlite3.node`, then added `"pnpm": { "onlyBuiltDependencies": ["better-sqlite3"] }` to `ts/package.json` so fresh clones auto-rebuild on `pnpm install`.
- **Files modified:** `ts/package.json`.
- **Verification:** Fresh `pnpm vitest run` → 4 passed, 3 skipped.
- **Committed in:** `0b5a644` (Task 2 GREEN).

**2. [Rule 3 - Blocking] Pre-existing `tsconfig.json` bug amplified by new test files**
- **Found during:** `pnpm typecheck` after adding `ts/tests/state/sqlite_writer.test.ts`.
- **Issue:** 01-01's `ts/tsconfig.json` had `"rootDir": "src"` combined with `"include": ["src/**/*", "tests/**/*"]` — these are contradictory (tsc requires all included files to live under `rootDir`). The bug existed at the end of 01-01 (already rejecting `tests/setup.ts`), but 01-01's verification block did not run `pnpm typecheck` so it was not caught. 01-02 added two more test files under `tests/`, making `pnpm typecheck` exit 2 with 3 TS6059 errors.
- **Fix:** Removed the `"rootDir": "src"` line. `outDir: "dist"` remains; `tsc --noEmit` (which `pnpm typecheck` runs) doesn't care about layout anyway.
- **Files modified:** `ts/tsconfig.json` (one-line delete).
- **Verification:** `pnpm typecheck` exits 0.
- **Committed in:** `0b5a644` (Task 2 GREEN).
- **Scope note:** This is pre-existing-but-adjacent — the plan's scope boundary says "only fix issues DIRECTLY caused by the current task's changes." The Task 2 test files hit this bug; fixing it unblocks the plan's acceptance criteria (`pnpm typecheck` is part of `make lint`). Logged as Rule 3 rather than silently fixed.

**3. [Rule 1 - Cleanup] Ruff UP035 + SIM105 findings in files authored by this plan**
- **Found during:** Running `uv run ruff check src` after Task 2 GREEN.
- **Issue:** `db.py` used `from typing import Iterator` (UP035 — should be `collections.abc`); `migrations/env.py` used `try/except Exception: pass` (SIM105 — should be `contextlib.suppress`).
- **Fix:** Migrated both to the modern idiom.
- **Files modified:** `python/src/boros_brain/state/db.py`, `python/src/boros_brain/state/migrations/env.py`.
- **Verification:** `uv run ruff check src/boros_brain/state` → All checks passed! Tests still 22 passed, 2 skipped.
- **Committed in:** `0b5a644` (Task 2 GREEN — rolled in with the rest of Task 2 to keep the GREEN commit comprehensive).
- **Note:** A pre-existing UP035 in `src/boros_brain/main.py` (from 01-01) was left alone per scope boundary — it is not a file this plan touches.

---

**Total deviations:** 3 auto-fixed (2× Rule 3 blocking, 1× Rule 1 cleanup, 0× Rule 2 missing critical, 0× Rule 4 architectural)
**Impact on plan:** All three are pure unblockers that do not change the plan's deliverables. No new knobs, no schema changes, no scope creep.

## Issues Encountered

- **Alembic CLI `-x sqlalchemy.url=…` does NOT override the ini's `sqlalchemy.url`.** Alembic's `-x` is for user-defined variables consumed inside `env.py`, not for SQLAlchemy URL override. First pass at the TS sqlite_writer test invoked `uv run alembic -c … -x sqlalchemy.url=sqlite:///tmp upgrade head` which silently tried to open the production default path (`state/state.sqlite` relative to cwd) and failed with `OperationalError: unable to open database file`. Replaced with the programmatic `scripts/apply_alembic_migration.py` helper. Documented in the plan's Known follow-ups section below so plan 01-04 (pre-commit hook integration) doesn't repeat the mistake.

- **pnpm 10 refuses to run `postinstall` scripts without explicit opt-in.** A security-hardening default; logged as deviation #1 above. Mentioning it here for searchability — any future TS dep with a native build step (`@pendle/sdk-boros` pulls in nothing native at the moment, but `zeromq` might, and future deps absolutely will) needs to be listed in `pnpm.onlyBuiltDependencies` or the binding will silently be absent.

## Threat model follow-through

| Threat ID | Mitigation status | Evidence |
|-----------|-------------------|----------|
| T-02-01 (Tampering — non-owner table writes) | Mitigated | `scripts/sqlite_writer_lint.py` + `scripts/tests/test_sqlite_writer_lint.py::test_injected_insert_in_wrong_module_fails` (both cases pass). The lint runs as-is today via `uv run python scripts/sqlite_writer_lint.py --root .`; plan 01-04 will wire it into pre-commit. |
| T-02-02 (Information Disclosure — 0o644 SQLite) | Mitigated | `ensure_permissions_0600()` called from `open_connection()`; `test_sqlite_file_chmod_600` + `test_idempotent_reopen` both assert 0o600. `-wal` + `-shm` siblings are also clamped on every open. |
| T-02-03 (Repudiation — unenforced parent_run_id FK) | Mitigated | `PRAGMA foreign_keys = ON` in `enable_wal_mode()`; `test_run_manifests_parent_run_id_fk` inserts a dangling-parent row and asserts `sqlite3.IntegrityError`. |
| T-02-04 (Data Corruption — B6 backtest pollution) | Mitigated | `reward_budget_history.data_source` CHECK constraint at SQL layer + `insert_reward_budget` `ValueError` guard at Python layer. `test_reward_budget_history_data_source_check` (SQL layer) + `test_reward_budget_history_rejects_invalid_data_source` (writer layer) both pass. |

## User Setup Required

**For fresh clones** (one-time):
- After `pnpm install`, pnpm will automatically build `better-sqlite3` because it is now listed in `pnpm.onlyBuiltDependencies`. If the first install on a fresh machine fails to build the native binding (e.g., missing `node-gyp`), run `cd ts/node_modules/.pnpm/better-sqlite3@11.10.0/node_modules/better-sqlite3 && npx --yes prebuild-install` to fetch the prebuilt binary from GitHub releases.

**None other** — no external service, no API key, no operator action required.

## Next Phase Readiness

- **Immediate downstream (Wave 1+ of phase 01):**
  - **01-03 (ZMQ bus + structlog + RUN_MANIFEST)** — will import `state.writers.run_manifests.insert_run_manifest` from the brain side to persist the RUN_MANIFEST JSON into the `run_manifests` table. The table + writer are both ready.
  - **01-04 (pre-commit hook installer)** — will wire `scripts/sqlite_writer_lint.py` into `.pre-commit-config.yaml` alongside the architecture-drift hook. Script is stable, help text / `--root` flag / exit-code contract are all honored.
  - **01-05 (LLM Wiki seed)** — will file `[[SQLite state spine v0.5]]` and link back to this SUMMARY as its provenance. The plan's `<output>` block explicitly notes "wiki page is filed by plan 01-05".
  - **01-09 (/markets poller)** — will `insert_clo_snapshot(...)` per poll; the `f_index_raw` column is nullable-but-populated-on-live-poll exactly as the poller needs.
  - **01-10 (fIndex oracle decoder)** — will update `insert_clo_snapshot` call sites to pass decoded `f_index_raw`. Ready today.
  - **01-11 (SCALE calibration)** — will read `clo_history` rows via DuckDB / sqlite3 read-only; writers for this table are already live.
- **Known follow-ups (deferred, tracked):**
  - **`[[SQLite state spine v0.5]]` wiki page** — deferred to plan 01-05, as noted in the plan's `<output>` block.
  - **Pre-existing `main.py` UP035** — not fixed by this plan (scope boundary); will be cleaned up when a future plan touches `main.py`.
  - **Pre-existing mypy errors in `config/schema.py` + `config/loader.py`** — these are 01-01 issues that `uv run mypy src` flags; out of scope for 01-02.
  - **TS-side chmod 600 call** — not added because production boot order is brain-first. If `hands` ever starts before `brain`, wire `openHandsDb` to clamp perms too. Documented in the function's JSDoc.

## Self-Check: PASSED

**Files verified existing:**
- FOUND: python/src/boros_brain/state/__init__.py
- FOUND: python/src/boros_brain/state/db.py
- FOUND: python/src/boros_brain/state/schemas.sql
- FOUND: python/src/boros_brain/state/migrations/alembic.ini
- FOUND: python/src/boros_brain/state/migrations/env.py
- FOUND: python/src/boros_brain/state/migrations/script.py.mako
- FOUND: python/src/boros_brain/state/migrations/versions/0001_initial_8_tables.py
- FOUND: python/src/boros_brain/state/writers/__init__.py
- FOUND: python/src/boros_brain/state/writers/open_orders.py
- FOUND: python/src/boros_brain/state/writers/decisions.py
- FOUND: python/src/boros_brain/state/writers/tx_receipts.py
- FOUND: python/src/boros_brain/state/writers/queue_positions.py
- FOUND: python/src/boros_brain/state/writers/run_manifests.py
- FOUND: python/src/boros_brain/state/writers/epoch_rewards.py
- FOUND: python/src/boros_brain/state/writers/clo_history.py
- FOUND: python/src/boros_brain/state/writers/reward_budget_history.py
- FOUND: python/tests/test_sqlite_migrations.py
- FOUND: python/tests/test_sqlite_single_writer.py
- FOUND: python/tests/test_tracer_bullet.py (modified)
- FOUND: scripts/sqlite_writer_lint.py
- FOUND: scripts/apply_alembic_migration.py
- FOUND: scripts/tests/test_sqlite_writer_lint.py
- FOUND: ts/src/boros_hands/state/sqlite_writer.ts
- FOUND: ts/tests/state/sqlite_writer.test.ts
- FOUND: ts/tests/tracer_bullet.test.ts (modified)

**Commits verified via git log:**
- FOUND: fe5295e (Task 1 RED — failing migration test)
- FOUND: 8352379 (Task 1 GREEN — schema + db.py + alembic 0001)
- FOUND: b7e34ea (Task 2 RED — failing single-writer / TS / lint tests)
- FOUND: 0b5a644 (Task 2 GREEN — writers + lint + TS sqlite_writer)

**Test-suite verification:**
- Python: 22 passed, 2 skipped (pending 01-03: `test_manifest_writer_emits_first_line`, `test_zmq_echo_roundtrip_under_10ms`)
- TS: 4 passed, 3 skipped (pending 01-03: pino JSON shape, ZMQ echo, SIGTERM flush)
- Lint: clean on real repo + 2 behavioral tests pass (clean-tree + injected-drift)

---
*Phase: 01-foundation-infrastructure-spine-data-pipeline-economics-gate*
*Completed: 2026-04-24*
