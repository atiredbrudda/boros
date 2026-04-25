"""B5 absorbed — LossFitDegradedBreaker tests (RED until 04-04 lands).

Covers:
  - test_fires_on_degraded_status: fit_status='degraded' → SHRINK_TO_Q_MIN
  - test_silent_on_ok_status: fit_status='ok' → silent

B5 (loss-fit degraded) is absorbed into the breaker framework rather than
standing alone as a fallback. This ensures the operator is alerted when the
loss model grid quality has degraded below the threshold for safe EV computation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-04.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.loss_fit_degraded")
LossFitDegradedBreaker = breakers_pkg.LossFitDegradedBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"


@pytest.mark.asyncio
async def test_fires_on_degraded_status(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
) -> None:
    """B5: fit_status='degraded' → tripped=True, kill_command_kind=SHRINK_TO_Q_MIN.

    A degraded loss grid means E[loss|fill] estimates are unreliable;
    the EV computation is unsafe at full position size.
    """
    db = seed_loss_grid_artifact(
        fit_status="degraded",
        market_id=MARKET_ID,
        side="long",
    )
    breaker = LossFitDegradedBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=1_700_000_010,
    )
    assert sig.tripped is True, (
        f"fit_status='degraded' should trip B5, got tripped={sig.tripped}"
    )
    assert sig.kill_command_kind == "SHRINK_TO_Q_MIN", (
        f"Expected SHRINK_TO_Q_MIN, got {sig.kill_command_kind!r}"
    )


@pytest.mark.asyncio
async def test_silent_on_ok_status(
    tmp_path: Path,
    default_config: BotConfig,
    seed_loss_grid_artifact,
) -> None:
    """B5: fit_status='ok' → tripped=False (loss grid is healthy)."""
    db = seed_loss_grid_artifact(
        fit_status="ok",
        market_id=MARKET_ID,
        side="long",
    )
    breaker = LossFitDegradedBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=1_700_000_010,
    )
    assert sig.tripped is False, (
        f"fit_status='ok' should not trip B5, got tripped={sig.tripped}"
    )
