"""SAFE-07 — MaturityBreaker: remaining reward < migration_cost → ROLL_POSITION.

Detects when a market is approaching maturity and the expected remaining reward
earnings cannot cover the cost of migrating to the next market. The operator
should roll the position before forced settlement.

migration_cost = (entrance_fee_pendle + 2 × cancel_cost_pendle) × buffer_pct

Dependency injection pattern: gas_cache is injected by the BreakerCoordinator
(Plan 04-06). Tests pass gas_cache=None and cancel_cost defaults to 0.0.

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
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Breaker, BreakerSignal
from ...state.writers.decisions import read_last_r_me_pendle

__all__ = ["MaturityBreaker"]


class MaturityBreaker(Breaker):
    """SAFE-07: fires when expected remaining reward < migration cost.

    gas_cache is dependency-injected by the coordinator (Plan 04-06).
    Pass gas_cache=None (default) in tests — cancel_cost is treated as 0.0.

    last_r_me_pendle kwarg in check(): test-only override so tests can inject
    a known reward rate without needing a populated decisions table. Production
    calls omit this kwarg and the breaker reads from SQLite.
    """

    name = "maturity"

    def __init__(self, gas_cache: Any = None) -> None:
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
        if self._gas_cache is not None and w3 is not None:
            cancel_cost = await self._gas_cache.cancel_cost_pendle(w3=w3, config=config)
        else:
            cancel_cost = 0.0  # test path (gas_cache=None)

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
