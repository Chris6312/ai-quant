"""Add candle usage to the candle primary key."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260502_0010"
down_revision = "20260501_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow ML and trading candles to coexist for the same bar timestamp."""

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE candles
            SET usage = 'trading'
            WHERE usage IS NULL
            """
        )
    )

    op.drop_index("ix_candles_symbol_timeframe_time", table_name="candles")
    op.drop_constraint("candles_pkey", "candles", type_="primary")
    op.alter_column(
        "candles",
        "usage",
        existing_type=sa.String(length=16),
        nullable=False,
    )
    op.create_primary_key(
        "candles_pkey",
        "candles",
        ["time", "symbol", "timeframe", "usage"],
    )
    op.create_index(
        "ix_candles_symbol_timeframe_usage_time",
        "candles",
        ["symbol", "timeframe", "usage", "time"],
    )


def downgrade() -> None:
    """Restore the pre-ML-TF2 candle identity."""

    op.drop_index("ix_candles_symbol_timeframe_usage_time", table_name="candles")
    op.drop_constraint("candles_pkey", "candles", type_="primary")
    op.alter_column(
        "candles",
        "usage",
        existing_type=sa.String(length=16),
        nullable=True,
    )
    op.create_primary_key(
        "candles_pkey",
        "candles",
        ["time", "symbol", "timeframe"],
    )
    op.create_index(
        "ix_candles_symbol_timeframe_time",
        "candles",
        ["symbol", "timeframe", "time"],
    )
