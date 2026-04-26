"""PROTO-03 — backtest-local sidecar JSON emitter tests (Plan 05-09).

test_sidecar_atomic_write: sidecar file is written atomically; no .tmp leftovers.
test_sidecar_path_traversal_guard: output_dir outside var/backtest raises ValueError.
test_sidecar_content_matches_manifest_dump: sidecar JSON == manifest.model_dump().

[[backtest-cli-and-run-manifest-emission]]
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boros_brain.backtest.run_manifest import emit_backtest_manifest
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest


def test_sidecar_atomic_write(tmp_path: Path, default_config: BotConfig) -> None:
    """Sidecar file exists after emit; no leftover .tmp files.

    The atomic write (tempfile + Path.replace) must not leak .tmp files
    even on clean exit.

    Uses Path.cwd()/"var/backtest" to match emit_backtest_manifest's guard
    (which resolves Path("var/backtest") from CWD at call time).
    """
    import shutil

    manifest = build_run_manifest(default_config)
    # Resolve to the same root the guard uses: Path("var/backtest").resolve() at CWD.
    var_backtest_root = Path("var/backtest").resolve()
    output_dir = var_backtest_root / manifest.run_id

    try:
        path = emit_backtest_manifest(manifest, run_id=manifest.run_id, output_dir=output_dir)

        assert path.exists(), f"sidecar not written: {path}"
        # No leftover .tmp files
        leftover_tmps = list(output_dir.glob("*.json.tmp"))
        assert leftover_tmps == [], f"leftover .tmp files: {leftover_tmps}"
        # File is valid JSON
        payload = json.loads(path.read_text())
        assert isinstance(payload, dict)
        assert "run_id" in payload
    finally:
        # Cleanup: remove sidecar + run dir to keep CWD/var/backtest clean
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)


def test_sidecar_path_traversal_guard(tmp_path: Path, default_config: BotConfig) -> None:
    """output_dir outside var/backtest raises ValueError with 'path traversal blocked'."""
    manifest = build_run_manifest(default_config)
    with pytest.raises(ValueError, match="path traversal blocked"):
        emit_backtest_manifest(
            manifest,
            run_id=manifest.run_id,
            output_dir=tmp_path / "escape",
        )


def test_sidecar_content_matches_manifest_dump(default_config: BotConfig) -> None:
    """Sidecar JSON content == manifest.model_dump(mode='json').

    Verifies PROTOCOL 3 invariant: first log line + sidecar JSON contain identical content.
    """
    import shutil

    manifest = build_run_manifest(default_config)
    var_backtest_root = Path("var/backtest").resolve()
    output_dir = var_backtest_root / manifest.run_id

    try:
        path = emit_backtest_manifest(manifest, run_id=manifest.run_id, output_dir=output_dir)
        sidecar_content = path.read_text()
        expected = json.dumps(manifest.model_dump(mode="json"), indent=2)
        assert (
            sidecar_content == expected
        ), "sidecar content does not match manifest.model_dump() — PROTOCOL 3 violation"
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
