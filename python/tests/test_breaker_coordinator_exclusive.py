"""SAFE-10 — BreakerCoordinator exclusivity tests (GREEN after 04-06 lands).

Covers:
  - test_kill_fires_once: coordinator sends kill message on first tripped tick;
    second tick with same trip does NOT re-fire (hysteresis no-refire, Pitfall #6)
  - test_suppression: while any breaker is tripped, EvaluateOutput PLACE decisions
    are suppressed — no PlaceCmd reaches the cmd bus
  - test_suppression_logged: suppression events are recorded in state.breaker_events

Uses real ZMQ ipc:// sockets via the ipc_dir fixture (same pattern as
test_zmq_kill_priority.py) — NOT mocks — to prove the IPC boundary is correct.

ZMQ pattern (per test_zmq_kill_priority.py):
  CmdBus PUSH sockets BIND the endpoints.
  Test PULL sockets CONNECT (not bind) — this avoids double-bind hangs.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import zmq
import zmq.asyncio

from boros_brain.config.schema import BotConfig

# RED state guard: modules under test land in Plan 04-06.
coordinator_mod = pytest.importorskip("boros_brain.decision.breaker_coordinator")
BreakerCoordinator = coordinator_mod.BreakerCoordinator
breakers_base = pytest.importorskip("boros_brain.decision.breakers.base")
BreakerSignal = breakers_base.BreakerSignal

from boros_brain.bus.cmd import CmdBus  # noqa: E402 — existing (Plan 01-03)

MARKET_ID = "BINANCE-ETHUSDT-29MAY2026"
BASE_TS = 1_700_000_000


class _AlwaysTrippedBreaker:
    """Fake breaker that always returns a tripped signal. Used for coordinator tests."""

    name = "test_always"

    async def check(self, **kw) -> BreakerSignal:
        return BreakerSignal(
            tripped=True,
            reason="test_always_tripped",
            kill_command_kind="CANCEL_ALL",
        )


class _NeverTrippedBreaker:
    """Fake breaker that never trips. Used to verify healthy-state behavior."""

    name = "test_never"

    async def check(self, **kw) -> BreakerSignal:
        return BreakerSignal(
            tripped=False,
            reason="test_never_healthy",
        )


@pytest.mark.asyncio
async def test_kill_fires_once(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    ipc_dir: Path,
) -> None:
    """SAFE-10 Pitfall #6 hysteresis: tripped breaker sends kill ONCE; second tick is silent.

    CmdBus BINDS both endpoints. PULL sockets CONNECT after bind.
    Sleep 0.05s after connect so ZMQ can establish the socket (slow-joiner protection).
    """
    cmd_endpoint = f"ipc://{ipc_dir}/coord1_cmd"
    kill_endpoint = f"ipc://{ipc_dir}/coord1_kill"

    # CmdBus binds first (it owns the PUSH sockets).
    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)

    # PULL sockets connect (not bind) to avoid double-bind hang.
    ctx = zmq.asyncio.Context.instance()
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.connect(kill_endpoint)
    await asyncio.sleep(0.05)  # slow-joiner protection

    coord = BreakerCoordinator(
        cmd_bus=bus,
        config=default_config,
        run_id="test-coord-001",
        gas_cache=None,
        breakers=[_AlwaysTrippedBreaker()],
    )

    # First tick — breaker tripped → expect one kill message.
    await coord.tick(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        current_chain_ts=BASE_TS,
    )
    kill_msg = await asyncio.wait_for(kill_pull.recv_json(), timeout=1.0)
    assert kill_msg.get("kind") == "kill", f"Unexpected kill message: {kill_msg}"

    # Second tick — still tripped, must NOT re-fire (Pitfall #6 hysteresis).
    await coord.tick(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        current_chain_ts=BASE_TS + 1,
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(kill_pull.recv_json(), timeout=0.1)

    kill_pull.close()
    bus.close()


@pytest.mark.asyncio
async def test_suppression(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    ipc_dir: Path,
) -> None:
    """SAFE-10 kill-authority exclusivity: no PLACE messages reach cmd bus while any breaker is tripped.

    After a breaker fires, the coordinator.gate() method must filter out all PLACE
    EvaluateOutput decisions. No PlaceCmd should arrive on cmd_endpoint.
    """
    cmd_endpoint = f"ipc://{ipc_dir}/coord2_cmd"
    kill_endpoint = f"ipc://{ipc_dir}/coord2_kill"

    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)

    ctx = zmq.asyncio.Context.instance()
    cmd_pull = ctx.socket(zmq.PULL)
    cmd_pull.connect(cmd_endpoint)
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.connect(kill_endpoint)
    await asyncio.sleep(0.05)

    coord = BreakerCoordinator(
        cmd_bus=bus,
        config=default_config,
        run_id="test-coord-002",
        gas_cache=None,
        breakers=[_AlwaysTrippedBreaker()],
    )

    # Fire the breaker.
    await coord.tick(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        current_chain_ts=BASE_TS,
    )
    # Drain the kill message so we start fresh.
    try:
        await asyncio.wait_for(kill_pull.recv_json(), timeout=0.5)
    except asyncio.TimeoutError:
        pass  # Kill may not have arrived yet — OK for this test

    # Use PLACE (not HOLD) to properly test suppression of the normal cmd path.
    fake_place_decision = type("FakeDecision", (), {"decision_kind": "PLACE"})()
    await coord.gate([fake_place_decision], current_chain_ts=BASE_TS + 1)

    # No PlaceCmd should have arrived on cmd_pull (suppressed by active breaker).
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(cmd_pull.recv_json(), timeout=0.1)

    cmd_pull.close()
    kill_pull.close()
    bus.close()


@pytest.mark.asyncio
async def test_suppression_logged(
    tmp_path: Path,
    default_config: BotConfig,
    tmp_sqlite_path: Path,
    ipc_dir: Path,
) -> None:
    """SAFE-10: suppressed decisions are written to state.breaker_events with kind='suppression'."""
    from tests.conftest import apply_migrations

    apply_migrations(tmp_sqlite_path)

    cmd_endpoint = f"ipc://{ipc_dir}/coord3_cmd"
    kill_endpoint = f"ipc://{ipc_dir}/coord3_kill"

    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)

    ctx = zmq.asyncio.Context.instance()
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.connect(kill_endpoint)
    await asyncio.sleep(0.05)

    coord = BreakerCoordinator(
        cmd_bus=bus,
        config=default_config,
        run_id="test-coord-003",
        gas_cache=None,
        breakers=[_AlwaysTrippedBreaker()],
    )

    await coord.tick(
        sqlite_path=tmp_sqlite_path,
        w3=None,
        parquet_root=tmp_path,
        current_chain_ts=BASE_TS,
    )
    try:
        await asyncio.wait_for(kill_pull.recv_json(), timeout=0.5)
    except asyncio.TimeoutError:
        pass

    # Use PLACE (not HOLD) so the coordinator writes a suppression row.
    fake_place = type("FakeDecision", (), {"decision_kind": "PLACE"})()
    await coord.gate([fake_place], current_chain_ts=BASE_TS + 1)

    # Verify suppression row exists in breaker_events.
    from boros_brain.state.db import open_connection

    with open_connection(tmp_sqlite_path) as conn:
        rows = conn.execute(
            "SELECT kind FROM breaker_events WHERE kind = 'suppression'"
        ).fetchall()
    assert len(rows) >= 1, (
        f"Expected at least 1 suppression row in breaker_events, got {len(rows)}"
    )

    kill_pull.close()
    bus.close()
