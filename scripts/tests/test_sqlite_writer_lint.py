"""Behavioral tests for scripts/sqlite_writer_lint.py (INFRA-03 / PROTO-02).

Two cases:
  1. Clean repo → lint exits 0
  2. Drift injected (`INSERT INTO decisions` in boros_brain.main) → lint exits 1
     and the violation message names both the table and the offending file.

We copy the full repo tree into a tmp workdir so the injected-drift test does not
pollute the real repo and so the lint's `--root` flag exercises its real path logic.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINT = ROOT / "scripts" / "sqlite_writer_lint.py"


def _copy_repo(dst: Path) -> None:
    """Copy only python/src + ts/src — enough for the lint to exercise its scanner."""
    ignore = shutil.ignore_patterns(
        ".venv",
        "node_modules",
        ".pnpm",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "state",
        "logs",
        "dist",
        "*.parquet",
    )
    (dst / "python" / "src").mkdir(parents=True, exist_ok=True)
    (dst / "ts" / "src").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        ROOT / "python" / "src", dst / "python" / "src", ignore=ignore, dirs_exist_ok=True
    )
    shutil.copytree(ROOT / "ts" / "src", dst / "ts" / "src", ignore=ignore, dirs_exist_ok=True)


def _run_lint(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LINT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_clean_tree_passes(tmp_path: Path) -> None:
    _copy_repo(tmp_path)
    result = _run_lint(tmp_path)
    assert result.returncode == 0, (
        f"lint failed on clean tree:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_injected_insert_in_wrong_module_fails(tmp_path: Path) -> None:
    _copy_repo(tmp_path)
    # Inject a forbidden write into main.py (not a decisions writer file).
    victim = tmp_path / "python" / "src" / "boros_brain" / "main.py"
    victim.write_text(
        victim.read_text()
        + "\n# drift: the following line is rogue — should be rejected by the lint.\n"
        + "def _bad() -> None:  # pragma: no cover\n"
        + "    conn.execute('INSERT INTO decisions (decision_id) VALUES (?)', ('x',))\n"
    )
    result = _run_lint(tmp_path)
    assert result.returncode == 1, (
        f"lint did NOT flag injected drift: stdout={result.stdout}, stderr={result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "decisions" in combined, f"violation message missing table name: {combined}"
    assert "main.py" in combined, f"violation message missing offending file: {combined}"
