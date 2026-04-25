"""SAFE-07 — MaturityBreaker: remaining reward < migration_cost → ROLL_POSITION.

Detects when a market is approaching maturity and the expected remaining reward
earnings cannot cover the cost of migrating to the next market. The operator
should roll the position before forced settlement.

migration_cost = (entrance_fee_pendle + 2 × cancel_cost_pendle) × buffer_pct

Dependency injection pattern: gas_cache is dependency-injected (mandatory) by
the BreakerCoordinator in production and by a fake stub in tests. The DECIDE-03
invariant requires cancel_cost to flow exclusively from gas_history.GasHistoryCache.
As of Plan 04-07 (2026-04-25), gas_cache is a mandatory argument — there is no
gas_cache=None default. Tests inject a _FakeGasCache stub returning 0.0.

last_r_me_pendle: populated by Plan 04-06's decision engine loop writing
r_share_per_epoch_pendle to state.decisions. Until that loop writes its first
row, read_last_r_me_pendle returns None and the breaker returns
reason='no_decision_history_yet'.

STRIDE: T-04-05-06 — ROLL_POSITION signal is persisted to state.breaker_events
by the coordinator; operator manually confirms the roll by updating BotConfig.
v0.5 has no auto-roll.

[[breaker-maturity-migration]]: SAFE-07 spec, migration_cost formula, ROLL_POSITION
semantics, operator workflow
[[boros-fee-schedule]]: entrance_fee + cancel cost reference values
[[circuit-breakers-v05]]: breaker taxonomy + routing
[[gas-history-ewma-cancel-cost]]: DECIDE-03 cancel-cost flow / GasHistoryCache contract
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Breaker, BreakerSignal
from ...state.writers.decisions import read_last_r_me_pendle

__all__ = ["MaturityBreaker"]


class MaturityBreaker(Breaker):
    """SAFE-07: fires when expected remaining reward < migration cost.

    gas_cache is dependency-injected (mandatory) by the BreakerCoordinator in
    production (main.py:221: MaturityBreaker(gas_cache=gas_cache)) and by a
    _FakeGasCache stub in tests. The DECIDE-03 invariant requires cancel_cost
    to flow exclusively from gas_history.GasHistoryCache — no hardcoded
    scalars in decision/. The lint script scripts/no_hardcoded_cancel_cost_lint.py
    enforces this invariant mechanically.

    last_r_me_pendle kwarg in check(): test-only override so tests can inject
    a known reward rate without needing a populated decisions table. Production
    calls omit this kwarg and the breaker reads from SQLite.
    """

    name = "maturity"

    def __init__(self, gas_cache: Any) -> None:
        self._gas_cache = gas_cache

    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
        last_r_me_pendle: float | None = None,  # test injection override
    ) -> BreakerSignal:
        """Evaluate SAFE-07 maturity migration condition."""
        cfg = config.decision.breakers.maturity
        market = config.markets[0]

        time_to_mat_s = market.maturity_ts - current_chain_ts
        if time_to_mat_s <= 0:
            return BreakerSignal(
                tripped=True,
                reason="market_matured",
                kill_command_kind="ROLL_POSITION",
            )

        epochs_remaining = time_to_mat_s / (config.reward_share_model.epoch_days * 86400)

        # Use injected value (tests) or read from SQLite (production).
        if last_r_me_pendle is None:
            last_r_me_pendle = read_last_r_me_pendle(
                sqlite_path, market.market_id, config.side
            )

        if last_r_me_pendle is None:
            return BreakerSignal(
                tripped=False,
                reason="no_decision_history_yet",
            )

        expected_remaining_pendle = epochs_remaining * last_r_me_pendle

        # migration_cost = entrance_fee + 2 × cancel_cost, times the buffer multiplier.
        # cancel_cost is sourced unconditionally from the injected gas cache
        # (DECIDE-03 invariant — gas_history.GasHistoryCache is the single source).
        # Tests inject a _FakeGasCache returning 0.0; production injects the real
        # GasHistoryCache instance via BreakerCoordinator (see main.py:221).
        cancel_cost = await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)

        migration_cost = (
            config.execution.entrance_fee_pendle + 2.0 * cancel_cost
        ) * cfg.migration_cost_buffer_pct

        if expected_remaining_pendle < migration_cost:
            return BreakerSignal(
                tripped=True,
                reason="maturity_migration_due",
                payload={
                    "epochs_remaining": epochs_remaining,
                    "expected_pendle": expected_remaining_pendle,
                    "migration_cost_pendle": migration_cost,
                },
                kill_command_kind="ROLL_POSITION",
            )

        return BreakerSignal(
            tripped=False,
            reason="ok",
            payload={
                "epochs_remaining": epochs_remaining,
                "expected_pendle": expected_remaining_pendle,
            },
        )
