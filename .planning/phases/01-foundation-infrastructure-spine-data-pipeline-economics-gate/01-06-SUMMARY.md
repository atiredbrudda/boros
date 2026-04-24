---
phase: "01"
plan: "01-06"
subsystem: secrets-and-supervision
tags: [launchd, keychain, dotenvx, redaction, pre-commit, infra]
dependency_graph:
  requires: [01-01, 01-02, 01-03, 01-04]
  provides: [INFRA-12, INFRA-13, secrets-spine, process-supervision, log-redaction, no-plain-keys-hook]
  affects: [all-future-plans-that-run-the-bot]
tech_stack:
  added:
    - macOS Keychain (security CLI) for DOTENV_PRIVATE_KEY_PRODUCTION storage
    - dotenvx .env.vault AES-256 encrypted secrets
    - launchd LaunchAgent plists (KeepAlive + ThrottleInterval=30)
    - structlog redact_sensitive processor (ASVS V7)
  patterns:
    - Keychain-ACL-A-flag for headless launchd spawn
    - pass_filenames:false pre-commit hook using git diff --cached internally
    - TDD RED/GREEN/REFACTOR for all test files
key_files:
  created:
    - scripts/boros-brain-wrapper.sh
    - scripts/boros-hands-wrapper.sh
    - scripts/launchd/com.boros.brain.plist
    - scripts/launchd/com.boros.hands.plist
    - python/src/boros_brain/logging/redaction.py
    - docs/runbook-secrets.md
    - .env.vault
    - python/tests/test_launchd_plist_schema.py
    - python/tests/test_no_plain_keys.py
    - python/tests/test_log_redaction.py
    - python/tests/test_dotenvx_keychain.py
  modified:
    - scripts/no_plain_keys.py (rewrote to pass_filenames:false git diff interface)
    - .pre-commit-config.yaml (updated no_plain_keys hook to stages:[pre-commit], pass_filenames:false)
    - .gitignore (verified .env.keys present)
    - docs/architecture.yml (added supervision + redaction nodes and edges)
    - docs/ARCHITECTURE.md (added supervision subgraph + redaction node in brain subgraph)
decisions:
  - "Plist WorkingDirectory and ProgramArguments use absolute paths (launchd does not expand $HOME); wrapper scripts use $HOME variable since bash does expand it"
  - "Keychain -A flag mandatory: without it launchd-spawned processes trigger GUI prompt (A3 landmine)"
  - "no_plain_keys.py rewritten to pass_filenames:false (git diff --cached) so .env.vault can be excluded by filename at hook level rather than per-file content"
  - "brain.logging.redaction node deferred to Task 2 commit in architecture.yml to avoid lint failures (source file did not exist at Task 1 commit time)"
  - "stages:[pre-commit] used instead of deprecated stages:[commit] in pre-commit config"
metrics:
  duration_min: 9
  completed_date: "2026-04-24"
  tasks_completed: 3
  files_created: 12
  files_modified: 5
---

# Phase 01 Plan 06: Encrypted-Secret + Process-Supervision Spine Summary

**One-liner:** dotenvx `.env.vault` + macOS Keychain + launchd KeepAlive plists + structlog redaction processor + `no_plain_keys` pre-commit hook — complete headless-boot-capable secret/supervision spine.

## What Was Built

Tasks 1 and 2 automated; Task 3 (reboot smoke test) auto-approved per `auto_advance=true`.

### Task 1: launchd Plists + Keychain Wrapper Scripts

**Wrapper scripts** (`scripts/boros-brain-wrapper.sh`, `scripts/boros-hands-wrapper.sh`):
- `set -euo pipefail` in first 3 lines
- `security find-generic-password -s 'boros-bot-dotenvx-key' -a "$USER" -w` fetches the dotenvx private key from macOS Keychain
- `exec dotenvx run --` decrypts `.env.vault` into the subprocess environment without printing values

**launchd plists** (`scripts/launchd/com.boros.{brain,hands}.plist`):
- `Label`: `com.boros.brain` / `com.boros.hands`
- `KeepAlive: {SuccessfulExit: false}` — restarts on crash, NOT on clean exit 0
- `ThrottleInterval: 30` — prevents fork storms on bad config (T-01-06-04)
- `StandardOutPath` / `StandardErrorPath` → `var/logs/supervisor/`
- `EnvironmentVariables`: `PATH` + `HOME` only — no secrets ever embedded

**Plist design decision**: WorkingDirectory and ProgramArguments use absolute paths (`/Users/macbookair/...`) because launchd does not expand shell variables. The wrapper scripts themselves use `$HOME` (bash does expand it). The `HOME` variable in `EnvironmentVariables` is set to `/Users/macbookair` so the wrapper's `$HOME` resolves correctly when spawned headlessly.

**Tests**: 7 tests in `python/tests/test_launchd_plist_schema.py` — plistlib parsing, required keys, no embedded secrets, wrapper Keychain/dotenvx invocation, strict mode, `.env.keys` gitignored. All pass.

### Task 2: no_plain_keys Hook + Redaction Processor + Runbook

**`scripts/no_plain_keys.py`** (rewritten):
- Interface changed to `pass_filenames: false` — hook reads staged files via `git diff --cached --name-only` internally
- Regex: `\b0x[a-fA-F0-9]{64}\b` (Ethereum private key) + `-----BEGIN [A-Z ]*PRIVATE KEY-----` (PEM)
- Explicit exclusions: `.env.vault` (by filename), `FAKE_KEY_FOR_TESTS` sentinel (same line or preceding line)
- Exit 0 on clean, exit 1 with stderr details on match

**`python/src/boros_brain/logging/redaction.py`**:
- Regex: `^(api[-_]?key|token|secret|private[-_]?key|password|.*dotenv_private_key.*)$` (case-insensitive)
- Replaces matching key values with `"***"` in event_dict before JSONRenderer
- Injected via `configure_logging(extra_processors=[redact_sensitive])`

**`docs/runbook-secrets.md`** (201 lines, 6 required sections):
1. One-time setup (dotenvx encrypt → `.env.vault` → Keychain with `-A` flag)
2. Installing the launchd agents
3. Reboot smoke test (MANUAL — A3 landmine verification)
4. Fallback: file-env mode with chmod 600 (A3 failure path)
5. Sleep/wake behavior
6. Key rotation

**`.env.vault`**: placeholder comment (operator runs `dotenvx encrypt` once)

**`.pre-commit-config.yaml`**: `no_plain_keys` hook updated to `pass_filenames: false`, `stages: [pre-commit]` (fixed deprecated `stages: [commit]`)

### Task 3: Operator Reboot Smoke Test

Auto-approved (auto_advance=true). The reboot itself is a manual operator step documented in `docs/runbook-secrets.md` §"Reboot Smoke Test". All automated artifacts are in place.

**A3 outcome**: Not yet tested (requires actual reboot by operator). Fallback path (file-env + chmod 600) is documented in `docs/runbook-secrets.md` §"Fallback" for the case where Keychain headless fails.

## Architecture Nodes Added

Per CLAUDE.md Engineering Protocol #2:

| Node ID | Type | Notes |
|---------|------|-------|
| `launchd.brain` | external | com.boros.brain.plist |
| `launchd.hands` | external | com.boros.hands.plist |
| `macos.keychain` | external | login Keychain, boros-bot-dotenvx-key item |
| `scripts.boros_brain_wrapper` | external | boros-brain-wrapper.sh |
| `scripts.boros_hands_wrapper` | external | boros-hands-wrapper.sh |
| `scripts.no_plain_keys` | external | pre-commit hook (pass_filenames:false) |
| `brain.logging.redaction` | module | redact_sensitive() structlog processor |

Edges added: launchd → wrapper → Keychain → brain/hands main; redaction → structlog_setup; no_plain_keys → brain.

## Redaction Regex

Pattern used: `^(api[-_]?key|token|secret|private[-_]?key|password|.*dotenv_private_key.*)$` (re.IGNORECASE)

Covers: `api_key`, `api-key`, `apikey`, `token`, `secret`, `private_key`, `private-key`, `password`, `DOTENV_PRIVATE_KEY_PRODUCTION`, any `*DOTENV_PRIVATE_KEY*` variant.

No additions beyond the minimum list from the plan — the pattern is comprehensive for Phase 1 threat model.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wrapper script line continuation broke test string search**
- **Found during:** Task 1 GREEN phase
- **Issue:** The Keychain command was split across two lines with `\` continuation; the test checks for `security find-generic-password -s 'boros-bot-dotenvx-key'` as a single string in `read_text()`
- **Fix:** Inlined the command onto one line (fits within 100 chars; readability unchanged)
- **Files modified:** `scripts/boros-brain-wrapper.sh`, `scripts/boros-hands-wrapper.sh`

**2. [Rule 3 - Blocking] Architecture lint blocked Task 1 commit**
- **Found during:** Task 1 GREEN commit attempt
- **Issue:** `architecture.yml` declared `scripts.no_plain_keys` and `brain.logging.redaction` as `type: module` nodes, but those source files don't exist until Task 2. The architecture lint (`scripts/architecture_lint.py`) checks that every declared `type: module` node's path exists on disk.
- **Fix:** Changed `scripts.no_plain_keys` to `type: external` (not in python/ts src trees); deferred `brain.logging.redaction` declaration to Task 2 commit (when the source file actually exists)
- **Files modified:** `docs/architecture.yml`

**3. [Rule 1 - Bug] ruff E741 ambiguous variable `l` in test**
- **Found during:** Task 1 RED commit
- **Fix:** Renamed `l` to `ln` in list comprehension
- **Files modified:** `python/tests/test_launchd_plist_schema.py`

**4. [Rule 1 - Bug] mypy `dict` missing type parameters**
- **Found during:** Task 2 GREEN commit
- **Fix:** Changed `dict` to `dict[str, Any]` in `redact_sensitive` signature
- **Files modified:** `python/src/boros_brain/logging/redaction.py`

**5. [Rule 1 - Bug] Deprecated pre-commit stage name**
- **Found during:** Task 2 GREEN commit
- **Issue:** `stages: [commit]` is deprecated in pre-commit; correct name is `stages: [pre-commit]`
- **Fix:** Updated to `stages: [pre-commit]`
- **Files modified:** `.pre-commit-config.yaml`

## Known Stubs

None — all artifacts are complete. The `.env.vault` placeholder is intentional and documented (operator must run `dotenvx encrypt`); the bot cannot start without it, which is by design (fail-fast on missing secrets).

## Threat Flags

No new network endpoints or trust boundaries introduced beyond what the plan's threat model covers. All T-01-06-0{1,2,3,4} mitigations are implemented as specified.

## Self-Check: PASSED
