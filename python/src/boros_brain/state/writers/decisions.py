"""Single writer for the `decisions` table (brain-owned).

PROTO-02: any module outside this file that writes to `decisions` is a bug.
scripts/sqlite_writer_lint.py grep-enforces this at commit time.

Caller owns the transaction lifecycle — db.py opens connections in autocommit
mode by default; batch callers wrap in explicit BEGIN/COMMIT.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def read_last_r_me_pendle(sqlite_path: Path, market_id: str, side: str) -> float | None:
    """Return the most-recent r_share_per_epoch_pendle for market_id + side, or None.

    Used by MaturityBreaker (SAFE-07) to estimate remaining reward earning.
    The column r_share_per_epoch_pendle is populated by Plan 04-06's decision
    engine loop. Until that loop writes its first row, this function returns None
    and MaturityBreaker returns reason='no_decision_history_yet'.

    Wraps OperationalError so callers get None if the column is absent (schema
    migration not yet applied).

    Read-only — not subject to PROTO-02 single-writer lint.
    """
    from boros_brain.state.db import open_connection

    try:
        with open_connection(sqlite_path) as conn:
            row = conn.execute(
                "SELECT r_share_per_epoch_pendle FROM decisions "
                "WHERE market_id = ? AND side = ? "
                "ORDER BY chain_ts DESC LIMIT 1",
                (market_id, side),
            ).fetchone()
        return float(row[0]) if row else None
    except Exception:  # noqa: BLE001 — column absent or table missing
        return None


def insert_decision(
    conn: sqlite3.Connection,
    *,
    decision_id: str,
    ts_ms: int,
    run_id: str,
    market_id: str,
    decision: str,
    ev_hold: float | None = None,
    p_fill: float | None = None,
    e_loss: float | None = None,
    r_share: float | None = None,
    reason: str | None = None,
) -> None:
    """Insert one decision row.

    `decision` must be one of 'place' | 'hold' | 'cancel' | 'emergency_cancel' |
    'no_action' — the DB CHECK constraint enforces this; we do not pre-validate
    here to keep the writer slim.
    """
    conn.execute(
        "INSERT INTO decisions "
        "(decision_id, ts_ms, run_id, market_id, decision, ev_hold, p_fill, e_loss, r_share, reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            decision_id,
            ts_ms,
            run_id,
            market_id,
            decision,
            ev_hold,
            p_fill,
            e_loss,
            r_share,
            reason,
        ),
    )
