"""Tests for Phase 2 crypto scope API wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_session
from app.api.routers.research import router as research_router


@dataclass(slots=True)
class _FakeWatchlistRow:
    symbol: str
    asset_class: str
    is_active: bool = True


class _FakeScalarResult:
    def __init__(self, rows: list[_FakeWatchlistRow]) -> None:
        self._rows = rows

    def __iter__(self) -> Iterator[_FakeWatchlistRow]:
        return iter(self._rows)


class _FakeSession:
    def __init__(self, rows: list[_FakeWatchlistRow]) -> None:
        self._rows = rows

    async def scalars(self, statement: object) -> _FakeScalarResult:
        del statement
        active_rows = [row for row in self._rows if row.is_active]
        return _FakeScalarResult(active_rows)


async def _override_session() -> AsyncIterator[_FakeSession]:
    yield _FakeSession(
        [
            _FakeWatchlistRow(symbol='AAPL', asset_class='stock'),
            _FakeWatchlistRow(symbol='MSFT', asset_class='stock'),
            _FakeWatchlistRow(symbol='BTC/USD', asset_class='crypto'),
        ]
    )


def test_research_scope_endpoint_exposes_stock_and_crypto_truth() -> None:
    """The research scope endpoint should separate stock watchlist and crypto scope."""

    app = FastAPI()
    app.include_router(research_router)
    app.dependency_overrides[get_session] = _override_session

    with TestClient(app) as client:
        response = client.get('/research/scope')

    assert response.status_code == 200
    payload = response.json()
    assert payload['stock_watchlist_symbols'] == ['AAPL', 'MSFT']
    assert payload['stock_watchlist_count'] == 2
    assert payload['stock_watchlist_source'] == 'research watchlist'
    assert payload['crypto_universe_count'] == payload['crypto_watchlist_count']
    assert payload['crypto_universe_source'] == 'KRAKEN_UNIVERSE'
    assert payload['crypto_watchlist_source'] == 'crypto universe'
    assert 'BTC/USD' in payload['crypto_watchlist_symbols']
