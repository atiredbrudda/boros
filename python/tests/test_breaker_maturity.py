"""SAFE-07 — MaturityBreaker tests.

Covers:
  - test_fires_when_remaining_below_migration_cost: maturity 1h away → ROLL_POSITION
  - test_silent_when_remaining_above_migration_cost: maturity 30d away → silent
  - test_no_decision_history_yet: no r_me history → tripped=False, reason='no_decision_history_yet'

SAFE-07 detects when a market is close to maturity and remaining reward-earning
time is less than the migration cost amortization buffer. The operator should
roll the position to the next market before maturity causes forced settlement.

migration_cost = entrance_fee_pendle + 2 × cancel_cost_pendle (cancel_cost=0 in tests)

As of Plan 04-07, tests inject a _FakeGasCache returning 0.0 cancel_cost.
The gas_cache parameter is mandatory (no None default) after this plan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boros_brain.config.schema import BotConfig

# Module lands in Plan 04-05.
breakers_pkg = pytest.importorskip("boros_brain.decision.breakers.maturity")
MaturityBreaker = breakers_pkg.MaturityBreaker

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
CURRENT_TS = 1_700_000_000
ONE_HOUR_S = 3600
THIRTY_DAYS_S = 30 * 86400


class _FakeGasCache:
    """Test stub for MaturityBreaker.gas_cache.

    Returns 0.0 from cancel_cost_pendle unconditionally — equivalent to the
    old `gas_cache=None` test path that was removed by Plan 04-07 to satisfy
    the DECIDE-03 lint (no hardcoded cancel_cost literals in decision/).
    """

    async def cancel_cost_pendle(self, *, w3, config) -> float:
        return 0.0


# Minimal market dict for maturity breaker tests.
_MARKET_DICT = {
    "market_id": MARKET_ID,
    "scale": 1.0,
    "s": 0.01,
    "clo_lower_thresh": 9300.0,
    "clo_upper_thresh": 9500.0,
    "fIndex_oracle_address": "0x0000000000000000000000000000000000000001",
    "maturity_ts": CURRENT_TS + THIRTY_DAYS_S,  # default; overridden per test
    "underlying_exchange": "binance",
    "underlying_symbol": "ETHUSDT",
}


def _config_with_market(base: BotConfig, maturity_ts: int) -> BotConfig:
    """Return a copy of base config with one market at the given maturity_ts."""
    d = base.model_dump(mode="json")
    market = dict(_MARKET_DICT)
    market["maturity_ts"] = maturity_ts
    d["markets"] = [market]
    return BotConfig.model_validate(d)


@pytest.mark.asyncio
async def test_fires_when_remaining_below_migration_cost(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-07: maturity 1 hour away + tiny remaining reward → ROLL_POSITION.

    With only 1 hour to maturity, expected rewards cannot cover migration cost.
    epochs_remaining ≈ 0.0059 (1h / 7d), last_r_me=0.001 PENDLE/epoch →
    expected = 5.9e-6 PENDLE < entrance_fee_pendle=0.5 PENDLE → fires.
    """
    config_dict = _config_with_market(default_config, CURRENT_TS + ONE_HOUR_S).model_dump(mode="json")
    config_dict["execution"]["entrance_fee_pendle"] = 0.5
    config = BotConfig.model_validate(config_dict)

    breaker = MaturityBreaker(gas_cache=_FakeGasCache())
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=CURRENT_TS,
        last_r_me_pendle=0.001,  # inject directly — no decisions table populated yet
    )
    assert sig.tripped is True, f"Expected tripped=True for maturity 1h away + tiny reward, got {sig.tripped}"
    assert sig.kill_command_kind == "ROLL_POSITION", f"Expected ROLL_POSITION, got {sig.kill_command_kind!r}"


@pytest.mark.asyncio
async def test_silent_when_remaining_above_migration_cost(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-07: maturity 30 days away + healthy reward → breaker silent.

    epochs_remaining ≈ 4.28 (30d / 7d), last_r_me=10 PENDLE/epoch →
    expected = 42.8 PENDLE >> entrance_fee_pendle=0.5 PENDLE → no fire.
    """
    config_dict = _config_with_market(default_config, CURRENT_TS + THIRTY_DAYS_S).model_dump(mode="json")
    config_dict["execution"]["entrance_fee_pendle"] = 0.5
    config = BotConfig.model_validate(config_dict)

    breaker = MaturityBreaker(gas_cache=_FakeGasCache())
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=CURRENT_TS,
        last_r_me_pendle=10.0,  # healthy reward
    )
    assert sig.tripped is False, f"Expected tripped=False for maturity 30d away, got tripped={sig.tripped}"


@pytest.mark.asyncio
async def test_no_decision_history_yet(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-07: no rows in decisions → tripped=False, reason='no_decision_history_yet'.

    Before the decision engine loop writes its first row, the breaker cannot
    compute expected_remaining_pendle. It must stay silent — not fire on missing data.
    """
    config = _config_with_market(default_config, CURRENT_TS + THIRTY_DAYS_S)

    # No last_r_me_pendle injected; SQLite has no decisions rows → returns None.
    breaker = MaturityBreaker(gas_cache=_FakeGasCache())
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=CURRENT_TS,
    )
    assert sig.tripped is False, f"Expected tripped=False with no decision history, got {sig.tripped}"
    assert sig.reason == "no_decision_history_yet", f"Expected reason='no_decision_history_yet', got {sig.reason!r}"


@pytest.mark.asyncio
async def test_fires_when_market_already_matured(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
) -> None:
    """SAFE-07: market_ts in the past → tripped=True, reason='market_matured'.

    The early-return branch (time_to_mat_s <= 0) fires unconditionally — no
    reward-history or gas-cache call is needed. This is the most urgent signal
    the breaker can emit and must not regress.
    """
    config = _config_with_market(default_config, CURRENT_TS - 1)  # past maturity
    breaker = MaturityBreaker(gas_cache=_FakeGasCache())
    sig = await breaker.check(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        config=config,
        current_chain_ts=CURRENT_TS,
    )
    assert sig.tripped is True, f"Expected tripped=True for already-matured market, got {sig.tripped}"
    assert sig.reason == "market_matured", f"Expected reason='market_matured', got {sig.reason!r}"
    assert (
        sig.kill_command_kind == "ROLL_POSITION"
    ), f"Expected kill_command_kind='ROLL_POSITION', got {sig.kill_command_kind!r}"
