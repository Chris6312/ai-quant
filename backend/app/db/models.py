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
    UniqueConstraint,
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



class PaperAccountRow(Base):
    """Durable paper cash ledger by asset class."""

    __tablename__ = "paper_account"
    __table_args__ = (
        UniqueConstraint("asset_class", name="uq_paper_account_asset_class"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    cash_balance: Mapped[float] = mapped_column(Numeric, nullable=False)
    default_cash_balance: Mapped[float] = mapped_column(Numeric, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    reset_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class PaperPositionRow(Base):
    """Durable paper position state restored after restart."""

    __tablename__ = "paper_positions"
    __table_args__ = (
        Index("ix_paper_positions_symbol_status", "symbol", "status"),
        Index("ix_paper_positions_asset_status", "asset_class", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    size: Mapped[float] = mapped_column(Numeric, nullable=False)
    average_entry_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperOrderRow(Base):
    """Durable paper order record used before and after restart."""

    __tablename__ = "paper_orders"
    __table_args__ = (
        Index("ix_paper_orders_symbol_created", "symbol", "created_at"),
        Index("ix_paper_orders_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_size: Mapped[float] = mapped_column(Numeric, nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    filled_size: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    average_fill_price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    remaining_size: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    strategy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="paper")
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperFillRow(Base):
    """Durable paper fill event used for audit and restart recovery."""

    __tablename__ = "paper_fills"
    __table_args__ = (
        Index("ix_paper_fills_order", "order_id"),
        Index("ix_paper_fills_symbol_filled", "symbol", "filled_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("paper_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("paper_positions.id", ondelete="SET NULL"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    fill_size: Mapped[float] = mapped_column(Numeric, nullable=False)
    fill_price: Mapped[float] = mapped_column(Numeric, nullable=False)
    gross: Mapped[float] = mapped_column(Numeric, nullable=False)
    commission: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    cash_after: Mapped[float] = mapped_column(Numeric, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="paper")
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
