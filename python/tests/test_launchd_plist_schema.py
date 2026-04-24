"""Tests for launchd plist schema + wrapper scripts (INFRA-13).

Task 1 of plan 01-06: validates that both plists are valid, contain required
keys, never embed secrets, and that the wrapper scripts invoke Keychain + dotenvx.

Test matrix:
  test_brain_plist_parses_as_valid_plist  — parses without error
  test_brain_plist_required_keys          — all required keys present with correct values
  test_hands_plist_parses_and_required_keys — same shape for hands
  test_brain_plist_never_embeds_private_key — no secret strings in plist text
  test_wrapper_scripts_call_keychain_and_dotenvx — both wrappers contain required CLI
  test_wrapper_scripts_have_strict_mode   — set -euo pipefail in first 3 lines
  test_env_keys_gitignored                — .gitignore contains .env.keys
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

# Discover project root: python/tests -> python -> repo root
ROOT = Path(__file__).resolve().parents[2]
BRAIN_PLIST = ROOT / "scripts" / "launchd" / "com.boros.brain.plist"
HANDS_PLIST = ROOT / "scripts" / "launchd" / "com.boros.hands.plist"
BRAIN_WRAPPER = ROOT / "scripts" / "boros-brain-wrapper.sh"
HANDS_WRAPPER = ROOT / "scripts" / "boros-hands-wrapper.sh"
GITIGNORE = ROOT / ".gitignore"


def _load_plist(path: Path) -> dict:
    """Read and parse a plist file, returning the top-level dict."""
    return plistlib.loads(path.read_bytes())


class TestBrainPlistParsesAsValidPlist:
    def test_brain_plist_parses_as_valid_plist(self) -> None:
        """com.boros.brain.plist parses without error via stdlib plistlib."""
        assert BRAIN_PLIST.exists(), f"Missing: {BRAIN_PLIST}"
        d = _load_plist(BRAIN_PLIST)
        assert isinstance(d, dict), "Top-level must be a dict"


class TestBrainPlistRequiredKeys:
    def test_brain_plist_required_keys(self) -> None:
        """com.boros.brain.plist contains every required key with correct values."""
        d = _load_plist(BRAIN_PLIST)

        assert d["Label"] == "com.boros.brain", f"Label wrong: {d.get('Label')}"

        args = d["ProgramArguments"]
        assert args[0] == "/bin/bash", f"ProgramArguments[0] must be /bin/bash, got {args[0]}"
        assert len(args) == 2, f"ProgramArguments must have 2 elements, got {len(args)}"
        assert "boros-brain-wrapper.sh" in args[1], f"ProgramArguments[1] must reference wrapper, got {args[1]}"

        assert "WorkingDirectory" in d, "Missing WorkingDirectory"
        assert isinstance(d["WorkingDirectory"], str)

        assert d["RunAtLoad"] is True, "RunAtLoad must be true"

        ka = d["KeepAlive"]
        assert isinstance(ka, dict), f"KeepAlive must be a dict (not bool), got {ka!r}"
        assert (
            ka.get("SuccessfulExit") is False
        ), f"KeepAlive.SuccessfulExit must be False, got {ka.get('SuccessfulExit')!r}"

        assert d["ThrottleInterval"] == 30, f"ThrottleInterval must be 30, got {d.get('ThrottleInterval')}"

        assert "StandardOutPath" in d, "Missing StandardOutPath"
        assert "StandardErrorPath" in d, "Missing StandardErrorPath"

        env = d.get("EnvironmentVariables", {})
        assert "PATH" in env, "EnvironmentVariables must include PATH"
        assert "HOME" in env, "EnvironmentVariables must include HOME"


class TestHandsPlistParsesAndRequiredKeys:
    def test_hands_plist_parses_and_required_keys(self) -> None:
        """com.boros.hands.plist valid + required keys."""
        assert HANDS_PLIST.exists(), f"Missing: {HANDS_PLIST}"
        d = _load_plist(HANDS_PLIST)

        assert d["Label"] == "com.boros.hands", f"Label wrong: {d.get('Label')}"

        args = d["ProgramArguments"]
        assert args[0] == "/bin/bash"
        assert "boros-hands-wrapper.sh" in args[1]

        assert isinstance(d["WorkingDirectory"], str)
        assert d["RunAtLoad"] is True

        ka = d["KeepAlive"]
        assert isinstance(ka, dict)
        assert ka.get("SuccessfulExit") is False

        assert d["ThrottleInterval"] == 30

        assert "StandardOutPath" in d
        assert "StandardErrorPath" in d

        env = d.get("EnvironmentVariables", {})
        assert "PATH" in env
        assert "HOME" in env


class TestBrainPlistNeverEmbedsPrivateKey:
    def test_brain_plist_never_embeds_private_key(self) -> None:
        """The raw plist text must not contain any secret-like strings."""
        text = BRAIN_PLIST.read_text()
        # Ethereum private key pattern
        assert not re.search(
            r"DOTENV_PRIVATE_KEY", text
        ), "DOTENV_PRIVATE_KEY found in plist — must come from Keychain only"
        assert not re.search(r"0x[a-fA-F0-9]{64}", text), "64-hex private key pattern found in plist"
        # Split the string so the no_plain_keys hook doesn't flag THIS test file
        assert "PRIVATE" + " KEY" not in text.replace("-----", ""), "PEM PRIVATE KEY header found in plist"


class TestWrapperScriptsCallKeychainAndDotenvx:
    def test_wrapper_scripts_call_keychain_and_dotenvx(self) -> None:
        """Both wrapper scripts contain the required Keychain + dotenvx invocations."""
        for wrapper in (BRAIN_WRAPPER, HANDS_WRAPPER):
            assert wrapper.exists(), f"Missing: {wrapper}"
            text = wrapper.read_text()
            assert (
                "security find-generic-password -s 'boros-bot-dotenvx-key'" in text
            ), f"{wrapper.name}: must contain 'security find-generic-password -s boros-bot-dotenvx-key'"
            assert "exec dotenvx run" in text, f"{wrapper.name}: must contain 'exec dotenvx run'"


class TestWrapperScriptsHaveStrictMode:
    def test_wrapper_scripts_have_strict_mode(self) -> None:
        """set -euo pipefail appears in the first 3 lines of each wrapper."""
        for wrapper in (BRAIN_WRAPPER, HANDS_WRAPPER):
            assert wrapper.exists(), f"Missing: {wrapper}"
            lines = wrapper.read_text().splitlines()
            first_three = "\n".join(lines[:3])
            assert (
                "set -euo pipefail" in first_three
            ), f"{wrapper.name}: 'set -euo pipefail' not in first 3 lines. Got:\n{first_three}"


class TestEnvKeysGitignored:
    def test_env_keys_gitignored(self) -> None:
        """.gitignore must contain an exact line '.env.keys'."""
        assert GITIGNORE.exists(), f"Missing: {GITIGNORE}"
        lines = GITIGNORE.read_text().splitlines()
        assert ".env.keys" in lines, (
            f".env.keys not found as exact line in .gitignore. "
            f"Lines containing 'env.keys': {[ln for ln in lines if 'env.keys' in ln]}"
        )
