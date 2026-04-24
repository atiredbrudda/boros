"""Per-table writer modules — single-writer-per-table discipline (PROTO-02).

Brain-owned (writes live here in production):
  - decisions, queue_positions, run_manifests, epoch_rewards,
    clo_history, reward_budget_history

Hands-owned (writes live in ts/src/boros_hands/state/sqlite_writer.ts):
  - open_orders, tx_receipts
  The Python modules for these tables are TEST_ONLY = True so integration
  tests can seed state without crossing the IPC boundary.

scripts/sqlite_writer_lint.py grep-enforces the ownership map at commit time.
"""

from . import (
    clo_history,
    decisions,
    epoch_rewards,
    open_orders,
    queue_positions,
    reward_budget_history,
    run_manifests,
    tx_receipts,
)

__all__ = [
    "clo_history",
    "decisions",
    "epoch_rewards",
    "open_orders",
    "queue_positions",
    "reward_budget_history",
    "run_manifests",
    "tx_receipts",
]
