"""Writer module for `tx_receipts` — HANDS-owned in production.

Production writes for this table live in ts/src/boros_hands/state/sqlite_writer.ts.
The Python writer here exists ONLY for test-fixture seeding; the lint recognizes
this via the module-scope `TEST_ONLY = True` marker.

Send Txs Bot confirmations arrive on the hands side (after the submit HTTP roundtrip),
so the writer naturally lives there. Keeping a Python seeding helper lets
integration tests build realistic state without spinning up the TS process.
"""

from __future__ import annotations

import sqlite3

TEST_ONLY = True


def insert_tx_receipt(
    conn: sqlite3.Connection,
    *,
    tx_hash: str,
    run_id: str,
    submitted_at_ts: int,
    confirmed_at_ts: int | None,
    status: str,
    gas_used: int | None,
    intent: str,
    related_order_id: str | None,
    event_type: str = "unknown",
    chain_ts: int | None = None,
    market_id: str | None = None,
    order_id: str | None = None,
) -> None:
    """Insert one tx_receipts row. Test-fixture use only.

    The event_type, chain_ts, market_id, and order_id columns were added by
    migration 0007_phase4_tables (Plan 04-02/04-04). Pass event_type='fill'
    for fill events so SAFE-05 FillRateBreaker can count them.
    """
    conn.execute(
        "INSERT INTO tx_receipts "
        "(tx_hash, run_id, submitted_at_ts, confirmed_at_ts, status, gas_used, "
        " intent, related_order_id, event_type, chain_ts, market_id, order_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tx_hash,
            run_id,
            submitted_at_ts,
            confirmed_at_ts,
            status,
            gas_used,
            intent,
            related_order_id,
            event_type,
            chain_ts,
            market_id,
            order_id,
        ),
    )


def read_tx_receipts_fill_count(
    sqlite_path,
    *,
    market_id: str | None = None,
    since_ts: int | None = None,
) -> int:
    """Count tx_receipts rows with event_type='fill' within the given window.

    Read-only helper (SELECT only). Not restricted by sqlite_writer_lint.
    Used by FillRateBreaker.check() for SAFE-05 fill-rate runaway detection.

    Parameters
    ----------
    sqlite_path : Path | str
        SQLite WAL DB path.
    market_id : str | None
        If given, filter to this market only.
    since_ts : int | None
        If given, only count rows with chain_ts >= since_ts.

    Returns
    -------
    int
        Count of fill events in the window. Returns 0 if no rows found.
    """
    from boros_brain.state.db import open_connection
    from pathlib import Path

    sql = "SELECT COUNT(*) FROM tx_receipts WHERE event_type = 'fill'"
    params: list = []
    if market_id is not None:
        sql += " AND market_id = ?"
        params.append(market_id)
    if since_ts is not None:
        sql += " AND chain_ts >= ?"
        params.append(since_ts)

    with open_connection(sqlite_path) as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0
