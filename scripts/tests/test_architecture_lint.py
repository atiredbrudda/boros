"""Tests for scripts/architecture_lint.py (INFRA-09 / PROTO-02).

Test matrix:
  Test 1 — clean fixture: declared module + function present → exit 0
  Test 2 — code drift: undeclared public function in source → exit 1, message mentions fn
  Test 3 — yml drift: architecture.yml declares missing path → exit 1, message mentions node
  Test 4 — real tree: actual repo passes with defaults → exit 0
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "architecture_lint.py"
FIXTURE_ROOT = REPO_ROOT / "scripts" / "tests" / "fixtures"


def _run_lint(extra_args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINT_SCRIPT)] + extra_args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class TestArchitectureLint:
    def test_clean_tree_passes(self) -> None:
        """Test 1: arch_clean fixture — declared module + matching source → exit 0."""
        clean_dir = FIXTURE_ROOT / "arch_clean"
        result = _run_lint(
            [
                "--yml", str(clean_dir / "architecture.yml"),
                "--src", str(clean_dir),
                "--ts-src", str(clean_dir),  # no TS in fixture; empty scan is OK
            ]
        )
        assert result.returncode == 0, (
            f"Expected exit 0 on clean fixture. stderr:\n{result.stderr}"
        )

    def test_drift_in_code_fails(self) -> None:
        """Test 2: arch_drift fixture — undeclared public function → exit 1."""
        drift_dir = FIXTURE_ROOT / "arch_drift"
        result = _run_lint(
            [
                "--yml", str(drift_dir / "architecture.yml"),
                "--src", str(drift_dir),
                "--ts-src", str(drift_dir),
            ]
        )
        assert result.returncode == 1, (
            f"Expected exit 1 on drift fixture. stderr:\n{result.stderr}"
        )
        assert "undeclared_fn" in result.stderr or "test.a" in result.stderr, (
            f"Expected violation message to mention undeclared_fn. stderr:\n{result.stderr}"
        )

    def test_drift_in_yml_fails(self) -> None:
        """Test 3: architecture.yml declares node whose path does not exist → exit 1."""
        import tempfile, yaml

        bad_yml = {
            "version": 1,
            "nodes": [
                {
                    "id": "missing_module",
                    "type": "module",
                    "process": "brain",
                    "path": "nonexistent.py",
                    "public_functions": [],
                }
            ],
            "edges": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            yml_path = tmp_path / "architecture.yml"
            yml_path.write_text(yaml.dump(bad_yml))
            result = _run_lint(
                [
                    "--yml", str(yml_path),
                    "--src", str(tmp_path),
                    "--ts-src", str(tmp_path),
                ]
            )
        assert result.returncode == 1, (
            f"Expected exit 1 for missing path. stderr:\n{result.stderr}"
        )
        assert "missing_module" in result.stderr or "nonexistent.py" in result.stderr, (
            f"Expected message to mention missing_module or nonexistent.py. stderr:\n{result.stderr}"
        )

    def test_real_tree_clean(self) -> None:
        """Test 4: run lint against actual repo root → exits 0 (Task-1 manifest matches codebase)."""
        result = subprocess.run(
            [sys.executable, str(LINT_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, (
            f"Real tree lint failed. This means architecture.yml is out of sync with source.\n"
            f"stderr:\n{result.stderr}"
        )
