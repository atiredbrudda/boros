"""BACK-01 / B6 — reward budget lineage filter: replay reads only 'operator' rows.

Test functions:
  - test_replay_filters_synthetic_current_rows_via_sql: seed 2 rows (operator + synthetic_current); engine reads ONLY operator
  - test_replay_logs_warning_when_synthetic_current_present: warning log line lineage_filter.synthetic_current_rejected
  - test_replay_sql_filter_is_at_sql_layer_not_python: defensive grep — WHERE data_source MUST appear in replay.py

Turns GREEN in Plan 05-02 when boros_brain.backtest.replay lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-02.
# This importorskip also skips test_replay_sql_filter_is_at_sql_layer_not_python
# since relay.py does not yet exist.
replay = pytest.importorskip("boros_brain.backtest.replay")
ReplayEngine = replay.ReplayEngine

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_replay_filters_synthetic_current_rows_via_sql(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
) -> None:
    """BACK-01 / B6: replay reads ONLY rows with data_source='operator' from reward_budget_history.

    Seeds two reward_budget_history rows: one operator + one synthetic_current.
    The engine must use only the operator row for reward share calculations.
    """
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    # Seed reward_budget_history with operator + synthetic_current rows
    from boros_brain.state.db import open_connection
    with open_connection(tmp_sqlite_path) as conn:
        conn.executemany(
            "INSERT INTO reward_budget_history (market_id, epoch_start_ts, data_source, "
            "e_liq_per_epoch_pendle, long_side_split, short_side_split, recorded_at_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (MARKET_ID, 1_700_000_000, "operator", 100.0, 0.5, 0.5, 1_700_000_000),
                (MARKET_ID, 1_700_000_000, "synthetic_current", 999.0, 0.5, 0.5, 1_700_000_001),
            ],
        )
        conn.commit()

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-lineage-filter",
        manifest=None,
    )

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(engine.run())

    # Engine must have used e_liq=100.0 (operator) not 999.0 (synthetic_current)
    assert result is not None
    assert getattr(result, "reward_budget_source", "operator") == "operator"


def test_replay_logs_warning_when_synthetic_current_present(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_market_trades_parquet,
    seed_order_book_raw_parquet,
    seed_order_book_combined_parquet,
    caplog,
) -> None:
    """BACK-01 / B6: replay emits a warning log when synthetic_current rows are present in DB."""
    import logging
    parquet_root = seed_market_trades_parquet(market_id=MARKET_ID)
    seed_order_book_raw_parquet(market_id=MARKET_ID, parquet_root=parquet_root)
    seed_order_book_combined_parquet(market_id=MARKET_ID, parquet_root=parquet_root)

    from boros_brain.state.db import open_connection
    with open_connection(tmp_sqlite_path) as conn:
        conn.execute(
            "INSERT INTO reward_budget_history (market_id, epoch_start_ts, data_source, "
            "e_liq_per_epoch_pendle, long_side_split, short_side_split, recorded_at_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (MARKET_ID, 1_700_000_000, "synthetic_current", 999.0, 0.5, 0.5, 1_700_000_001),
        )
        conn.commit()

    engine = ReplayEngine(
        config=default_config,
        market_id=MARKET_ID,
        side="long",
        parquet_root=parquet_root,
        sqlite_path=tmp_sqlite_path,
        cancel_latency_s=1.0,
        run_id="test-lineage-warning",
        manifest=None,
    )

    with caplog.at_level(logging.WARNING):
        import asyncio
        asyncio.get_event_loop().run_until_complete(engine.run())

    assert any(
        "lineage_filter.synthetic_current_rejected" in record.message
        for record in caplog.records
    ), "Expected warning log 'lineage_filter.synthetic_current_rejected'"


def test_replay_sql_filter_is_at_sql_layer_not_python(
    tmp_path: Path,
) -> None:
    """BACK-01 / B6: defensive — WHERE data_source filter must be in replay.py SQL, not Python.

    Greps python/src/boros_brain/backtest/replay.py for 'WHERE data_source' or
    "data_source = 'operator'" to verify the filter is pushed to the SQL layer.
    """
    import re
    replay_src = Path(__file__).resolve().parents[2] / "python/src/boros_brain/backtest/replay.py"
    assert replay_src.exists(), f"replay.py not found at {replay_src} — Plan 05-02 must land it"

    content = replay_src.read_text()
    pattern = re.compile(r"data_source\s*=\s*['\"]operator['\"]|WHERE\s+data_source")
    assert pattern.search(content), (
        "replay.py must filter reward_budget_history rows via SQL "
        "(WHERE data_source = 'operator'), not in Python. "
        "B6 lineage guard requires the filter to be at the SQL layer."
    )
