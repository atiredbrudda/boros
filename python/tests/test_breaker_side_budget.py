"""SAFE-08 — SideBudgetBreaker tests (RED until 04-05 lands).

Covers:
  - test_fires_at_30_pct_drift: long_side_split drifts from 0.5 → 0.34 (32% drift) → tripped
  - test_silent_at_20_pct_drift: long_side_split drifts from 0.5 → 0.40 (20% drift) → silent

SAFE-08 detects when the per-side reward budget split has drifted significantly
since the operator calibrated placement. A 30%+ drift means the operator's
side-split assumption is stale and placement should be paused for recalibration.

drift_pct = |current_split - baseline_split| / baseline_split
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.side_budget")
SideBudgetBreaker = breakers_pkg.SideBudgetBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000
EPOCH_S = 7 * 86400  # 1 week (reward epoch)


@pytest.mark.asyncio
async def test_fires_at_30_pct_drift(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
) -> None:
    """SAFE-08: long_side_split drifts from 0.5 → 0.34 (32% > 30%) → tripped.

    drift_pct = |0.5 - 0.34| / 0.5 = 0.32 > 0.30 → fires with HALVE_POSITION_AND_ALERT.
    """
    # Baseline calibration (old epoch)
    db = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-18T00:00:00Z",  # 1 epoch ago
                "source": "dapp_ui",
            },
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.34,
                "short_side_split": 0.66,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",  # now
                "source": "dapp_ui",
            },
        ]
    )
    breaker = SideBudgetBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is True, (
        f"32% side-budget drift should trip SAFE-08, got tripped={sig.tripped}"
    )
    assert sig.kill_command_kind == "HALVE_POSITION_AND_ALERT"


@pytest.mark.asyncio
async def test_silent_at_20_pct_drift(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
) -> None:
    """SAFE-08: long_side_split drifts from 0.5 → 0.40 (20% < 30%) → silent.

    drift_pct = |0.5 - 0.40| / 0.5 = 0.20 < 0.30 → no fire.
    """
    db = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-18T00:00:00Z",
                "source": "dapp_ui",
            },
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.40,
                "short_side_split": 0.60,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",
                "source": "dapp_ui",
            },
        ]
    )
    breaker = SideBudgetBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False, (
        f"20% side-budget drift should not trip SAFE-08, got tripped={sig.tripped}"
    )
