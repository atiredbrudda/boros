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
  8. Phase 2 Plan 02-04: synchronous initial fill-model fit + spawn refit loop.
  9. Phase 3 Plan 03-04: synchronous initial loss-model fit + spawn refit loop;
     spawn CompetitionTracker (REST + parquet) at 5s cadence.
  10. Await SIGTERM / SIGINT (launchd sends SIGTERM; Ctrl-C sends SIGINT).

Dry-run path (`--dry-run`): brings up the bus, publishes one heartbeat, then
exits 0. Used by the tracer-bullet subprocess smoke test and by operator sanity
checks before paper-mode boot.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

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
        await event_bus.publish(Heartbeat(from_tier="brain", ts_ms=int(time.time() * 1000), run_id=manifest.run_id))
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

    # Phase 2 Plan 02-04: synchronous initial fill-model fit (blocks ~30s on a
    # warm market; required so predict() has an artifact before the 1 Hz decision
    # loop starts). Skipped automatically in dry-run mode (the `return` above
    # short-circuits).
    from .fill_model.refit_loop import (
        refit_once as fill_refit_once,
        run_fill_model_refit_loop,
    )
    await fill_refit_once(cfg, manifest.run_id)
    fill_refit_task = asyncio.create_task(
        run_fill_model_refit_loop(cfg, manifest.run_id)
    )

    # Phase 3 Plan 03-04: synchronous initial loss-model fit + spawn async
    # loss-model refit loop. Mirrors the fill_model pattern exactly (same
    # signature: (cfg, run_id), no extra plumbing required).
    from .loss_model.refit_loop import (
        refit_once as loss_refit_once,
        run_loss_model_refit_loop,
    )
    await loss_refit_once(cfg, manifest.run_id)
    loss_refit_task = asyncio.create_task(
        run_loss_model_refit_loop(cfg, manifest.run_id)
    )

    # Phase 3 Plan 03-04: spawn CompetitionTracker (5s REST + parquet cadence).
    # CompetitionTracker (Plan 03-02) needs (conn, rest, event_pub) — adapt
    # main.py's existing constructs (EventBus.publish takes a StrictMsg, not a
    # topic-string; httpx.AsyncClient has no post_all_limit_orders helper).
    # The adapters are intentionally THIN and live here so 03-02's signature
    # stays stable across the wire-up.
    from .data.rest_client import make_boros_rest_client
    from .reward_model.competition_tracker import run_competition_tracker_loop
    from .state.db import open_connection

    comp_conn = open_connection(Path(cfg.infra.sqlite_path)).__enter__()
    comp_http = make_boros_rest_client(cfg)
    comp_rest = _CompetitionRestAdapter(comp_http)
    comp_event_pub = _TopicEventPubAdapter(event_bus, run_id=manifest.run_id)
    comp_task = asyncio.create_task(
        run_competition_tracker_loop(
            cfg,
            manifest.run_id,
            conn=comp_conn,
            rest=comp_rest,
            event_pub=comp_event_pub,
        )
    )

    await stop.wait()
    heartbeat.stop()
    for t in (
        send_task,
        monitor_task,
        ingest_task,
        fill_refit_task,
        loss_refit_task,
        comp_task,
    ):
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t
    # Phase 3 Plan 03-04: tear down CompetitionTracker side-resources.
    with contextlib.suppress(Exception):
        await comp_http.aclose()
    with contextlib.suppress(Exception):
        comp_conn.close()
    cmd_bus.close()
    event_bus.close()
    log.info("brain_shutdown")
    return 0


class _CompetitionRestAdapter:
    """Adapter wrapping the shared httpx.AsyncClient so it satisfies the
    CompetitionTracker REST contract (`async post_all_limit_orders(...)`).

    Plan 03-04 keeps CompetitionTracker's signature stable from Plan 03-02 by
    constructing this thin shim in main.py rather than refactoring the tracker
    itself. The Boros REST endpoint (per RESEARCH §REWARD-02) is
    `POST /open-api/v2/accounts/all-limit-orders` with a JSON body of
    `{user_address, account_id}`.
    """

    def __init__(self, http: Any) -> None:
        self._http = http
        self._log = structlog.get_logger("boros_brain.main.competition_rest")

    async def post_all_limit_orders(
        self, user_address: str, account_id: int
    ) -> list[dict[str, Any]]:
        resp = await self._http.post(
            "/v2/accounts/all-limit-orders",
            json={"userAddress": user_address, "accountId": account_id},
        )
        resp.raise_for_status()
        body = resp.json()
        # Open-API shape: {data: [...]} OR list[...] — accept both.
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list):
                return data
            return []
        if isinstance(body, list):
            return body
        return []


class _TopicEventPubAdapter:
    """Adapter wrapping EventBus so it satisfies the CompetitionTracker
    event-publisher contract (`async publish(topic: str, payload: dict)`).

    EventBus.publish takes a StrictMsg, not a (topic, payload) pair — the
    tracker's degraded-mode signal is rare and best surfaced as a structured
    log line at WARNING. Plan 03-04 routes the topic + payload through
    structlog (run_id auto-bound by contextvars) so the operator sees it in
    the brain log file alongside everything else.
    """

    def __init__(self, event_bus: Any, *, run_id: str) -> None:
        self._event_bus = event_bus
        self._run_id = run_id
        self._log = structlog.get_logger("boros_brain.main.competition_event_pub")

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        self._log.warning(
            "competition_tracker_event",
            topic=topic,
            run_id=self._run_id,
            **payload,
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
