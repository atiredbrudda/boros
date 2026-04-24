#!/usr/bin/env python3
"""Pre-commit hook: reject staged files containing plaintext private keys.

Rejects: 0x<64 hex>, BEGIN [X] PRIVATE KEY blocks.
Ignores: .env.vault (dotenvx ciphertext has high-entropy strings);
         lines where FAKE_KEY_FOR_TESTS sentinel appears on same or preceding line.

Called with pass_filenames: false — reads staged file list from git itself.

Exit 0 on clean, 1 on match.
"""
import re
import subprocess
import sys
from pathlib import Path

HEX_KEY = re.compile(r"\b0x[a-fA-F0-9]{64}\b")
# Split string so this script doesn't flag itself
_PEM_PREFIX = "-----" + "BEGIN"
PEM_KEY = re.compile(_PEM_PREFIX + r" [A-Z ]*PRIVATE KEY-----")


def staged_files() -> list[Path]:
    """Return list of staged file paths via git diff --cached --name-only."""
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        text=True,
    )
    return [Path(p) for p in out.splitlines() if p.strip()]


def scan(path: Path) -> list[tuple[int, str]]:
    """Scan a single file for private key patterns; return (lineno, line) hits."""
    # Explicitly skip .env.vault — dotenvx ciphertext is intentionally high-entropy
    if path.name == ".env.vault":
        return []
    if not path.exists() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    hits: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        if HEX_KEY.search(line) or PEM_KEY.search(line):
            # Allowlist: FAKE_KEY_FOR_TESTS sentinel on same line
            if "FAKE_KEY_FOR_TESTS" in line:
                continue
            # Allowlist: FAKE_KEY_FOR_TESTS sentinel on immediately preceding line
            prev = lines[i - 2] if i >= 2 else ""
            if "FAKE_KEY_FOR_TESTS" in prev:
                continue
            hits.append((i, line))
    return hits


def main() -> int:
    """Entry point for pre-commit hook (pass_filenames: false)."""
    fail = 0
    for p in staged_files():
        hits = scan(p)
        for lineno, line in hits:
            print(f"[no_plain_keys] {p}:{lineno}: {line[:80]}", file=sys.stderr)
            fail = 1
    return fail


if __name__ == "__main__":
    sys.exit(main())
