"""Single writer for the `decisions` table (brain-owned).

PROTO-02: any module outside this file that writes to `decisions` is a bug.
scripts/sqlite_writer_lint.py grep-enforces this at commit time.

Caller owns the transaction lifecycle — db.py opens connections in autocommit
mode by default; batch callers wrap in explicit BEGIN/COMMIT.
"""

from __future__ import annotations

import sqlite3


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
