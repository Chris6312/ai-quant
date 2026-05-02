"""Add stock schema and persistence foundation."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260501_0009"
down_revision = "20260427_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create stock-only persistence tables."""

    op.create_table(
        "stock_symbols",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("exchange", sa.String(length=32), nullable=True),
        sa.Column("sector", sa.String(length=96), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uq_stock_symbols_symbol"),
    )
    op.create_index("ix_stock_symbols_active_symbol", "stock_symbols", ["is_active", "symbol"])

    op.create_table(
        "stock_universe_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "source",
            "as_of",
            name="uq_stock_candidate_symbol_source_asof",
        ),
    )
    op.create_index("ix_stock_candidates_as_of", "stock_universe_candidates", ["as_of"])
    op.create_index(
        "ix_stock_candidates_symbol_as_of",
        "stock_universe_candidates",
        ["symbol", "as_of"],
    )

    op.create_table(
        "stock_watchlist",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=True),
        sa.Column("promoted_reason", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uq_stock_watchlist_symbol"),
    )
    op.create_index("ix_stock_watchlist_status_symbol", "stock_watchlist", ["status", "symbol"])
    op.create_index(
        "ix_stock_watchlist_strategy_status",
        "stock_watchlist",
        ["strategy_type", "status"],
    )

    op.create_table(
        "stock_candles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(), nullable=True),
        sa.Column("high", sa.Numeric(), nullable=True),
        sa.Column("low", sa.Numeric(), nullable=True),
        sa.Column("close", sa.Numeric(), nullable=True),
        sa.Column("volume", sa.Numeric(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("usage", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "timeframe",
            "timestamp",
            "usage",
            name="uq_stock_candles_lane",
        ),
    )
    op.create_index(
        "ix_stock_candles_symbol_timeframe_timestamp",
        "stock_candles",
        ["symbol", "timeframe", "timestamp"],
    )
    op.create_index("ix_stock_candles_usage_timestamp", "stock_candles", ["usage", "timestamp"])

    op.create_table(
        "stock_news_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=96), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "url", name="uq_stock_news_symbol_url"),
    )
    op.create_index(
        "ix_stock_news_symbol_published",
        "stock_news_events",
        ["symbol", "published_at"],
    )
    op.create_index(
        "ix_stock_news_source_published",
        "stock_news_events",
        ["source", "published_at"],
    )

    op.create_table(
        "stock_congress_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("representative", sa.String(length=128), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=True),
        sa.Column("amount_range", sa.String(length=64), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("delay_days", sa.Integer(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_congress_symbol_filing",
        "stock_congress_events",
        ["symbol", "filing_date"],
    )
    op.create_index("ix_stock_congress_representative", "stock_congress_events", ["representative"])

    op.create_table(
        "stock_insider_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("insider_name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("transaction_type", sa.String(length=32), nullable=True),
        sa.Column("shares", sa.Numeric(), nullable=True),
        sa.Column("price", sa.Numeric(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_insider_symbol_filing",
        "stock_insider_events",
        ["symbol", "filing_date"],
    )
    op.create_index("ix_stock_insider_name", "stock_insider_events", ["insider_name"])

    op.create_table(
        "stock_strategy_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("max_hold_hours", sa.Integer(), nullable=False),
        sa.Column("is_short_allowed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_hold_hours > 0", name="ck_stock_strategy_max_hold_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_type", name="uq_stock_strategy_profiles_type"),
    )

    op.create_table(
        "stock_paper_positions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("entry_price", sa.Numeric(), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("max_hold_hours", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_hold_hours > 0", name="ck_stock_position_max_hold_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stock_paper_positions_symbol_status",
        "stock_paper_positions",
        ["symbol", "status"],
    )
    op.create_index(
        "ix_stock_paper_positions_strategy_status",
        "stock_paper_positions",
        ["strategy_type", "status"],
    )

    op.create_table(
        "stock_paper_fills",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["stock_paper_positions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_paper_fills_position", "stock_paper_fills", ["position_id"])
    op.create_index(
        "ix_stock_paper_fills_symbol_filled",
        "stock_paper_fills",
        ["symbol", "filled_at"],
    )


def downgrade() -> None:
    """Drop stock-only persistence tables."""

    op.drop_index("ix_stock_paper_fills_symbol_filled", table_name="stock_paper_fills")
    op.drop_index("ix_stock_paper_fills_position", table_name="stock_paper_fills")
    op.drop_table("stock_paper_fills")
    op.drop_index("ix_stock_paper_positions_strategy_status", table_name="stock_paper_positions")
    op.drop_index("ix_stock_paper_positions_symbol_status", table_name="stock_paper_positions")
    op.drop_table("stock_paper_positions")
    op.drop_table("stock_strategy_profiles")
    op.drop_index("ix_stock_insider_name", table_name="stock_insider_events")
    op.drop_index("ix_stock_insider_symbol_filing", table_name="stock_insider_events")
    op.drop_table("stock_insider_events")
    op.drop_index("ix_stock_congress_representative", table_name="stock_congress_events")
    op.drop_index("ix_stock_congress_symbol_filing", table_name="stock_congress_events")
    op.drop_table("stock_congress_events")
    op.drop_index("ix_stock_news_source_published", table_name="stock_news_events")
    op.drop_index("ix_stock_news_symbol_published", table_name="stock_news_events")
    op.drop_table("stock_news_events")
    op.drop_index("ix_stock_candles_usage_timestamp", table_name="stock_candles")
    op.drop_index("ix_stock_candles_symbol_timeframe_timestamp", table_name="stock_candles")
    op.drop_table("stock_candles")
    op.drop_index("ix_stock_watchlist_strategy_status", table_name="stock_watchlist")
    op.drop_index("ix_stock_watchlist_status_symbol", table_name="stock_watchlist")
    op.drop_table("stock_watchlist")
    op.drop_index("ix_stock_candidates_symbol_as_of", table_name="stock_universe_candidates")
    op.drop_index("ix_stock_candidates_as_of", table_name="stock_universe_candidates")
    op.drop_table("stock_universe_candidates")
    op.drop_index("ix_stock_symbols_active_symbol", table_name="stock_symbols")
    op.drop_table("stock_symbols")
