"""ORM models for the core trading bot schema."""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CandleRow(Base):
    """Persisted OHLCV candle."""

    __tablename__ = "candles"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), primary_key=True)
    open: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    high: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    low: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    close: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    volume: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)


class WatchlistRow(Base):
    """Active watchlist entry."""

    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    added_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    research_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchSignalRow(Base):
    """Universe research signal record."""

    __tablename__ = "research_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )


class CongressTradeRow(Base):
    """Congressional trade disclosure."""

    __tablename__ = "congress_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    politician: Mapped[str] = mapped_column(String(128), nullable=False)
    chamber: Mapped[str | None] = mapped_column(String(16), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    trade_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trade_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disclosure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days_to_disclose: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )


class InsiderTradeRow(Base):
    """Insider trade disclosure."""

    __tablename__ = "insider_trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    insider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    shares: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    price_per_share: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    total_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )


class PositionRow(Base):
    """Open or closed portfolio position."""

    __tablename__ = "positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    size: Mapped[float] = mapped_column(Numeric, nullable=False)
    sl_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    tp_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ml_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    research_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
