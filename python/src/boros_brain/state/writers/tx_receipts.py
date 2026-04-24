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
) -> None:
    """Insert one tx_receipts row. Test-fixture use only."""
    conn.execute(
        "INSERT INTO tx_receipts "
        "(tx_hash, run_id, submitted_at_ts, confirmed_at_ts, status, gas_used, intent, related_order_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tx_hash,
            run_id,
            submitted_at_ts,
            confirmed_at_ts,
            status,
            gas_used,
            intent,
            related_order_id,
        ),
    )
