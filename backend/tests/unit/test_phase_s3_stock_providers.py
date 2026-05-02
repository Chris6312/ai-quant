"""Phase S3 stock provider boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config.settings import Settings
from app.stock.providers import (
    STOCK_PROVIDER_CAPABILITIES,
    StockCandle,
    StockCandleRequest,
    StockHistoricalCandleProvider,
    StockProviderFailureLog,
    StockProviderHealthStatus,
    StockProviderName,
    StockProviderRole,
    build_stock_provider_configs,
    evaluate_stock_provider_health,
    normalize_stock_symbol,
)


class _FakeHistoricalProvider:
    """Small contract implementation used by the provider protocol test."""

    provider = StockProviderName.ALPACA

    async def get_historical_candles(
        self,
        request: StockCandleRequest,
    ) -> tuple[StockCandle, ...]:
        return (
            StockCandle(
                symbol=request.symbol,
                timeframe=request.timeframe,
                time=request.start,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1_000.0,
                provider=self.provider,
            ),
        )


def test_stock_provider_capabilities_assign_each_s3_role() -> None:
    """S3 provider ownership should be declared without runtime workers."""

    capability_by_role = {
        capability.role: capability for capability in STOCK_PROVIDER_CAPABILITIES
    }

    assert capability_by_role[StockProviderRole.HISTORICAL_CANDLES].provider == (
        StockProviderName.ALPACA
    )
    assert capability_by_role[StockProviderRole.LIVE_QUOTES].provider == StockProviderName.TRADIER
    assert capability_by_role[StockProviderRole.INTRADAY_CANDLES].provider == (
        StockProviderName.TRADIER
    )
    assert capability_by_role[StockProviderRole.INSIDER_FILINGS].provider == StockProviderName.SEC
    assert capability_by_role[StockProviderRole.CONGRESS_FILINGS].provider == (
        StockProviderName.CONGRESS
    )
    assert capability_by_role[StockProviderRole.NEWS_ARTICLES].provider == StockProviderName.NEWS


def test_stock_provider_configs_are_disabled_placeholders_by_default() -> None:
    """Default stock provider config should not imply live provider access."""

    configs = build_stock_provider_configs(Settings())

    assert len(configs) == len(STOCK_PROVIDER_CAPABILITIES)
    assert all(not config.enabled for config in configs)
    assert {
        evaluate_stock_provider_health(config).status for config in configs
    } == {StockProviderHealthStatus.NOT_CONFIGURED}


def test_enabled_provider_health_reports_missing_credentials() -> None:
    """Health checks should be config-only and identify missing placeholders."""

    settings = Settings(
        _env_file=None,
        stock_alpaca_historical_enabled=True,
        alpaca_api_key=None,
        alpaca_api_secret=None,
    )

    alpaca_config = next(
        config
        for config in build_stock_provider_configs(settings)
        if config.role == StockProviderRole.HISTORICAL_CANDLES
    )
    health = evaluate_stock_provider_health(alpaca_config)

    assert health.status == StockProviderHealthStatus.DEGRADED
    assert "api_key" in health.reason
    assert "api_secret" in health.reason


def test_symbol_normalization_is_stock_specific() -> None:
    """Stock symbols should normalize without treating crypto aliases as valid stocks."""

    normalized = normalize_stock_symbol(" aapl ")
    share_class = normalize_stock_symbol("BRK.B")
    crypto_pair = normalize_stock_symbol("BTC/USD")

    assert normalized.canonical_symbol == "AAPL"
    assert normalized.provider_symbol == "AAPL"
    assert normalized.is_supported is True
    assert share_class.is_supported is False
    assert share_class.unsupported_reason == "contains unsupported provider character '.'"
    assert crypto_pair.is_supported is False
    assert crypto_pair.unsupported_reason == "contains unsupported provider character '/'"


def test_failure_log_records_provider_failure_contracts() -> None:
    """Provider failures should be structured and bounded for later persistence."""

    failure_log = StockProviderFailureLog(max_entries=1)
    first_time = datetime(2026, 5, 1, tzinfo=UTC)
    second_time = datetime(2026, 5, 2, tzinfo=UTC)

    failure_log.record(
        provider=StockProviderName.TRADIER,
        role=StockProviderRole.LIVE_QUOTES,
        symbol="msft",
        message="timeout",
        occurred_at=first_time,
    )
    retained = failure_log.record(
        provider=StockProviderName.SEC,
        role=StockProviderRole.INSIDER_FILINGS,
        symbol="aapl",
        message="parse error",
        occurred_at=second_time,
    )

    assert failure_log.list_failures() == (retained,)
    assert retained.symbol == "AAPL"
    assert retained.occurred_at == second_time


@pytest.mark.asyncio
async def test_historical_provider_protocol_shape() -> None:
    """Future historical providers should satisfy the candle contract."""

    provider: StockHistoricalCandleProvider = _FakeHistoricalProvider()
    request = StockCandleRequest(
        symbol="AAPL",
        timeframe="1Day",
        start=datetime(2026, 5, 1, tzinfo=UTC),
        end=datetime(2026, 5, 2, tzinfo=UTC),
    )

    candles = await provider.get_historical_candles(request)

    assert candles[0].provider == StockProviderName.ALPACA
    assert candles[0].symbol == "AAPL"
