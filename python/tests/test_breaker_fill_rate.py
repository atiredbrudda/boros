"""SAFE-05 — FillRateBreaker tests (RED until 04-04 lands).

Covers:
  - test_fires_at_4_fills: 4 fills in 1 hour → K=4 >= threshold → PAUSE_AND_ALERT
  - test_silent_at_3_fills: 3 fills in 1 hour → K=3 < threshold → silent

The fill-rate circuit breaker fires when fills accumulate faster than
K_fills_per_hour (decision.breakers.fill_rate.k_fills_per_hour, default=4).
Fills are bad — runaway fill rate signals placement has drifted into the market.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-04.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.fill_rate")
FillRateBreaker = breakers_pkg.FillRateBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
CURRENT_TS = 1_700_000_000
ONE_HOUR_S = 3600


@pytest.mark.asyncio
async def test_fires_at_4_fills(
    tmp_path: Path,
    default_config: BotConfig,
    seed_tx_receipts_fills,
) -> None:
    """SAFE-05: 4 fills in last hour → K >= threshold → tripped=True, PAUSE_AND_ALERT."""
    db = seed_tx_receipts_fills(
        n_fills=4,
        since_chain_ts=CURRENT_TS - ONE_HOUR_S,
        market_id=MARKET_ID,
    )
    breaker = FillRateBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=CURRENT_TS,
    )
    assert sig.tripped is True, f"Expected tripped=True for 4 fills in {ONE_HOUR_S}s, got tripped=False"
    assert sig.kill_command_kind == "PAUSE_AND_ALERT"


@pytest.mark.asyncio
async def test_silent_at_3_fills(
    tmp_path: Path,
    default_config: BotConfig,
    seed_tx_receipts_fills,
) -> None:
    """SAFE-05: 3 fills in last hour → K < threshold → tripped=False."""
    db = seed_tx_receipts_fills(
        n_fills=3,
        since_chain_ts=CURRENT_TS - ONE_HOUR_S,
        market_id=MARKET_ID,
    )
    breaker = FillRateBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=CURRENT_TS,
    )
    assert sig.tripped is False, f"Expected tripped=False for 3 fills in {ONE_HOUR_S}s, got tripped=True"
