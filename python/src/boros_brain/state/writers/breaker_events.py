"""Single writer for the `breaker_events` table (brain-owned). Plan 04-02.

PROTO-02 single-writer discipline: any module outside this file that writes to
breaker_events is a bug. BreakerCoordinator.tick + BreakerCoordinator.gate are
the only callers.

Append-only audit log: every trip, suppression, and re-arm event is persisted
here. Pitfall #2 (never accumulate in-memory): if the breaker coordinator crashes
and restarts, the coordinator reconstructs state from this table — not from
process memory.

[[breaker-coordinator-kill-mutex]]: coordinator owns the kill mutex + persists via this writer
"""

from __future__ import annotations

import sqlite3
from typing import Literal

_ALLOWED: frozenset[str] = frozenset({"kill_emitted", "suppression", "rearmed"})

__all__ = ["insert_breaker_event"]


def insert_breaker_event(
    conn: sqlite3.Connection,
    *,
    kind: Literal["kill_emitted", "suppression", "rearmed"],
    breaker_name: str,
    reason: str,
    chain_ts: int,
    run_id: str,
    payload_json: str | None = None,
) -> None:
    """Insert one breaker_events audit row.

    Validates `kind` against the allowed literal set BEFORE the SQL CHECK fires,
    to produce a clean Python ValueError rather than a cryptic sqlite3.IntegrityError.
    Matches competition_history.py lines 33-36 validation pattern.

    Caller owns transaction lifecycle — NO conn.commit() here (db.py contract).

    Parameters
    ----------
    conn:
        Open SQLite WAL connection (brain-owned).
    kind:
        Event type: 'kill_emitted' | 'suppression' | 'rearmed'.
        kill_emitted  — KillCmd was sent on the rising edge (first trip cycle).
        suppression   — A PLACE or CANCEL cmd was suppressed while breaker active.
        rearmed       — Breaker re-armed after min_re_arm_s elapsed.
    breaker_name:
        Name of the breaker that fired (e.g. 'margin_trajectory').
    reason:
        Human-readable reason string from BreakerSignal.reason.
    chain_ts:
        Chain-time in seconds when the event occurred.
    run_id:
        Active run_id for traceability.
    payload_json:
        JSON-serialized BreakerSignal payload for full audit trail.
    """
    if kind not in _ALLOWED:
        raise ValueError(
            f"breaker_events.kind={kind!r} not in {sorted(_ALLOWED)}. "
            "Use 'kill_emitted', 'suppression', or 'rearmed'."
        )
    conn.execute(
        "INSERT INTO breaker_events "
        "(kind, breaker_name, reason, chain_ts, run_id, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kind, breaker_name, reason, chain_ts, run_id, payload_json),
    )
