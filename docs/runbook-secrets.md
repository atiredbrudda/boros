# Runbook: Secrets, Keychain, and Process Supervision

This runbook documents the one-time operator setup for encrypted secrets
(dotenvx + macOS Keychain) and the launchd LaunchAgent installation for
headless bot operation. Follow every step in order the first time. Reference
the A3 fallback section if the post-reboot smoke test fails.

## One-time Setup

### 1. Generate `.env.vault` from plaintext env

Create a `.env` file (gitignored) with all plaintext secrets:

```bash
# .env (gitignored)
AGENT_WALLET_PRIVATE_KEY=0x...       # 64-hex agent hot wallet key
DOTENV_PRIVATE_KEY_PRODUCTION=       # left blank; filled by dotenvx encrypt
```

Encrypt it:

```bash
cd ~/Documents/project/test/rerun7/boros
dotenvx encrypt
# → writes .env.vault (safe to commit) and .env.keys (gitignored — contains the KEK)
git add .env.vault
git commit -m "chore: update encrypted .env.vault"
```

`.env.keys` is gitignored and must never be committed.
`.env.vault` is AES-256 encrypted and safe to commit.

### 2. Store the private key in macOS Keychain

Run this ONCE interactively (operator present at keyboard). The `-A` flag
grants access to all applications under the current UID — required so
launchd-spawned processes can read the item without a GUI prompt.

```bash
security add-generic-password \
    -A \
    -s 'boros-bot-dotenvx-key' \
    -a "$USER" \
    -w "$(grep DOTENV_PRIVATE_KEY_PRODUCTION .env.keys | cut -d= -f2 | tr -d '"')"
```

**Why `-A`?** Without it, macOS restricts the Keychain item to the creating
application (Terminal). launchd-spawned wrapper scripts are a different
"application" and would trigger a GUI prompt or silent failure. The `-A`
flag (allow all) is the standard solution for headless automation on a
personal laptop. Threat model: someone with local disk access already has
a worse attack surface than the Keychain item.

Approve the Keychain GUI prompt when it appears (once only).

## Installing the launchd Agents

Copy the plists to `~/Library/LaunchAgents/` and bootstrap them:

```bash
cp scripts/launchd/com.boros.brain.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.boros.hands.plist ~/Library/LaunchAgents/

launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.boros.brain.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.boros.hands.plist

launchctl enable gui/$(id -u)/com.boros.brain
launchctl enable gui/$(id -u)/com.boros.hands

# Start immediately without waiting for next boot:
launchctl kickstart -k gui/$(id -u)/com.boros.brain
launchctl kickstart -k gui/$(id -u)/com.boros.hands
```

To stop an agent without unloading it:

```bash
launchctl bootout gui/$(id -u)/com.boros.brain
# Then re-bootstrap when ready to restart:
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.boros.brain.plist
```

## Reboot Smoke Test (MANUAL — A3 Landmine Verification)

**MANDATORY** after first install. This verifies that launchd + Keychain
work headlessly after a cold reboot — a macOS-version-specific issue
documented as the A3 landmine in the project planning context.

1. **REBOOT** the MacBook.
2. Log in to the operator account.
3. Wait 60 seconds for launchd to start both agents.
4. Open Terminal and run:

```bash
launchctl list | grep boros
```

**Expected output**: both `com.boros.brain` and `com.boros.hands` present.
Column 2 (last exit code) should be `0` or `-` (currently running).

If column 2 shows `78` (`EX_CONFIG`): launchd has permanently disabled the
restart loop. Check `var/logs/supervisor/*.stderr.log` for the cause. Exit
code 78 means the bot detected a fatal config error and deliberately stopped
the loop.

5. Verify the first log line is a RUN_MANIFEST:

```bash
ls -t var/logs/$(date +%F)/*.brain.log.jsonl | head -1 | xargs head -1 | jq
```

**Expected**: JSON with `"event": "RUN_MANIFEST"` (or `manifest_version` field),
plus `run_id` (ULID), `git_sha`, `strategy_version`, and the full knob tree.

6. Same for hands:

```bash
ls -t var/logs/$(date +%F)/*.hands.log.jsonl | head -1 | xargs head -1 | jq
```

If a Keychain GUI prompt appeared during boot — this is the **A3 failure
mode**. Follow the Fallback section below.

## Fallback: File-env Mode with chmod 600

If the Keychain headless approach fails (A3 landmine triggered), use the
file-env fallback. This is **less secure** (plaintext key on disk) but
guarantees headless operation.

```bash
mkdir -p ~/.boros
echo "DOTENV_PRIVATE_KEY_PRODUCTION=<value from .env.keys>" > ~/.boros/env.key
chmod 600 ~/.boros/env.key
```

Then modify `scripts/boros-brain-wrapper.sh` to source the file instead:

```bash
#!/bin/bash
set -euo pipefail
cd "$HOME/Documents/project/test/rerun7/boros"
# Fallback: source from chmod-600 file instead of Keychain
# shellcheck disable=SC1091
source "$HOME/.boros/env.key"
exec dotenvx run -- uv run --directory python python -m boros_brain.main --mode=live
```

Do the same for `boros-hands-wrapper.sh`. Re-run the reboot smoke test.

Document in `docs/override-log.md` that the fallback was activated, with
a note on the macOS version and why Keychain headless failed.

## Sleep/Wake Behavior

Running bot processes retain their decrypted environment (`DOTENV_PRIVATE_KEY_PRODUCTION`
is already in memory). A crash *during* a sleep/wake cycle is safe — the
process already held the key. However, a crash that triggers launchd restart
during a locked-Keychain window (e.g., screen-saver locks the keychain) will
fail silently. launchd logs the wrapper's stderr in `var/logs/supervisor/`.

**Recommendation**: Keep the laptop logged in and screen-saver off during
live operation. The $100 deployment does not justify more complex solutions.

## Key Rotation

To rotate the dotenvx private key:

```bash
# 1. Remove old Keychain item
security delete-generic-password -s 'boros-bot-dotenvx-key' -a "$USER"

# 2. Regenerate .env.vault with a new key
dotenvx encrypt --force  # creates a new .env.keys

# 3. Re-add to Keychain with -A flag
security add-generic-password -A \
    -s 'boros-bot-dotenvx-key' \
    -a "$USER" \
    -w "$(grep DOTENV_PRIVATE_KEY_PRODUCTION .env.keys | cut -d= -f2 | tr -d '"')"

# 4. Commit the updated .env.vault
git add .env.vault && git commit -m "chore: rotate dotenvx encryption key"
```

## Do NOT

- **Commit `.env.keys`** — it contains the plaintext KEK for `.env.vault`.
  The `no_plain_keys.py` pre-commit hook blocks obvious key patterns, but
  `.env.keys` itself is blocked by `.gitignore`.

- **Log the decrypted environment** — `structlog_setup.py` includes the
  `redact_sensitive` processor that replaces values of keys matching
  `api_key`, `token`, `secret`, `private_key`, `password`, and
  `DOTENV_PRIVATE_KEY*` with `***` before JSON render.

- **Use `dotenvx decrypt` in production wrappers** — decrypt is for debugging
  only. The production wrapper uses `dotenvx run --` which decrypts into the
  subprocess environment without printing the values.

- **Skip the reboot smoke test** — the A3 landmine is real and macOS-version-specific.
  The automated tests cannot cover it. Always verify after initial install.
