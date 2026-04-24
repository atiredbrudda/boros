"""ZMQ PUSH bus — brain → hands (INFRA-05).

Two separate sockets implement the KILL priority lane. The hands-side listener
drains the kill socket first on every tick; see ts/src/boros_hands/bus/cmd_listener.ts.

`LINGER=100` means a slow close drops enqueued messages after 100ms rather than
blocking the brain shutdown path — safe because KILL is idempotent and PLACE is
retry-able at the next decision tick.
"""

from __future__ import annotations

import zmq
import zmq.asyncio

from .messages import KillCmd, StrictMsg


class CmdBus:
    """Brain-side PUSH sockets for the cmd + kill lanes."""

    def __init__(self, cmd_endpoint: str, kill_endpoint: str):
        self.ctx = zmq.asyncio.Context.instance()
        self.cmd = self.ctx.socket(zmq.PUSH)
        self.cmd.setsockopt(zmq.LINGER, 100)
        self.cmd.bind(cmd_endpoint)
        self.kill = self.ctx.socket(zmq.PUSH)
        self.kill.setsockopt(zmq.LINGER, 100)
        self.kill.bind(kill_endpoint)

    async def send_cmd(self, msg: StrictMsg) -> None:
        """Enqueue a PlaceCmd / CancelCmd on the normal cmd socket."""
        await self.cmd.send_json(msg.model_dump(mode="json"))  # type: ignore[misc,func-returns-value]

    async def send_kill(self, msg: KillCmd) -> None:
        """Enqueue a KillCmd on the priority kill socket."""
        await self.kill.send_json(msg.model_dump(mode="json"))  # type: ignore[misc,func-returns-value]

    def close(self) -> None:
        self.cmd.close()
        self.kill.close()
