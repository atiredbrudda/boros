#!/usr/bin/env python3
"""Plain-key lint (security, PROTO-05-adjacent / T-04-03).

Greps staged files for patterns matching `0x<64 hex chars>` (Ethereum private key) and
PEM private key headers (BEGIN PRIVATE KEY / BEGIN EC PRIVATE KEY / BEGIN RSA PRIVATE KEY).

Exceptions: all-zero synthetic test keys (`0x` + 64 × `0`) are allowed so test fixtures
using `FAKE_KEY = "0x" + "0"*64` don't trigger.

Exit 0 on clean, exit 1 with violation details on detection.

Usage (from pre-commit hook — receives individual file paths):
  python scripts/no_plain_keys.py <file> [<file> ...]
"""
import argparse
import re
import sys
from pathlib import Path

# Matches 0x followed by exactly 64 hex chars (Ethereum private key length)
ETH_KEY_RE = re.compile(r"\b0x[a-fA-F0-9]{64}\b")
# All-zero synthetic key pattern (explicitly allowed for test fixtures)
ALL_ZERO_RE = re.compile(r"\b0x0{64}\b")
# PEM private key headers — pattern split to avoid self-triggering on lint script itself
_PEM_PREFIX = "-----" + "BEGIN"
PEM_RE = re.compile(_PEM_PREFIX + r" (?:RSA |EC )?PRIVATE KEY-----")


def scan_file(path: Path) -> list[str]:
    """Scan a single file and return a list of violation strings."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (PermissionError, OSError):
        return []

    violations: list[str] = []
    lines = text.splitlines()

    for m in ETH_KEY_RE.finditer(text):
        # Skip all-zero test keys
        if ALL_ZERO_RE.match(m.group(0)):
            continue
        # Calculate line number
        line_no = text[: m.start()].count("\n") + 1
        violations.append(
            f"{path}:{line_no}: 64-hex private-key pattern detected — "
            "use dotenvx encrypted env or macOS Keychain (see INFRA-12)"
        )

    if PEM_RE.search(text):
        violations.append(
            f"{path}: PEM private key header detected — "
            "private keys must never be committed; use macOS Keychain (see INFRA-12)"
        )

    return violations


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Plain-key lint — blocks Ethereum private keys and PEM headers from commits"
    )
    ap.add_argument("paths", nargs="*", type=Path, help="Files to scan")
    args = ap.parse_args()

    all_violations: list[str] = []
    for p in args.paths:
        if p.is_file():
            all_violations.extend(scan_file(p))

    if all_violations:
        print("\n".join(all_violations), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
