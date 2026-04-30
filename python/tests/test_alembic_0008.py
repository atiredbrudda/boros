"""Phase 05.2 Wave 2a — Alembic 0008 migration tests.

Tests:
  - test_alembic_0008_upgrades_fresh_db: fresh DB gets both new columns
  - test_alembic_0008_upgrades_idempotently: second upgrade is a no-op
  - test_alembic_0008_creates_index: index ix_market_reward_calibration_market_effective
  - test_alembic_head_is_0008: alembic_version table records 0008 as head

Uses scripts/apply_alembic_migration.py programmatic runner (alembic -x does NOT
override sqlalchemy.url — see STATE.md decision log 2026-04-24).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def _alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _apply_migration(db_path: Path, target: str) -> None:
    cfg = _alembic_cfg(db_path)
    command.upgrade(cfg, target)


def test_alembic_0008_upgrades_fresh_db(tmp_path: Path) -> None:
    """On a DB with 0007 already applied, upgrade to 0008 adds both new columns."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migration(db, "0007_phase4_tables")
    _apply_migration(db, "0008_market_reward_calibration_effective_at")

    with sqlite3.connect(str(db)) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(market_reward_calibration)").fetchall()]

    assert "effective_at_utc" in cols, f"effective_at_utc not found in columns: {cols}"
    assert "next_refresh_at_utc" in cols, f"next_refresh_at_utc not found in columns: {cols}"


def test_alembic_0008_upgrades_idempotently(tmp_path: Path) -> None:
    """Applying 0008 twice is a no-op — no exception, no duplicate columns."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migration(db, "0007_phase4_tables")

    # Apply once
    _apply_migration(db, "0008_market_reward_calibration_effective_at")

    # Apply again — must not raise
    _apply_migration(db, "0008_market_reward_calibration_effective_at")

    with sqlite3.connect(str(db)) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(market_reward_calibration)").fetchall()]

    # Exactly one of each new column (not duplicated)
    assert cols.count("effective_at_utc") == 1, f"effective_at_utc appears {cols.count('effective_at_utc')} times"
    assert cols.count("next_refresh_at_utc") == 1, f"next_refresh_at_utc appears {cols.count('next_refresh_at_utc')} times"


def test_alembic_0008_creates_index(tmp_path: Path) -> None:
    """After 0008, index ix_market_reward_calibration_market_effective must exist."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migration(db, "0007_phase4_tables")
    _apply_migration(db, "0008_market_reward_calibration_effective_at")

    with sqlite3.connect(str(db)) as conn:
        idx_rows = conn.execute("PRAGMA index_list(market_reward_calibration)").fetchall()
    idx_names = [r[1] for r in idx_rows]

    assert "ix_market_reward_calibration_market_effective" in idx_names, (
        f"Expected index not found. Existing indexes: {idx_names}"
    )


def test_alembic_head_is_0008(tmp_path: Path) -> None:
    """After upgrade to head, alembic_version table records 0008 as the current revision."""
    db = tmp_path / "state.sqlite"
    db.touch()
    _apply_migration(db, "head")

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()

    assert row is not None, "alembic_version table is empty after head upgrade"
    assert row[0] == "0008_market_reward_calibration_effective_at", (
        f"Expected 0008_market_reward_calibration_effective_at, got {row[0]!r}"
    )
