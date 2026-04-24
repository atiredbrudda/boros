"""Entrypoint for the boros_brain process.

MANIFEST-FIRST boot sequence (PROTO-01):
  1. Parse CLI args (--mode, --config, --dry-run).
  2. Load BotConfig from YAML (01-01).
  3. Build RUN_MANIFEST via reflection over BotConfig (01-03 Task 1).
  4. Write sidecar JSON + run_manifests SQLite row (01-02 writer + 01-03 writer).
  5. Configure structlog with contextvars-bound run_id; emit RUN_MANIFEST as the
     first log line.
  6. Await SIGTERM / SIGINT (launchd sends SIGTERM; Ctrl-C sends SIGINT).

Plan 01-03 Task 2 will insert ZMQ bus bring-up + heartbeat tasks between steps
5 and 6.
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path
from typing import Sequence

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

    if dry_run:
        log.info("dry_run_exit")
        return 0

    # Install SIGTERM/SIGINT handlers. launchd sends SIGTERM on stop/restart.
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    # ZMQ bus + heartbeat loops wire in here (plan 01-03 Task 2).
    await stop.wait()
    log.info("brain_shutdown")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
