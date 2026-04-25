"""Writer module for `open_orders` — HANDS-owned in production.

Production writes for this table live in ts/src/boros_hands/state/sqlite_writer.ts.
The Python writer here exists ONLY for test-fixture seeding; the lint recognizes
this via the module-scope `TEST_ONLY = True` marker.

PROTO-02: any Python module OTHER THAN this one that writes to `open_orders`
is a violation even with TEST_ONLY, and the lint catches it.
"""

from __future__ import annotations

import sqlite3

# Module-scope marker. The lint scans for this literal string at module top
# before allowing INSERT INTO open_orders / UPDATE open_orders in this file.
TEST_ONLY = True


def insert_open_order(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    market_id: str,
    side: str,
    depth_ticks: int,
    size_wei: str,
    rate: int,
    status: str,
    placed_at_ts: int,
    run_id: str,
) -> None:
    """Insert one open-order row. Test-fixture use only.

    Production upsert-on-fill flow is in ts/src/boros_hands/state/sqlite_writer.ts
    (because the WebSocket fill detector lives on the hands side and the fill →
    cancel hot path must not cross the ZMQ boundary).
    """
    conn.execute(
        "INSERT INTO open_orders "
        "(order_id, market_id, side, depth_ticks, size_wei, rate, status, placed_at_ts, run_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            order_id,
            market_id,
            side,
            depth_ticks,
            size_wei,
            rate,
            status,
            placed_at_ts,
            run_id,
        ),
    )


def read_open_orders_for_market(sqlite_path: "Path", *, market_id: str) -> list[dict]:
    """Read ACTIVE open_orders for the configured market.

    v0.5: reads what hands writes (TS owns the writer). Used by the 1 Hz
    _decision_loop in main.py (Plan 04-06) to feed per-order EV evaluation.

    Read-only — not subject to PROTO-02 single-writer lint (no INSERT/UPDATE).
    Self-managing connection (opens + closes within this call).
    """
    from pathlib import Path as _Path
    from boros_brain.state.db import open_connection

    with open_connection(_Path(sqlite_path)) as conn:
        rows = conn.execute(
            "SELECT order_id, market_id, side, depth_ticks, size_wei, rate, status "
            "FROM open_orders WHERE market_id = ? AND status = 'active'",
            (market_id,),
        ).fetchall()
    return [
        dict(zip(["order_id", "market_id", "side", "depth_ticks", "size_wei", "rate", "status"], r))
        for r in rows
    ]


def update_open_order_status(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    status: str,
) -> None:
    """Flip an open_order's status. Test-fixture use only — see module docstring."""
    conn.execute(
        "UPDATE open_orders SET status = ? WHERE order_id = ?",
        (status, order_id),
    )
