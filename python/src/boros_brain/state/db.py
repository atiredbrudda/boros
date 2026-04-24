"""SQLite WAL connection helpers (INFRA-03).

Single-writer-per-table discipline is enforced at the application layer by
`scripts/sqlite_writer_lint.py` — this module only opens WAL connections and
clamps file permissions to 0o600 per the T-02-02 threat-mitigation.

Invariants every `open_connection()` call establishes:
  - `PRAGMA journal_mode = WAL` (many readers + one writer)
  - `PRAGMA synchronous = NORMAL` (WAL durable+fast combo)
  - `PRAGMA foreign_keys = ON` (required for run_manifests.parent_run_id FK;
    SQLite default is OFF, so this must be set per-connection)
  - `chmod 600` on the .sqlite file (and -wal / -shm siblings when present)
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def ensure_permissions_0600(path: Path) -> None:
    """Clamp 0o600 on the SQLite file and its -wal / -shm siblings.

    Called from `open_connection()` — not one-time-at-creation — because a crash
    during WAL truncation can leave fresh -wal/-shm files around that must also
    be owner-only.
    """
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            os.chmod(p, 0o600)


def enable_wal_mode(conn: sqlite3.Connection) -> None:
    """Apply the three PRAGMAs every boros SQLite connection requires.

    - journal_mode=WAL: many readers + one writer; cross-process safe via file lock.
    - synchronous=NORMAL: durable on power loss for WAL; ~2-5x faster than FULL.
    - foreign_keys=ON: enforces run_manifests.parent_run_id; SQLite default is OFF.
    """
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")


@contextmanager
def open_connection(path: Path | str) -> Iterator[sqlite3.Connection]:
    """Open a WAL-mode SQLite connection with FKs on. 0o600 perms.

    Creates parent dirs if they do not exist. Uses `isolation_level=None` —
    autocommit by default; callers that want explicit transactions issue
    `BEGIN`/`COMMIT` directly.

    Callers are responsible for committing their own writes. Writer modules in
    `state/writers/` follow the convention of NOT committing inside the insert
    helper — the caller owns the transaction lifecycle.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None => autocommit; use explicit BEGIN/COMMIT for batches.
    conn = sqlite3.connect(str(path), isolation_level=None)
    try:
        enable_wal_mode(conn)
        ensure_permissions_0600(path)
        yield conn
    finally:
        conn.close()
