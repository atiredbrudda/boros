"""reward_budget_history — add id/polled_at_utc/chain_ts/run_id columns (DATA-11 / 01-10).

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24

Changes vs original 0001 schema for reward_budget_history:
  - Drop snapshot_ts INTEGER + (snapshot_ts, market_id) composite PK
  - Add id INTEGER PRIMARY KEY AUTOINCREMENT
  - Add polled_at_utc TEXT NOT NULL (ISO8601 UTC wall-clock, replaces snapshot_ts)
  - Add chain_ts INTEGER (on-chain block ts from chain_time cache)
  - Add run_id TEXT NOT NULL (traceability to run_manifests)
  - data_source CHECK constraint was already present in 0001 schema
  - Add index ix_reward_budget_market_polled on (market_id, polled_at_utc DESC)

Idempotency: if schemas.sql (used by 0001) was already updated to the new
structure before this migration runs (fresh database), snapshot_ts will not
exist. This migration detects that case via inspection and only creates the
index if it doesn't already exist, making 0002 safe for both legacy (upgrade
path) and fresh (new install) databases.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

# revision identifiers — must be at module scope for Alembic scanner.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    """Check if a column exists in the given table via the current migration connection."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def _has_index(table: str, index_name: str) -> bool:
    """Check if a named index exists on the given table."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    indexes = [ix["name"] for ix in inspector.get_indexes(table)]
    return index_name in indexes


def upgrade() -> None:
    # If snapshot_ts exists, this is a legacy database — migrate to new structure.
    # If snapshot_ts does NOT exist, schemas.sql already created the new schema in 0001.
    if _has_column("reward_budget_history", "snapshot_ts"):
        # Legacy path: recreate table dropping snapshot_ts and adding new columns.
        with op.batch_alter_table(
            "reward_budget_history",
            recreate="always",
        ) as batch_op:
            batch_op.drop_column("snapshot_ts")
            batch_op.add_column(
                sa.Column(
                    "polled_at_utc",
                    sa.Text,
                    nullable=False,
                    server_default="1970-01-01T00:00:00+00:00",
                )
            )
            batch_op.add_column(sa.Column("chain_ts", sa.Integer, nullable=True))
            batch_op.add_column(
                sa.Column(
                    "run_id",
                    sa.Text,
                    nullable=False,
                    server_default="",
                )
            )

    # Add the performance index if not already present (covers both paths).
    if not _has_index("reward_budget_history", "ix_reward_budget_market_polled"):
        op.create_index(
            "ix_reward_budget_market_polled",
            "reward_budget_history",
            ["market_id", sa.text("polled_at_utc DESC")],
        )


def downgrade() -> None:
    if _has_index("reward_budget_history", "ix_reward_budget_market_polled"):
        op.drop_index("ix_reward_budget_market_polled", table_name="reward_budget_history")
    if _has_column("reward_budget_history", "polled_at_utc"):
        with op.batch_alter_table(
            "reward_budget_history",
            recreate="always",
        ) as batch_op:
            batch_op.drop_column("polled_at_utc")
            batch_op.drop_column("chain_ts")
            batch_op.drop_column("run_id")
            batch_op.add_column(
                sa.Column(
                    "snapshot_ts",
                    sa.Integer,
                    nullable=False,
                    server_default="0",
                )
            )
