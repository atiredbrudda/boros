"""SAFE-08 — SideBudgetBreaker tests.

Covers:
  - test_fires_at_30_pct_drift: long_side_split drifts 0.5 → 0.34 (32%) → tripped
  - test_silent_at_20_pct_drift: long_side_split drifts 0.5 → 0.40 (20%) → silent
  - test_silent_on_zero_baseline_split: lag long_side_split == 0 → tripped=False
  - test_silent_on_insufficient_history: only 1 row → reason='insufficient_calibration_history'

SAFE-08 detects when the per-side reward budget split has drifted significantly
since the operator calibrated placement. A 30%+ drift means the operator's
side-split assumption is stale and placement should be paused for recalibration.

drift_pct = (lag_split - latest_split) / lag_split
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# Module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.side_budget")
SideBudgetBreaker = breakers_pkg.SideBudgetBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000
EPOCH_S = 7 * 86400  # 1 week (reward epoch)

# Minimal market dict for side budget breaker tests.
_MARKET_DICT = {
    "market_id": MARKET_ID,
    "scale": 1.0,
    "s": 0.01,
    "clo_lower_thresh": 9300.0,
    "clo_upper_thresh": 9500.0,
    "fIndex_oracle_address": "0x0000000000000000000000000000000000000001",
    "maturity_ts": BASE_TS + 30 * 86400,
    "underlying_exchange": "binance",
    "underlying_symbol": "ETHUSDT",
}


def _config_with_market(base: BotConfig, side: str = "long") -> BotConfig:
    """Return a copy of base config with one market and specified side."""
    d = base.model_dump(mode="json")
    d["markets"] = [_MARKET_DICT]
    d["side"] = side
    return BotConfig.model_validate(d)


@pytest.mark.asyncio
async def test_fires_at_30_pct_drift(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
) -> None:
    """SAFE-08: long_side_split drifts from 0.5 → 0.34 (32% > 30%) → tripped.

    drift_pct = (0.5 - 0.34) / 0.5 = 0.32 > 0.30 → fires with HALVE_POSITION_AND_ALERT.
    """
    config = _config_with_market(default_config, side="long")
    db = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-18T00:00:00Z",  # 1 epoch ago (lag)
                "source": "dapp_ui",
            },
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.34,
                "short_side_split": 0.66,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",  # now (latest)
                "source": "dapp_ui",
            },
        ]
    )
    breaker = SideBudgetBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=config,
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

    drift_pct = (0.5 - 0.40) / 0.5 = 0.20 < 0.30 → no fire.
    """
    config = _config_with_market(default_config, side="long")
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
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False, (
        f"20% side-budget drift should not trip SAFE-08, got tripped={sig.tripped}"
    )


@pytest.mark.asyncio
async def test_silent_on_zero_baseline_split(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
) -> None:
    """SAFE-08: lag long_side_split == 0 → tripped=False, reason='zero_baseline_split'.

    Cannot compute drift percentage from a zero baseline without division by zero.
    """
    config = _config_with_market(default_config, side="long")
    db = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.0,
                "short_side_split": 1.0,
                "calibrated_at_utc": "2026-04-18T00:00:00Z",  # lag row: long_side_split=0
                "source": "dapp_ui",
            },
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
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
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False
    assert sig.reason == "zero_baseline_split", (
        f"Expected reason='zero_baseline_split', got {sig.reason!r}"
    )


@pytest.mark.asyncio
async def test_silent_on_insufficient_history(
    tmp_path: Path,
    default_config: BotConfig,
    seed_market_reward_calibration,
) -> None:
    """SAFE-08: only 1 calibration row → reason='insufficient_calibration_history' (Pitfall #3).

    First-day operator-pause noise guard: the breaker must NOT fire if there
    aren't at least 2 calibration rows available.
    """
    config = _config_with_market(default_config, side="long")
    db = seed_market_reward_calibration(
        [
            {
                "market_id": MARKET_ID,
                "e_liq_per_epoch_pendle": 1000.0,
                "long_side_split": 0.5,
                "short_side_split": 0.5,
                "calibrated_at_utc": "2026-04-25T00:00:00Z",  # only 1 row
                "source": "dapp_ui",
            },
        ]
    )
    breaker = SideBudgetBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False
    assert "insufficient_calibration_history" in sig.reason, (
        f"Expected reason containing 'insufficient_calibration_history', got {sig.reason!r}"
    )
