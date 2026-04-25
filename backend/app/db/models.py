"""ORM models for the core trading bot schema."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
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
    usage: Mapped[str | None] = mapped_column(String(16), nullable=True)


class WatchlistRow(Base):
    """Active watchlist entry."""

    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    added_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    research_score: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    low_score_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
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
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )



class CryptoDailySentimentRow(Base):
    """Daily aggregated crypto news sentiment by canonical symbol."""

    __tablename__ = "crypto_daily_sentiment"
    __table_args__ = (
        Index("ix_crypto_daily_sentiment_symbol_date", "symbol", "sentiment_date"),
        Index("ix_crypto_daily_sentiment_asset_date", "asset_class", "sentiment_date"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    sentiment_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    neutral_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    compound_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
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
        default=lambda: datetime.now(tz=UTC),
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
        default=lambda: datetime.now(tz=UTC),
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
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)



class PredictionRow(Base):
    """Persisted ML prediction snapshot."""

    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_asset_created", "asset_class", "created_at"),
        Index("ix_predictions_symbol_candle", "symbol", "candle_time"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    probability_down: Mapped[float] = mapped_column(Float, nullable=False)
    probability_flat: Mapped[float] = mapped_column(Float, nullable=False)
    probability_up: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    gate_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    top_driver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_event_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signal_event: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class PredictionShapRow(Base):
    """Persisted per-feature LightGBM contribution values for a prediction."""

    __tablename__ = "prediction_shap"
    __table_args__ = (
        Index("ix_prediction_shap_prediction_abs", "prediction_id", "abs_value"),
    )

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    prediction_id: Mapped[str] = mapped_column(
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_value: Mapped[float] = mapped_column(Float, nullable=False)
    shap_value: Mapped[float] = mapped_column(Float, nullable=False)
    abs_value: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
class TradeRow(Base):
    """Completed trade record for P&L accounting."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    position_id: Mapped[str | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    exit_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    size: Mapped[float] = mapped_column(Numeric, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False)
    commission: Mapped[float] = mapped_column(Numeric, default=0.0, nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )


class PortfolioSnapshotRow(Base):
    """Portfolio snapshot for NAV and P&L auditing."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nav: Mapped[float] = mapped_column(Numeric, nullable=False)
    stock_cash: Mapped[float] = mapped_column(Numeric, nullable=False)
    crypto_cash: Mapped[float] = mapped_column(Numeric, nullable=False)
    open_position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    realized_pnl_today: Mapped[float] = mapped_column(Numeric, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
