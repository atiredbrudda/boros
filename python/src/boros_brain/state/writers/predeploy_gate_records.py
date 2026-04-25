"""Single writer for the `predeploy_gate_records` table (brain-owned). Plan 04-02.

PROTO-02 single-writer discipline. The predeploy_gate CLI subcommand (Plan 04-06)
is the only caller. Any `INSERT INTO predeploy_gate_records` outside this module
triggers scripts/sqlite_writer_lint.py.

Pitfall #8: Phase 7 live boot reads the latest record via get_latest_predeploy_gate_record
and refuses to start if git_sha or config_hash doesn't match the current run. Operator
cannot deploy with a config that was never gate-validated.

Record contains git_sha + config_hash for provenance, wiki_page_path for the
economist-readable postmortem trail, and gate_passed for the go/no-go outcome.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["insert_predeploy_gate_record", "get_latest_predeploy_gate_record"]


def insert_predeploy_gate_record(
    conn: sqlite3.Connection,
    *,
    gate_passed: bool,
    git_sha: str,
    git_dirty: bool,
    config_hash: str,
    wiki_page_path: str,
    run_id: str,
    chain_ts: int,
) -> None:
    """Insert one predeploy_gate_records row.

    Converts Python bools to SQLite integers (1/0) before the INSERT.
    The CHECK constraints in migration 0007 enforce gate_passed IN (0,1)
    and git_dirty IN (0,1) at the DB level as a belt-and-braces guard.

    Caller owns transaction lifecycle — NO conn.commit() here (db.py contract).
    """
    conn.execute(
        "INSERT INTO predeploy_gate_records "
        "(gate_passed, git_sha, git_dirty, config_hash, wiki_page_path, run_id, chain_ts) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            1 if gate_passed else 0,
            git_sha,
            1 if git_dirty else 0,
            config_hash,
            wiki_page_path,
            run_id,
            chain_ts,
        ),
    )


def get_latest_predeploy_gate_record(sqlite_path: Path) -> dict[str, object] | None:
    """Return the most recent predeploy_gate_records row as a dict, or None.

    Self-managing connection (opens + closes within this call). Used by the
    Phase 7 live boot guard and test fixtures.

    Returns
    -------
    dict or None
        Keys: id, gate_passed (bool), git_sha, git_dirty (bool), config_hash,
        wiki_page_path, run_id, chain_ts.
        None if the table is empty.
    """
    from boros_brain.state.db import open_connection

    with open_connection(sqlite_path) as conn:
        row = conn.execute(
            "SELECT id, gate_passed, git_sha, git_dirty, config_hash, "
            "wiki_page_path, run_id, chain_ts "
            "FROM predeploy_gate_records ORDER BY chain_ts DESC LIMIT 1"
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "gate_passed": bool(row[1]),
        "git_sha": row[2],
        "git_dirty": bool(row[3]),
        "config_hash": row[4],
        "wiki_page_path": row[5],
        "run_id": row[6],
        "chain_ts": row[7],
    }
