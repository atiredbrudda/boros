"""SAFE-09 — UnderlyingStaleBreaker tests (RED until 04-05 lands).

Parametrized over exchange/age/expected_cadence tuples to verify the 2× cadence
staleness rule fires at the right boundary.

Covers:
  ("binance", 17_280, 28_800, False)  — 0.6× expected cadence → silent
  ("binance", 60_000, 28_800, True)   — 2.08× expected cadence → fires
  ("hyperliquid", 121, 60, True)      — 2.02× → fires
  ("hyperliquid", 119, 60, False)     — 1.98× → silent

The expected_cadence_s_per_exchange knob maps exchange name → cadence.
Binance: 8h = 28800s. Hyperliquid: 1min = 60s.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# RED state guard: module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.underlying_stale")
UnderlyingStaleBreaker = breakers_pkg.UnderlyingStaleBreaker

CURRENT_TS = 1_700_000_000


@pytest.mark.parametrize(
    "exchange, age_s, expected_cadence_s, should_fire",
    [
        ("binance", 17_280, 28_800, False),    # 0.60× cadence — fresh
        ("binance", 60_000, 28_800, True),     # 2.08× cadence — stale
        ("hyperliquid", 121, 60, True),        # 2.02× cadence — stale
        ("hyperliquid", 119, 60, False),       # 1.98× cadence — fresh
    ],
    ids=["binance_fresh", "binance_stale", "hyperliquid_stale", "hyperliquid_fresh"],
)
@pytest.mark.asyncio
async def test_underlying_stale_parametrized(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    seed_underlying_apr_parquet,
    exchange: str,
    age_s: int,
    expected_cadence_s: int,
    should_fire: bool,
) -> None:
    """SAFE-09: fires when underlying APR parquet data age > 2× expected cadence."""
    last_ts = CURRENT_TS - age_s
    parquet_root = seed_underlying_apr_parquet(
        last_ts=last_ts,
        exchange=exchange,
        symbol="ETHUSDT",
        parquet_root=tmp_path / "parquet",
    )

    # Build config with expected_cadence_s_per_exchange mapped.
    config_dict = default_config.model_dump(mode="json")
    config_dict.setdefault("decision", {}).setdefault("breakers", {}).setdefault(
        "underlying_stale", {}
    )["expected_cadence_s_per_exchange"] = {exchange: expected_cadence_s}
    patched_config = BotConfig.model_validate(config_dict)

    breaker = UnderlyingStaleBreaker()
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=parquet_root,
        config=patched_config,
        current_chain_ts=CURRENT_TS,
    )
    assert sig.tripped is should_fire, (
        f"exchange={exchange}, age_s={age_s}, cadence={expected_cadence_s}: "
        f"expected tripped={should_fire}, got tripped={sig.tripped} (reason={sig.reason!r}). "
        f"age/cadence ratio = {age_s/expected_cadence_s:.2f}× (fires at >2.0×)"
    )
