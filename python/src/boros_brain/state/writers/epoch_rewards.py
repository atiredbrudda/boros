"""Single writer for the `epoch_rewards` table (brain-owned).

PROTO-02 single-writer discipline. Reward-accrual + Merkle claim bookkeeping
writes here only.
"""

from __future__ import annotations

import sqlite3


def insert_epoch_reward(
    conn: sqlite3.Connection,
    *,
    epoch_end_ts: int,
    market_id: str,
    our_accrued_pendle: float,
    claimed: int = 0,
    claim_tx_hash: str | None = None,
) -> None:
    """Insert an epoch-reward accrual record.

    `claimed` is 0/1 — the DB CHECK constraint enforces this.
    """
    conn.execute(
        "INSERT INTO epoch_rewards "
        "(epoch_end_ts, market_id, our_accrued_pendle, claimed, claim_tx_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (epoch_end_ts, market_id, our_accrued_pendle, claimed, claim_tx_hash),
    )


def mark_claim_tx(
    conn: sqlite3.Connection,
    *,
    epoch_end_ts: int,
    market_id: str,
    claim_tx_hash: str,
) -> None:
    """Update an existing epoch_rewards row with a claim tx hash.

    `UPDATE epoch_rewards` must live ONLY in this file (single-writer lint).
    """
    conn.execute(
        "UPDATE epoch_rewards SET claimed=1, claim_tx_hash=? "
        "WHERE epoch_end_ts=? AND market_id=?",
        (claim_tx_hash, epoch_end_ts, market_id),
    )
