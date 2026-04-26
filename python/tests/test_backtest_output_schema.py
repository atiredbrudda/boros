"""BACK-05 — output schema round-trip and Hive-partitioned parquet layout.

Test functions:
  - test_backtest_run_output_round_trips_via_pydantic: model_dump → model_validate round-trip
  - test_parquet_partition_path_layout: write a row → lands at run_id=<ulid>/sweep_axis=base/results.parquet
  - test_path_traversal_guard_blocks_escape: malicious sweep_value raises ValueError
  - test_duckdb_query_round_trip: 3 rows written; DuckDB glob query returns 3 rows

Turns GREEN in Plan 05-05 when boros_brain.backtest.schemas and boros_brain.backtest.report land.

[[backtest-replay-engine-v05]]
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from boros_brain.backtest.report import (
    _ensure_under_root,  # noqa: PLC2701 — white-box guard test
    write_backtest_row,
)
from boros_brain.backtest.schemas import BacktestRunOutput
from boros_brain.config.schema import BotConfig

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def _make_row(
    *,
    run_id: str = "01HWABCDEF1234567890ABCDE0",
    sweep_axis: str = "base",
    sweep_value: float | str = 0.0,
    parent_run_id: str | None = None,
) -> BacktestRunOutput:
    """Build a minimal valid BacktestRunOutput for testing."""
    return BacktestRunOutput(
        run_id=run_id,
        parent_run_id=parent_run_id,
        git_sha="abc1234",
        strategy_version="v0.5",
        market_id=MARKET_ID,
        side="long",
        sweep_axis=sweep_axis,  # type: ignore[arg-type]
        sweep_value=sweep_value,
        bootstrap_idx=None,
        raw_pnl_pendle=1.5,
        raw_pnl_usd=3.0,
        annualized_pnl_pct=0.12,
        sharpe_equivalent=1.5,
        max_drawdown_pct=0.05,
        n_decisions=100,
        n_fills=2,
        n_cancels=10,
        n_purges=0,
        cumulative_fees_pendle=0.01,
        cumulative_gas_pendle=0.005,
        predicted_p_fill_mean=0.03,
        realized_fill_rate=0.02,
        calibration_residual=0.01,
        e_liq_calibrated_at="2026-04-26T00:00:00Z",
        event_index_coverage="full",
        voluntary_cancel_branch="benign",
        parquet_partition="run_id=01HWABCDEF1234567890ABCDE0/sweep_axis=base",
        plots_dir=None,
    )


def test_backtest_run_output_round_trips_via_pydantic(
    default_config: BotConfig,
) -> None:
    """BACK-05: BacktestRunOutput Pydantic model round-trips via model_dump → model_validate."""
    row = _make_row()
    dumped = row.model_dump(mode="json")
    restored = BacktestRunOutput.model_validate(dumped)
    assert restored == row


def test_parquet_partition_path_layout(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-05: write_backtest_row writes to run_id=<ulid>/sweep_axis=base/results.parquet."""
    # Base axis: no sweep_value directory
    run_id = "01HWABCDEF1234567890ABCDE0"
    base_row = _make_row(run_id=run_id, sweep_axis="base", sweep_value=0.0)
    base_path = write_backtest_row(base_row, parquet_root=tmp_path)
    expected_base = tmp_path / f"run_id={run_id}" / "sweep_axis=base" / "results.parquet"
    assert base_path == expected_base
    assert base_path.exists()

    # Cancel-latency axis: includes sweep_value directory
    run_id2 = "01HWABCDEF1234567890ABCDE1"
    cl_row = _make_row(run_id=run_id2, sweep_axis="cancel_latency", sweep_value=2.0)
    cl_path = write_backtest_row(cl_row, parquet_root=tmp_path)
    expected_cl = tmp_path / f"run_id={run_id2}" / "sweep_axis=cancel_latency" / "sweep_value=2.0" / "results.parquet"
    assert cl_path == expected_cl
    assert cl_path.exists()


def test_path_traversal_guard_blocks_escape(
    tmp_path: Path,
) -> None:
    """BACK-05 / T-05-07: _ensure_under_root raises ValueError when out_dir escapes parquet_root.

    White-box test: call _ensure_under_root directly with an out_dir that is clearly
    outside parquet_root. This avoids dependence on filesystem depth (how many ../
    are needed to escape a particular tmp_path on a given OS).
    """
    parquet_root = tmp_path / "inner"
    parquet_root.mkdir()
    outside_dir = tmp_path / "outside"  # sibling of inner — outside parquet_root

    with pytest.raises(ValueError, match="path traversal blocked"):
        _ensure_under_root(outside_dir.resolve(), parquet_root.resolve())


def test_duckdb_query_round_trip(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-05: write 3 rows to tmp_path; DuckDB glob query returns 3 rows."""
    rows = [_make_row(run_id=f"01HWABCDEF1234567890ABC{i:03d}"[:26], sweep_axis="base") for i in range(3)]
    for row in rows:
        write_backtest_row(row, parquet_root=tmp_path)

    conn = duckdb.connect(database=":memory:")
    glob_path = str(tmp_path / "**" / "*.parquet")
    result = conn.execute(f"SELECT * FROM read_parquet('{glob_path}', hive_partitioning=true)").fetchall()
    assert len(result) == 3
