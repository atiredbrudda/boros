"""Tests for boros_brain.data.ingester.cli — CLI dispatcher + RUN_MANIFEST emission.

Cases:
1. test_cli_dispatches_market_trades_kind — exits 0, prints rows_written=3
2. test_cli_emits_run_manifest — manifest JSON sidecar is written with a ULID run_id
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

# Root of the project (python/tests → python → repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
STRATEGY_YAML = REPO_ROOT / "strategy" / "v0.5-default.yaml"
PYTHON_DIR = REPO_ROOT / "python"


def test_cli_dispatches_market_trades_kind(tmp_path: Path) -> None:
    """CLI with --kind market_trades exits 0 and prints a summary containing rows_written=3."""
    fixture = FIXTURES / "sample_market_trades.ndjson"
    out_dir = tmp_path / "parquet"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    # Override logs and sqlite to tmp locations so the CLI doesn't need a live DB
    # The CLI falls back to sidecar-only manifest write when SQLite is uninitialized
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "boros_brain.data.ingester.cli",
            "--kind",
            "market_trades",
            "--src",
            str(fixture),
            "--market-id",
            "ETH",
            "--out",
            str(out_dir),
            "--config",
            str(STRATEGY_YAML),
        ],
        capture_output=True,
        text=True,
        cwd=str(PYTHON_DIR),
        env={
            **__import__("os").environ,
            # point logs/sqlite to tmp so no side effects on the real state dir
            "BOROS_LOGS_DIR": str(logs_dir),
        },
    )
    assert completed.returncode == 0, (
        f"CLI exited {completed.returncode}\n--- stdout ---\n{completed.stdout}\n" f"--- stderr ---\n{completed.stderr}"
    )
    # stdout must contain the summary line
    assert (
        "rows_written=3" in completed.stdout or "rows_written=3" in completed.stdout
    ), f"Expected 'rows_written=3' in stdout:\n{completed.stdout}"
    # Parquet tree must exist
    parquet_glob = list((out_dir / "market_trades").rglob("*.parquet"))
    assert parquet_glob, f"No parquet files written under {out_dir / 'market_trades'}"


def test_cli_emits_run_manifest(tmp_path: Path) -> None:
    """After CLI run a manifest JSON sidecar exists with a ULID run_id."""
    fixture = FIXTURES / "sample_market_trades.ndjson"
    out_dir = tmp_path / "parquet"
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "boros_brain.data.ingester.cli",
            "--kind",
            "market_trades",
            "--src",
            str(fixture),
            "--market-id",
            "ETH",
            "--out",
            str(out_dir),
            "--config",
            str(STRATEGY_YAML),
        ],
        capture_output=True,
        text=True,
        cwd=str(PYTHON_DIR),
        env={
            **__import__("os").environ,
            "BOROS_LOGS_DIR": str(logs_dir),
        },
    )
    assert completed.returncode == 0, f"CLI failed:\n{completed.stderr}"

    # Find manifest JSON sidecar under the logs dir
    # CLI uses config.infra.logs_dir from the YAML, which is "logs" relative to cwd.
    # cwd = PYTHON_DIR, so logs dir is PYTHON_DIR/logs/<date>/<run_id>.manifest.json
    # We allow either PYTHON_DIR/logs or tmp_path/logs.
    manifest_files = list(Path(PYTHON_DIR / "logs").rglob("*.manifest.json"))
    if not manifest_files:
        manifest_files = list(logs_dir.rglob("*.manifest.json"))

    assert manifest_files, "No *.manifest.json found in logs dir. " f"Searched {PYTHON_DIR / 'logs'} and {logs_dir}"
    # Validate it's parseable JSON with a run_id field
    manifest = json.loads(manifest_files[0].read_text())
    assert "run_id" in manifest, f"manifest missing run_id: {manifest.keys()}"
    # ULID is 26 chars uppercase alphanumeric
    assert len(manifest["run_id"]) == 26, f"Unexpected run_id format: {manifest['run_id']}"
