"""Phase 8 historical GDELT article ingestion tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.research.gdelt_client import (
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
