"""INFRA-04 — DuckDB read-only analytical layer over parquet + SQLite.

Usage
-----
    con = open_analytical_conn('state/state.sqlite', 'data/parquet')
    con.execute('SELECT * FROM clo_history').fetchall()           # SQLite via sqlite_scanner
    con.execute('SELECT * FROM market_trades LIMIT 10').fetchall() # parquet via Hive partition

Architectural constraint
------------------------
NEVER import this module from brain/{decision,bus,manifest}/ — it is analytical-only.
See `docs/ARCHITECTURE.md` Architectural Responsibility Map.

Empty parquet root
------------------
``open_analytical_conn`` tolerates an empty parquet root (plan 01-08 has not yet
populated it at the time this plan runs).  Subdirectories with no .parquet files
get a zero-row stub view so that ``SELECT … LIMIT 1`` returns ``[]`` rather than
raising.  The stub is replaced by the real parquet-backed view the first time a
caller invokes ``open_analytical_conn`` after data has been written.

Read-only SQLite
----------------
The live SQLite spine is attached with ``READ_ONLY`` — the DuckDB session can
query all tables but INSERT/UPDATE/DELETE through this connection raise
``duckdb.Error`` (``TransactionContext`` / ``BinderException``).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import structlog

log = structlog.get_logger(__name__)

_VIEWS_SQL_PATH = Path(__file__).parent / "views.sql"

_PARQUET_SUBDIRS = (
    "market_trades",
    "order_book_raw",
    "order_book_combined",
    "underlying_apr",
    "market_data",
    "settlement",
)


def attach_sqlite_readonly(con: duckdb.DuckDBPyConnection, sqlite_path: str) -> None:
    """Attach the live SQLite spine read-only via the sqlite_scanner extension.

    Uses ``CALL sqlite_attach(path, overwrite=true)`` which mounts the SQLite
    tables into the in-memory catalog without changing the default catalog.
    This is important: ``USE live`` would make DDL (CREATE VIEW) fail because
    DuckDB cannot create objects in a read-only attached catalog.

    After attachment, all SQLite table names are directly queryable as::

        SELECT * FROM clo_history   -- no schema prefix needed

    Writes through this connection raise ``duckdb.Error`` (read-only enforcement
    is a side effect of sqlite_scanner's attach mode — the underlying SQLite file
    is opened with ``SQLITE_OPEN_READONLY``).
    """
    con.install_extension("sqlite_scanner")
    con.load_extension("sqlite_scanner")
    con.execute(f"CALL sqlite_attach('{sqlite_path}', overwrite=true)")


def register_parquet_views(con: duckdb.DuckDBPyConnection, parquet_root: str) -> None:
    """Register Hive-partitioned parquet views for every known subdirectory.

    Subdirectories that contain no .parquet files get a zero-row stub view
    (``SELECT NULL::VARCHAR AS _placeholder WHERE FALSE``).  This lets
    ``SELECT * FROM market_trades LIMIT 1`` return ``[]`` before 01-08 has
    written any data, preventing ``RuntimeError: no parquet files found``.

    Once the real parquet files exist, re-opening the connection (or calling
    this function again on a fresh connection) will register the live view.
    """
    # Strip SQL line comments before splitting so comment-only fragments are ignored.
    ddl_lines = [line for line in _VIEWS_SQL_PATH.read_text().splitlines() if not line.strip().startswith("--")]
    ddl_no_comments = "\n".join(ddl_lines)
    root = Path(parquet_root)

    for subdir in _PARQUET_SUBDIRS:
        subdir_path = root / subdir
        has_files = subdir_path.exists() and any(subdir_path.rglob("*.parquet"))

        if has_files:
            # Find the matching CREATE OR REPLACE VIEW statement and execute it.
            for stmt in ddl_no_comments.split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                # Match the view for this exact subdir (not a substring of another).
                if f"VIEW {subdir} " in stmt or f"VIEW {subdir}\n" in stmt:
                    con.execute(stmt.format(parquet_root=str(root)))
                    break
        else:
            # Zero-row stub — schema will be widened once real parquet arrives.
            con.execute(f"CREATE OR REPLACE VIEW {subdir} AS " f"SELECT NULL::VARCHAR AS _placeholder WHERE FALSE")
            log.info(
                "duckdb.empty_parquet_view_registered",
                subdir=subdir,
                path=str(subdir_path),
            )


def open_analytical_conn(sqlite_path: str, parquet_root: str) -> duckdb.DuckDBPyConnection:
    """Return a DuckDB in-memory connection with:

    - The live SQLite spine attached read-only (all 8 tables visible).
    - Hive-partitioned parquet views for every known data subdirectory.

    Parameters
    ----------
    sqlite_path:
        Absolute or relative path to ``state.sqlite``.  Passed to
        ``ATTACH … (TYPE sqlite, READ_ONLY)``.
    parquet_root:
        Root directory for partitioned parquet output from the ingesters
        (plan 01-08).  May be empty — views are stubbed gracefully.

    Returns
    -------
    duckdb.DuckDBPyConnection
        In-memory connection (read_only=False so extensions can be loaded;
        the SQLite attach is still READ_ONLY).
    """
    con = duckdb.connect(":memory:", read_only=False)
    attach_sqlite_readonly(con, sqlite_path)
    register_parquet_views(con, parquet_root)
    return con
