"""Single writer for the `clo_history` table (brain-owned).

PROTO-02 single-writer discipline. DATA-06 /markets poller (plan 01-09) + the
fIndex decoder (plan 01-10) both write here — only via this module.
"""

from __future__ import annotations

import sqlite3


def insert_clo_snapshot(
    conn: sqlite3.Connection,
    *,
    snapshot_ts: int,
    market_id: str,
    clo_lower_thresh: float,
    clo_upper_thresh: float,
    f_index_raw: int | None = None,
) -> None:
    """Insert one CLO + fIndex snapshot.

    `f_index_raw` is nullable for historical backfills that predate fIndex
    decoding. The 01-09 live poller populates it on every call.
    """
    conn.execute(
        "INSERT INTO clo_history "
        "(snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw) "
        "VALUES (?, ?, ?, ?, ?)",
        (snapshot_ts, market_id, clo_lower_thresh, clo_upper_thresh, f_index_raw),
    )
