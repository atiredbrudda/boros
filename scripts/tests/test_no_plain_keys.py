"""Tests for scripts/no_plain_keys.py (security, T-04-03).

Test matrix:
  Test A — clean content → exit 0
  Test B — 64-hex private key pattern → exit 1
  Test C — all-zero test key (0x000...000) → exit 0 (explicitly allowed synthetic key)
  Test D — PEM private key header → exit 1
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "no_plain_keys.py"


def _run(content: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        tmp_path = f.name
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), tmp_path],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    Path(tmp_path).unlink(missing_ok=True)
    return result


class TestNoPlainKeys:
    def test_clean_content_passes(self) -> None:
        """Test A: content with no keys → exit 0."""
        result = _run("# Normal config file\nsome_setting = 42\n")
        assert result.returncode == 0, (
            f"Expected exit 0 for clean content. stderr:\n{result.stderr}"
        )

    def test_eth_private_key_fails(self) -> None:
        """Test B: 64-hex key following 0x → exit 1."""
        # A real-looking (but fake) Ethereum private key
        fake_key = "0x" + "a1b2c3d4" * 8  # 64 hex chars
        result = _run(f"# config\nPRIVATE_KEY={fake_key}\n")
        assert result.returncode == 1, (
            f"Expected exit 1 for 64-hex key. stderr:\n{result.stderr}"
        )

    def test_all_zero_key_passes(self) -> None:
        """Test C: all-zero synthetic test key is explicitly allowed → exit 0."""
        zero_key = "0x" + "0" * 64
        result = _run(f"# test config — synthetic key\nFAKE_KEY = '{zero_key}'\n")
        assert result.returncode == 0, (
            f"Expected exit 0 for all-zero synthetic key. stderr:\n{result.stderr}"
        )

    def test_pem_private_key_fails(self) -> None:
        """Test D: PEM private key header → exit 1."""
        # Split string to avoid triggering the no-plain-keys hook on this test file itself.
        pem_header = "-----" + "BEGIN PRIVATE KEY-----"
        pem_content = f"{pem_header}\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----\n"
        result = _run(pem_content)
        assert result.returncode == 1, (
            f"Expected exit 1 for PEM private key. stderr:\n{result.stderr}"
        )
