"""Tests for scripts/wiki_cite_lint.py (INFRA-11 / PROTO-03).

Test matrix:
  Test 5 — prose cite: [[wiki-link]] outside code blocks → exit 0
  Test 6 — no cite: zero [[...]] references → exit 1, message names the file
  Test 7 — code-block only cite: [[link]] only inside ``` ... ``` → exit 1
  Test 8 — unrelated directory: markdown NOT in research/decisions/postmortem → exit 0
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "wiki_cite_lint.py"
FIXTURE_ROOT = REPO_ROOT / "scripts" / "tests" / "fixtures"


def _run_lint(paths: list[str | Path], extra_flags: list[str] | None = None) -> subprocess.CompletedProcess:
    args = [sys.executable, str(LINT_SCRIPT)]
    if extra_flags:
        args += extra_flags
    args += [str(p) for p in paths]
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class TestWikiCiteLint:
    def test_prose_cite_passes(self) -> None:
        """Test 5: markdown with [[wiki-link]] in prose → exit 0."""
        md = FIXTURE_ROOT / "wiki_cite_pass" / "research" / "dummy.md"
        result = _run_lint([md])
        assert result.returncode == 0, (
            f"Expected exit 0 for file with prose wiki-link. stderr:\n{result.stderr}"
        )

    def test_no_cite_fails(self) -> None:
        """Test 6: markdown with zero [[...]] outside code → exit 1, message names the file."""
        md = FIXTURE_ROOT / "wiki_cite_fail" / "research" / "dummy.md"
        result = _run_lint([md])
        assert result.returncode == 1, (
            f"Expected exit 1 for file with no wiki citation. stderr:\n{result.stderr}"
        )
        assert "dummy.md" in result.stderr, (
            f"Expected file name in violation message. stderr:\n{result.stderr}"
        )

    def test_code_block_only_cite_fails(self) -> None:
        """Test 7: [[link]] only inside fenced code block → lint detects and exits 1.

        The fixture file (wiki_cite_fail/research/dummy.md) contains a [[link]] inside
        a fenced code block but no prose link — the strip_code_blocks function should
        remove it before searching, so the file still fails.
        """
        md = FIXTURE_ROOT / "wiki_cite_fail" / "research" / "dummy.md"
        # Read the file to confirm it has a code-block link but no prose link
        text = md.read_text()
        assert "[[" in text, "Fixture should contain at least one [[ to exercise the code-block stripping"
        result = _run_lint([md])
        assert result.returncode == 1, (
            f"Expected exit 1: [[link]] inside code block only should not satisfy the lint.\n"
            f"stderr:\n{result.stderr}"
        )

    def test_ignores_unrelated_directories(self) -> None:
        """Test 8: markdown in docs/ or .planning/ (not research/decisions/postmortem) → exit 0."""
        # docs/ARCHITECTURE.md is a tracked file NOT under the policed paths
        docs_md = REPO_ROOT / "docs" / "ARCHITECTURE.md"
        result = _run_lint([docs_md])
        assert result.returncode == 0, (
            f"Expected exit 0 for markdown NOT under research/decisions/postmortem.\n"
            f"stderr:\n{result.stderr}"
        )
