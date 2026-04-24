"""INFRA-06 — parent_run_id FK chain enforced by the `run_manifests` table."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from boros_brain.config.schema import BotConfig
from boros_brain.manifest.writer import build_run_manifest, write_manifest
from boros_brain.state.db import open_connection
from boros_brain.state.writers.run_manifests import insert_run_manifest

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def _upgrade(db_path: Path) -> None:
    with open_connection(db_path):
        pass
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_parent_run_id_chain(default_config: BotConfig, tmp_path: Path) -> None:
    """Two consecutive write_manifest() calls form a parent→child chain."""
    db = tmp_path / "state.sqlite"
    logs_dir = tmp_path / "logs"
    _upgrade(db)

    m1 = build_run_manifest(default_config)
    write_manifest(m1, logs_dir=logs_dir, sqlite_path=db)

    m2 = build_run_manifest(default_config, parent_run_id=m1.run_id)
    write_manifest(m2, logs_dir=logs_dir, sqlite_path=db)

    with open_connection(db) as conn:
        rows = conn.execute("SELECT run_id, parent_run_id FROM run_manifests ORDER BY run_id").fetchall()
    mapping = dict(rows)
    assert mapping[m1.run_id] is None
    assert mapping[m2.run_id] == m1.run_id


def test_parent_run_id_fk_enforced(tmp_path: Path) -> None:
    """FK constraint: inserting with a bogus parent_run_id must raise IntegrityError."""
    db = tmp_path / "state.sqlite"
    _upgrade(db)
    with open_connection(db) as conn, pytest.raises(sqlite3.IntegrityError):
        insert_run_manifest(
            conn,
            run_id="orphan-1",
            parent_run_id="NONEXISTENT_PARENT",
            started_at_iso="2026-04-24T00:00:00+00:00",
            mode="paper",
            strategy_version="v0.5.0",
            git_sha="deadbeef",
            git_dirty=0,
            market_id="ETHUSDT-29MAY2026",
            side="long",
            wallet_address_hash="abc1234deadbeef0",
            config_json=json.dumps({}),
        )
