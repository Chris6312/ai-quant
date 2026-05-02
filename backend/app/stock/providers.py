"""Stock provider contracts, ownership metadata, and config helpers.

This module intentionally defines boundaries only. It does not fetch provider
data, start workers, place orders, or make trading decisions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from app.config.settings import Settings


class StockProviderName(StrEnum):
    """Known stock provider placeholders."""

    ALPACA = "alpaca"
    TRADIER = "tradier"
    SEC = "sec"
    CONGRESS = "congress"
    NEWS = "news"
    EARNINGS_ANALYST = "earnings_analyst"


class StockProviderRole(StrEnum):
    """Stock provider responsibilities."""

    HISTORICAL_CANDLES = "historical_candles"
    LIVE_QUOTES = "live_quotes"
    INTRADAY_CANDLES = "intraday_candles"
    INSIDER_FILINGS = "insider_filings"
    CONGRESS_FILINGS = "congress_filings"
    NEWS_ARTICLES = "news_articles"
    EARNINGS_ANALYST = "earnings_analyst"


class StockProviderLane(StrEnum):
    """The stock lane a provider feeds in future phases."""

    ML_BACKTESTING = "ml_backtesting"
    TRADING_RUNTIME = "trading_runtime"
    CONTEXT = "context"
    OPTIONAL_CONTEXT = "optional_context"


class StockProviderHealthStatus(StrEnum):
    """Non-runtime health states for provider configuration."""

    NOT_CONFIGURED = "not_configured"
    READY = "ready"
    DEGRADED = "degraded"


@dataclass(slots=True, frozen=True)
class StockProviderCapability:
    """Declare the owner for one stock provider job."""

    provider: StockProviderName
    role: StockProviderRole
    lane: StockProviderLane
    description: str


@dataclass(slots=True, frozen=True)
class StockProviderConfig:
    """Configuration placeholder for one provider role."""

    provider: StockProviderName
    role: StockProviderRole
    enabled: bool
    base_url: str | None
    api_key_configured: bool
    api_secret_configured: bool = True
    account_id_configured: bool = True
    required: bool = True


@dataclass(slots=True, frozen=True)
class StockProviderHealth:
    """Health result derived from configuration only."""

    provider: StockProviderName
    role: StockProviderRole
    status: StockProviderHealthStatus
    reason: str


@dataclass(slots=True, frozen=True)
class StockProviderFailure:
    """Structured provider failure record for future persistence/logging."""

    provider: StockProviderName
    role: StockProviderRole
    symbol: str | None
    message: str
    occurred_at: datetime


@dataclass(slots=True, frozen=True)
class StockSymbolNormalization:
    """Result of applying stock symbol normalization rules."""

    raw_symbol: str
    canonical_symbol: str
    provider_symbol: str
    is_supported: bool
    unsupported_reason: str | None


@dataclass(slots=True, frozen=True)
class StockCandleRequest:
    """Contract input for future historical or intraday stock candle providers."""

    symbol: str
    timeframe: str
    start: datetime
    end: datetime


@dataclass(slots=True, frozen=True)
class StockCandle:
    """Provider-neutral stock candle contract."""

    symbol: str
    timeframe: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    provider: StockProviderName


@dataclass(slots=True, frozen=True)
class StockQuote:
    """Provider-neutral live stock quote contract."""

    symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    as_of: datetime
    provider: StockProviderName


class StockHistoricalCandleProvider(Protocol):
    """Boundary for future historical stock candle sources."""

    provider: StockProviderName

    async def get_historical_candles(
        self,
        request: StockCandleRequest,
    ) -> Sequence[StockCandle]:
        """Return historical candles for ML/backtesting."""


class StockIntradayCandleProvider(Protocol):
    """Boundary for future active-watchlist intraday candle sources."""

    provider: StockProviderName

    async def get_intraday_candles(
        self,
        request: StockCandleRequest,
    ) -> Sequence[StockCandle]:
        """Return intraday candles for active stock watchlist symbols only."""


class StockQuoteProvider(Protocol):
    """Boundary for future live quote sources."""

    provider: StockProviderName

    async def get_quote(self, symbol: str) -> StockQuote:
        """Return one quote snapshot."""


STOCK_PROVIDER_CAPABILITIES: tuple[StockProviderCapability, ...] = (
    StockProviderCapability(
        provider=StockProviderName.ALPACA,
        role=StockProviderRole.HISTORICAL_CANDLES,
        lane=StockProviderLane.ML_BACKTESTING,
        description="Historical stock candles for ML and backtesting only.",
    ),
    StockProviderCapability(
        provider=StockProviderName.TRADIER,
        role=StockProviderRole.LIVE_QUOTES,
        lane=StockProviderLane.TRADING_RUNTIME,
        description="Live stock quotes.",
    ),
    StockProviderCapability(
        provider=StockProviderName.TRADIER,
        role=StockProviderRole.INTRADAY_CANDLES,
        lane=StockProviderLane.TRADING_RUNTIME,
        description="Active stock watchlist intraday candles.",
    ),
    StockProviderCapability(
        provider=StockProviderName.SEC,
        role=StockProviderRole.INSIDER_FILINGS,
        lane=StockProviderLane.CONTEXT,
        description="SEC Form 4 insider filing context.",
    ),
    StockProviderCapability(
        provider=StockProviderName.CONGRESS,
        role=StockProviderRole.CONGRESS_FILINGS,
        lane=StockProviderLane.CONTEXT,
        description="Congressional filing context.",
    ),
    StockProviderCapability(
        provider=StockProviderName.NEWS,
        role=StockProviderRole.NEWS_ARTICLES,
        lane=StockProviderLane.CONTEXT,
        description="Stock article ingestion context.",
    ),
    StockProviderCapability(
        provider=StockProviderName.EARNINGS_ANALYST,
        role=StockProviderRole.EARNINGS_ANALYST,
        lane=StockProviderLane.OPTIONAL_CONTEXT,
        description="Optional future earnings and analyst context.",
    ),
)


def normalize_stock_symbol(symbol: str) -> StockSymbolNormalization:
    """Normalize a stock symbol without mapping crypto or provider-specific aliases."""

    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        return StockSymbolNormalization(
            raw_symbol=symbol,
            canonical_symbol=canonical_symbol,
            provider_symbol=canonical_symbol,
            is_supported=False,
            unsupported_reason="symbol is empty",
        )

    for unsupported_char in ("/", "."):
        if unsupported_char in canonical_symbol:
            return StockSymbolNormalization(
                raw_symbol=symbol,
                canonical_symbol=canonical_symbol,
                provider_symbol=canonical_symbol,
                is_supported=False,
                unsupported_reason=f"contains unsupported provider character '{unsupported_char}'",
            )

    return StockSymbolNormalization(
        raw_symbol=symbol,
        canonical_symbol=canonical_symbol,
        provider_symbol=canonical_symbol,
        is_supported=True,
        unsupported_reason=None,
    )


def build_stock_provider_configs(settings: Settings) -> tuple[StockProviderConfig, ...]:
    """Build stock provider config placeholders from application settings."""

    return (
        StockProviderConfig(
            provider=StockProviderName.ALPACA,
            role=StockProviderRole.HISTORICAL_CANDLES,
            enabled=settings.stock_alpaca_historical_enabled,
            base_url=settings.alpaca_base_url,
            api_key_configured=settings.alpaca_api_key is not None,
            api_secret_configured=settings.alpaca_api_secret is not None,
        ),
        StockProviderConfig(
            provider=StockProviderName.TRADIER,
            role=StockProviderRole.LIVE_QUOTES,
            enabled=settings.stock_tradier_quotes_enabled,
            base_url=settings.tradier_base_url,
            api_key_configured=settings.tradier_api_key is not None,
            account_id_configured=settings.tradier_account_id is not None,
        ),
        StockProviderConfig(
            provider=StockProviderName.TRADIER,
            role=StockProviderRole.INTRADAY_CANDLES,
            enabled=settings.stock_tradier_intraday_candles_enabled,
            base_url=settings.tradier_base_url,
            api_key_configured=settings.tradier_api_key is not None,
            account_id_configured=settings.tradier_account_id is not None,
        ),
        StockProviderConfig(
            provider=StockProviderName.SEC,
            role=StockProviderRole.INSIDER_FILINGS,
            enabled=settings.stock_sec_insider_enabled,
            base_url=settings.stock_sec_base_url,
            api_key_configured=True,
            required=False,
        ),
        StockProviderConfig(
            provider=StockProviderName.CONGRESS,
            role=StockProviderRole.CONGRESS_FILINGS,
            enabled=settings.stock_congress_enabled,
            base_url=settings.stock_congress_base_url,
            api_key_configured=settings.stock_congress_api_key is not None,
            required=False,
        ),
        StockProviderConfig(
            provider=StockProviderName.NEWS,
            role=StockProviderRole.NEWS_ARTICLES,
            enabled=settings.stock_news_enabled,
            base_url=settings.research_news_base_url,
            api_key_configured=settings.research_news_api_key is not None,
            required=False,
        ),
        StockProviderConfig(
            provider=StockProviderName.EARNINGS_ANALYST,
            role=StockProviderRole.EARNINGS_ANALYST,
            enabled=settings.stock_earnings_analyst_enabled,
            base_url=settings.stock_earnings_analyst_base_url,
            api_key_configured=settings.stock_earnings_analyst_api_key is not None,
            required=False,
        ),
    )


def evaluate_stock_provider_health(config: StockProviderConfig) -> StockProviderHealth:
    """Return a config-only health status for a stock provider placeholder."""

    if not config.enabled:
        return StockProviderHealth(
            provider=config.provider,
            role=config.role,
            status=StockProviderHealthStatus.NOT_CONFIGURED,
            reason="provider role is disabled",
        )

    missing: list[str] = []
    if not config.base_url:
        missing.append("base_url")
    if not config.api_key_configured:
        missing.append("api_key")
    if not config.api_secret_configured:
        missing.append("api_secret")
    if not config.account_id_configured:
        missing.append("account_id")

    if missing:
        return StockProviderHealth(
            provider=config.provider,
            role=config.role,
            status=StockProviderHealthStatus.DEGRADED,
            reason=f"missing {', '.join(missing)}",
        )

    return StockProviderHealth(
        provider=config.provider,
        role=config.role,
        status=StockProviderHealthStatus.READY,
        reason="provider role is configured",
    )


class StockProviderFailureLog:
    """Bounded in-memory failure log contract for future provider persistence."""

    def __init__(self, max_entries: int) -> None:
        self.max_entries = max(max_entries, 1)
        self._failures: list[StockProviderFailure] = []

    def record(
        self,
        *,
        provider: StockProviderName,
        role: StockProviderRole,
        message: str,
        symbol: str | None = None,
        occurred_at: datetime | None = None,
    ) -> StockProviderFailure:
        """Record one structured provider failure."""

        normalized_symbol = normalize_stock_symbol(symbol).canonical_symbol if symbol else None
        failure = StockProviderFailure(
            provider=provider,
            role=role,
            symbol=normalized_symbol,
            message=message,
            occurred_at=occurred_at or datetime.now(tz=UTC),
        )
        self._failures.append(failure)
        del self._failures[: -self.max_entries]
        return failure

    def list_failures(self) -> tuple[StockProviderFailure, ...]:
        """Return recorded provider failures in insertion order."""

        return tuple(self._failures)


__all__ = [
    "STOCK_PROVIDER_CAPABILITIES",
    "StockCandle",
    "StockCandleRequest",
    "StockHistoricalCandleProvider",
    "StockIntradayCandleProvider",
    "StockProviderCapability",
    "StockProviderConfig",
    "StockProviderFailure",
    "StockProviderFailureLog",
    "StockProviderHealth",
    "StockProviderHealthStatus",
    "StockProviderLane",
    "StockProviderName",
    "StockProviderRole",
    "StockQuote",
    "StockQuoteProvider",
    "StockSymbolNormalization",
    "build_stock_provider_configs",
    "evaluate_stock_provider_health",
    "normalize_stock_symbol",
]
