"""Phase 8 historical GDELT article ingestion tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest

from app.research.gdelt_client import (
    GdeltHistoricalNewsClient,
    build_gdelt_article_search_request,
    build_gdelt_query_params,
    parse_gdelt_articles,
)


def test_gdelt_request_uses_canonical_symbol_and_crypto_query() -> None:
    """Historical searches should normalize symbols and include crypto context."""

    request = build_gdelt_article_search_request(
        symbol="XBT/USD",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        max_records=50,
    )

    assert request.symbol == "BTC/USD"
    assert request.window.start_date == date(2026, 4, 1)
    assert request.window.end_date == date(2026, 4, 2)
    assert '"bitcoin"' in request.query
    assert "crypto" in request.query
    assert request.max_records == 50


def test_gdelt_query_params_use_inclusive_date_window() -> None:
    """GDELT calls should cover the whole requested daily window."""

    request = build_gdelt_article_search_request(
        symbol="ETH/USD",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
        max_records=25,
    )

    params = build_gdelt_query_params(request)

    assert params["mode"] == "ArtList"
    assert params["format"] == "json"
    assert params["sort"] == "HybridRel"
    assert params["maxrecords"] == 25
    assert params["startdatetime"] == "20260401000000"
    assert params["enddatetime"] == "20260402235959"


def test_parse_gdelt_articles_normalizes_valid_articles() -> None:
    """GDELT payloads should normalize into the shared article scoring contract."""

    articles = parse_gdelt_articles(
        {
            "articles": [
                {
                    "title": " Bitcoin ETF demand grows ",
                    "url": "HTTPS://Example.COM/btc?utm_source=x",
                    "seendate": "20260425T143000Z",
                    "domain": "Example.com",
                    "description": " BTC inflows improve as institutional demand grows. ",
                }
            ]
        }
    )

    assert len(articles) == 1
    article = articles[0]
    assert article.title == "Bitcoin ETF demand grows"
    assert article.url == "https://example.com/btc"
    assert article.published_at == datetime(2026, 4, 25, 14, 30, tzinfo=UTC)
    assert article.source == "GDELT:Example.com"
    assert article.summary == "BTC inflows improve as institutional demand grows."


def test_parse_gdelt_articles_rejects_unusable_rows() -> None:
    """Malformed GDELT rows should not enter downstream sentiment scoring."""

    articles = parse_gdelt_articles(
        {
            "articles": [
                {"title": "Missing URL", "seendate": "20260425T143000Z"},
                {"url": "https://example.test/no-title", "seendate": "20260425T143000Z"},
                {"title": "Bad date", "url": "https://example.test/bad", "seendate": "bad"},
            ]
        }
    )

    assert articles == ()


@pytest.mark.asyncio
async def test_gdelt_client_returns_empty_articles_for_empty_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty 200 responses should not fail a historical backfill window."""

    async def fake_get(
        self: httpx.AsyncClient,
        url: str,
        params: object | None = None,
    ) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=200, content=b"", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = GdeltHistoricalNewsClient(
        base_url="https://gdelt.example.test/doc",
        rate_limit_pause_s=0.0,
        rate_limit_retries=0,
    )

    result = await client.search_articles(
        symbol="BTC/USD",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
    )

    assert result.symbol == "BTC/USD"
    assert result.articles == ()


@pytest.mark.asyncio
async def test_gdelt_client_returns_empty_articles_after_exhausted_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GDELT 429 exhaustion should cool down and return an empty window result."""

    calls = 0

    async def fake_sleep(delay: float) -> None:
        assert delay == 0.0

    async def fake_get(
        self: httpx.AsyncClient,
        url: str,
        params: object | None = None,
    ) -> httpx.Response:
        nonlocal calls
        calls += 1
        request = httpx.Request("GET", url)
        return httpx.Response(status_code=429, content=b"rate limited", request=request)

    monkeypatch.setattr("app.research.gdelt_client.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = GdeltHistoricalNewsClient(
        base_url="https://gdelt.example.test/doc",
        rate_limit_pause_s=0.0,
        rate_limit_retries=1,
    )

    result = await client.search_articles(
        symbol="ETH/USD",
        start_date=date(2025, 2, 1),
        end_date=date(2025, 2, 28),
    )

    assert calls == 2
    assert result.symbol == "ETH/USD"
    assert result.articles == ()


@pytest.mark.asyncio
async def test_gdelt_client_returns_empty_articles_for_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network timeouts should not mark the whole sentiment window failed."""

    async def fake_get(
        self: httpx.AsyncClient,
        url: str,
        params: object | None = None,
    ) -> httpx.Response:
        request = httpx.Request("GET", url)
        raise httpx.ReadTimeout("timed out", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    client = GdeltHistoricalNewsClient(
        base_url="https://gdelt.example.test/doc",
        rate_limit_pause_s=0.0,
        rate_limit_retries=0,
    )

    result = await client.search_articles(
        symbol="BTC/USD",
        start_date=date(2025, 3, 1),
        end_date=date(2025, 3, 1),
    )

    assert result.symbol == "BTC/USD"
    assert result.articles == ()
