"""INFRA-05 — KILL lane preempts the normal cmd queue.

We send 10 PlaceCmd messages on the cmd socket then 1 KillCmd on the kill
socket, and a consumer that drains the kill socket FIRST on every tick must
process the KillCmd before any of the 10 PlaceCmd messages.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import zmq
import zmq.asyncio

from boros_brain.bus.cmd import CmdBus
from boros_brain.bus.messages import KillCmd, PlaceCmd


@pytest.mark.asyncio
async def test_kill_lane_preempts_cmd(ipc_dir: Path) -> None:
    cmd_endpoint = f"ipc://{ipc_dir}/cmd"
    kill_endpoint = f"ipc://{ipc_dir}/cmd.kill"

    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)

    ctx = zmq.asyncio.Context.instance()
    cmd_pull = ctx.socket(zmq.PULL)
    cmd_pull.connect(cmd_endpoint)
    kill_pull = ctx.socket(zmq.PULL)
    kill_pull.connect(kill_endpoint)
    await asyncio.sleep(0.05)

    # Produce: 10 PlaceCmd, THEN 1 KillCmd. In arrival order the PlaceCmds are
    # on the wire first; the consumer must still drain kill first.
    for i in range(10):
        await bus.send_cmd(
            PlaceCmd(
                order_id=f"ord-{i}",
                market_id="ETHUSDT-29MAY2026",
                side="long",
                depth_ticks=50,
                size_wei="1",
                rate=9400,
                run_id="r",
            )
        )
    await bus.send_kill(KillCmd(reason="test_emergency", run_id="r"))

    # Let ZMQ flush the sockets.
    await asyncio.sleep(0.05)

    processed: list[str] = []

    async def consumer() -> None:
        """Drain kill socket first on every tick (poll zero-blocking); then one cmd."""
        while True:
            # Try kill socket with zero-timeout poll.
            try:
                msg = await asyncio.wait_for(kill_pull.recv_json(), timeout=0.001)
                processed.append(f"KILL:{msg['reason']}")
                continue  # after kill, loop back — kill always first
            except (TimeoutError, zmq.error.Again):
                pass
            # Then drain one cmd message.
            try:
                msg = await asyncio.wait_for(cmd_pull.recv_json(), timeout=0.001)
                processed.append(f"CMD:{msg['order_id']}")
            except (TimeoutError, zmq.error.Again):
                # No more pending messages — exit.
                return

    await consumer()

    cmd_pull.close()
    kill_pull.close()
    bus.close()

    assert processed, "consumer processed no messages"
    assert processed[0].startswith("KILL:"), f"KILL did not preempt; order was: {processed}"
    # All 10 PlaceCmds should follow after the KILL.
    cmds = [p for p in processed if p.startswith("CMD:")]
    assert len(cmds) == 10, f"expected 10 cmds after KILL, got {len(cmds)}"
