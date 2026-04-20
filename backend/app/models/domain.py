"""Domain value objects used outside the persistence layer."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class Candle:
    """Represent an OHLCV candle."""

    time: datetime
    symbol: str
    asset_class: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


@dataclass(slots=True, frozen=True)
class WatchlistEntry:
    """Represent a watchlist symbol."""

    symbol: str
    asset_class: str
    added_by: str | None
    research_score: float | None
    is_active: bool
    notes: str | None


@dataclass(slots=True, frozen=True)
class Position:
    """Represent a position in the portfolio."""

    symbol: str
    asset_class: str
    side: str
    entry_price: float
    size: float
    sl_price: float | None
    tp_price: float | None
    strategy_id: str | None
    ml_confidence: float | None
    research_score: float | None
    status: str
