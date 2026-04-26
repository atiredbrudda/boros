"""Wave-0 prerequisite — no_zmq_singleton_in_tests_lint.py audit script tests.

Covers:
  - test_lint_passes_when_tests_dir_is_clean: lint passes on whole codebase (all
    Context.instance() violations removed as part of Wave-0 fix in Plan 05-01)
  - test_lint_catches_singleton_use: lint detects `zmq.asyncio.Context.instance()`
    in a temp file injected under PROTECTED_DIRS

BACK-07 success criterion #6 / Wave-0 lint guard. See [[wave-0-zmq-fixture-leak-fix]].
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_lint_module(lint_script: Path):
    """Load the lint module fresh (avoids cached state from prior calls)."""
    spec = importlib.util.spec_from_file_location(lint_script.stem + "_fresh", lint_script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _get_lint_script() -> Path:
    scripts_dir = REPO_ROOT / "scripts"
    lint_script = scripts_dir / "no_zmq_singleton_in_tests_lint.py"
    assert lint_script.exists(), f"Lint script not found at {lint_script}"
    return lint_script


def test_lint_passes_when_tests_dir_is_clean() -> None:
    """Wave-0 — lint passes on the full test directory when no Context.instance() exists.

    All Context.instance() uses in python/tests/ were replaced with per-test
    Context() + try/finally: ctx.term() during Plan 05-01 Wave-0. This test
    verifies the directory stays clean on every subsequent commit.
    """
    lint_script = _get_lint_script()
    old_cwd = os.getcwd()
    try:
        # Lint uses relative PROTECTED_DIRS — must run from repo root
        os.chdir(REPO_ROOT)
        mod = _load_lint_module(lint_script)
        exit_code = mod.main()
        assert exit_code == 0, (
            f"no_zmq_singleton_in_tests_lint exited {exit_code} (expected 0 on a clean tree). "
            "A test file has re-introduced zmq.asyncio.Context.instance()."
        )
    finally:
        os.chdir(old_cwd)


def test_lint_catches_singleton_use(tmp_path: Path, monkeypatch) -> None:
    """Wave-0 — lint detects zmq.asyncio.Context.instance() in a test file.

    Writes a 3-line temp file with a Context.instance() call, monkeypatches
    _all_protected_files to return just that file, asserts exit code == 1.
    """
    lint_script = _get_lint_script()

    # Write offending file to tmp_path
    bad_file = tmp_path / "temp_singleton.py"
    bad_file.write_text(
        "import zmq.asyncio\n"
        "ctx = zmq.asyncio.Context.instance()\n"
    )

    old_cwd = os.getcwd()
    try:
        os.chdir(REPO_ROOT)
        mod = _load_lint_module(lint_script)
        # Monkeypatch _all_protected_files to return only our injected file
        monkeypatch.setattr(mod, "_all_protected_files", lambda: [bad_file])
        exit_code = mod.main()
        assert exit_code == 1, (
            f"Expected lint exit code 1 (singleton violation), got {exit_code}"
        )
    finally:
        os.chdir(old_cwd)
