"""INFRA-14 — Chain-time cache + drift monitor.

Every chain-relevant time comparison in brain/{decision,data,screener}/ MUST use
``now_cached()`` instead of ``time.time()``.  The ``no_time_time_lint.py``
pre-commit hook (and ``test_no_time_time_in_hotpath.py``) enforce this ban at
commit time — any ``time.time()`` call outside this file in those directories
causes the hook to fail with a line reference.

The only legitimate ``time.time()`` usages in this file are in ``startup_check``
and ``drift_monitor_tick`` where they explicitly *measure* the difference between
the wall clock and the chain timestamp (that comparison IS the drift calculation).

Startup invariant
-----------------
``ChainTimeCache.startup_check()`` (called by ``main.py`` at boot):
  - Fetches the latest block timestamp directly.
  - Raises ``ChainTimeDriftHalt`` if |wall_time - chain_time| > chain_drift_warn_s.
    (5 s default — stricter than the runtime 30 s halt threshold; a 10 s drift at
    boot means NTP is badly off, refuse to start.)
  - Returns the drift in seconds for the RUN_MANIFEST
    ``chain_time_drift_at_start_seconds`` field (research line 520).

Runtime invariant
-----------------
``drift_monitor_tick()`` (called ~every 60 s by a supervisor task):
  - Uses the TTL-cached value from ``now_cached()``.
  - drift > chain_drift_warn_s  → WARN log record.
  - drift > chain_drift_halt_s  → invokes ``halt_callback``.

RPC timeout (T-01-07-03 mitigation)
------------------------------------
``get_latest_block_timestamp`` is wrapped in ``asyncio.wait_for(timeout=5.0)``.
On timeout: WARN log with ``stale=True``, return last-cached value.
TTL expiry does NOT halt — only confirmed drift > 30 s does.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
from web3 import AsyncWeb3

from boros_brain.config.schema import BotConfig
from boros_brain.data.rpc_client import get_latest_block_timestamp

log = structlog.get_logger(__name__)


class ChainTimeDriftHalt(RuntimeError):
    """Raised by ``startup_check()`` when initial drift exceeds the warn threshold.

    The startup threshold is chain_drift_warn_s (default 5 s) — intentionally
    tighter than the runtime halt threshold (chain_drift_halt_s, default 30 s),
    because a large drift at startup means NTP is off and the bot should refuse
    to start rather than limp along with stale oracles.
    """


HaltCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def _default_halt_callback(reason: str, payload: dict[str, Any]) -> None:
    """Fallback when the ZMQ bus hasn't been wired yet — log only.

    main.py replaces this with the real CmdBus.send_kill wrapper once the bus
    is initialised (dependency-injection via ``ChainTimeCache(halt_callback=…)``).
    """
    log.error("chain_time.halt_callback_unwired", reason=reason, **payload)


@dataclass
class ChainTimeCache:
    """TTL-cached chain timestamp with startup check and drift monitor.

    Attributes
    ----------
    w3:
        AsyncWeb3 instance (from ``make_arbitrum_rpc``).
    config:
        Live BotConfig.  Reads ``data.chain_time_cache_ttl_s``,
        ``infra.chain_drift_warn_s``, ``infra.chain_drift_halt_s``.
    halt_callback:
        Async callable invoked when runtime drift > chain_drift_halt_s.
        Defaults to log-only; wire the real ZMQ KILL publish at startup.
    """

    w3: AsyncWeb3  # type: ignore[type-arg]
    config: BotConfig
    halt_callback: HaltCallback = field(default=_default_halt_callback)
    _value: int | None = field(default=None, init=False, repr=False)
    _ts: float = field(default=0.0, init=False, repr=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def now_cached(self) -> int:
        """Return cached chain timestamp (unix seconds).

        Fetches from RPC when cache is cold or TTL has elapsed.
        TTL = ``config.data.chain_time_cache_ttl_s`` (default 1.0 s).

        On RPC timeout (> 5 s): logs WARN with ``stale=True`` and returns the
        last-cached value (T-01-07-03).  TTL expiry alone does NOT halt.
        """
        now_wall = time.monotonic()
        ttl = self.config.data.chain_time_cache_ttl_s
        if self._value is None or (now_wall - self._ts) >= ttl:
            try:
                self._value = await asyncio.wait_for(get_latest_block_timestamp(self.w3), timeout=5.0)
                self._ts = now_wall
            except TimeoutError:
                log.warning(
                    "chain_time.rpc_timeout",
                    last_value=self._value,
                    stale=True,
                )
                # Return stale cached value — do NOT halt on transient timeout.
        return self._value  # type: ignore[return-value]

    async def startup_check(self) -> float:
        """Fetch the latest block timestamp and refuse to boot if drift is large.

        Called by ``main.py`` at startup *before* the decision loop.

        Returns
        -------
        float
            ``time.time() - chain_timestamp`` (signed, seconds).  Stored as
            ``chain_time_drift_at_start_seconds`` in the RUN_MANIFEST.

        Raises
        ------
        ChainTimeDriftHalt
            If ``|drift| > config.infra.chain_drift_warn_s``.
            Default threshold is 5 s — stricter than the runtime 30 s halt.
        """
        chain_ts = await get_latest_block_timestamp(self.w3)
        self._value = chain_ts
        self._ts = time.monotonic()
        drift = time.time() - chain_ts
        thresh = self.config.infra.chain_drift_warn_s
        if abs(drift) > thresh:
            msg = (
                f"Chain-time drift at startup |{drift:+.2f}s| exceeds threshold "
                f"{thresh}s. Check NTP; likely macOS sleep-wake state. "
                "Refusing to startup."
            )
            raise ChainTimeDriftHalt(msg)
        log.info("chain_time.startup_ok", drift_s=round(drift, 3))
        return float(drift)

    async def drift_monitor_tick(self) -> None:
        """Check current drift and log WARN / trigger halt as appropriate.

        Called ~every 60 s by a supervisor task.  Uses the TTL-cached value from
        ``now_cached()`` to avoid an extra RPC call on every tick.
        """
        chain_ts = await self.now_cached()
        drift = time.time() - chain_ts
        abs_drift = abs(drift)
        if abs_drift > self.config.infra.chain_drift_halt_s:
            await self.halt_callback(
                "chain_time_drift",
                {
                    "drift_s": abs_drift,
                    "threshold_s": self.config.infra.chain_drift_halt_s,
                },
            )
        elif abs_drift > self.config.infra.chain_drift_warn_s:
            log.warning("chain_time.drift_warn", drift_s=round(drift, 3))


# ---------------------------------------------------------------------------
# Module-level singleton — main.py calls install(cache) once at startup.
# Other hot-path modules do `from boros_brain.data.chain_time import now_cached`.
# ---------------------------------------------------------------------------

_GLOBAL_CACHE: ChainTimeCache | None = None


def install(cache: ChainTimeCache) -> None:
    """Register the global ChainTimeCache singleton.

    Called by ``main.py`` after constructing the cache (dependency injection).
    """
    global _GLOBAL_CACHE  # noqa: PLW0603
    _GLOBAL_CACHE = cache


async def now_cached() -> int:
    """Module-level convenience: delegate to the installed singleton."""
    if _GLOBAL_CACHE is None:
        raise RuntimeError("chain_time not installed — call install(cache) at main.py startup")
    return await _GLOBAL_CACHE.now_cached()


async def startup_check() -> float:
    """Module-level convenience: delegate to the installed singleton."""
    if _GLOBAL_CACHE is None:
        raise RuntimeError("chain_time not installed — call install(cache) at main.py startup")
    return await _GLOBAL_CACHE.startup_check()


async def drift_monitor_tick() -> None:
    """Module-level convenience: delegate to the installed singleton."""
    if _GLOBAL_CACHE is None:
        raise RuntimeError("chain_time not installed — call install(cache) at main.py startup")
    await _GLOBAL_CACHE.drift_monitor_tick()
