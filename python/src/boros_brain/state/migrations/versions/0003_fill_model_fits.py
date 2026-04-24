"""Add fill_model_fits table + index.

Revision ID: 0003_fill_model_fits
Revises: 0002
Create Date: 2026-04-24

Idempotency: schemas.sql (executed by 0001) already includes fill_model_fits DDL
using CREATE TABLE IF NOT EXISTS, so on a fresh database the table is created by
0001. This migration detects that case via inspection and only creates the table
and index if they don't already exist — matching the same pattern used by 0002
for the reward_budget_history idempotency.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0003_fill_model_fits"
down_revision = "0002"
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
    # now includes fill_model_fits DDL), skip creation — just ensure the index.
    if not _has_table("fill_model_fits"):
        op.create_table(
            "fill_model_fits",
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("fit_window_start_ts", sa.Integer(), nullable=False),
            sa.Column("fit_window_end_ts", sa.Integer(), nullable=False),
            sa.Column("market_id", sa.Text(), nullable=False),
            sa.Column("side", sa.Text(), nullable=False),
            sa.Column("covariate_whitelist", sa.Text(), nullable=False),
            sa.Column("beta", sa.Text(), nullable=False),
            sa.Column("beta_stderr", sa.Text(), nullable=False),
            sa.Column("log_likelihood", sa.Float(), nullable=False),
            sa.Column("deviance", sa.Float(), nullable=False),
            sa.Column("aic", sa.Float(), nullable=False),
            sa.Column("n_observations", sa.Integer(), nullable=False),
            sa.Column("converged", sa.Integer(), nullable=False),
            sa.Column("fit_status", sa.Text(), nullable=False),
            sa.Column("gof_ks_pval", sa.Float(), nullable=True),
            sa.Column("gof_lr_vs_null", sa.Float(), nullable=True),
            sa.Column("event_index_coverage", sa.Text(), nullable=False, server_default="full"),
            sa.Column("created_at", sa.Integer(), nullable=False),
            sa.CheckConstraint("side IN ('long','short')", name="ck_fill_model_fits_side"),
            sa.CheckConstraint("converged IN (0,1)", name="ck_fill_model_fits_converged"),
            sa.CheckConstraint("fit_status IN ('ok','degraded','stale')", name="ck_fill_model_fits_status"),
            sa.CheckConstraint("event_index_coverage IN ('full','degraded')", name="ck_fill_model_fits_eic"),
            sa.PrimaryKeyConstraint("market_id", "side", "fit_window_end_ts"),
        )

    # Add index if not already present (covers both fresh-DB and legacy-upgrade paths).
    if not _has_index("fill_model_fits", "ix_fill_model_fits_market_side_end"):
        op.create_index(
            "ix_fill_model_fits_market_side_end",
            "fill_model_fits",
            ["market_id", "side", sa.text("fit_window_end_ts DESC")],
        )


def downgrade() -> None:
    if _has_index("fill_model_fits", "ix_fill_model_fits_market_side_end"):
        op.drop_index("ix_fill_model_fits_market_side_end", table_name="fill_model_fits")
    if _has_table("fill_model_fits"):
        op.drop_table("fill_model_fits")
