"""SAFE-03 — CloRemovalBreaker tests (RED until 04-04 lands).

Covers (parametrized):
  - (0.0, 100.0) → tripped=True (lower removed)
  - (100.0, 0.0) → tripped=True (upper removed)
  - (50.0, 100.0) → tripped=False (healthy range)
  - No rows → tripped=False, reason='no_clo_history_yet'

A market with CLO thresholds of zero is no longer incentivized — any active
position should be cancelled before the rewards epoch processes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-04.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.clo_removal")
CloRemovalBreaker = breakers_pkg.CloRemovalBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000


@pytest.mark.parametrize(
    "clo_lower, clo_upper, expected_tripped, expected_reason_fragment",
    [
        (0.0, 100.0, True, None),           # lower zero → incentive removed
        (100.0, 0.0, True, None),           # upper zero → incentive removed
        (50.0, 100.0, False, None),         # healthy range
        (None, None, False, "no_clo_history_yet"),  # no rows in DB
    ],
    ids=["lower_zero", "upper_zero", "healthy", "no_rows"],
)
@pytest.mark.asyncio
async def test_clo_removal_parametrized(
    tmp_path: Path,
    default_config: BotConfig,
    seed_clo_history,
    clo_lower: Optional[float],
    clo_upper: Optional[float],
    expected_tripped: bool,
    expected_reason_fragment: Optional[str],
) -> None:
    """SAFE-03 parametrized: (clo_lower, clo_upper) → expected trip state."""
    if clo_lower is not None and clo_upper is not None:
        db = seed_clo_history(
            rows=[(BASE_TS, clo_lower, clo_upper)],
            market_id=MARKET_ID,
        )
    else:
        # No rows — use empty migrated DB
        from tests.conftest import apply_migrations
        from boros_brain.state.db import open_connection

        db_path = tmp_path / "state_empty.sqlite"
        apply_migrations(db_path)
        db = db_path

    breaker = CloRemovalBreaker()
    sig = await breaker.check(
        sqlite_path=db,
        w3=None,
        parquet_root=tmp_path,
        config=default_config,
        current_chain_ts=BASE_TS + 10,
    )

    assert sig.tripped is expected_tripped, (
        f"clo_lower={clo_lower}, clo_upper={clo_upper}: "
        f"expected tripped={expected_tripped}, got {sig.tripped} (reason={sig.reason!r})"
    )
    if expected_reason_fragment:
        assert expected_reason_fragment in sig.reason, (
            f"Expected reason to contain {expected_reason_fragment!r}, got {sig.reason!r}"
        )
