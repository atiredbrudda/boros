"""initial 8 tables — INFRA-03 state spine.

Replays ../../schemas.sql. Any schema change lands in schemas.sql first, then
a new Alembic revision is authored in the same commit (PROTO-02 discipline).

Revision ID: 0001
Revises:
Create Date: 2026-04-23
"""

from __future__ import annotations

import re
from pathlib import Path

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Path to the canonical DDL file — two levels up from this versions/ directory.
_HERE = Path(__file__).resolve()
SCHEMAS_SQL = _HERE.parents[2] / "schemas.sql"

# Tables created by this migration, in creation order (for a clean downgrade).
_TABLES = [
    "open_orders",
    "decisions",
    "tx_receipts",
    "queue_positions",
    "run_manifests",
    "epoch_rewards",
    "clo_history",
    "reward_budget_history",
]


def _split_sql(sql: str) -> list[str]:
    """Strip comments + split on top-level semicolons into executable statements."""
    # Remove line comments (-- ...) but preserve the newline so statement boundaries
    # inside the remaining text stay intact.
    no_comments = re.sub(r"--[^\n]*", "", sql)
    # Split on semicolons; drop empties after stripping.
    return [s.strip() for s in no_comments.split(";") if s.strip()]


def upgrade() -> None:
    """Execute each statement in schemas.sql via op.execute()."""
    sql_text = SCHEMAS_SQL.read_text()
    for stmt in _split_sql(sql_text):
        op.execute(stmt)


def downgrade() -> None:
    """Drop all 8 tables in reverse creation order + their indexes (CASCADE via SQLite DROP)."""
    for tbl in reversed(_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {tbl}")
