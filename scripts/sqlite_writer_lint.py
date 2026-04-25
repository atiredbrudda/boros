#!/usr/bin/env python3
"""Single-writer-per-table lint (INFRA-03 / PROTO-02).

For each of the 8 tables, verify that `INSERT INTO <table>` / `UPDATE <table>` /
`ON CONFLICT ... <table>` appears ONLY in the designated owner file.

Ownership map (authoritative):
  open_orders           -> ts/src/boros_hands/state/sqlite_writer.ts  (hands)
  tx_receipts           -> ts/src/boros_hands/state/sqlite_writer.ts  (hands)
  decisions             -> python/src/boros_brain/state/writers/decisions.py
  queue_positions       -> python/src/boros_brain/state/writers/queue_positions.py
  run_manifests         -> python/src/boros_brain/state/writers/run_manifests.py
  epoch_rewards         -> python/src/boros_brain/state/writers/epoch_rewards.py
  clo_history           -> python/src/boros_brain/state/writers/clo_history.py
  reward_budget_history -> python/src/boros_brain/state/writers/reward_budget_history.py

TEST_ONLY exception: the Python writer modules for hands-owned tables
(`open_orders.py`, `tx_receipts.py`) MAY contain INSERT/UPDATE as long as they
carry a literal `TEST_ONLY = True` line at module scope. This is how integration
tests seed state without crossing the IPC boundary.

Exit codes:
  0  clean tree
  1  one or more violations (printed to stderr)
  2  usage error
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

OWNER_MAP: dict[str, str] = {
    "open_orders": "ts/src/boros_hands/state/sqlite_writer.ts",
    "tx_receipts": "ts/src/boros_hands/state/sqlite_writer.ts",
    "decisions": "python/src/boros_brain/state/writers/decisions.py",
    "queue_positions": "python/src/boros_brain/state/writers/queue_positions.py",
    "run_manifests": "python/src/boros_brain/state/writers/run_manifests.py",
    "epoch_rewards": "python/src/boros_brain/state/writers/epoch_rewards.py",
    "clo_history": "python/src/boros_brain/state/writers/clo_history.py",
    "reward_budget_history": "python/src/boros_brain/state/writers/reward_budget_history.py",
    # Plan 04-02 — Phase 4 table owners
    "margin_history": "python/src/boros_brain/state/writers/margin_history.py",
    "breaker_events": "python/src/boros_brain/state/writers/breaker_events.py",
    "predeploy_gate_records": "python/src/boros_brain/state/writers/predeploy_gate_records.py",
    "competition_history": "python/src/boros_brain/state/writers/competition_history.py",
    "market_reward_calibration": "python/src/boros_brain/state/writers/market_reward_calibration.py",
    "loss_grid_artifacts": "python/src/boros_brain/state/writers/loss_grid_artifacts.py",
    "fill_model_fits": "python/src/boros_brain/state/writers/fill_model_fits.py",
}

# Per-table TEST_ONLY-exception file (Python side only; TS has no TEST_ONLY concept).
TEST_ONLY_EXCEPTION_FILES: dict[str, str] = {
    "open_orders": "python/src/boros_brain/state/writers/open_orders.py",
    "tx_receipts": "python/src/boros_brain/state/writers/tx_receipts.py",
}


def _write_pattern(table: str) -> re.Pattern[str]:
    """Regex matching any write statement against `table`."""
    return re.compile(
        rf"(INSERT\s+INTO\s+{table}\b|"
        rf"UPDATE\s+{table}\b|"
        rf"ON\s+CONFLICT[^;]*{table}\b|"
        rf"DELETE\s+FROM\s+{table}\b)",
        re.IGNORECASE,
    )


def _all_sources(root: Path) -> list[Path]:
    """All python/src and ts/src files (skipping node_modules, .venv, __pycache__, dist)."""
    py = list((root / "python" / "src").rglob("*.py")) if (root / "python" / "src").exists() else []
    ts = list((root / "ts" / "src").rglob("*.ts")) if (root / "ts" / "src").exists() else []
    return [
        p
        for p in (py + ts)
        if not any(
            skip in p.parts
            for skip in (".venv", "node_modules", "__pycache__", "dist", ".pnpm")
        )
    ]


def scan(root: Path) -> list[str]:
    """Return list of violation descriptions; empty on clean tree."""
    violations: list[str] = []
    sources = _all_sources(root)
    for table, owner_rel in OWNER_MAP.items():
        pat = _write_pattern(table)
        for src in sources:
            try:
                rel = src.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel == owner_rel:
                continue

            # TEST_ONLY exception for hands-owned Python writers.
            if (
                table in TEST_ONLY_EXCEPTION_FILES
                and rel == TEST_ONLY_EXCEPTION_FILES[table]
            ):
                text = src.read_text()
                if "TEST_ONLY = True" in text:
                    continue

            text = src.read_text()
            if pat.search(text):
                violations.append(f"{rel}: writes to `{table}` (owner: {owner_rel})")
    return violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", type=Path, help="Repo root to scan")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    if not (root / "python").exists() and not (root / "ts").exists():
        print(f"error: {root} does not look like a boros repo (no python/ or ts/)", file=sys.stderr)
        return 2

    vs = scan(root)
    if vs:
        print("sqlite_writer_lint: single-writer violations detected", file=sys.stderr)
        for v in vs:
            print(f"  {v}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
