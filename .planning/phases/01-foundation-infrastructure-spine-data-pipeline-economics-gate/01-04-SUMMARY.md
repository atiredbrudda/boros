---
phase: "01"
plan: "01-04"
subsystem: engineering-protocol-enforcement
tags: [architecture-lint, wiki-cite-lint, pre-commit, engineering-protocols, infra]
dependency_graph:
  requires: [01-01, 01-02, 01-03]
  provides: [architecture-manifest, pre-commit-hooks, lint-enforcement]
  affects: [all-future-plans]
tech_stack:
  added:
    - pre-commit 4.x (hook runner)
    - ruff v0.7.0 (Python linting + formatting)
    - mypy v1.13.0 strict (Python type checking)
    - biome v1.9.4 (TypeScript linting + formatting)
    - types-PyYAML (mypy stubs)
  patterns:
    - AST-walk for Python module discovery (architecture_lint)
    - regex scan for TypeScript module discovery (architecture_lint)
    - code-block stripping before wiki-link search (wiki_cite_lint)
    - bare type:ignore + --no-warn-unused-ignores for Pydantic default_factory mypy pattern
key_files:
  created:
    - docs/architecture.yml
    - docs/override-log.md
    - scripts/architecture_lint.py
    - scripts/wiki_cite_lint.py
    - scripts/no_plain_keys.py
    - .pre-commit-config.yaml
    - scripts/tests/test_architecture_lint.py
    - scripts/tests/test_wiki_cite_lint.py
    - scripts/tests/test_no_plain_keys.py
    - scripts/tests/fixtures/arch_clean/architecture.yml
    - scripts/tests/fixtures/arch_clean/test/a.py
    - scripts/tests/fixtures/arch_drift/architecture.yml
    - scripts/tests/fixtures/arch_drift/test/a.py
    - scripts/tests/fixtures/wiki_cite_pass/research/dummy.md
    - scripts/tests/fixtures/wiki_cite_fail/research/dummy.md
  modified:
    - docs/ARCHITECTURE.md (first committed in this plan)
    - python/src/boros_brain/bus/cmd.py (type: ignore for pyzmq stubs)
    - python/src/boros_brain/bus/events.py (dict[str,Any] return type)
    - python/src/boros_brain/config/schema.py (type: ignore for Pydantic default_factory)
    - python/src/boros_brain/logging/structlog_setup.py (Any return type, orjson str cast)
    - python/src/boros_brain/main.py (contextlib.suppress SIM105 fix + contextlib import)
    - python/src/boros_brain/manifest/schema.py (dict[str,Any] for config field)
    - python/tests/test_heartbeat_lost_sibling.py (contextlib.suppress SIM105 fix)
    - python/tests/test_parent_run_id_chain.py (combined nested with SIM117 fix)
    - python/tests/test_sqlite_migrations.py (combined nested with SIM117 fix)
    - python/pyproject.toml + python/uv.lock (types-PyYAML dev dep)
decisions:
  - "Bootstrap commit uses --no-verify exactly once: docs/architecture.yml creation is a circular dep (the lint it would fail doesn't exist yet). Logged in docs/override-log.md with #override: bootstrap tag."
  - "architecture_lint skips __init__.py files (namespace package markers) and migrations/ directory (Alembic internals) — these are not architecture nodes."
  - "architecture_lint catches drift in both directions: undeclared code modules AND orphaned yml declarations AND public functions in code not declared in yml."
  - "wiki_cite_lint uses POLICED_PATH_PARTS = (research, decisions, postmortem) — only fires on repo-root-level directories, not .planning/research/ (bootstrap-exempt pre-hook files)."
  - "no_plain_keys.py excludes .planning/ paths (planning docs contain fake key patterns as documentation examples). All source/config/env files remain fully policed."
  - "mypy --no-warn-unused-ignores added to pre-commit because Pydantic default_factory type errors only appear without the pydantic mypy plugin; bare type: ignore + no-warn-unused-ignores handles both plugin-present and plugin-absent cases."
  - "python3 used in all system-language local pre-commit hooks (macOS has no bare `python` in PATH)."
metrics:
  duration_minutes: 22
  completed_date: "2026-04-24"
  tasks_completed: 3
  files_changed: 82
---

# Phase 01 Plan 04: Engineering Protocol Enforcement (architecture-lint + wiki-cite-lint + pre-commit) Summary

**One-liner:** Architecture drift lint (AST + regex), wiki-cite enforcement, and no-plain-keys security hook wired into pre-commit 4.x, bootstrapped with a single `--no-verify` exception logged in `docs/override-log.md`.

## What Was Built

### Task 1 — Bootstrap architecture.yml + ARCHITECTURE.md + override-log.md

- `docs/architecture.yml`: 75 nodes (2 process, 28 module, 8 storage, 34 config_knob, 3 external), 50 edges — complete Phase-1 manifest from plans 01-01/02/03
- `docs/ARCHITECTURE.md`: Mermaid flowchart already existed from plan 01-03; committed to git in this plan
- `docs/override-log.md`: Audit trail for `--no-verify` bypasses; bootstrap entry logged with commit hash `9f6db24`
- Committed with `git commit --no-verify` + `#override: bootstrap` tag (one-time circular-dep exception per plan spec)

### Task 2 — architecture_lint.py + wiki_cite_lint.py + fixtures + tests

- `scripts/architecture_lint.py`: AST-walks `python/src/`, regex-walks `ts/src/`, diffs against `docs/architecture.yml`; catches undeclared modules, orphaned declarations, missing paths, and public functions in code but not declared in yml
- `scripts/wiki_cite_lint.py`: Polices `research/`, `decisions/`, `postmortem/` markdown; strips fenced/inline code before searching for `[[wiki-link]]`; only fires on policed path components (not `.planning/research/`)
- 4 arch-lint tests + 4 wiki-cite tests — all 8 pass; real tree exits 0

### Task 3 — .pre-commit-config.yaml + no_plain_keys.py + ruff/mypy/biome wave close

- `.pre-commit-config.yaml`: Wires all Engineering Protocol enforcement hooks
- `scripts/no_plain_keys.py`: Blocks `0x<64hex>` ETH keys + PEM headers; all-zero synthetic keys exempt
- Wave-close fixes (Rule 1 — bugs blocking pre-commit):
  - SIM105: `contextlib.suppress()` replacing bare `try/except CancelledError: pass` in `main.py` and heartbeat test
  - SIM117: Combined nested `with` statements in FK enforcement tests
  - mypy: Type annotations for `Any`, `dict[str, Any]`, `type: ignore[misc,func-returns-value]` for pyzmq asyncio stubs

## Verification Results

```
python3 scripts/architecture_lint.py    → exit 0 (clean tree)
python3 scripts/sqlite_writer_lint.py --root .  → exit 0
pre-commit run --all-files              → all 10 hooks green (exit 0)
pytest scripts/tests/ -q               → 14 passed
pytest python/tests/ -q                → 38 passed
```

## architecture.yml Statistics

- **Nodes:** 75 (2 process, 28 module, 8 storage, 34 config_knob, 3 external)
- **Edges:** 50 (calls, reads, writes, emits-event, depends-on-config)

## Pre-commit Hook Summary

```
architecture-lint         — Protocol #2: code change requires architecture.yml update
wiki-cite-lint            — Protocol #1: research/decisions/postmortem must cite wiki
sqlite-writer-lint        — INFRA-03: single-writer-per-table discipline
no-plain-keys             — T-04-03: block ETH private keys + PEM headers
config-round-trip-test    — PROTO-04: BotConfig round-trip stays valid
manifest-contains-all-knobs — PITFALLS D2: every BotConfig field in RUN_MANIFEST
ruff / ruff-format        — Python code quality
mypy (strict)             — Python type checking
biome-check               — TypeScript linting + formatting
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] architecture_lint false-positives on __init__.py packages**
- **Found during:** Task 2, Test 4 (real tree)
- **Issue:** `bus/__init__.py` generated module ID `brain.bus` (a namespace package), not a declared architecture node
- **Fix:** Skip ALL `__init__.py` files in AST walk; skip `migrations/` directory (Alembic internals)
- **Files modified:** `scripts/architecture_lint.py`
- **Commit:** 8bdf994

**2. [Rule 1 - Bug] architecture_lint only checked yml→code direction for public functions**
- **Found during:** Task 2, Test 2 (drift detection)
- **Issue:** `undeclared_fn` in source but not in yml was not caught (only yml-declared-but-missing was checked)
- **Fix:** Added reverse check: for each declared module, report public functions in code not declared in yml
- **Files modified:** `scripts/architecture_lint.py`
- **Commit:** 8bdf994

**3. [Rule 1 - Bug] Fixture path resolution for arch_clean test**
- **Found during:** Task 2, Test 1
- **Issue:** Fixture `src_module.py` at root of `arch_clean/` generated no module ID (requires package structure)
- **Fix:** Restructured fixtures to `arch_clean/test/a.py` and `arch_drift/test/a.py`; updated fixture ymls with repo-root-relative paths
- **Files modified:** fixtures/arch_clean/*, fixtures/arch_drift/*
- **Commit:** 8bdf994

**4. [Rule 1 - Bug] no_plain_keys.py self-triggered on its own docstring**
- **Found during:** Task 3, self-scan acceptance check
- **Issue:** Docstring contained literal `-----BEGIN PRIVATE KEY-----` string matching the PEM regex
- **Fix:** Replaced literal with paraphrased description; broke PEM pattern assembly string to avoid self-match
- **Files modified:** `scripts/no_plain_keys.py`
- **Commit:** 4d2db1b

**5. [Rule 3 - Blocking] pre-commit hooks used `python` but macOS has no bare `python` in PATH**
- **Found during:** Task 3, first commit attempt
- **Issue:** `language: system` hooks with `entry: python ...` failed with "Executable not found"
- **Fix:** Changed all local hook entries from `python` to `python3`
- **Files modified:** `.pre-commit-config.yaml`
- **Commit:** 4d2db1b

**6. [Rule 1 - Bug] ruff SIM105/SIM117 violations blocking pre-commit**
- **Found during:** Task 3, first pre-commit run
- **Issue:** Pre-existing `try/except CancelledError: pass` and nested `with` patterns in 01-03 code
- **Fix:** Applied SIM105 → `contextlib.suppress()` in `main.py` + heartbeat test; SIM117 → combined `with` in FK tests
- **Files modified:** main.py, test_heartbeat_lost_sibling.py, test_parent_run_id_chain.py, test_sqlite_migrations.py
- **Commit:** 4d2db1b

**7. [Rule 1 - Bug] mypy type annotation gaps blocking pre-commit**
- **Found during:** Task 3, first pre-commit run
- **Issue:** Missing `Any`, bare `dict`, untyped `_orjson_dumps`, pyzmq asyncio stubs deficiency
- **Fix:** Added type annotations; `# type: ignore[misc,func-returns-value]` for pyzmq; `--no-warn-unused-ignores` for Pydantic default_factory pattern
- **Files modified:** structlog_setup.py, manifest/schema.py, bus/events.py, bus/cmd.py, config/schema.py
- **Commit:** 4d2db1b

**8. [Rule 1 - Bug] test_no_plain_keys.py triggered its own hook**
- **Found during:** Task 3, second commit attempt
- **Issue:** Test file contained literal `-----BEGIN PRIVATE KEY-----` in test content string
- **Fix:** Split the string across concatenation: `"-----" + "BEGIN PRIVATE KEY-----"`
- **Files modified:** `scripts/tests/test_no_plain_keys.py`
- **Commit:** 4d2db1b

## Known Stubs

None — all planned deliverables fully wired and functional.

## Threat Flags

No new unplanned network endpoints, auth paths, or trust boundary crossings introduced.
The `no-plain-keys` hook (T-04-03 mitigation) is fully wired via pre-commit.

## Self-Check: PASSED

All key files verified on disk. All commit hashes found in git log.
14 lint tests pass. 38 Python unit tests pass. `pre-commit run --all-files` exits 0.
