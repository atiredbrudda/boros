"""Single writer for the `queue_positions` table (brain-owned).

PROTO-02 single-writer discipline. FILL-03 queue tracker writes here only.
"""

from __future__ import annotations

import sqlite3


def insert_queue_position(
    conn: sqlite3.Connection,
    *,
    snapshot_ts: int,
    market_id: str,
    side: str,
    tick: int,
    our_order_id: str,
    queue_ahead_size_wei: str,
) -> None:
    """Insert one queue-ahead snapshot.

    `queue_ahead_size_wei` is a string (256-bit wei values exceed Python int
    when rendered as SQLite REAL; TEXT is the canonical wei representation).
    """
    conn.execute(
        "INSERT INTO queue_positions "
        "(snapshot_ts, market_id, side, tick, our_order_id, queue_ahead_size_wei) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (snapshot_ts, market_id, side, tick, our_order_id, queue_ahead_size_wei),
    )
