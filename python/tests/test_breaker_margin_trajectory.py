"""SAFE-01 — MarginTrajectoryBreaker tests (RED until 04-04 lands).

Covers:
  - test_predicts_breach: downward slope → tripped=True
  - test_no_fire_when_growing: upward slope → tripped=False (Pitfall #4 sign guard)
  - test_no_fire_with_insufficient_history: n<min_samples → tripped=False

Pitfall #4: sign confusion — negative slope means margin is shrinking (bad),
positive slope means margin is growing (good). Breaker must NOT fire when growing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-04.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.margin_trajectory")
MarginTrajectoryBreaker = breakers_pkg.MarginTrajectoryBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000


@pytest.mark.asyncio
async def test_predicts_breach(
    tmp_path: Path,
    default_config: BotConfig,
    seed_margin_history,
) -> None:
    """SAFE-01: downward slope (-1 USD/s) over 20 samples → breaker fires.

    margin_trajectory reason must be present; kill_command_kind must be
    HALVE_POSITION_AND_ALERT or EMERGENCY_CLOSE.
    """
    db = seed_margin_history(slope=-1.0, n=20)
    breaker = MarginTrajectoryBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS + 20,
    )
    assert sig.tripped is True
    assert "margin_trajectory" in sig.reason
    assert sig.kill_command_kind in ("HALVE_POSITION_AND_ALERT", "EMERGENCY_CLOSE")


@pytest.mark.asyncio
async def test_no_fire_when_growing(
    tmp_path: Path,
    default_config: BotConfig,
    seed_margin_history,
) -> None:
    """SAFE-01 Pitfall #4 sign guard: upward slope (+1 USD/s) → breaker silent.

    Growing margin means collateral health is improving; no reason to fire.
    reason must contain 'growing' to confirm the branch was taken.
    """
    db = seed_margin_history(slope=+1.0, n=20)
    breaker = MarginTrajectoryBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS + 20,
    )
    assert sig.tripped is False
    assert "growing" in sig.reason


@pytest.mark.asyncio
async def test_no_fire_with_insufficient_history(
    tmp_path: Path,
    default_config: BotConfig,
    seed_margin_history,
) -> None:
    """SAFE-01: only 5 history samples → insufficient for fit → breaker silent.

    reason must contain 'insufficient_history' so the operator can distinguish
    a real pass from a pass caused by missing data.
    """
    db = seed_margin_history(slope=-1.0, n=5)
    breaker = MarginTrajectoryBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS + 5,
    )
    assert sig.tripped is False
    assert "insufficient_history" in sig.reason
