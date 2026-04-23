"""Add candle usage lane and backfill known rows."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260422_0004"
down_revision = "20260419_0003"
branch_labels = None
depends_on = None

_USAGE_CHECK_NAME = "ck_candles_usage_allowed"


def upgrade() -> None:
    """Add nullable candle usage lane and classify known historical rows."""

    op.add_column(
        "candles",
        sa.Column("usage", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        _USAGE_CHECK_NAME,
        "candles",
        "usage IS NULL OR usage IN ('ml', 'trading')",
    )

    conn = op.get_bind()

    # ML lane:
    # - Alpaca batched training candles
    # - imported crypto CSV training candles
    # - current crypto 1D Kraken catch-up candles used by ML refresh
    conn.execute(
        sa.text(
            """
            UPDATE candles
            SET usage = 'ml'
            WHERE source IN ('alpaca_training', 'crypto_csv_training')
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE candles
            SET usage = 'ml'
            WHERE usage IS NULL
              AND source = 'kraken'
              AND asset_class = 'crypto'
              AND timeframe = '1d'
            """
        )
    )

    # Trading lane:
    # - Tradier runtime/watchlist candles
    # - Kraken non-1D candles used by runtime/watchlist workflows
    conn.execute(
        sa.text(
            """
            UPDATE candles
            SET usage = 'trading'
            WHERE usage IS NULL
              AND source = 'tradier'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE candles
            SET usage = 'trading'
            WHERE usage IS NULL
              AND source = 'kraken'
              AND NOT (asset_class = 'crypto' AND timeframe = '1d')
            """
        )
    )

    # Leave any unmatched rows as NULL for manual review before making the column non-nullable.


def downgrade() -> None:
    """Remove candle usage lane."""

    op.drop_constraint(_USAGE_CHECK_NAME, "candles", type_="check")
    op.drop_column("candles", "usage")