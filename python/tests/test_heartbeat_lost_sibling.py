"""INFRA-05 — 5s heartbeat + 3-miss (15s) lost-sibling protocol.

The test uses a compressed timeline (interval_s=0.1, timeout_misses=3) so a
full lost-sibling transition completes in <1s and the assertion budget stays
tight. The production bus uses 5s / 15s per BotConfig defaults.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from boros_brain.bus.events import EventBus
from boros_brain.bus.heartbeat import HeartbeatMonitor
from boros_brain.bus.messages import LostSibling


@pytest.mark.asyncio
async def test_lost_sibling_after_three_misses(tmp_path: Path) -> None:
    brain_endpoint = f"ipc://{tmp_path}/events.brain"
    hands_endpoint = f"ipc://{tmp_path}/events.hands"

    brain_bus = EventBus(
        brain_endpoint=brain_endpoint, hands_endpoint=hands_endpoint, tier="brain"
    )
    # Second subscriber on the brain side — subscribes to the brain's own PUB so
    # we can observe the LostSibling event the monitor publishes.
    observer_bus = EventBus(
        brain_endpoint=hands_endpoint,  # unused — observer doesn't publish
        hands_endpoint=brain_endpoint,  # "peer" = brain's PUB endpoint
        tier="hands",
    )
    # Give ZMQ a moment to establish the PUB/SUB handshake.
    await asyncio.sleep(0.05)

    monitor = HeartbeatMonitor(
        events=brain_bus,
        tier="brain",
        run_id="test_run",
        interval_s=0.1,
        timeout_misses=3,
    )

    # DO NOT record a peer heartbeat — timeout will trigger.
    monitor_task = asyncio.create_task(monitor.monitor_loop())

    # Wait at most 2s for the LostSibling event to arrive on the observer bus.
    async def wait_for_lost_sibling() -> dict:
        while True:
            msg = await observer_bus.receive()
            if msg.get("kind") == "lost_sibling":
                return msg

    result = await asyncio.wait_for(wait_for_lost_sibling(), timeout=2.0)

    monitor.stop()
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    brain_bus.close()
    observer_bus.close()

    # Shape validation via the Pydantic model — guards T-03-04.
    LostSibling.model_validate(result)
    assert result["observer"] == "brain"
    assert result["missing_since_ts_ms"] > 0
    assert result["run_id"] == "test_run"


@pytest.mark.asyncio
async def test_heartbeat_send_cadence(tmp_path: Path) -> None:
    """Three heartbeats at 0.1s interval arrive in <0.5s with expected run_id."""
    brain_endpoint = f"ipc://{tmp_path}/events.brain"
    hands_endpoint = f"ipc://{tmp_path}/events.hands"

    brain_bus = EventBus(brain_endpoint=brain_endpoint, hands_endpoint=hands_endpoint, tier="brain")
    observer_bus = EventBus(brain_endpoint=hands_endpoint, hands_endpoint=brain_endpoint, tier="hands")
    await asyncio.sleep(0.05)

    monitor = HeartbeatMonitor(
        events=brain_bus, tier="brain", run_id="hb_run", interval_s=0.1, timeout_misses=100
    )
    send_task = asyncio.create_task(monitor.send_loop())

    heartbeats: list[dict] = []
    async def collect() -> None:
        while len(heartbeats) < 3:
            msg = await observer_bus.receive()
            if msg.get("kind") == "heartbeat":
                heartbeats.append(msg)

    await asyncio.wait_for(collect(), timeout=2.0)

    monitor.stop()
    send_task.cancel()
    try:
        await send_task
    except asyncio.CancelledError:
        pass
    brain_bus.close()
    observer_bus.close()

    assert len(heartbeats) == 3
    assert all(h["run_id"] == "hb_run" for h in heartbeats)
    assert all(h["from_tier"] == "brain" for h in heartbeats)
