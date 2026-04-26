"""Wave-0 tracer-bullet scaffolding.

Each stub flips from skip → green as its dependent plan lands:
  - test_sqlite_open_orders_roundtrip     → wired by plan 01-02 (INFRA-03)  ✓
  - test_manifest_writer_emits_first_line → wired by plan 01-03 (INFRA-06)  ✓
  - test_zmq_echo_roundtrip_under_10ms    → wired by plan 01-03 (INFRA-05)  ✓
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from boros_brain.state import writers
from boros_brain.state.db import open_connection

_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"
_APPLY_MIGRATION = _ROOT / "scripts" / "apply_alembic_migration.py"

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


@pytest.mark.wave0_scaffold
def test_manifest_writer_emits_first_line(tmp_path: Path) -> None:
    """Subprocess end-to-end: boros_brain.main --dry-run writes manifest-first log + sidecar.

    INFRA-06 un-skip: plan 01-03 Task 1 landed the writer + structlog bind.
    """
    sqlite_path = tmp_path / "state.sqlite"
    logs_dir = tmp_path / "logs"

    # Apply migrations to the tmp sqlite up-front (same as prod boot: alembic
    # upgrade head runs before brain main starts).
    subprocess.run(
        [sys.executable, str(_APPLY_MIGRATION), f"sqlite:///{sqlite_path}"],
        check=True,
        capture_output=True,
    )

    cfg_yaml = tmp_path / "cfg.yaml"
    cfg_yaml.write_text(
        textwrap.dedent(
            f"""
            mode: paper
            strategy_version: v0.5.0-tracer
            market_id: ETHUSDT-29MAY2026
            side: long
            root_wallet_address: "0x0000000000000000000000000000000000000abc"
            agent_wallet_address: "0x0000000000000000000000000000000000000def"
            data:
              rpc_url_arbitrum: "https://arb1.arbitrum.io/rpc"
            infra:
              sqlite_path: "{sqlite_path}"
              logs_dir: "{logs_dir}"
            """
        ).strip()
    )

    result = subprocess.run(
        [sys.executable, "-m", "boros_brain.main", "--mode=paper", f"--config={cfg_yaml}", "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    log_files = list(logs_dir.rglob("*.brain.log.jsonl"))
    assert len(log_files) == 1, f"expected exactly one brain log file, got {log_files}"
    first = json.loads(log_files[0].read_text().splitlines()[0])
    assert first["event"] == "RUN_MANIFEST"
    assert _ULID_RE.match(first["run_id"]), f"run_id not a ULID: {first['run_id']}"
    # Sidecar JSON parity
    sidecars = list(logs_dir.rglob("*.manifest.json"))
    assert len(sidecars) == 1
    sidecar = json.loads(sidecars[0].read_text())
    assert sidecar["run_id"] == first["run_id"]


@pytest.mark.wave0_scaffold
@pytest.mark.asyncio
async def test_zmq_echo_roundtrip_under_10ms(ipc_dir: Path) -> None:
    """INFRA-05 un-skip: brain CmdBus → PULL round-trip, median < 10ms.

    Minimal duplicate of tests/test_zmq_echo.py so the tracer-bullet marker
    alone flips green without pytest plugin re-resolution. Full fidelity
    performance test lives in test_zmq_echo.py (100 iterations, p95 checked).
    """
    import asyncio
    import statistics
    import time

    import zmq
    import zmq.asyncio

    from boros_brain.bus.cmd import CmdBus
    from boros_brain.bus.messages import PlaceCmd

    cmd_endpoint = f"ipc://{ipc_dir}/cmd"
    kill_endpoint = f"ipc://{ipc_dir}/cmd.kill"
    bus = CmdBus(cmd_endpoint=cmd_endpoint, kill_endpoint=kill_endpoint)
    ctx = zmq.asyncio.Context()  # NOT Context.instance() — per-test, terminate at end
    try:
        pull = ctx.socket(zmq.PULL)
        pull.connect(cmd_endpoint)
        await asyncio.sleep(0.05)

        latencies: list[float] = []
        for i in range(30):  # tracer-bullet = smoke test; 30 iters is enough
            msg = PlaceCmd(
                order_id=f"t-{i}",
                market_id="ETHUSDT-29MAY2026",
                side="long",
                depth_ticks=50,
                size_wei="1",
                rate=9400,
                run_id="tracer",
            )
            t0 = time.perf_counter()
            await bus.send_cmd(msg)
            _ = await pull.recv_json()
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        median_ms = statistics.median(latencies)
        pull.close()
    finally:
        ctx.term()
    bus.close()
    assert median_ms < 10.0, f"tracer-bullet ZMQ roundtrip median {median_ms:.2f}ms > 10ms budget"


@pytest.mark.wave0_scaffold
def test_sqlite_open_orders_roundtrip(tmp_path: Path) -> None:
    """INFRA-03 un-skip: alembic → seed via TEST_ONLY writer → raw SELECT reads row back.

    Wired by plan 01-02. The TEST_ONLY-guarded Python writer for `open_orders`
    exists exactly for this kind of integration seeding; the production hands-side
    writer lives in ts/src/boros_hands/state/sqlite_writer.ts.
    """
    db = tmp_path / "tracer.sqlite"
    with open_connection(db):
        pass
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")

    with open_connection(db) as conn:
        writers.open_orders.insert_open_order(
            conn,
            order_id="ord-tracer",
            market_id="ETHUSDT-29MAY2026",
            side="long",
            depth_ticks=50,
            size_wei="1000000000000000000",
            rate=9400,
            status="filling",
            placed_at_ts=1_714_000_000,
            run_id="run-tracer",
        )
        row = conn.execute(
            "SELECT order_id, status, market_id, side FROM open_orders WHERE order_id='ord-tracer'"
        ).fetchone()

    assert row == ("ord-tracer", "filling", "ETHUSDT-29MAY2026", "long")
