"""Tests for the Alpaca training fetcher."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.config.constants import ML_CANDLE_USAGE


class _FakeResponse:
    """Stand in for an HTTP response."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        """Simulate a successful HTTP response."""

    def json(self) -> object:
        """Return the configured JSON payload."""

        return self._payload


class _FakeClient:
    """Stand in for httpx.AsyncClient."""

    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def get(
        self,
        url: str,
        params: dict[str, object],
        headers: dict[str, str],
    ) -> _FakeResponse:
        """Record the call and return a fake response."""

        self.calls.append({"url": url, "params": params, "headers": headers})
        return _FakeResponse(self.payload)


class _FakeRepository:
    """Stand in for the candle repository."""

    def __init__(self) -> None:
        self.rows: list[object] = []
        self.latest_times: dict[str, datetime | None] = {"AAPL": None, "MSFT": None}

    async def get_latest_candle_times(
        self,
        symbols: list[str],
        timeframe: str,
        source: str | None = None,
    ) -> dict[str, datetime | None]:
        """Return latest candle timestamps for a batch."""

        return {symbol: self.latest_times.get(symbol) for symbol in symbols}

    async def bulk_upsert(self, rows: list[object]) -> None:
        """Capture inserted rows."""

        self.rows.extend(rows)


@pytest.mark.asyncio
async def test_fetch_batch_parses_multi_symbol_payload() -> None:
    """The fetcher should parse Alpaca bars into domain candles."""

    payload = {
        "bars": {
            "AAPL": [
                {
                    "t": "2026-04-18T14:30:00Z",
                    "o": 100.0,
                    "h": 102.0,
                    "l": 99.5,
                    "c": 101.0,
                    "v": 1_000.0,
                }
            ]
        }
    }
    client = _FakeClient(payload)
    fetcher = AlpacaTrainingFetcher(client=client)
    batch = await fetcher.fetch_batch(
        symbols=["AAPL"],
        timeframe="1Day",
        start=datetime(2026, 4, 1, tzinfo=UTC),
        end=datetime(2026, 4, 18, tzinfo=UTC),
        asset_class="stock",
    )
    assert "AAPL" in batch
    candle = batch["AAPL"][0]
    assert candle.source == "alpaca_training"
    assert candle.symbol == "AAPL"
    assert client.calls[0]["params"]["symbols"] == "AAPL"


@pytest.mark.asyncio
async def test_sync_universe_persists_new_rows() -> None:
    """The sync flow should persist only new training candles."""

    payload = {
        "bars": {
            "AAPL": [
                {
                    "t": "2026-04-18T14:30:00Z",
                    "o": 100.0,
                    "h": 102.0,
                    "l": 99.5,
                    "c": 101.0,
                    "v": 1_000.0,
                }
            ],
            "MSFT": [
                {
                    "t": "2026-04-18T14:30:00Z",
                    "o": 200.0,
                    "h": 202.0,
                    "l": 199.0,
                    "c": 201.0,
                    "v": 2_000.0,
                }
            ],
        }
    }
    client = _FakeClient(payload)
    repository = _FakeRepository()
    fetcher = AlpacaTrainingFetcher(repository=repository, client=client)
    total_rows = await fetcher.sync_universe(["AAPL", "MSFT"], ["1Day"])
    assert total_rows == 2
    assert len(repository.rows) == 2
    assert all(row.source == "alpaca_training" for row in repository.rows)
    assert all(row.usage == ML_CANDLE_USAGE for row in repository.rows)



@pytest.mark.asyncio
async def test_fetch_batch_parses_crypto_payload() -> None:
    """The fetcher should parse Alpaca crypto bars into domain candles."""

    payload = {
        "bars": {
            "BTC/USD": [
                {
                    "t": "2026-04-18T00:00:00Z",
                    "o": 85000.0,
                    "h": 86000.0,
                    "l": 84000.0,
                    "c": 85500.0,
                    "v": 123.45,
                }
            ]
        }
    }
    client = _FakeClient(payload)
    fetcher = AlpacaTrainingFetcher(client=client)
    batch = await fetcher.fetch_batch(
        symbols=["BTC/USD"],
        timeframe="1Day",
        start=datetime(2026, 4, 1, tzinfo=UTC),
        end=datetime(2026, 4, 18, tzinfo=UTC),
        asset_class="crypto",
    )
    assert "BTC/USD" in batch
    candle = batch["BTC/USD"][0]
    assert candle.source == "alpaca_training"
    assert candle.symbol == "BTC/USD"
    assert candle.asset_class == "crypto"
    assert client.calls[0]["url"].endswith("/v1beta3/crypto/us/bars")
