"""SAFE-10 — BreakerCoordinator: brain-side kill mutex (Plan 04-06).

The coordinator is the single authority for:
  1. Sweeping all 10 breakers every 1 Hz cycle (via tick()).
  2. Emitting a KillCmd on the RISING EDGE ONLY when a breaker first trips
     (Pitfall #6 hysteresis — one KillCmd per trip, not every cycle).
  3. Suppressing ALL PLACE/CANCEL commands from the engine while any breaker
     is active (SAFE-10 exclusivity).
  4. Persisting every trip, suppression, and re-arm event to state.breaker_events
     (Pitfall #2 — never accumulate in-memory; coordinator reconstructs state
     from the DB on restart).

Per-breaker timeout: 200ms (Pitfall #1 — no breaker may block the 1 Hz loop).
ZMQ LINGER: already set on CmdBus sockets (Pitfall #9).

[[breaker-coordinator-kill-mutex]]: SAFE-10 spec and coordinator design
[[circuit-breakers-v05]]: full breaker taxonomy
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from ..bus.cmd import CmdBus
from ..bus.messages import CancelCmd, KillCmd, PlaceCmd
from ..config.schema import BotConfig
from ..state.db import open_connection
from ..state.writers.breaker_events import insert_breaker_event
from .breakers.base import Breaker, BreakerSignal
from .gas_history import GasHistoryCache

log = structlog.get_logger(__name__)

__all__ = ["BreakerCoordinator"]


class BreakerCoordinator:
    """Brain-side kill mutex for SAFE-10.

    Owns the rising-edge KillCmd discipline and PLACE/CANCEL suppression while
    any breaker is tripped. All events are persisted to state.breaker_events
    (Pitfall #2 — no in-memory-only accumulation).

    Parameters
    ----------
    cmd_bus:
        The ZMQ CmdBus — send_kill() targets the priority KILL lane,
        send_cmd() targets the normal cmd lane.
    config:
        Live BotConfig (frozen). Provides sqlite_path and breaker knobs.
    run_id:
        Active run_id for traceability in breaker_events rows.
    gas_cache:
        GasHistoryCache singleton injected so MaturityBreaker can access
        cancel cost estimates without a direct import cycle.
    breakers:
        Ordered list of Breaker subclasses to sweep every tick.
    """

    def __init__(
        self,
        *,
        cmd_bus: CmdBus,
        config: BotConfig,
        run_id: str,
        gas_cache: GasHistoryCache | None,
        breakers: list[Breaker],
    ) -> None:
        self._cmd_bus = cmd_bus
        self._config = config
        self._run_id = run_id
        self._gas_cache = gas_cache
        self._breakers = breakers
        # Rising-edge tracking: breaker.name -> first_tripped_chain_ts
        self._tripped: dict[str, int] = {}
        # Cached from last tick() call so gate() can write to the same DB.
        self._last_sqlite_path: Path = Path(config.infra.sqlite_path)

    async def tick(
        self,
        *,
        sqlite_path: Path,
        w3: Any,
        parquet_root: Path,
        current_chain_ts: int,
    ) -> dict[str, BreakerSignal]:
        """Sweep all breakers; emit KillCmd on RISING edge only (Pitfall #6 hysteresis).

        Each breaker has a 200ms timeout (Pitfall #1 — no breaker may block the
        1 Hz loop). Timeout and exception results are treated as non-tripped to
        avoid false positives from transient failures.

        Returns a dict of breaker name -> BreakerSignal for the caller's inspection.
        """
        signals: dict[str, BreakerSignal] = {}
        # Cache sqlite_path so gate() writes to the same DB (critical for tests).
        self._last_sqlite_path = sqlite_path

        for b in self._breakers:
            try:
                sig = await asyncio.wait_for(
                    b.check(
                        sqlite_path=sqlite_path,
                        w3=w3,
                        parquet_root=parquet_root,
                        config=self._config,
                        current_chain_ts=current_chain_ts,
                    ),
                    timeout=0.2,  # Pitfall #1: 200ms per breaker
                )
            except asyncio.TimeoutError:
                log.warning(
                    "breaker.timeout",
                    name=b.name,
                    current_chain_ts=current_chain_ts,
                )
                sig = BreakerSignal(tripped=False, reason="timeout")
            except Exception as exc:  # noqa: BLE001
                log.error("breaker.error", name=b.name, err=str(exc))
                sig = BreakerSignal(tripped=False, reason="error")

            signals[b.name] = sig

            was_tripped = b.name in self._tripped

            if sig.tripped and not was_tripped:
                # RISING EDGE — fire KillCmd ONCE (Pitfall #6 hysteresis).
                self._tripped[b.name] = current_chain_ts
                await self._cmd_bus.send_kill(
                    KillCmd(
                        reason=f"{b.name}:{sig.reason}",
                        run_id=self._run_id,
                        kill_command_kind=sig.kill_command_kind,
                    )
                )
                log.error(
                    "breaker_tripped",
                    breaker=b.name,
                    reason=sig.reason,
                    kill_command_kind=sig.kill_command_kind,
                    payload=sig.payload,
                )
                # Persist trip event — Pitfall #2: never in-memory-only.
                # Use sqlite_path arg (from tick caller) so tests can inject a tmp DB.
                try:
                    with open_connection(sqlite_path) as conn:
                        insert_breaker_event(
                            conn,
                            kind="kill_emitted",
                            breaker_name=b.name,
                            reason=sig.reason,
                            chain_ts=current_chain_ts,
                            run_id=self._run_id,
                            payload_json=sig.model_dump_json(),
                        )
                        conn.commit()
                except Exception as db_exc:  # noqa: BLE001
                    log.error(
                        "breaker_coordinator.db_write_failed",
                        kind="kill_emitted",
                        breaker=b.name,
                        err=str(db_exc),
                    )

            elif not sig.tripped and was_tripped:
                # Hysteresis: only un-trip after min_re_arm_s has elapsed.
                re_arm_cfg = getattr(self._config.decision.breakers, b.name, None)
                re_arm_s: float = (
                    getattr(re_arm_cfg, "min_re_arm_s", 60.0)
                    if re_arm_cfg is not None
                    else 60.0
                )
                if current_chain_ts - self._tripped[b.name] >= re_arm_s:
                    del self._tripped[b.name]
                    log.info(
                        "breaker_rearmed",
                        breaker=b.name,
                        re_arm_s=re_arm_s,
                        current_chain_ts=current_chain_ts,
                    )
                    try:
                        with open_connection(self._last_sqlite_path) as conn:
                            insert_breaker_event(
                                conn,
                                kind="rearmed",
                                breaker_name=b.name,
                                reason="auto_rearm",
                                chain_ts=current_chain_ts,
                                run_id=self._run_id,
                            )
                            conn.commit()
                    except Exception as db_exc:  # noqa: BLE001
                        log.error(
                            "breaker_coordinator.db_write_failed",
                            kind="rearmed",
                            breaker=b.name,
                            err=str(db_exc),
                        )

        return signals

    async def gate(
        self, decisions: list[Any], *, current_chain_ts: int
    ) -> None:
        """Suppress all PLACE/CANCEL while any breaker is active (SAFE-10 exclusivity).

        When no breakers are tripped, forward PLACE/CANCEL decisions through the
        cmd bus. When any breaker is active, suppress all PLACE/CANCEL decisions
        and persist a suppression row to state.breaker_events.

        Pitfall #2: every suppression event is written to the DB, not just logged.
        """
        if not self._tripped:
            # No active breakers — forward decisions normally.
            for d in decisions:
                if d.decision_kind == "PLACE":
                    await self._cmd_bus.send_cmd(self._build_place_cmd(d))
                elif d.decision_kind == "CANCEL":
                    await self._cmd_bus.send_cmd(self._build_cancel_cmd(d))
                # HOLD / HOLD_NO_REPLACE -> no cmd emitted
            return

        # Suppression path: at least one breaker is tripped.
        active_breaker_names = ",".join(sorted(self._tripped.keys()))
        suppressed_any = False
        for d in decisions:
            if d.decision_kind in ("PLACE", "CANCEL"):
                log.warning(
                    "breaker_coordinator.suppressed",
                    decision_kind=d.decision_kind,
                    active_breakers=list(self._tripped.keys()),
                )
                suppressed_any = True
                try:
                    payload_json: str | None = None
                    if hasattr(d, "model_dump_json"):
                        payload_json = d.model_dump_json()
                    with open_connection(self._last_sqlite_path) as conn:
                        insert_breaker_event(
                            conn,
                            kind="suppression",
                            breaker_name=active_breaker_names,
                            reason=f"active_breaker_blocked_{d.decision_kind}",
                            chain_ts=current_chain_ts,
                            run_id=self._run_id,
                            payload_json=payload_json,
                        )
                        conn.commit()
                except Exception as db_exc:  # noqa: BLE001
                    log.error(
                        "breaker_coordinator.db_write_failed",
                        kind="suppression",
                        decision_kind=d.decision_kind,
                        err=str(db_exc),
                    )

    def _build_place_cmd(self, d: Any) -> PlaceCmd:
        """Construct a minimal PlaceCmd from EvaluateOutput reasoning fields.

        v0.5 minimal cmd shape — Phase 6 hands extends with full calldata and
        pre-signed cancel. The order params come from EvaluateOutput.reasoning
        (order_id, market_id, side). Size and rate are placeholders until Phase 6
        wires the sizer output into the decision loop.
        """
        return PlaceCmd(
            order_id=getattr(d, "order_id", ""),
            market_id=getattr(d, "market_id", ""),
            side=getattr(d, "side", "long"),
            depth_ticks=getattr(d, "depth_ticks", 0),
            size_wei=getattr(d, "size_wei", "0"),
            rate=getattr(d, "rate", 0),
            run_id=self._run_id,
        )

    def _build_cancel_cmd(self, d: Any) -> CancelCmd:
        """Construct a minimal CancelCmd from EvaluateOutput reasoning fields.

        v0.5 minimal cmd shape — Phase 6 hands extends with pre-signed calldata.
        """
        return CancelCmd(
            order_id=getattr(d, "order_id", ""),
            run_id=self._run_id,
        )

    async def halt_via_chain_time(self, reason: str, payload: dict[str, Any]) -> None:
        """Replaces ChainTimeCache._default_halt_callback.

        Routes chain-drift halt through the ZMQ KILL priority lane so the
        hands process receives an orderly shutdown signal rather than an abrupt
        process kill. This is wired during main.py boot (Plan 04-06 Task 3):
            chain_cache.halt_callback = coord.halt_via_chain_time
        """
        log.error(
            "chain_time_halt_via_coordinator",
            reason=reason,
            payload=payload,
        )
        await self._cmd_bus.send_kill(
            KillCmd(
                reason=f"chain_time_halt:{reason}",
                run_id=self._run_id,
                kill_command_kind="HALT_AND_ALERT",
            )
        )
