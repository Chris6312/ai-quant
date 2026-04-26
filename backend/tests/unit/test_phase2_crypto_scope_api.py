"""Tests for Phase 2 crypto scope API wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_session
from app.api.routers.research import router as research_router
from app.config.crypto_scope import clear_research_crypto_promoted_symbols


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
            _FakeWatchlistRow(symbol="AAPL", asset_class="stock"),
            _FakeWatchlistRow(symbol="MSFT", asset_class="stock"),
            _FakeWatchlistRow(symbol="BTC/USD", asset_class="crypto"),
        ]
    )


def _build_app() -> FastAPI:
    clear_research_crypto_promoted_symbols()
    app = FastAPI()
    app.include_router(research_router)
    app.dependency_overrides[get_session] = _override_session
    return app


def test_research_scope_endpoint_exposes_stock_and_crypto_truth() -> None:
    """The research scope endpoint should separate stock watchlist and crypto scope."""

    app = _build_app()

    with TestClient(app) as client:
        response = client.get("/research/scope")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stock_watchlist_symbols"] == ["AAPL", "MSFT"]
    assert payload["stock_watchlist_count"] == 2
    assert payload["stock_watchlist_source"] == "research watchlist"
    assert payload["crypto_universe_count"] == payload["crypto_watchlist_count"]
    assert payload["crypto_universe_source"] == "KRAKEN_UNIVERSE"
    assert payload["crypto_watchlist_source"] == "crypto universe"
    assert payload["crypto_promoted_symbols"] == []
    assert payload["crypto_promoted_count"] == 0
    assert "BTC/USD" in payload["crypto_watchlist_symbols"]


def test_research_crypto_watchlist_focuses_research_without_runtime_change() -> None:
    """Promoted crypto should narrow Research scope only."""

    app = _build_app()

    with TestClient(app) as client:
        update_response = client.put(
            "/research/crypto-watchlist",
            json={"symbols": ["ETH/USD", "BTC/USD"]},
        )
        scope_response = client.get("/research/scope")

    assert update_response.status_code == 200
    update_payload = update_response.json()
    assert update_payload["crypto_promoted_symbols"] == ["BTC/USD", "ETH/USD"]
    assert update_payload["crypto_watchlist_symbols"] == ["BTC/USD", "ETH/USD"]
    assert update_payload["runtime_scope_changed"] is False

    assert scope_response.status_code == 200
    scope_payload = scope_response.json()
    assert scope_payload["crypto_watchlist_source"] == "research promoted crypto"
    assert scope_payload["crypto_watchlist_symbols"] == ["BTC/USD", "ETH/USD"]
    assert scope_payload["crypto_universe_count"] > scope_payload["crypto_watchlist_count"]


def test_research_crypto_watchlist_rejects_unknown_symbols() -> None:
    """Soft watchlist symbols must still belong to the canonical crypto universe."""

    app = _build_app()

    with TestClient(app) as client:
        response = client.put(
            "/research/crypto-watchlist",
            json={"symbols": ["NOPE/USD"]},
        )

    assert response.status_code == 400
    assert "NOPE/USD" in response.json()["detail"]


def test_research_crypto_watchlist_clear_restores_universe_fallback() -> None:
    """Clearing promoted crypto should restore full-universe Research fallback."""

    app = _build_app()

    with TestClient(app) as client:
        client.put("/research/crypto-watchlist", json={"symbols": ["BTC/USD"]})
        clear_response = client.delete("/research/crypto-watchlist")

    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["crypto_promoted_symbols"] == []
    assert payload["crypto_watchlist_source"] == "crypto universe"
    assert payload["crypto_watchlist_count"] == 15
    assert payload["runtime_scope_changed"] is False
