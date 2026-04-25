"""Add 4 Phase-4 tables + tx_receipts.event_type column (Plan 04-02).

Revision ID: 0007_phase4_tables
Revises: 0006_market_reward_calibration
Create Date: 2026-04-25

Creates four tables in one revision:
  margin_history          — SAFE-01 margin trajectory breaker data
  breaker_events          — SAFE-10 audit log (append-only, kind CHECK constraint)
  predeploy_gate_records  — Pitfall #8 provenance record (git_sha + config_hash)
  competition_history     — defensive no-op if 0005 already created it

Also adds event_type column to tx_receipts if absent.

tx_receipts.event_type is NOT in the original schemas.sql — confirmed by
inspecting 0001_initial_8_tables.py which replays schemas.sql. The column
is added with server_default='unknown' so existing rows stay valid.
T-04-02-07: pre-migration rows have event_type='unknown', which is excluded
from fill-rate breaker queries (filter by event_type='fill' only), so
conservative under-counting applies — false negative is preferable to
over-firing the fill-rate breaker.

Idempotency: every DDL operation is guarded by _has_table / _has_index /
_has_column inspection, so this migration can be re-applied without error.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0007_phase4_tables"
down_revision = "0006_market_reward_calibration"
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


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in [c["name"] for c in sa_inspect(bind).get_columns(table)]


def upgrade() -> None:
    # ── margin_history ────────────────────────────────────────────────────────
    if not _has_table("margin_history"):
        op.create_table(
            "margin_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("chain_ts", sa.Integer(), nullable=False),
            sa.Column("market_id", sa.Text(), nullable=False),
            sa.Column("net_margin_usd", sa.Float(), nullable=False),
            sa.Column("maintenance_margin_usd", sa.Float(), nullable=False),
            sa.Column("available_collateral_usd", sa.Float(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
        )

    if not _has_index("margin_history", "ix_margin_history_market_chain_ts"):
        op.create_index(
            "ix_margin_history_market_chain_ts",
            "margin_history",
            ["market_id", sa.text("chain_ts DESC")],
        )

    # ── breaker_events ────────────────────────────────────────────────────────
    if not _has_table("breaker_events"):
        op.create_table(
            "breaker_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("breaker_name", sa.Text(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("chain_ts", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "kind IN ('kill_emitted','suppression','rearmed')",
                name="ck_breaker_events_kind",
            ),
        )

    if not _has_index("breaker_events", "ix_breaker_events_breaker_chain_ts"):
        op.create_index(
            "ix_breaker_events_breaker_chain_ts",
            "breaker_events",
            ["breaker_name", sa.text("chain_ts DESC")],
        )

    if not _has_index("breaker_events", "ix_breaker_events_kind"):
        op.create_index(
            "ix_breaker_events_kind",
            "breaker_events",
            ["kind"],
        )

    # ── predeploy_gate_records ────────────────────────────────────────────────
    if not _has_table("predeploy_gate_records"):
        op.create_table(
            "predeploy_gate_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("gate_passed", sa.Integer(), nullable=False),
            sa.Column("git_sha", sa.Text(), nullable=False),
            sa.Column("git_dirty", sa.Integer(), nullable=False),
            sa.Column("config_hash", sa.Text(), nullable=False),
            sa.Column("wiki_page_path", sa.Text(), nullable=False),
            sa.Column("run_id", sa.Text(), nullable=False),
            sa.Column("chain_ts", sa.Integer(), nullable=False),
            sa.CheckConstraint(
                "gate_passed IN (0, 1)",
                name="ck_predeploy_gate_records_gate_passed",
            ),
            sa.CheckConstraint(
                "git_dirty IN (0, 1)",
                name="ck_predeploy_gate_records_git_dirty",
            ),
        )

    if not _has_index("predeploy_gate_records", "ix_predeploy_gate_records_chain_ts"):
        op.create_index(
            "ix_predeploy_gate_records_chain_ts",
            "predeploy_gate_records",
            [sa.text("chain_ts DESC")],
        )

    # ── competition_history (defensive no-op if 0005 created it) ─────────────
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

    if not _has_index("competition_history", "ix_competition_history_market_polled"):
        op.create_index(
            "ix_competition_history_market_polled",
            "competition_history",
            ["market_id", sa.text("polled_at_utc DESC")],
        )

    # ── tx_receipts.event_type + chain_ts + market_id + order_id ─────────────
    # These columns are added idempotently (guarded by _has_column).
    # event_type: SAFE-05 FillRateBreaker filters by event_type='fill'.
    # chain_ts: SAFE-05 window filter (rows within last 1 hour).
    # market_id: SAFE-05 per-market fill count.
    # order_id: test fixture seeding convenience (maps to related_order_id semantics).
    if _has_table("tx_receipts") and not _has_column("tx_receipts", "event_type"):
        op.add_column(
            "tx_receipts",
            sa.Column(
                "event_type",
                sa.Text(),
                nullable=False,
                server_default="unknown",
            ),
        )
    if _has_table("tx_receipts") and not _has_column("tx_receipts", "chain_ts"):
        op.add_column(
            "tx_receipts",
            sa.Column(
                "chain_ts",
                sa.Integer(),
                nullable=True,
            ),
        )
    if _has_table("tx_receipts") and not _has_column("tx_receipts", "market_id"):
        op.add_column(
            "tx_receipts",
            sa.Column(
                "market_id",
                sa.Text(),
                nullable=True,
            ),
        )
    if _has_table("tx_receipts") and not _has_column("tx_receipts", "order_id"):
        op.add_column(
            "tx_receipts",
            sa.Column(
                "order_id",
                sa.Text(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    # No downgrade — Phase 4 tables stay forward-compatible.
    # Removing event_type or dropping Phase 4 tables would break active pollers
    # and breaker queries. If a rollback is needed, restore from backup.
    pass
