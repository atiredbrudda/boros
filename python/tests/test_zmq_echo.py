"""INFRA-05 — brain CmdBus ↔ hands PULL echo round-trip under 10ms (median).

Uses pure-Python Pull sockets on both ends (in-process test harness). The
cross-language TS ↔ Python round-trip is covered in ts/tests/bus/zmq_echo.test.ts.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path

import pytest
import zmq
import zmq.asyncio

from boros_brain.bus.cmd import CmdBus
from boros_brain.bus.messages import PlaceCmd


@pytest.mark.asyncio
async def test_zmq_echo_roundtrip_under_10ms(tmp_path: Path) -> None:
    """Median round-trip < 10ms over 100 iterations on ipc sockets."""
    cmd_endpoint = f"ipc://{tmp_path}/cmd"
    kill_endpoint = f"ipc://{tmp_path}/cmd.kill"

    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)

    # Separate asyncio context for the hands-side Pull so we don't tangle with
    # the CmdBus's zmq.asyncio.Context.instance() singleton under test.
    ctx = zmq.asyncio.Context.instance()
    pull = ctx.socket(zmq.PULL)
    pull.connect(cmd_endpoint)
    # Small delay to let the connect settle — ZMQ is asynchronous.
    await asyncio.sleep(0.05)

    latencies_ms: list[float] = []
    N = 100
    for i in range(N):
        msg = PlaceCmd(
            order_id=f"ord-{i}",
            market_id="ETHUSDT-29MAY2026",
            side="long",
            depth_ticks=50,
            size_wei="1000000000000000000",
            rate=9400,
            run_id="test-run",
        )
        t0 = time.perf_counter()
        await bus.send_cmd(msg)
        received = await pull.recv_json()
        t1 = time.perf_counter()
        assert received["order_id"] == f"ord-{i}"
        latencies_ms.append((t1 - t0) * 1000.0)

    median = statistics.median(latencies_ms)
    p95 = statistics.quantiles(latencies_ms, n=20)[18]  # ~p95
    pull.close()
    bus.close()

    assert median < 10.0, f"median round-trip {median:.3f}ms exceeds 10ms budget (p95={p95:.3f}ms)"
