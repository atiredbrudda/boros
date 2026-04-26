"""LOCKED D-01 — operator-manual calibration via CLI → SQLite market_reward_calibration.

Tests the Pydantic + writer + SQL CHECK three-layer guard discipline for the
operator-supplied E_liq_per_epoch + side splits.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from boros_brain.reward_model.calibrate import insert_operator_calibration
from boros_brain.state.writers.market_reward_calibration import (
    get_latest_market_reward_calibration,
)


def _apply_migrations(db: Path) -> None:
    ROOT = Path(__file__).resolve().parents[2]
    ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


def test_calibration_round_trips(tmp_path: Path) -> None:
    """One row in, one row out — full round-trip via Pydantic + writer."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    insert_operator_calibration(
        db,
        market_id="BINANCE-ETHUSDT-29MAY2026",
        e_liq_per_epoch_pendle=273.0,
        long_side_split=0.14,
        short_side_split=0.86,
        source="dapp_ui",
        run_id="test_run",
    )

    row = get_latest_market_reward_calibration(db, "BINANCE-ETHUSDT-29MAY2026")
    assert row is not None
    assert row["e_liq_per_epoch_pendle"] == 273.0
    assert row["long_side_split"] == 0.14
    assert row["short_side_split"] == 0.86
    assert row["data_source"] == "operator"
    assert row["source"] == "dapp_ui"
    assert row["run_id"] == "test_run"


def test_split_validator_rejects_sum_mismatch(tmp_path: Path) -> None:
    """P3-4 — Pydantic catches split sum != 1.0 BEFORE SQL round-trip."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    with pytest.raises(Exception) as exc_info:  # ValidationError or ValueError
        insert_operator_calibration(
            db,
            market_id="M",
            e_liq_per_epoch_pendle=100.0,
            long_side_split=0.6,
            short_side_split=0.5,  # sums to 1.1
            source="dapp_ui",
            run_id="test_run",
        )
    msg = str(exc_info.value)
    assert "must == 1.0" in msg or "1.0" in msg, f"expected P3-4 split-sum error, got: {msg}"


def test_data_source_check_rejects_non_operator(tmp_path: Path) -> None:
    """LOCKED D-01 SQL-layer guard — CHECK constraint blocks non-operator data_source."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    # Bypass the Python-layer writer (which hardcodes 'operator') to test SQL CHECK directly.
    with sqlite3.connect(db) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO market_reward_calibration "
            "(market_id, e_liq_per_epoch_pendle, long_side_split, short_side_split, "
            " calibrated_at_utc, data_source, source, run_id) "
            "VALUES ('M', 100.0, 0.5, 0.5, '2026-04-24', 'polled', 'dapp_ui', 'r')"
        )


def test_negative_e_liq_raises(tmp_path: Path) -> None:
    """e_liq_per_epoch_pendle < 0 must raise (Pydantic ge=0 + writer guard)."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    with pytest.raises((ValueError, Exception)):
        insert_operator_calibration(
            db,
            market_id="M",
            e_liq_per_epoch_pendle=-1.0,
            long_side_split=0.5,
            short_side_split=0.5,
            source="dapp_ui",
            run_id="r",
        )


def test_source_enum_rejects_invalid(tmp_path: Path) -> None:
    """source enum enforced via Pydantic Literal + SQL CHECK."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        insert_operator_calibration(
            db,
            market_id="M",
            e_liq_per_epoch_pendle=100.0,
            long_side_split=0.5,
            short_side_split=0.5,
            source="invalid_source",
            run_id="r",
        )


def test_cli_calibrate_smoke(tmp_path: Path) -> None:
    """Smoke-test the calibrate CLI subcommand end-to-end."""
    import subprocess
    import sys

    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "boros_brain.reward_model",
            "--config",
            "strategy/v0.5-default.yaml",
            "calibrate",
            "--market",
            "BINANCE-ETHUSDT-29MAY2026",
            "--e-liq-pendle",
            "273.0",
            "--long-split",
            "0.14",
            "--short-split",
            "0.86",
            "--source",
            "dapp_ui",
            "--sqlite-path",
            str(db),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"calibrate CLI failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    row = get_latest_market_reward_calibration(db, "BINANCE-ETHUSDT-29MAY2026")
    assert row is not None
    assert row["e_liq_per_epoch_pendle"] == 273.0
    assert row["data_source"] == "operator"


def test_cli_calibrate_split_mismatch_returns_2(tmp_path: Path) -> None:
    """Split-sum mismatch via CLI exits 2 (Pydantic ValidationError)."""
    import subprocess
    import sys

    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "boros_brain.reward_model",
            "--config",
            "strategy/v0.5-default.yaml",
            "calibrate",
            "--market",
            "M",
            "--e-liq-pendle",
            "100.0",
            "--long-split",
            "0.6",
            "--short-split",
            "0.5",  # sums to 1.1
            "--source",
            "dapp_ui",
            "--sqlite-path",
            str(db),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"expected exit 2 (validation), got {result.returncode}\n" f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
