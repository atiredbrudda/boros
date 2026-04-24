"""Add market_reward_calibration table + index (LOCKED D-01 — Plan 03-02).

Revision ID: 0006_market_reward_calibration
Revises: 0005_competition_history
Create Date: 2026-04-24

LOCKED D-01 (2026-04-24) per user decision: supersedes ELiqPoller's polling of
liquidityRewardPerEpoch / longBudget / shortBudget from GET /markets — those
fields are absent from the live API. Operator-manual only.

data_source CHECK constraint enforces only 'operator' — single lineage marker
per LOCKED D-01. SQL CHECK is belt-and-braces with the writer-layer hardcoded
literal in state.writers.market_reward_calibration.

Idempotency: schemas.sql (executed by 0001) now includes market_reward_calibration
DDL using CREATE TABLE IF NOT EXISTS, so on a fresh database the table is
created by 0001. This migration detects that case via inspection and only
creates the table and index if they don't already exist.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0006_market_reward_calibration"
down_revision = "0005_competition_history"
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
    if not _has_table("market_reward_calibration"):
        op.create_table(
            "market_reward_calibration",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("market_id", sa.Text(), nullable=False),
            sa.Column("e_liq_per_epoch_pendle", sa.Float(), nullable=False),
            sa.Column("long_side_split", sa.Float(), nullable=False),
            sa.Column("short_side_split", sa.Float(), nullable=False),
            sa.Column("calibrated_at_utc", sa.Text(), nullable=False),
            sa.Column("data_source", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.CheckConstraint(
                "e_liq_per_epoch_pendle >= 0.0",
                name="ck_market_reward_calibration_e_liq_nonneg",
            ),
            sa.CheckConstraint(
                "long_side_split BETWEEN 0.0 AND 1.0",
                name="ck_market_reward_calibration_long_split",
            ),
            sa.CheckConstraint(
                "short_side_split BETWEEN 0.0 AND 1.0",
                name="ck_market_reward_calibration_short_split",
            ),
            sa.CheckConstraint(
                "data_source = 'operator'",
                name="ck_market_reward_calibration_data_source",
            ),
            sa.CheckConstraint(
                "source IN ('dapp_ui','team_statement','pendle_docs')",
                name="ck_market_reward_calibration_source",
            ),
        )

    if not _has_index(
        "market_reward_calibration",
        "ix_market_reward_calibration_market_calibrated",
    ):
        op.create_index(
            "ix_market_reward_calibration_market_calibrated",
            "market_reward_calibration",
            ["market_id", sa.text("calibrated_at_utc DESC")],
        )


def downgrade() -> None:
    if _has_index(
        "market_reward_calibration",
        "ix_market_reward_calibration_market_calibrated",
    ):
        op.drop_index(
            "ix_market_reward_calibration_market_calibrated",
            table_name="market_reward_calibration",
        )
    if _has_table("market_reward_calibration"):
        op.drop_table("market_reward_calibration")
