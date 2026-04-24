"""Tests for scripts/no_plain_keys.py pre-commit hook (INFRA-12 / T-01-06-01).

The hook in plan 01-06 uses git diff --cached --name-only internally
(pass_filenames: false mode). Tests create a temp git repo, stage files,
and invoke the hook via subprocess.

Test matrix:
  test_no_plain_keys_passes_on_empty_diff   — no staged files → exit 0
  test_no_plain_keys_fails_on_raw_hex_key   — 64-hex key pattern → exit 1
  test_no_plain_keys_fails_on_begin_private_key — PEM header → exit 1
  test_no_plain_keys_passes_on_zero_fake_key — FAKE_KEY_FOR_TESTS sentinel → exit 0
  test_no_plain_keys_ignores_env_vault      — .env.vault file → exit 0
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_SCRIPT = REPO_ROOT / "scripts" / "no_plain_keys.py"


def _git_init(tmp_path: Path) -> None:
    """Initialise a minimal git repo in tmp_path."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )


def _stage_file(tmp_path: Path, filename: str, content: str) -> None:
    """Write and stage a file in the tmp git repo."""
    (tmp_path / filename).write_text(content)
    subprocess.run(
        ["git", "add", filename],
        check=True,
        capture_output=True,
        cwd=str(tmp_path),
    )


def _run_hook(tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the no_plain_keys hook in the tmp git repo context."""
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )


class TestNoPlainKeysPasses:
    def test_no_plain_keys_passes_on_empty_diff(self, tmp_path: Path) -> None:
        """No staged files → exit 0."""
        _git_init(tmp_path)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, f"Expected exit 0 on empty diff. stderr:\n{result.stderr}"


class TestNoPlainKeysFails:
    def test_no_plain_keys_fails_on_raw_hex_key(self, tmp_path: Path) -> None:
        """Staged file containing 0x<64 hex> → exit 1."""
        _git_init(tmp_path)
        # Use a non-all-zero key (all-zero is the allowed test sentinel)
        fake_key = "0x" + "a1b2c3d4" * 8  # 64 non-zero hex chars
        _stage_file(tmp_path, "config.py", f'PRIVATE_KEY = "{fake_key}"\n')
        result = _run_hook(tmp_path)
        assert (
            result.returncode == 1
        ), f"Expected exit 1 for 64-hex key. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    def test_no_plain_keys_fails_on_begin_private_key(self, tmp_path: Path) -> None:
        """Staged file containing PEM private key header → exit 1."""
        _git_init(tmp_path)
        # Split the PEM header so no_plain_keys doesn't flag THIS test file
        pem_header = "-----" + "BEGIN EC PRIVATE KEY-----"
        _stage_file(tmp_path, "key.pem", f"{pem_header}\nMIIEvQ==\n-----END EC PRIVATE KEY-----\n")
        result = _run_hook(tmp_path)
        assert result.returncode == 1, f"Expected exit 1 for PEM header. stderr:\n{result.stderr}"


class TestNoPlainKeysPassesSentinel:
    def test_no_plain_keys_passes_on_zero_fake_key(self, tmp_path: Path) -> None:
        """All-zero test key used as FAKE_KEY_FOR_TESTS sentinel → exit 0."""
        _git_init(tmp_path)
        # Explicit test-sentinel pattern: FAKE_KEY_FOR_TESTS sentinel on same line
        zero_key = "0x" + "0" * 64
        _stage_file(
            tmp_path,
            "test_fixture.py",
            f'FAKE_KEY_FOR_TESTS = "{zero_key}"\n',
        )
        result = _run_hook(tmp_path)
        assert result.returncode == 0, f"Expected exit 0 for FAKE_KEY_FOR_TESTS sentinel. stderr:\n{result.stderr}"


class TestNoPlainKeysIgnoresEnvVault:
    def test_no_plain_keys_ignores_env_vault(self, tmp_path: Path) -> None:
        """.env.vault with base64/random-looking ciphertext → exit 0."""
        _git_init(tmp_path)
        # Simulate dotenvx-encrypted vault content (high-entropy base64)
        vault_content = (
            "# dotenvx encrypted vault\n"
            'DOTENV_VAULT_PRODUCTION="encrypted:abc123def456/+xyz=="\n'
            "# Safe to commit (AES-256 encrypted)\n"
        )
        _stage_file(tmp_path, ".env.vault", vault_content)
        result = _run_hook(tmp_path)
        assert result.returncode == 0, f"Expected exit 0 for .env.vault file. stderr:\n{result.stderr}"
