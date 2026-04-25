"""Add crypto daily sentiment persistence table."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260424_0006"
down_revision = "20260424_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create daily crypto sentiment aggregate table."""

    op.create_table(
        "crypto_daily_sentiment",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("sentiment_date", sa.Date(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positive_score", sa.Float(), nullable=True),
        sa.Column("neutral_score", sa.Float(), nullable=True),
        sa.Column("negative_score", sa.Float(), nullable=True),
        sa.Column("compound_score", sa.Float(), nullable=True),
        sa.Column("coverage_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crypto_daily_sentiment_symbol_date",
        "crypto_daily_sentiment",
        ["symbol", "sentiment_date"],
    )
    op.create_index(
        "ix_crypto_daily_sentiment_asset_date",
        "crypto_daily_sentiment",
        ["asset_class", "sentiment_date"],
    )


def downgrade() -> None:
    """Drop daily crypto sentiment aggregate table."""

    op.drop_index("ix_crypto_daily_sentiment_asset_date", table_name="crypto_daily_sentiment")
    op.drop_index("ix_crypto_daily_sentiment_symbol_date", table_name="crypto_daily_sentiment")
    op.drop_table("crypto_daily_sentiment")
