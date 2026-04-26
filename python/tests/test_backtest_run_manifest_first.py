"""PROTO-01 — backtest CLI emits RUN_MANIFEST as first log line.

Test functions:
  - test_backtest_cli_emits_run_manifest_first: first log line is RUN_MANIFEST with mode='backtest'
  - test_backtest_writes_sidecar_json: <var/backtest>/<run_id>/<run_id>.manifest.json exists

Turns GREEN in Plan 05-09 when boros_brain.backtest.cli lands.

[[backtest-replay-engine-v05]]
[[backtest-cli-and-run-manifest-emission]]
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from boros_brain.backtest.cli import main  # noqa: F401 — confirms module lands
from boros_brain.backtest.run_manifest import emit_backtest_manifest
from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_backtest_cli_emits_run_manifest_first(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """PROTO-01: manifest.model_dump() contains event-compatible RUN_MANIFEST fields.

    The full subprocess test (launch CLI, capture stdout, parse first line) is covered
    in test_backtest_cli_smoke.py. This test confirms the manifest fields used by the
    'RUN_MANIFEST' log.info call are present on the built manifest.
    """
    manifest = build_run_manifest(default_config)
    dumped = manifest.model_dump(mode="json")
    # These are the fields spread into log.info("RUN_MANIFEST", **manifest.model_dump())
    assert "run_id" in dumped
    assert "mode" in dumped
    assert "git_sha" in dumped
    assert "strategy_version" in dumped
    assert "config" in dumped
    assert isinstance(dumped["config"], dict)


def test_backtest_writes_sidecar_json(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """PROTO-01: sidecar JSON exists and contains full BotConfig.model_dump.

    After emit_backtest_manifest, the sidecar at
    var/backtest/<run_id>/<run_id>.manifest.json must exist and contain
    the full BotConfig tree (including backtest.* knobs) plus run metadata.
    """
    manifest = build_run_manifest(default_config)
    var_backtest_root = Path("var/backtest").resolve()
    output_dir = var_backtest_root / manifest.run_id

    try:
        path = emit_backtest_manifest(manifest, run_id=manifest.run_id, output_dir=output_dir)
        assert path.exists(), f"sidecar not written: {path}"
        payload = json.loads(path.read_text())
        assert "run_id" in payload
        assert "config" in payload
        # backtest meta-knobs must appear in the manifest (PROTO-04)
        assert "backtest" in payload["config"], "manifest.config must contain 'backtest' key"
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
