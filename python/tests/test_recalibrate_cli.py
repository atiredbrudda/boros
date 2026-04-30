"""CLI-level tests for the calibrate subcommand with new --effective-at-utc and
--next-refresh-at-utc flags (Wave 2b — Plan 05.2-04).

Tests:
  - test_cli_calibrate_with_effective_at_flag: explicit flags round-trip
  - test_cli_calibrate_no_effective_at_flag_uses_default: omitted flags → defaults applied
  - test_cli_emits_manifest_before_db_write: MANIFEST-FIRST invariant (PROTO-03 regression)

[[market-reward-calibration-operator-workflow]]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def _apply_migrations(db: Path) -> None:
    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_calibrate_cli(
    db: Path,
    extra_args: list[str] | None = None,
) -> tuple[int, str, str]:
    """Helper: run the calibrate subcommand via subprocess and return (returncode, stdout, stderr)."""
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "boros_brain.reward_model",
        "--config",
        "strategy/v0.5-default.yaml",
        "calibrate",
        "--market",
        "FOO",
        "--e-liq-pendle",
        "309.96",
        "--long-split",
        "0.327",
        "--short-split",
        "0.673",
        "--source",
        "dapp_ui",
        "--sqlite-path",
        str(db),
    ]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_cli_calibrate_with_effective_at_flag(tmp_path: Path) -> None:
    """W2b: --effective-at-utc and --next-refresh-at-utc flags round-trip through CLI → DB."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    returncode, stdout, stderr = _run_calibrate_cli(
        db,
        extra_args=[
            "--effective-at-utc",
            "2026-04-30T00:00:00Z",
            "--next-refresh-at-utc",
            "2026-05-07T00:00:00Z",
        ],
    )

    assert returncode == 0, (
        f"calibrate CLI failed with explicit flags:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
    )

    # Confirm the row was persisted with the correct values
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT long_side_split, effective_at_utc, next_refresh_at_utc "
            "FROM market_reward_calibration WHERE market_id = 'FOO' "
            "ORDER BY calibrated_at_utc DESC LIMIT 1"
        ).fetchone()

    assert row is not None, "No row inserted for market FOO"
    long_split, effective_at, next_refresh = row
    assert long_split == pytest.approx(0.327, rel=1e-3)
    assert effective_at == "2026-04-30T00:00:00Z"
    assert next_refresh == "2026-05-07T00:00:00Z"


def test_cli_calibrate_no_effective_at_flag_uses_default(tmp_path: Path) -> None:
    """W2b: omitting --effective-at-utc and --next-refresh-at-utc uses defaults:
    effective_at ≈ now, next_refresh ≈ now + epoch_days (7 days).
    """
    import re
    from datetime import datetime, timezone

    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    returncode, stdout, stderr = _run_calibrate_cli(db)

    assert returncode == 0, (
        f"calibrate CLI failed without new flags:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
    )

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT effective_at_utc, next_refresh_at_utc "
            "FROM market_reward_calibration WHERE market_id = 'FOO' "
            "ORDER BY calibrated_at_utc DESC LIMIT 1"
        ).fetchone()

    assert row is not None, "No row inserted for market FOO"
    effective_at, next_refresh = row

    # Both must be valid ISO8601
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", effective_at), (
        f"effective_at_utc not ISO8601: {effective_at!r}"
    )
    assert re.match(r"^\d{4}-\d{2}-\d{2}T", next_refresh), (
        f"next_refresh_at_utc not ISO8601: {next_refresh!r}"
    )

    # next_refresh must be approximately effective_at + 7 days
    eff = datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
    nxt = datetime.fromisoformat(next_refresh.replace("Z", "+00:00"))
    delta_days = (nxt - eff).total_seconds() / 86400
    assert delta_days == pytest.approx(7.0, rel=0.01), (
        f"Expected next_refresh ≈ effective_at + 7 days, got delta={delta_days:.2f} days"
    )


def test_cli_emits_manifest_before_db_write(tmp_path: Path) -> None:
    """REGRESSION (PROTO-03): RUN_MANIFEST must be emitted as the first log line
    before any DB work is done.

    The structlog output goes to a `.log.jsonl` file under logs/<YYYY-MM-DD>/.
    We locate the newest run's log file by finding the latest `.manifest.json`
    sidecar written during this test run, then check line ordering in the `.jsonl`.
    """
    import glob
    import time

    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    # Record timestamp before the run so we can find new log files
    before_ts = time.time()

    returncode, stdout, stderr = _run_calibrate_cli(db)

    assert returncode == 0, (
        f"calibrate CLI failed:\nSTDOUT: {stdout}\nSTDERR: {stderr}"
    )

    # Find the log file written during this run: search the repo's logs/ directory
    # for .jsonl files newer than before_ts
    logs_root = REPO_ROOT / "logs"
    if not logs_root.exists():
        # Try relative to cwd
        logs_root = Path(".").resolve() / "logs"

    candidate_files = []
    if logs_root.exists():
        for jsonl_path in logs_root.rglob("*.reward_model.log.jsonl"):
            if jsonl_path.stat().st_mtime > before_ts:
                candidate_files.append(jsonl_path)

    assert candidate_files, (
        f"No reward_model.log.jsonl file written after this test started in {logs_root}. "
        f"stdout={stdout!r} stderr={stderr!r}"
    )

    # Use the newest file (most likely the one from this invocation)
    log_file = sorted(candidate_files, key=lambda p: p.stat().st_mtime)[-1]
    log_lines = [ln.strip() for ln in log_file.read_text().splitlines() if ln.strip()]

    assert log_lines, f"Log file {log_file} is empty"

    # Parse lines and verify RUN_MANIFEST is first substantive event
    manifest_pos = None
    persist_pos = None

    for i, line in enumerate(log_lines):
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        event = obj.get("event", "")
        if event == "RUN_MANIFEST" and manifest_pos is None:
            manifest_pos = i
        if "calibration_persisted" in event and persist_pos is None:
            persist_pos = i

    assert manifest_pos is not None, (
        f"RUN_MANIFEST log line not found in {log_file}.\n"
        f"First lines: {log_lines[:5]}"
    )
    assert manifest_pos == 0, (
        f"RUN_MANIFEST must be the FIRST log line (line 0), "
        f"but found at line {manifest_pos}"
    )
    if persist_pos is not None:
        assert manifest_pos < persist_pos, (
            f"RUN_MANIFEST must appear BEFORE calibration_persisted "
            f"(manifest at line {manifest_pos}, persist at line {persist_pos})"
        )
