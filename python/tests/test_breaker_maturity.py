"""SAFE-07 — MaturityBreaker tests (RED until 04-05 lands).

Covers:
  - test_fires_when_remaining_below_migration_cost: maturity 1 hour away → ROLL_POSITION
  - test_silent_when_remaining_above_migration_cost: maturity 30 days away → silent

SAFE-07 detects when a market is close to maturity and remaining reward-earning
time is less than the migration cost amortization buffer. The operator should
roll the position to the next market before maturity causes forced settlement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.maturity")
MaturityBreaker = breakers_pkg.MaturityBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
CURRENT_TS = 1_700_000_000
ONE_HOUR_S = 3600
THIRTY_DAYS_S = 30 * 86400


@pytest.mark.asyncio
async def test_fires_when_remaining_below_migration_cost(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-07: maturity 1 hour away + tiny remaining reward → ROLL_POSITION.

    With only 1 hour to maturity, expected rewards cannot cover migration cost.
    The breaker should fire with kill_command_kind=ROLL_POSITION.
    """
    # Patch config with maturity 1 hour from now.
    config_dict = default_config.model_dump(mode="json")
    if "markets" in config_dict and config_dict["markets"]:
        config_dict["markets"][0]["maturity_ts"] = CURRENT_TS + ONE_HOUR_S
    close_config = BotConfig.model_validate(config_dict)

    breaker = MaturityBreaker()
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=close_config,
        current_chain_ts=CURRENT_TS,
        last_r_me_pendle=0.001,  # tiny remaining reward
    )
    assert sig.tripped is True, (
        f"Expected tripped=True for maturity 1h away + tiny reward, got {sig.tripped}"
    )
    assert sig.kill_command_kind == "ROLL_POSITION", (
        f"Expected ROLL_POSITION, got {sig.kill_command_kind!r}"
    )


@pytest.mark.asyncio
async def test_silent_when_remaining_above_migration_cost(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-07: maturity 30 days away + healthy reward → breaker silent."""
    config_dict = default_config.model_dump(mode="json")
    if "markets" in config_dict and config_dict["markets"]:
        config_dict["markets"][0]["maturity_ts"] = CURRENT_TS + THIRTY_DAYS_S
    far_config = BotConfig.model_validate(config_dict)

    breaker = MaturityBreaker()
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=far_config,
        current_chain_ts=CURRENT_TS,
        last_r_me_pendle=10.0,  # healthy reward
    )
    assert sig.tripped is False, (
        f"Expected tripped=False for maturity 30d away, got tripped={sig.tripped}"
    )
