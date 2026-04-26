"""BACK-05 — output schema round-trip and Hive-partitioned parquet layout.

Test functions:
  - test_backtest_run_output_round_trips_via_pydantic: model_dump → model_validate round-trip
  - test_parquet_partition_path_layout: write a row → lands at run_id=<ulid>/sweep_axis=base/results.parquet

Turns GREEN in Plan 05-05 when boros_brain.backtest.schemas and boros_brain.backtest.report land.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: modules under test land in Plan 05-05.
schemas_mod = pytest.importorskip("boros_brain.backtest.schemas")
BacktestRunOutput = schemas_mod.BacktestRunOutput
report_mod = pytest.importorskip("boros_brain.backtest.report")
write_backtest_row = report_mod.write_backtest_row

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_backtest_run_output_round_trips_via_pydantic(
    default_config: BotConfig,
) -> None:
    """BACK-05: BacktestRunOutput Pydantic model round-trips via model_dump → model_validate."""
    pytest.skip("Plan 05-05 implements this — currently RED")


def test_parquet_partition_path_layout(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """BACK-05: write_backtest_row writes to run_id=<ulid>/sweep_axis=base/results.parquet."""
    pytest.skip("Plan 05-05 implements this — currently RED")
