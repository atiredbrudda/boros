"""Entrypoint for the boros_brain process.

MANIFEST-FIRST boot sequence (PROTO-01):
  1. Parse CLI args (--mode, --config, --dry-run).
  2. Load BotConfig from YAML (01-01).
  3. Build RUN_MANIFEST via reflection over BotConfig (01-03 Task 1).
  4. Write sidecar JSON + run_manifests SQLite row (01-02 writer + 01-03 writer).
  5. Configure structlog with contextvars-bound run_id; emit RUN_MANIFEST as the
     first log line.
  6. Bring up the ZMQ CmdBus + EventBus (01-03 Task 2, INFRA-05).
  7. Spawn heartbeat send + monitor + peer-ingest asyncio tasks.
  8. Await SIGTERM / SIGINT (launchd sends SIGTERM; Ctrl-C sends SIGINT).

Dry-run path (`--dry-run`): brings up the bus, publishes one heartbeat, then
exits 0. Used by the tracer-bullet subprocess smoke test and by operator sanity
checks before paper-mode boot.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from pathlib import Path
from typing import Sequence

from .bus.cmd import CmdBus
from .bus.events import EventBus
from .bus.heartbeat import HeartbeatMonitor
from .bus.messages import Heartbeat
from .config.loader import load_config
from .logging.structlog_setup import configure_logging, get_logger
from .manifest.writer import build_run_manifest, write_manifest

_VALID_MODES = ("live", "paper", "backtest", "ingest", "screen")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="boros-brain")
    parser.add_argument(
        "--mode",
        required=True,
        choices=_VALID_MODES,
        help="Execution mode (live/paper/backtest/ingest/screen).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("strategy/v0.5-default.yaml"),
        help="Path to BotConfig YAML (PROTO-04 SSoT).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit RUN_MANIFEST + exit 0 (smoke-test boot path without awaiting signals).",
    )
    return parser


async def run(config_path: Path, dry_run: bool = False) -> int:
    cfg = load_config(config_path)
    manifest = build_run_manifest(cfg)
    logs_dir = Path(cfg.infra.logs_dir)
    sqlite_path = Path(cfg.infra.sqlite_path)
    write_manifest(manifest, logs_dir=logs_dir, sqlite_path=sqlite_path)
    configure_logging(
        run_id=manifest.run_id,
        tier="brain",
        logs_dir=logs_dir,
        first_manifest_line=manifest.model_dump(mode="json"),
    )
    log = get_logger("boros_brain.main")
    log.info("brain_booted", mode=cfg.mode, run_id=manifest.run_id)

    # Bring up ZMQ bus + heartbeat.
    cmd_bus = CmdBus(
        cmd_endpoint=cfg.infra.zmq_cmd_endpoint,
        kill_endpoint=cfg.infra.zmq_kill_endpoint,
    )
    event_bus = EventBus(
        brain_endpoint=cfg.infra.zmq_events_brain_endpoint,
        hands_endpoint=cfg.infra.zmq_events_hands_endpoint,
        tier="brain",
    )
    heartbeat = HeartbeatMonitor(
        events=event_bus,
        tier="brain",
        run_id=manifest.run_id,
        interval_s=cfg.infra.heartbeat_interval_s,
        timeout_misses=cfg.infra.heartbeat_timeout_misses,
    )

    if dry_run:
        # Smoke-test invariant: publish one heartbeat so the tracer-bullet test
        # confirms the bus is wired end-to-end, then exit cleanly.
        await event_bus.publish(
            Heartbeat(from_tier="brain", ts_ms=int(time.time() * 1000), run_id=manifest.run_id)
        )
        log.info("heartbeat_emitted", run_id=manifest.run_id)
        cmd_bus.close()
        event_bus.close()
        log.info("dry_run_exit")
        return 0

    # Install SIGTERM/SIGINT handlers. launchd sends SIGTERM on stop/restart.
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    # Spawn heartbeat send + monitor + peer-ingest as background tasks.
    send_task = asyncio.create_task(heartbeat.send_loop())
    monitor_task = asyncio.create_task(heartbeat.monitor_loop())

    async def _peer_heartbeat_ingest() -> None:
        while not stop.is_set():
            msg = await event_bus.receive()
            if msg.get("kind") == "heartbeat" and msg.get("from_tier") != "brain":
                heartbeat.record_peer_heartbeat(msg["ts_ms"])

    ingest_task = asyncio.create_task(_peer_heartbeat_ingest())

    await stop.wait()
    heartbeat.stop()
    for t in (send_task, monitor_task, ingest_task):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    cmd_bus.close()
    event_bus.close()
    log.info("brain_shutdown")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
