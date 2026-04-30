"""Phase 05.2 Wave 2a — add effective_at_utc + next_refresh_at_utc to market_reward_calibration.

Bug #2 fix infrastructure: operator-supplied calibration rows need explicit
'authoritative starting at' and 'should be re-checked by' timestamps so
epoch-keyed rows (e.g. prior epoch long_split=0.327, current epoch 0.760)
can co-exist in the table with the latest-effective-row read picking the
active epoch. Prior rows (including the original 0.784) stay as immutable
historical record.

Idempotent via _has_column guard (mirrors 0007 pattern). Forward-only — new
columns are nullable; backfill happens by setting them to calibrated_at_utc
on existing rows.

Wiki: [[phase-05-2-alembic-0008]] (filed in W2a).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0008_market_reward_calibration_effective_at"
down_revision = "0007_phase4_tables"
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
    """Add effective_at_utc + next_refresh_at_utc columns + supporting index."""
    if not _has_table("market_reward_calibration"):
        # 0006 hasn't run; this migration is a no-op for that path.
        return

    if not _has_column("market_reward_calibration", "effective_at_utc"):
        op.add_column(
            "market_reward_calibration",
            sa.Column("effective_at_utc", sa.Text(), nullable=True),
        )
        # Backfill: existing rows get effective_at_utc = calibrated_at_utc.
        op.execute(
            "UPDATE market_reward_calibration "
            "SET effective_at_utc = calibrated_at_utc "
            "WHERE effective_at_utc IS NULL"
        )

    if not _has_column("market_reward_calibration", "next_refresh_at_utc"):
        op.add_column(
            "market_reward_calibration",
            sa.Column("next_refresh_at_utc", sa.Text(), nullable=True),
        )
        # Backfill: existing rows get next_refresh_at_utc = calibrated_at_utc
        # (operator can re-trigger refresh on any read).
        op.execute(
            "UPDATE market_reward_calibration "
            "SET next_refresh_at_utc = calibrated_at_utc "
            "WHERE next_refresh_at_utc IS NULL"
        )

    if not _has_index("market_reward_calibration", "ix_market_reward_calibration_market_effective"):
        op.create_index(
            "ix_market_reward_calibration_market_effective",
            "market_reward_calibration",
            ["market_id", sa.text("effective_at_utc DESC")],
        )


def downgrade() -> None:
    # No downgrade — Phase 05.2 columns stay forward-compatible.
    # Removing columns would invalidate operator-calibrated rows that
    # depend on them. Restore from backup if rollback is genuinely needed.
    pass
