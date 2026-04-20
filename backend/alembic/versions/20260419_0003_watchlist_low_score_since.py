"""Add low_score_since tracking to watchlist entries."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260419_0003"
down_revision = "20260419_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the low_score_since column to watchlist."""

    op.add_column(
        "watchlist",
        sa.Column("low_score_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove the low_score_since column from watchlist."""

    op.drop_column("watchlist", "low_score_since")
