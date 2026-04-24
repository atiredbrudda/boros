"""ZMQ PUB/SUB bus — bidirectional events (INFRA-05, checker issue #07).

Two-endpoint topology: each tier BINDS its own PUB endpoint and SUBSCRIBES to
the peer's PUB endpoint. No string-mangling — endpoints come verbatim from
`config.infra.zmq_events_{brain,hands}_endpoint`.

This bus carries heartbeats, LostSibling events, RunManifestAnnounce, and
future fill-forward events.
"""

from __future__ import annotations

import zmq
import zmq.asyncio

from .messages import StrictMsg


class EventBus:
    """Two-endpoint PUB/SUB bus for cross-tier events."""

    def __init__(self, brain_endpoint: str, hands_endpoint: str, tier: str):
        self.ctx = zmq.asyncio.Context.instance()
        self.pub = self.ctx.socket(zmq.PUB)
        self.sub = self.ctx.socket(zmq.SUB)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "")  # subscribe to every topic
        self.tier = tier
        # Each tier binds its OWN PUB; subscribes to the peer's PUB endpoint.
        if tier == "brain":
            self.pub.bind(brain_endpoint)
            self.sub.connect(hands_endpoint)
        elif tier == "hands":
            self.pub.bind(hands_endpoint)
            self.sub.connect(brain_endpoint)
        else:
            raise ValueError(f"tier must be 'brain' or 'hands', got {tier!r}")

    async def publish(self, msg: StrictMsg) -> None:
        await self.pub.send_json(msg.model_dump(mode="json"))

    async def receive(self) -> dict:
        """Block until the next event arrives from the peer's PUB."""
        return await self.sub.recv_json()

    def close(self) -> None:
        self.pub.close()
        self.sub.close()
