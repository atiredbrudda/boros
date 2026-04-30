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


def test_pydantic_market_reward_calibration_has_new_fields(tmp_path: Path) -> None:
    """W2a — MarketRewardCalibration must accept effective_at_utc + next_refresh_at_utc."""
    from pydantic import ValidationError

    from boros_brain.config.schema import MarketRewardCalibration

    # Valid construction with new fields
    obj = MarketRewardCalibration(
        e_liq_per_epoch_pendle=309.96,
        long_side_split=0.327,
        short_side_split=0.673,
        calibrated_at_utc="2026-04-30T00:00:00Z",
        effective_at_utc="2026-04-30T00:00:00Z",
        next_refresh_at_utc="2026-05-07T00:00:00Z",
    )
    assert obj.effective_at_utc == "2026-04-30T00:00:00Z"
    assert obj.next_refresh_at_utc == "2026-05-07T00:00:00Z"

    # Missing effective_at_utc must raise ValidationError
    with pytest.raises(ValidationError):
        MarketRewardCalibration(
            e_liq_per_epoch_pendle=309.96,
            long_side_split=0.327,
            short_side_split=0.673,
            calibrated_at_utc="2026-04-30T00:00:00Z",
            next_refresh_at_utc="2026-05-07T00:00:00Z",
        )

    # Non-ISO8601 string in effective_at_utc must raise ValueError or ValidationError
    with pytest.raises((ValueError, ValidationError)):
        MarketRewardCalibration(
            e_liq_per_epoch_pendle=309.96,
            long_side_split=0.327,
            short_side_split=0.673,
            calibrated_at_utc="2026-04-30T00:00:00Z",
            effective_at_utc="not-an-iso-string",
            next_refresh_at_utc="2026-05-07T00:00:00Z",
        )


def test_writer_round_trip_with_effective_at(tmp_path: Path) -> None:
    """W2a — writer persists effective_at_utc + next_refresh_at_utc; read-back returns them."""
    from boros_brain.state.writers.market_reward_calibration import (
        get_latest_market_reward_calibration,
        insert_market_reward_calibration,
    )

    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    insert_market_reward_calibration(
        db,
        market_id="BINANCE-ETHUSDT-25SEP2026",
        e_liq_per_epoch_pendle=309.96,
        long_side_split=0.760,
        short_side_split=0.240,
        calibrated_at_utc="2026-04-30T05:18:54Z",
        effective_at_utc="2026-04-30T00:00:00Z",
        next_refresh_at_utc="2026-05-07T00:00:00Z",
        source="dapp_ui",
        run_id="test-w2a",
    )

    row = get_latest_market_reward_calibration(db, "BINANCE-ETHUSDT-25SEP2026")
    assert row is not None
    assert row["effective_at_utc"] == "2026-04-30T00:00:00Z"
    assert row["next_refresh_at_utc"] == "2026-05-07T00:00:00Z"
    assert row["long_side_split"] == 0.760
    assert row["data_source"] == "operator"


def test_writer_rejects_missing_effective_at(tmp_path: Path) -> None:
    """W2a — insert_market_reward_calibration requires effective_at_utc (TypeError if missing)."""
    from boros_brain.state.writers.market_reward_calibration import insert_market_reward_calibration

    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migrations(db)

    with pytest.raises(TypeError):
        insert_market_reward_calibration(  # type: ignore[call-arg]
            db,
            market_id="M",
            e_liq_per_epoch_pendle=100.0,
            long_side_split=0.5,
            short_side_split=0.5,
            calibrated_at_utc="2026-04-30T00:00:00Z",
            # effective_at_utc deliberately omitted
            next_refresh_at_utc="2026-05-07T00:00:00Z",
            source="dapp_ui",
            run_id="r",
        )


def test_writer_validates_iso8601(tmp_path: Path) -> None:
    """W2a — non-ISO8601 effective_at_utc raises ValueError BEFORE DB connection."""
    from boros_brain.state.writers.market_reward_calibration import insert_market_reward_calibration

    db = tmp_path / "state.sqlite"
    # Note: do NOT call _apply_migrations — ValueError must fire before any DB open.
    # (The DB doesn't even need to exist for this test.)

    with pytest.raises(ValueError, match="ISO8601"):
        insert_market_reward_calibration(
            db,
            market_id="M",
            e_liq_per_epoch_pendle=100.0,
            long_side_split=0.5,
            short_side_split=0.5,
            calibrated_at_utc="2026-04-30T00:00:00Z",
            effective_at_utc="not-an-iso-string",
            next_refresh_at_utc="2026-05-07T00:00:00Z",
            source="dapp_ui",
            run_id="r",
        )


def test_writer_split_validation_still_holds(tmp_path: Path) -> None:
    """REGRESSION — split-sum validation still fires after adding new kwargs."""
    from boros_brain.state.writers.market_reward_calibration import insert_market_reward_calibration

    db = tmp_path / "state.sqlite"

    with pytest.raises(ValueError, match="must == 1.0"):
        insert_market_reward_calibration(
            db,
            market_id="M",
            e_liq_per_epoch_pendle=100.0,
            long_side_split=0.327,
            short_side_split=0.674,  # 0.327 + 0.674 = 1.001, != 1.0
            calibrated_at_utc="2026-04-30T00:00:00Z",
            effective_at_utc="2026-04-30T00:00:00Z",
            next_refresh_at_utc="2026-05-07T00:00:00Z",
            source="dapp_ui",
            run_id="r",
        )


def test_sqlite_writer_lint_still_passes(tmp_path: Path) -> None:
    """REGRESSION — PROTO-05 single-writer lint must exit 0 after writer extension."""
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/sqlite_writer_lint.py"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"sqlite_writer_lint.py failed (PROTO-05 single-writer violation):\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


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
