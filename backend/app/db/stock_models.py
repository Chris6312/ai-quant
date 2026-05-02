"""Stock-only ORM models for the stock asset lane."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StockSymbolRow(Base):
    """Canonical stock symbol identity for the stock-only lane."""

    __tablename__ = "stock_symbols"
    __table_args__ = (
        UniqueConstraint("symbol", name="uq_stock_symbols_symbol"),
        Index("ix_stock_symbols_active_symbol", "is_active", "symbol"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(96), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockUniverseCandidateRow(Base):
    """Stock screening candidate before watchlist promotion."""

    __tablename__ = "stock_universe_candidates"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "source",
            "as_of",
            name="uq_stock_candidate_symbol_source_asof",
        ),
        Index("ix_stock_candidates_as_of", "as_of"),
        Index("ix_stock_candidates_symbol_as_of", "symbol", "as_of"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockWatchlistRow(Base):
    """Approved stock monitoring list, separate from the crypto universe."""

    __tablename__ = "stock_watchlist"
    __table_args__ = (
        UniqueConstraint("symbol", name="uq_stock_watchlist_symbol"),
        Index("ix_stock_watchlist_status_symbol", "status", "symbol"),
        Index("ix_stock_watchlist_strategy_status", "strategy_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promoted_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockCandleRow(Base):
    """Stock OHLCV storage with separated usage lanes."""

    __tablename__ = "stock_candles"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "timestamp",
            "usage",
            name="uq_stock_candles_lane",
        ),
        Index("ix_stock_candles_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp"),
        Index("ix_stock_candles_usage_timestamp", "usage", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    high: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    low: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    close: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    volume: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    usage: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockNewsEventRow(Base):
    """Company-specific stock news metadata and sentiment shell."""

    __tablename__ = "stock_news_events"
    __table_args__ = (
        UniqueConstraint("symbol", "url", name="uq_stock_news_symbol_url"),
        Index("ix_stock_news_symbol_published", "symbol", "published_at"),
        Index("ix_stock_news_source_published", "source", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    headline: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(96), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockCongressEventRow(Base):
    """Congressional stock disclosure context, never a direct trigger."""

    __tablename__ = "stock_congress_events"
    __table_args__ = (
        Index("ix_stock_congress_symbol_filing", "symbol", "filing_date"),
        Index("ix_stock_congress_representative", "representative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    representative: Mapped[str] = mapped_column(String(128), nullable=False)
    transaction_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    amount_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delay_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockInsiderEventRow(Base):
    """SEC Form 4 stock insider disclosure used as a supporting signal."""

    __tablename__ = "stock_insider_events"
    __table_args__ = (
        Index("ix_stock_insider_symbol_filing", "symbol", "filing_date"),
        Index("ix_stock_insider_name", "insider_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    insider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shares: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockStrategyProfileRow(Base):
    """Stock strategy contract including frozen hold-time defaults."""

    __tablename__ = "stock_strategy_profiles"
    __table_args__ = (
        UniqueConstraint("strategy_type", name="uq_stock_strategy_profiles_type"),
        CheckConstraint("max_hold_hours > 0", name="ck_stock_strategy_max_hold_positive"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    strategy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_hold_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    is_short_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockPaperPositionRow(Base):
    """Stock-only paper position shell for later ledger durability."""

    __tablename__ = "stock_paper_positions"
    __table_args__ = (
        CheckConstraint("max_hold_hours > 0", name="ck_stock_position_max_hold_positive"),
        Index("ix_stock_paper_positions_symbol_status", "symbol", "status"),
        Index("ix_stock_paper_positions_strategy_status", "strategy_type", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(64), nullable=False)
    max_hold_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class StockPaperFillRow(Base):
    """Stock-only paper fill shell linked to stock paper positions."""

    __tablename__ = "stock_paper_fills"
    __table_args__ = (
        Index("ix_stock_paper_fills_position", "position_id"),
        Index("ix_stock_paper_fills_symbol_filled", "symbol", "filled_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    position_id: Mapped[str] = mapped_column(
        ForeignKey("stock_paper_positions.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric, nullable=False)
    price: Mapped[float] = mapped_column(Numeric, nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
