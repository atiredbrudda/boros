"""Breaker ABC + BreakerSignal — shared contract for all 10 circuit breakers.

All breaker modules (SAFE-01..09 + B5) implement `Breaker` and return `BreakerSignal`.
The `BreakerCoordinator` (Plan 04-06) consumes `BreakerSignal` and owns the kill mutex.

[[circuit-breakers-v05]]: breaker taxonomy + BreakerSignal routing
[[ev-cancel-rule]]: kill authority integration with EV loop
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict

log = structlog.get_logger(__name__)


class BreakerSignal(BaseModel):
    """Structured signal returned by every Breaker.check() call.

    `tripped=True` → coordinator emits KillCmd on the rising edge (Pitfall #6
    hysteresis: one KillCmd per FIRST tripped cycle, not every cycle).

    kill_command_kind selects the SAFE-10 action from the 10-element Literal
    set. Default 'CANCEL_ALL' is conservative — every breaker overrides this
    to the most appropriate action per RESEARCH.md §per-breaker tables.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tripped: bool
    reason: str = ""
    payload: dict[str, Any] = {}
    kill_command_kind: Literal[
        "CANCEL_ALL",
        "EMERGENCY_CLOSE",
        "PAUSE_AND_ALERT",
        "ROLL_POSITION",
        "HALVE_POSITION_AND_ALERT",
        "HALT_AND_ALERT",
        "SHRINK_TO_Q_MIN",
        "CANCEL_ALL_HOLD_NO_REPLACE",
        "CANCEL_ALL_AND_RECALIBRATE",
        "CANCEL_ALL_AND_ALERT",
    ] = "CANCEL_ALL"


class Breaker(ABC):
    """Abstract base for every predictive circuit breaker.

    Subclasses must define `name` as a class-level string attribute and override
    `check()`. The coordinator calls `check()` every cycle with a 200ms timeout
    (Pitfall #1 — no breaker may block the 1 Hz loop).

    All I/O is via explicit arguments — breakers NEVER call wall-clock time functions,
    NEVER maintain open file handles, and NEVER write to SQLite directly (that is
    the coordinator's job via the breaker_events writer).
    """

    name: str

    @abstractmethod
    async def check(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        config: Any,
        current_chain_ts: int,
    ) -> BreakerSignal:
        """Evaluate the breaker condition and return a BreakerSignal.

        Parameters
        ----------
        sqlite_path:
            Path to the SQLite WAL state DB (open_connection handles WAL mode).
        w3:
            AsyncWeb3 instance for any on-chain reads needed.
        parquet_root:
            Root of the partitioned parquet data tree (underlying_apr, etc.).
        config:
            Live BotConfig — frozen, read-only.
        current_chain_ts:
            Chain-time in seconds (from chain_time.now_cached). NEVER use
            wall-clock inside check() — no_time_time_lint.py enforces this.
        """
        ...


__all__ = ["Breaker", "BreakerSignal"]
