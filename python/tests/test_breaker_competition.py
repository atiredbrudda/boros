"""SAFE-06 — CompetitionBreaker tests (RED until 04-05 lands).

Covers:
  - test_fires_on_50_pct_drop: sigma_others drops >50% → tripped=True
  - test_silent_on_30_pct_drop: sigma_others drops 30% → tripped=False
  - test_silent_on_zero_baseline: sigma_others was 0 previously → tripped=False, reason='zero_baseline'

SAFE-06 detects a sudden collapse in competing order flow — if competition
disappears, the CLO range may be about to shift dramatically or the market is
becoming illiquid. Drop threshold default: 50% over one epoch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.competition")
CompetitionBreaker = breakers_pkg.CompetitionBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000
EPOCH_S = 7 * 86400  # 1 week


@pytest.mark.asyncio
async def test_fires_on_50_pct_drop(
    tmp_path: Path,
    default_config: BotConfig,
    seed_competition_history,
) -> None:
    """SAFE-06: sigma_others drops from 200 → 80 PENDLE (60% drop > 50%) → tripped.

    Two rows: one epoch ago sigma_others=200, now sigma_others=80.
    drop_pct = (200 - 80) / 200 = 0.60 > 0.50 → fires.
    """
    db = seed_competition_history(
        rows=[
            ("2026-04-18T00:00:00Z", BASE_TS - EPOCH_S, 10.0, 200.0),  # 1 epoch ago
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 80.0),             # now
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is True, (
        f"60% competition drop should trip SAFE-06, got tripped={sig.tripped} reason={sig.reason!r}"
    )


@pytest.mark.asyncio
async def test_silent_on_30_pct_drop(
    tmp_path: Path,
    default_config: BotConfig,
    seed_competition_history,
) -> None:
    """SAFE-06: sigma_others drops from 200 → 140 PENDLE (30% drop < 50%) → silent."""
    db = seed_competition_history(
        rows=[
            ("2026-04-18T00:00:00Z", BASE_TS - EPOCH_S, 10.0, 200.0),
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 140.0),
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
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
    """SAFE-06: lagged sigma_others == 0 → tripped=False, reason='zero_baseline'.

    Cannot compute a meaningful drop percentage from a zero baseline.
    The breaker must NOT fire (division-by-zero guard) and must document why.
    """
    db = seed_competition_history(
        rows=[
            ("2026-04-18T00:00:00Z", BASE_TS - EPOCH_S, 10.0, 0.0),   # baseline=0
            ("2026-04-25T00:00:00Z", BASE_TS, 10.0, 50.0),             # any current value
        ],
        market_id=MARKET_ID,
    )
    breaker = CompetitionBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS,
    )
    assert sig.tripped is False
    assert "zero_baseline" in sig.reason, (
        f"Expected reason='zero_baseline', got {sig.reason!r}"
    )
