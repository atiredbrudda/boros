"""SAFE-04 — CloShiftBreaker tests (RED until 04-04 lands).

Covers:
  - test_fires_on_n_tick_shift: >5 tick shift between two CLO snapshots → tripped
  - test_silent_under_threshold: <5 tick shift → silent
  - test_stay_out_of_range_branch_under_punitive: A1×A3 compound — same trigger scenario
    but with voluntary_cancel_forfeits_accumulated=True → CANCEL_ALL_HOLD_NO_REPLACE

Tick scale: config.markets[0].scale = 10000 (Binance ETH-rate market).
5 ticks = 5/10000 = 0.0005 APR shift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-04.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.clo_shift")
CloShiftBreaker = breakers_pkg.CloShiftBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000
SCALE = 10_000  # APR ticks scale for ETHUSDT markets
TICK_THRESHOLD = 5  # decision.breakers.clo_shift.n_ticks default


def _clo_value(ticks: int) -> float:
    """Convert tick count to CLO threshold float value."""
    return ticks / SCALE


@pytest.mark.asyncio
async def test_fires_on_n_tick_shift(
    tmp_path: Path,
    default_config: BotConfig,
    seed_clo_history,
) -> None:
    """SAFE-04: CLO lower shifts by 6 ticks (>5 threshold) → breaker fires.

    seed: (BASE_TS, clo_lower=9300, upper=9500), (BASE_TS+1, clo_lower=9306, upper=9500)
    shift_ticks = 9306 - 9300 = 6 > 5 → CANCEL_ALL_AND_RECALIBRATE
    """
    old_lower = 9300.0
    new_lower = 9306.0  # 6 tick shift (>5)
    db = seed_clo_history(
        rows=[
            (BASE_TS, old_lower, 9500.0),
            (BASE_TS + 60, new_lower, 9500.0),
        ],
        market_id=MARKET_ID,
    )
    breaker = CloShiftBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS + 60,
    )
    assert sig.tripped is True
    assert sig.kill_command_kind == "CANCEL_ALL_AND_RECALIBRATE"


@pytest.mark.asyncio
async def test_silent_under_threshold(
    tmp_path: Path,
    default_config: BotConfig,
    seed_clo_history,
) -> None:
    """SAFE-04: CLO lower shifts by 3 ticks (<5 threshold) → breaker silent."""
    old_lower = 9300.0
    new_lower = 9303.0  # 3 tick shift (<5)
    db = seed_clo_history(
        rows=[
            (BASE_TS, old_lower, 9500.0),
            (BASE_TS + 60, new_lower, 9500.0),
        ],
        market_id=MARKET_ID,
    )
    breaker = CloShiftBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS + 60,
    )
    assert sig.tripped is False


@pytest.mark.asyncio
async def test_stay_out_of_range_branch_under_punitive(
    tmp_path: Path,
    default_config: BotConfig,
    seed_clo_history,
) -> None:
    """SAFE-04 A1×A3 compound: CLO shift + punitive branch → CANCEL_ALL_HOLD_NO_REPLACE.

    When voluntary_cancel_forfeits_accumulated=True (punitive branch), a CLO shift
    that would normally trigger CANCEL_ALL_AND_RECALIBRATE instead triggers
    CANCEL_ALL_HOLD_NO_REPLACE to avoid forfeiting sunk rewards unnecessarily.

    A1 = voluntary cancel branch decision
    A3 = CLO shift out-of-range response
    """
    old_lower = 9300.0
    new_lower = 9306.0  # 6 tick shift — triggers the breaker
    db = seed_clo_history(
        rows=[
            (BASE_TS, old_lower, 9500.0),
            (BASE_TS + 60, new_lower, 9500.0),
        ],
        market_id=MARKET_ID,
    )

    # Clone config with punitive branch enabled.
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("strategy", {})
    config_dict["strategy"]["voluntary_cancel_forfeits_accumulated"] = True
    punitive_config = BotConfig.model_validate(config_dict)

    breaker = CloShiftBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=punitive_config,
        current_chain_ts=BASE_TS + 60,
    )
    assert sig.tripped is True
    assert sig.kill_command_kind == "CANCEL_ALL_HOLD_NO_REPLACE", (
        f"A1×A3 compound under punitive branch: expected CANCEL_ALL_HOLD_NO_REPLACE, " f"got {sig.kill_command_kind!r}"
    )
