"""Single writer for the `reward_budget_history` table (brain-owned).

PROTO-02 single-writer discipline. DATA-11 polled E_liq writes here only.

**B6 pitfall guard:** `data_source` must be 'polled' (forward-only live poll)
or 'synthetic_current' (historical backfill reconstructed from current budget).
The DB CHECK constraint enforces this at the SQL layer; this writer also rejects
invalid values at the Python layer so callers get a clean error before the SQL
round-trip. Phase-5 backtest filters rows by `data_source='polled'` to avoid
current-budget-synthetic leakage into historical P&L.

**Anti-pattern 4 guard (ARCHITECTURE.md §9 / PITFALLS §A2):**
E_liq_per_epoch rebalances dynamically per epoch. NEVER cache across polls.
Downstream readers (DATA-09, Phase 3 reward model) read the MOST RECENT row
ordered by `polled_at_utc DESC LIMIT 1`.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Literal

DataSource = Literal["polled", "synthetic_current"]
_ALLOWED: frozenset[str] = frozenset({"polled", "synthetic_current"})


def insert_reward_budget_row(
    conn: sqlite3.Connection,
    *,
    market_id: str,
    e_liq_per_epoch: float,
    long_budget: float,
    short_budget: float,
    chain_ts: int,
    run_id: str,
    data_source: DataSource = "polled",
) -> None:
    """Insert one reward-budget snapshot row.

    Writes `polled_at_utc` as the current UTC wall-clock time (ISO8601).
    `chain_ts` is the on-chain block timestamp from `get_chain_time_cached()`.

    Raises `ValueError` if `data_source` is not in {'polled', 'synthetic_current'}
    — the SQL CHECK constraint would also reject it, but surfacing a ValueError
    before the DB round-trip gives the caller a clearer stack trace (B6 guard).

    Single-writer discipline: this is the ONLY module allowed to INSERT into
    `reward_budget_history`. `scripts/sqlite_writer_lint.py` enforces this.
    """
    if data_source not in _ALLOWED:
        raise ValueError(f"data_source={data_source!r} not in {sorted(_ALLOWED)} (B6 pitfall guard)")
    conn.execute(
        "INSERT INTO reward_budget_history "
        "(polled_at_utc, chain_ts, market_id, e_liq_per_epoch, long_budget, short_budget, run_id, data_source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(UTC).isoformat(),
            chain_ts,
            market_id,
            e_liq_per_epoch,
            long_budget,
            short_budget,
            run_id,
            data_source,
        ),
    )
    conn.commit()
