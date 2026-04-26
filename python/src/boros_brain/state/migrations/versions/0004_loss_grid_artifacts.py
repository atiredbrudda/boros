"""Add loss_grid_artifacts table + index (Phase 3 LOSS-01).

Revision ID: 0004_loss_grid_artifacts
Revises: 0003_fill_model_fits
Create Date: 2026-04-24

Idempotency: schemas.sql (executed by 0001) now includes loss_grid_artifacts DDL
using CREATE TABLE IF NOT EXISTS, so on a fresh database the table is created by
0001. This migration detects that case via inspection and only creates the table
and index if they don't already exist — matching the same pattern used by 0002 /
0003 for the reward_budget_history / fill_model_fits idempotency.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0004_loss_grid_artifacts"
down_revision = "0003_fill_model_fits"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return table in inspector.get_table_names()


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    indexes = [ix["name"] for ix in inspector.get_indexes(table)]
    return index_name in indexes


def upgrade() -> None:
    # If the table already exists (created by 0001 executing schemas.sql which
    # now includes loss_grid_artifacts DDL), skip creation — just ensure the index.
    if not _has_table("loss_grid_artifacts"):
        op.create_table(
            "loss_grid_artifacts",
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("market_id", sa.Text(), nullable=False),
            sa.Column("side", sa.Text(), nullable=False),
            sa.Column("window_start_ts", sa.Integer(), nullable=False),
            sa.Column("window_end_ts", sa.Integer(), nullable=False),
            sa.Column("fit_status", sa.Text(), nullable=False),
            sa.Column("depth_bucket_edges", sa.Text(), nullable=False),
            sa.Column("tau_bucket_edges_days", sa.Text(), nullable=False),
            sa.Column("cells_json", sa.Text(), nullable=False),
            sa.Column(
                "event_index_coverage",
                sa.Text(),
                nullable=False,
                server_default="full",
            ),
            sa.Column("created_at", sa.Integer(), nullable=False),
            sa.CheckConstraint("side IN ('long','short')", name="ck_loss_grid_artifacts_side"),
            sa.CheckConstraint(
                "fit_status IN ('ok','degraded','stale')",
                name="ck_loss_grid_artifacts_status",
            ),
            sa.CheckConstraint(
                "event_index_coverage IN ('full','degraded')",
                name="ck_loss_grid_artifacts_eic",
            ),
            sa.PrimaryKeyConstraint("market_id", "side", "window_end_ts"),
        )

    # Add index if not already present (covers both fresh-DB and legacy-upgrade paths).
    if not _has_index("loss_grid_artifacts", "ix_loss_grid_artifacts_market_side_end"):
        op.create_index(
            "ix_loss_grid_artifacts_market_side_end",
            "loss_grid_artifacts",
            ["market_id", "side", sa.text("window_end_ts DESC")],
        )


def downgrade() -> None:
    if _has_index("loss_grid_artifacts", "ix_loss_grid_artifacts_market_side_end"):
        op.drop_index(
            "ix_loss_grid_artifacts_market_side_end",
            table_name="loss_grid_artifacts",
        )
    if _has_table("loss_grid_artifacts"):
        op.drop_table("loss_grid_artifacts")
