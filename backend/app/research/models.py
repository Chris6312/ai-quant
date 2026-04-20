"""Shared research models and value objects."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from pydantic import BaseModel, Field

from app.config.constants import DEFAULT_SIGNAL_WEIGHTS

type SignalWeights = dict[str, float]


@dataclass(slots=True, frozen=True)
class SentimentScore:
    """Represent one article sentiment result."""

    direction: str
    confidence: float
    numeric: float
    created_at: datetime


@dataclass(slots=True, frozen=True)
class ResearchScoreBreakdown:
    """Represent a composite watchlist score and its contributors."""

    symbol: str
    news_sentiment_7d: float
    congress_buy: float
    insider_buy: float
    screener_pass: float
    analyst_upgrade: float
    composite_score: float


@dataclass(slots=True, frozen=True)
class NewsArticle:
    """Represent a news article to score."""

    symbol: str
    title: str
    summary: str
    published_at: datetime
    source: str


@dataclass(slots=True, frozen=True)
class CongressTrade:
    """Represent one congressional trade disclosure."""

    symbol: str
    trade_type: str
    chamber: str | None
    days_to_disclose: int
    politician: str
    committee: str | None
    amount_range: str | None
    trade_date: date | None
    disclosure_date: date | None


@dataclass(slots=True, frozen=True)
class InsiderTrade:
    """Represent one insider filing."""

    symbol: str
    insider_name: str
    title: str | None
    transaction_type: str
    total_value: float
    filing_date: date | None
    transaction_date: date | None


@dataclass(slots=True, frozen=True)
class ScreeningMetrics:
    """Represent one stock screener result."""

    symbol: str
    avg_volume: float
    price: float
    market_cap: float
    pe_ratio: float | None
    relative_volume: float
    float_shares: float
    sector: str
    above_50d_ema: bool
    earnings_blocked: bool


@dataclass(slots=True, frozen=True)
class AnalystRating:
    """Represent an analyst rating event."""

    symbol: str
    firm: str
    action: str
    current_price: float
    old_price_target: float | None
    new_price_target: float | None
    rating: str
    published_at: datetime


@dataclass(slots=True, frozen=True)
class WatchlistCandidate:
    """Represent a symbol being considered for watchlist promotion."""

    symbol: str
    asset_class: str
    breakdown: ResearchScoreBreakdown
    added_by: str


class NewsArticlePayload(BaseModel):
    """API payload for a news article."""

    symbol: str
    title: str
    summary: str
    published_at: datetime
    source: str = Field(min_length=1)


class CongressTradePayload(BaseModel):
    """API payload for a congressional trade."""

    symbol: str
    trade_type: str
    chamber: str | None = None
    politician: str
    committee: str | None = None
    amount_range: str | None = None
    trade_date: date | None = None
    disclosure_date: date | None = None
    days_to_disclose: int


class InsiderTradePayload(BaseModel):
    """API payload for an insider trade."""

    symbol: str
    insider_name: str
    title: str | None = None
    transaction_type: str
    total_value: float = Field(ge=0.0)
    filing_date: date | None = None
    transaction_date: date | None = None


class ScreeningMetricsPayload(BaseModel):
    """API payload for screener metrics."""

    symbol: str
    avg_volume: float = Field(ge=0.0)
    price: float = Field(ge=0.0)
    market_cap: float = Field(ge=0.0)
    pe_ratio: float | None = None
    relative_volume: float = Field(ge=0.0)
    float_shares: float = Field(ge=0.0)
    sector: str
    above_50d_ema: bool
    earnings_blocked: bool


class AnalystRatingPayload(BaseModel):
    """API payload for an analyst rating event."""

    symbol: str
    firm: str
    action: str
    current_price: float = Field(ge=0.0)
    old_price_target: float | None = None
    new_price_target: float | None = None
    rating: str
    published_at: datetime


class WatchlistScorePayload(BaseModel):
    """API payload for a watchlist score breakdown."""

    symbol: str
    news_sentiment_7d: float
    congress_buy: float
    insider_buy: float
    screener_pass: float
    analyst_upgrade: float
    composite_score: float


DEFAULT_WEIGHTS: SignalWeights = DEFAULT_SIGNAL_WEIGHTS


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=UTC)
