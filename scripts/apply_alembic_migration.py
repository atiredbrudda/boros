#!/usr/bin/env python3
"""Apply the boros state-spine Alembic migration to an arbitrary SQLite URL.

Used by:
  - ts/tests/state/sqlite_writer.test.ts (via child_process.execSync)
  - any future tooling that needs to bring a fresh DB to head without relying
    on the alembic.ini's default `sqlalchemy.url`.

Usage:
  python scripts/apply_alembic_migration.py sqlite:///path/to/fresh.sqlite
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "python" / "src" / "boros_brain" / "state" / "migrations" / "alembic.ini"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} sqlite:///absolute/path.sqlite", file=sys.stderr)
        return 2
    db_url = argv[1]
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_INI.parent))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
