"""PROTO-01 — backtest CLI emits RUN_MANIFEST as first log line.

Test functions:
  - test_backtest_cli_emits_run_manifest_first: first log line is RUN_MANIFEST with mode='backtest'
  - test_backtest_writes_sidecar_json: <logs_dir>/<run_id>.manifest.json exists with full BotConfig.model_dump

Turns GREEN in Plan 05-09 when boros_brain.backtest.cli lands.

[[backtest-replay-engine-v05]]
"""
from __future__ import annotations

from pathlib import Path

import pytest

# RED state guard: module under test lands in Plan 05-09.
cli_mod = pytest.importorskip("boros_brain.backtest.cli")

from boros_brain.config.schema import BotConfig  # noqa: E402 — after importorskip


MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


def test_backtest_cli_emits_run_manifest_first(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """PROTO-01: backtest CLI first log line is RUN_MANIFEST with mode='backtest'.

    Invokes `python -m boros_brain.backtest run` via subprocess with a tiny
    synthetic config. Reads the first line of the log file and asserts it is a
    valid JSON RUN_MANIFEST with event='RUN_MANIFEST' and mode='backtest'.
    """
    pytest.skip("Plan 05-09 implements this — currently RED")


def test_backtest_writes_sidecar_json(
    tmp_path: Path,
    default_config: BotConfig,
) -> None:
    """PROTO-01: <logs_dir>/<run_id>.manifest.json exists with full BotConfig.model_dump.

    After a backtest run, the sidecar JSON must exist and contain the full
    BotConfig tree (including backtest.* knobs) plus run metadata.
    """
    pytest.skip("Plan 05-09 implements this — currently RED")
