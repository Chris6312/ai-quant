"""Initial schema for trading bot infrastructure."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260419_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the core schema objects."""

    now = sa.text("now()")
    open_default = sa.text("'open'")

    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    op.create_table(
        "candles",
        sa.Column("time", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=16), primary_key=True, nullable=False),
        sa.Column("open", sa.Numeric(), nullable=True),
        sa.Column("high", sa.Numeric(), nullable=True),
        sa.Column("low", sa.Numeric(), nullable=True),
        sa.Column("close", sa.Numeric(), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
    )
    op.execute(
        sa.text("SELECT create_hypertable('candles', 'time', if_not_exists => TRUE)")
    )
    op.create_index("ix_candles_symbol_timeframe_time", "candles", ["symbol", "timeframe", "time"])

    op.create_table(
        "watchlist",
        sa.Column("symbol", sa.String(length=32), primary_key=True, nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("added_by", sa.String(length=64), nullable=True),
        sa.Column("research_score", sa.Numeric(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "research_signals",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Numeric(), nullable=True),
        sa.Column("direction", sa.String(length=16), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_index(
        "ix_research_signals_symbol_signal_type_created_at",
        "research_signals",
        ["symbol", "signal_type", "created_at"],
    )

    op.create_table(
        "congress_trades",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("politician", sa.String(length=128), nullable=False),
        sa.Column("chamber", sa.String(length=16), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("trade_type", sa.String(length=16), nullable=True),
        sa.Column("amount_range", sa.String(length=64), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("disclosure_date", sa.Date(), nullable=True),
        sa.Column("days_to_disclose", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )

    op.create_table(
        "insider_trades",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("insider_name", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("transaction_type", sa.String(length=8), nullable=True),
        sa.Column("shares", sa.Numeric(), nullable=True),
        sa.Column("price_per_share", sa.Numeric(), nullable=True),
        sa.Column("total_value", sa.Numeric(), nullable=True),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(), nullable=False),
        sa.Column("size", sa.Numeric(), nullable=False),
        sa.Column("sl_price", sa.Numeric(), nullable=True),
        sa.Column("tp_price", sa.Numeric(), nullable=True),
        sa.Column("strategy_id", sa.String(length=64), nullable=True),
        sa.Column("ml_confidence", sa.Float(), nullable=True),
        sa.Column("research_score", sa.Numeric(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=open_default),
    )


def downgrade() -> None:
    """Drop the core schema objects."""

    op.drop_table("positions")
    op.drop_table("insider_trades")
    op.drop_table("congress_trades")
    op.drop_index(
        "ix_research_signals_symbol_signal_type_created_at",
        table_name="research_signals",
    )
    op.drop_table("research_signals")
    op.drop_table("watchlist")
    op.drop_index("ix_candles_symbol_timeframe_time", table_name="candles")
    op.drop_table("candles")
