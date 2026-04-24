"""INFRA-04 DuckDB analytical layer tests — TDD RED/GREEN for plan 01-07 Task 2."""

import pathlib
import re
import sqlite3

import polars as pl
import pytest

from boros_brain.duckdb_layer.setup import open_analytical_conn

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_sqlite_with_clo(tmp_path: pathlib.Path) -> str:
    """Minimal SQLite with a clo_history table + one row."""
    db = tmp_path / "state.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE clo_history " "(market_id TEXT, cloLower REAL, cloUpper REAL, ts INTEGER)")
    conn.execute("INSERT INTO clo_history VALUES ('ETH', 9300.0, 9500.0, 1700000000)")
    conn.commit()
    conn.close()
    return str(db)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_attach_sqlite_readonly(tmp_sqlite_with_clo: str, tmp_path: pathlib.Path) -> None:
    """SQLite tables are readable; writes through the DuckDB conn must raise."""
    parquet_root = tmp_path / "parquet"
    parquet_root.mkdir()
    con = open_analytical_conn(tmp_sqlite_with_clo, str(parquet_root))
    result = con.execute("SELECT COUNT(*) FROM clo_history").fetchone()
    assert result is not None
    assert result[0] == 1
    # Read-only enforcement: INSERT must raise (DuckDB raises duckdb.Error or subclass)
    import duckdb

    with pytest.raises(duckdb.Error):
        con.execute("INSERT INTO clo_history VALUES ('BTC', 309.6, 316.3, 1700000001)")
        con.commit()


def test_parquet_views_graceful_on_empty_root(tmp_sqlite_with_clo: str, tmp_path: pathlib.Path) -> None:
    """open_analytical_conn does NOT raise when the parquet root is empty.

    Querying an empty-root view must return 0 rows (not raise).
    """
    parquet_root = tmp_path / "empty_parquet"
    parquet_root.mkdir()
    con = open_analytical_conn(tmp_sqlite_with_clo, str(parquet_root))
    rows = con.execute("SELECT * FROM market_trades LIMIT 1").fetchall()
    assert rows == []


def test_parquet_views_with_sample_data(tmp_sqlite_with_clo: str, tmp_path: pathlib.Path) -> None:
    """Parquet files written under the Hive layout are visible via the view."""
    parquet_root = tmp_path / "parquet"
    mt = parquet_root / "market_trades" / "market_id=ETH" / "year_month=2025-08"
    mt.mkdir(parents=True)
    df = pl.DataFrame(
        {
            "eventIndex": [363_716_829_000_015, 363_716_829_000_016],
            "blockTimestamp": [1_754_021_093, 1_754_021_094],
            "rate": [0.073_32, 0.073_33],
            "side": ["short", "long"],
            "size_float": [0.005, 0.010],
            "txHash": ["0xaa", "0xbb"],
        }
    )
    df.write_parquet(str(mt / "part-0.parquet"))
    con = open_analytical_conn(tmp_sqlite_with_clo, str(parquet_root))
    n = con.execute("SELECT COUNT(*) FROM market_trades").fetchone()
    assert n is not None
    assert n[0] == 2


def test_views_sql_file_contains_expected_views() -> None:
    """views.sql must declare all five required views."""
    views_sql = pathlib.Path(__file__).resolve().parents[1] / "src/boros_brain/duckdb_layer/views.sql"
    content = views_sql.read_text()
    for v in (
        "market_trades",
        "order_book_raw",
        "order_book_combined",
        "underlying_apr",
        "market_data",
    ):
        assert f"CREATE OR REPLACE VIEW {v}" in content, f"view {v} missing from views.sql"


def test_duckdb_layer_not_imported_from_hotpath() -> None:
    """Architectural Responsibility Map: duckdb_layer MUST NOT be imported from
    brain/{decision,bus,manifest} — it is an analytical layer only."""
    root = pathlib.Path(__file__).resolve().parents[1] / "src/boros_brain"
    forbidden = (root / "decision", root / "bus", root / "manifest")
    pattern = re.compile(r"from\s+boros_brain\.duckdb_layer|import\s+boros_brain\.duckdb_layer")
    for d in forbidden:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            text = py.read_text()
            assert not pattern.search(text), f"{py} illegally imports duckdb_layer (hot-path pollution)"
