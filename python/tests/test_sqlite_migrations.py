"""INFRA-03 — SQLite WAL state spine migration + safety tests.

Each test is one assertion targeting a specific invariant:
  - WAL journal mode is actually enabled on connection open
  - All 8 tables exist after `alembic upgrade head` + `alembic_version` meta table
  - `reward_budget_history.data_source` CHECK constraint rejects bad values (B6)
  - `run_manifests.parent_run_id` FK is enforced when `PRAGMA foreign_keys=ON`
  - SQLite file permissions are clamped to 0o600 at connection time (T-02-02)
  - Repeated `open_connection()` is idempotent and does not change permissions
"""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from boros_brain.state.db import open_connection

# Repo root (python/tests → python/ → repo-root)
ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def _alembic_config_for(db_path: Path) -> Config:
    """Build an Alembic Config pointing at `db_path` with script_location resolved
    relative to the alembic.ini file."""
    cfg = Config(str(ALEMBIC_INI))
    # `script_location` in the .ini is relative to the .ini file; override to absolute.
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_wal_mode_enabled(tmp_sqlite_path: Path) -> None:
    """Opening a connection via db.py must leave journal_mode == 'wal'."""
    with open_connection(tmp_sqlite_path) as conn:
        row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"


def test_all_8_tables_exist_after_migration(tmp_path: Path) -> None:
    """`alembic upgrade head` must produce exactly the 8 canonical tables
    (plus alembic_version meta)."""
    db_path = tmp_path / "mig.sqlite"
    # Pre-create file with WAL + FKs (mirrors production open_connection contract).
    with open_connection(db_path):
        pass
    cfg = _alembic_config_for(db_path)
    command.upgrade(cfg, "head")

    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    names = {r[0] for r in rows}

    expected = {
        "open_orders",
        "decisions",
        "tx_receipts",
        "queue_positions",
        "run_manifests",
        "epoch_rewards",
        "clo_history",
        "reward_budget_history",
        "alembic_version",
    }
    # sqlite_sequence is an internal SQLite table created automatically when any
    # table uses AUTOINCREMENT (reward_budget_history.id). It is not a user table.
    names.discard("sqlite_sequence")
    assert names == expected, f"table set drift: got {names}, expected {expected}"


def test_reward_budget_history_data_source_check(tmp_path: Path) -> None:
    """B6 pitfall guard — CHECK constraint on `data_source` rejects invalid origin.

    Phase-5 backtest filters rows by this column; an unvalidated value silently
    pollutes backtest P&L.
    """
    db_path = tmp_path / "check.sqlite"
    with open_connection(db_path):
        pass
    command.upgrade(_alembic_config_for(db_path), "head")

    with open_connection(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reward_budget_history "
            "(polled_at_utc, chain_ts, market_id, e_liq_per_epoch, long_budget, short_budget, run_id, data_source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-04-24T00:00:00+00:00", 1, "ETHUSDT-29MAY2026", 10.0, 5.0, 5.0, "run-x", "invalid"),
        )


def test_run_manifests_parent_run_id_fk(tmp_path: Path) -> None:
    """FK enforcement is ON at connection time — dangling parent_run_id rejected.

    INFRA-06 (mid-run knob-change chain) depends on `parent_run_id` FK integrity.
    SQLite default is `PRAGMA foreign_keys=OFF`; `open_connection()` MUST enable it.
    """
    db_path = tmp_path / "fk.sqlite"
    with open_connection(db_path):
        pass
    command.upgrade(_alembic_config_for(db_path), "head")

    with open_connection(db_path) as conn:
        # FKs must be ON
        fk_state = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk_state == 1, "open_connection() did not enable foreign_keys"

        # Insert with dangling parent must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO run_manifests "
                "(run_id, parent_run_id, started_at_iso, mode, strategy_version, git_sha, git_dirty, "
                "market_id, side, wallet_address_hash, config_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "01H-child",
                    "01H-nonexistent-parent",  # dangling
                    "2026-04-23T23:50:00Z",
                    "paper",
                    "v0.5.0",
                    "deadbeef",
                    0,
                    "ETHUSDT-29MAY2026",
                    "long",
                    "0xhashed",
                    "{}",
                ),
            )


def test_sqlite_file_chmod_600(tmp_path: Path) -> None:
    """T-02-02 mitigation — SQLite file must be 0o600 after open_connection()."""
    db_path = tmp_path / "perms.sqlite"
    with open_connection(db_path):
        pass
    mode = stat.S_IMODE(os.stat(db_path).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_idempotent_reopen(tmp_path: Path) -> None:
    """Reopening the same DB must not change permissions or leave the connection broken."""
    db_path = tmp_path / "idem.sqlite"
    with open_connection(db_path):
        pass
    first_mode = stat.S_IMODE(os.stat(db_path).st_mode)

    # Second open
    with open_connection(db_path) as conn:
        row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0].lower() == "wal"

    second_mode = stat.S_IMODE(os.stat(db_path).st_mode)
    assert first_mode == second_mode == 0o600
