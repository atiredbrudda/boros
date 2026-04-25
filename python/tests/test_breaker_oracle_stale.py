"""SAFE-02 — OracleStaleBreaker tests (RED until 04-04 lands).

Covers:
  - test_fires_above_threshold: age_s > 0.70 * max_update_delay → tripped
  - test_silent_below_threshold: age_s <= 0.70 * max_update_delay → silent
  - test_boundary_exactly_at_threshold: age_s == 0.70 * max_update_delay → silent
    (strict inequality per RESEARCH §SAFE-02: fires when age_s > 0.7*max_delay)

See RESEARCH.md §SAFE-02 lines ~530-540 for the fIndex staleness threshold.
The 0.7 fraction is the SAFE-02 config knob (decision.breakers.oracle_stale.fraction_of_max).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-04.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.oracle_stale")
OracleStaleBreaker = breakers_pkg.OracleStaleBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
CURRENT_TS = 1_700_000_000
MAX_UPDATE_DELAY = 3600  # 1 hour — typical fIndex oracle maxUpdateDelay
THRESHOLD_FRACTION = 0.70


def _mock_findex_reader(f_time: int):
    """Return a mock findex_reader that returns the given f_time."""
    reader = MagicMock()
    reader.read_latest_findex = AsyncMock(
        return_value=type("FIndex", (), {"f_time": f_time})()
    )
    return reader


@pytest.mark.asyncio
async def test_fires_above_threshold(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-02: age_s = 0.71 * max_update_delay > 0.70 → breaker fires."""
    age_s = int(0.71 * MAX_UPDATE_DELAY)
    f_time = CURRENT_TS - age_s

    breaker = OracleStaleBreaker()
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=CURRENT_TS,
        f_time=f_time,
        max_update_delay=MAX_UPDATE_DELAY,
    )
    assert sig.tripped is True, (
        f"Expected tripped=True for age_s={age_s} > 0.7*{MAX_UPDATE_DELAY}={0.7*MAX_UPDATE_DELAY}"
    )


@pytest.mark.asyncio
async def test_silent_below_threshold(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-02: age_s = 0.69 * max_update_delay < 0.70 → breaker silent."""
    age_s = int(0.69 * MAX_UPDATE_DELAY)
    f_time = CURRENT_TS - age_s

    breaker = OracleStaleBreaker()
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=CURRENT_TS,
        f_time=f_time,
        max_update_delay=MAX_UPDATE_DELAY,
    )
    assert sig.tripped is False, (
        f"Expected tripped=False for age_s={age_s} <= 0.7*{MAX_UPDATE_DELAY}"
    )


@pytest.mark.asyncio
async def test_boundary_exactly_at_threshold(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-02: age_s exactly = 0.70 * max_update_delay → silent (strict >).

    Per RESEARCH.md §SAFE-02: fires when age_s > 0.7 * max_delay (strict inequality).
    Exact boundary is NOT a trip — only strictly above triggers.
    """
    age_s = int(THRESHOLD_FRACTION * MAX_UPDATE_DELAY)
    f_time = CURRENT_TS - age_s

    breaker = OracleStaleBreaker()
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=CURRENT_TS,
        f_time=f_time,
        max_update_delay=MAX_UPDATE_DELAY,
    )
    assert sig.tripped is False, (
        f"Boundary at exactly 0.70*max_delay should be silent (strict >); got tripped=True"
    )
