"""Boros brain entrypoint skeleton.

This is a boot-only shim for Wave 0 (plan 01-01). It parses --mode and prints a
single line. Nothing real is wired yet:

# RUN_MANIFEST emission wired by plan 01-03 (INFRA-06).
# ZMQ bus wired by plan 01-03 (INFRA-05).
# structlog wired by plan 01-03 (INFRA-07).
# SQLite WAL wired by plan 01-02 (INFRA-03).
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

_VALID_MODES = ("live", "paper", "backtest", "ingest", "screen")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="boros-brain")
    parser.add_argument(
        "--mode",
        required=True,
        choices=_VALID_MODES,
        help="Execution mode (live/paper/backtest/ingest/screen).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"boros-brain booted in mode={args.mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
