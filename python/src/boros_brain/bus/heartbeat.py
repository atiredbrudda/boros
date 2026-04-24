"""5s heartbeat send + 15s (3-miss) lost-sibling monitor (INFRA-05).

Two coroutines run concurrently:
  - send_loop:     publishes Heartbeat on the events PUB every `interval_s`.
  - monitor_loop:  checks `last_peer_heartbeat_ms`; after `interval_s * timeout_misses`
                   ms of silence, publishes a LostSibling event on the same PUB
                   (observable by THIS tier's own downstream consumers as well as
                   the peer when it returns).

Production settings come from BotConfig: `interval_s=5.0, timeout_misses=3` →
15s lost-sibling threshold. Tests compress the timeline to 0.1s / 3 for speed.

Peer-heartbeat ingestion (pumping `EventBus.receive()` into `record_peer_heartbeat`)
is the CALLER's job — kept out of this class so the bus can have multiple consumers
in production (manifest-announce handling, fill-forward, etc.).
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from .events import EventBus
from .messages import Heartbeat, LostSibling

LOST_SIBLING_EVENT = "lost_sibling"


class HeartbeatMonitor:
    """Send + watch heartbeats on a shared EventBus."""

    def __init__(
        self,
        events: EventBus,
        tier: Literal["brain", "hands"],
        run_id: str,
        interval_s: float = 5.0,
        timeout_misses: int = 3,
    ):
        self.events = events
        self.tier: Literal["brain", "hands"] = tier
        self.run_id = run_id
        self.interval_s = interval_s
        self.timeout_misses = timeout_misses
        self.timeout_s = interval_s * timeout_misses
        # Prime last-peer-heartbeat to "now" so fresh monitors don't insta-fire;
        # the monitor_loop refreshes this from record_peer_heartbeat() calls.
        self.last_peer_heartbeat_ms = int(time.time() * 1000)
        self._stopped = asyncio.Event()
        self._emitted_lost = False

    async def send_loop(self) -> None:
        """Publish a Heartbeat every `interval_s` until `stop()` is called."""
        while not self._stopped.is_set():
            hb = Heartbeat(
                from_tier=self.tier,
                ts_ms=int(time.time() * 1000),
                run_id=self.run_id,
            )
            await self.events.publish(hb)
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_s)
            except TimeoutError:
                continue

    async def monitor_loop(self) -> None:
        """Emit LostSibling after `timeout_misses` consecutive missed intervals."""
        while not self._stopped.is_set():
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_s)
                if self._stopped.is_set():
                    return
            except TimeoutError:
                pass
            now_ms = int(time.time() * 1000)
            elapsed_ms = now_ms - self.last_peer_heartbeat_ms
            if elapsed_ms > self.timeout_s * 1000 and not self._emitted_lost:
                # Observer is *this* tier — it's the one that detected the gap.
                observer: Literal["brain", "hands"] = self.tier
                lost = LostSibling(
                    observer=observer,
                    missing_since_ts_ms=self.last_peer_heartbeat_ms,
                    run_id=self.run_id,
                )
                await self.events.publish(lost)
                self._emitted_lost = True
                # Stay in LOST_SIBLING state; recovery = record_peer_heartbeat() call.
            elif elapsed_ms <= self.timeout_s * 1000:
                self._emitted_lost = False  # recovered

    def record_peer_heartbeat(self, ts_ms: int) -> None:
        """Caller pumps peer Heartbeats into here so monitor_loop can reset the gap."""
        self.last_peer_heartbeat_ms = ts_ms

    def stop(self) -> None:
        self._stopped.set()
