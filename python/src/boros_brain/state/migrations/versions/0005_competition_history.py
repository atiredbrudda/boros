"""Add competition_history table + index (Phase 3 REWARD-02 / Plan 03-02).

Revision ID: 0005_competition_history
Revises: 0004_loss_grid_artifacts
Create Date: 2026-04-24

Idempotency: schemas.sql (executed by 0001) now includes competition_history DDL
using CREATE TABLE IF NOT EXISTS, so on a fresh database the table is created by
0001. This migration detects that case via inspection and only creates the table
and index if they don't already exist — same pattern used by 0002 / 0003 / 0004.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0005_competition_history"
down_revision = "0004_loss_grid_artifacts"
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
    # now includes competition_history DDL), skip creation — just ensure the index.
    if not _has_table("competition_history"):
        op.create_table(
            "competition_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("polled_at_utc", sa.Text(), nullable=False),
            sa.Column("chain_ts", sa.Integer(), nullable=True),
            sa.Column("market_id", sa.Text(), nullable=False),
            sa.Column("q_me_pendle", sa.Float(), nullable=False),
            sa.Column("sigma_others_pendle", sa.Float(), nullable=False),
            sa.Column("data_source", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.CheckConstraint(
                "data_source IN ('live','fallback_parquet_only')",
                name="ck_competition_history_data_source",
            ),
        )

    if not _has_index(
        "competition_history", "ix_competition_history_market_polled"
    ):
        op.create_index(
            "ix_competition_history_market_polled",
            "competition_history",
            ["market_id", sa.text("polled_at_utc DESC")],
        )


def downgrade() -> None:
    if _has_index(
        "competition_history", "ix_competition_history_market_polled"
    ):
        op.drop_index(
            "ix_competition_history_market_polled",
            table_name="competition_history",
        )
    if _has_table("competition_history"):
        op.drop_table("competition_history")
