"""Add daily Bitcoin dominance feature source."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260427_0008"
down_revision = "20260426_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create daily Bitcoin dominance table for crypto ML features."""

    op.create_table(
        "btc_dominance_daily",
        sa.Column("dominance_date", sa.Date(), nullable=False),
        sa.Column("dominance_pct", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dominance_date"),
    )
    op.create_index(
        "ix_btc_dominance_daily_date",
        "btc_dominance_daily",
        ["dominance_date"],
    )


def downgrade() -> None:
    """Drop daily Bitcoin dominance table."""

    op.drop_index("ix_btc_dominance_daily_date", table_name="btc_dominance_daily")
    op.drop_table("btc_dominance_daily")
