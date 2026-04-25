"""SAFE-06 — CompetitionBreaker tests.

See [[breaker-competition-collapse]] and [[circuit-breakers-v05]].

Covers:
  - test_fires_on_50_pct_drop: Q_total drops >50% → tripped=True, PAUSE_AND_ALERT
  - test_silent_on_30_pct_drop: Q_total drops 30% → tripped=False
  - test_silent_on_zero_baseline: lag Q_total == 0 → tripped=False, reason='zero_baseline'
  - test_silent_on_insufficient_history: only 1 row → reason='insufficient_history' (Pitfall #3)

SAFE-06 detects a sudden collapse in competing order flow. Drop threshold default: 50%
over one epoch. Q_total = q_me_pendle + sigma_others_pendle.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# Module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.competition")
CompetitionBreaker = breakers_pkg.CompetitionBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000
EPOCH_S = 7 * 86400  # 1 week

# Minimal market dict that satisfies MarketCalibration schema for SAFE-06 tests.
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


def _config_with_market(base: BotConfig) -> BotConfig:
    """Return a copy of base config with one market appended."""
    d = base.model_dump(mode="json")
    d["markets"] = [_MARKET_DICT]
    return BotConfig.model_validate(d)


@pytest.mark.asyncio
async def test_fires_on_50_pct_drop(
    tmp_path: Path,
    default_config: BotConfig,
    seed_competition_history,
) -> None:
    """SAFE-06: Q_total drops from 200 → 80 PENDLE (60% drop > 50%) → tripped.

    lag row: q_me=10, sigma_others=190 → Q_total=200
    now row: q_me=10, sigma_others=70  → Q_total=80
    drop_pct = (200 - 80) / 200 = 0.60 > 0.50 → fires.
    """
    config = _config_with_market(default_config)
    db = seed_competition_history(
        rows=[
            ("2026-04-18T00:00:00Z", BASE_TS - EPOCH_S, 10.0, 190.0),  # 1 epoch ago, Q_total=200
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 70.0),             # now, Q_total=80
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is True, (
        f"60% competition drop should trip SAFE-06, got tripped={sig.tripped} reason={sig.reason!r}"
    )
    assert sig.kill_command_kind == "PAUSE_AND_ALERT"


@pytest.mark.asyncio
async def test_silent_on_30_pct_drop(
    tmp_path: Path,
    default_config: BotConfig,
    seed_competition_history,
) -> None:
    """SAFE-06: Q_total drops from 200 → 140 PENDLE (30% drop < 50%) → silent."""
    config = _config_with_market(default_config)
    db = seed_competition_history(
        rows=[
            ("2026-04-18T00:00:00Z", BASE_TS - EPOCH_S, 10.0, 190.0),  # Q_total=200
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 130.0),             # Q_total=140
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False, (
        f"30% competition drop should not trip SAFE-06, got tripped={sig.tripped}"
    )


@pytest.mark.asyncio
async def test_silent_on_zero_baseline(
    tmp_path: Path,
    default_config: BotConfig,
    seed_competition_history,
) -> None:
    """SAFE-06: lag Q_total == 0 → tripped=False, reason='zero_baseline'.

    Cannot compute a meaningful drop percentage from a zero baseline.
    The breaker must NOT fire (division-by-zero guard).
    """
    config = _config_with_market(default_config)
    db = seed_competition_history(
        rows=[
            ("2026-04-18T00:00:00Z", BASE_TS - EPOCH_S, 0.0, 0.0),   # Q_total=0 baseline
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 50.0),             # Q_total=60
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False
    assert "zero_baseline" in sig.reason, (
        f"Expected reason='zero_baseline', got {sig.reason!r}"
    )


@pytest.mark.asyncio
async def test_silent_on_insufficient_history(
    tmp_path: Path,
    default_config: BotConfig,
    seed_competition_history,
) -> None:
    """SAFE-06: only 1 row in history → reason='insufficient_history' (Pitfall #3).

    First-day operator-pause noise guard: breaker must NOT fire if there aren't
    at least 2 data points to compare (no epoch-lag row exists yet).
    """
    config = _config_with_market(default_config)
    db = seed_competition_history(
        rows=[
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 80.0),  # only 1 row
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False
    assert "insufficient_history" in sig.reason, (
        f"Expected reason='insufficient_history', got {sig.reason!r}"
    )
