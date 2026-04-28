"""Phase 8 crypto RSS ingestion tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx
from pytest import MonkeyPatch

import app.research.rss_client as rss_module
from app.research.rss_client import (
    CryptoRssClient,
    RssArticle,
    RssSource,
    deduplicate_articles,
    filter_relevant_articles,
    normalize_article_url,
    parse_rss_document,
    prepare_articles_for_scoring,
    summarize_article_matches,
)

RSS_DOCUMENT = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Example Crypto Feed</title>
    <item>
      <title>Bitcoin rallies as ETF inflows rise</title>
      <link>https://example.test/btc</link>
      <description>BTC and crypto markets moved higher.</description>
      <pubDate>Fri, 24 Apr 2026 12:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Macro rates update</title>
      <link>https://example.test/macro</link>
      <description>No digital asset details.</description>
      <pubDate>Fri, 24 Apr 2026 13:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_DOCUMENT = """<?xml version="1.0" encoding="UTF-8" ?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Ethereum developers discuss upgrade</title>
    <link href="https://example.test/eth" />
    <summary>ETH ecosystem update.</summary>
    <updated>2026-04-24T14:00:00Z</updated>
  </entry>
</feed>
"""


def test_parse_rss_document_normalizes_articles() -> None:
    """RSS items should become normalized article objects."""

    articles = parse_rss_document(RSS_DOCUMENT, "Example")

    assert len(articles) == 2
    assert articles[0].title == "Bitcoin rallies as ETF inflows rise"
    assert articles[0].url == "https://example.test/btc"
    assert articles[0].source == "Example"
    assert articles[0].published_at.isoformat() == "2026-04-24T12:30:00+00:00"


def test_parse_atom_document_normalizes_articles() -> None:
    """Atom entries should also be supported for source flexibility."""

    articles = parse_rss_document(ATOM_DOCUMENT, "AtomExample")

    assert len(articles) == 1
    assert articles[0].title == "Ethereum developers discuss upgrade"
    assert articles[0].url == "https://example.test/eth"
    assert articles[0].published_at.isoformat() == "2026-04-24T14:00:00+00:00"


def test_filter_relevant_articles_matches_symbol_aliases() -> None:
    """Symbol filtering should understand common crypto aliases."""

    articles = parse_rss_document(RSS_DOCUMENT, "Example")
    matches = filter_relevant_articles(articles, ["BTC/USD", "DOGE/USD"])

    assert matches[0].symbol == "BTC/USD"
    assert [article.url for article in matches[0].articles] == ["https://example.test/btc"]
    assert matches[1].symbol == "XDG/USD"
    assert matches[1].articles == ()


def test_summarize_article_matches_returns_compact_counts() -> None:
    """Task summaries should expose counts without article bodies."""

    article = RssArticle(
        title="Solana volume rises",
        url="https://example.test/sol",
        published_at=parse_rss_document(RSS_DOCUMENT, "Example")[0].published_at,
        source="Example",
        summary="SOL liquidity improves.",
    )
    matches = filter_relevant_articles([article], ["SOL/USD"])

    summary = summarize_article_matches(matches)

    assert summary["symbol_count"] == 1
    assert summary["matched_article_count"] == 1
    assert summary["per_symbol"] == {
        "SOL/USD": {"article_count": 1, "sources": ["Example"]}
    }


def test_normalize_article_url_removes_tracking_parameters() -> None:
    """Dedupe keys should not be split by common tracking parameters."""

    normalized = normalize_article_url(
        "HTTPS://Example.Test/news/btc/?utm_source=x&ref=feed&id=123#section"
    )

    assert normalized == "https://example.test/news/btc?id=123"


def test_deduplicate_articles_prefers_longer_summary_for_same_url() -> None:
    """Duplicate RSS syndications should collapse before scoring."""

    published_at = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    short = RssArticle(
        title="Bitcoin ETF inflows rise",
        url="https://example.test/btc?utm_campaign=rss",
        published_at=published_at,
        source="Example",
        summary="BTC rises.",
    )
    long = RssArticle(
        title="Bitcoin ETF inflows rise",
        url="https://example.test/btc",
        published_at=published_at,
        source="Example",
        summary="BTC rises as ETF inflows improve across crypto markets.",
    )

    deduped = deduplicate_articles([short, long])

    assert deduped == (long,)


def test_prepare_articles_for_scoring_filters_short_stale_and_duplicates() -> None:
    """Pre-scoring should keep FinBERT away from weak RSS noise."""

    now = datetime(2026, 4, 24, 12, 0, tzinfo=UTC)
    fresh = RssArticle(
        title="Solana volume rises after ecosystem update",
        url="https://example.test/sol",
        published_at=now,
        source="Example",
        summary="SOL liquidity improves as crypto market breadth expands.",
    )
    duplicate = RssArticle(
        title="Solana volume rises after ecosystem update",
        url="https://example.test/sol?utm_source=rss",
        published_at=now,
        source="Example",
        summary="SOL liquidity improves.",
    )
    short = RssArticle(
        title="SOL",
        url="https://example.test/sol-short",
        published_at=now,
        source="Example",
        summary="Up.",
    )
    stale = RssArticle(
        title="Solana stale update with enough words",
        url="https://example.test/sol-stale",
        published_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        source="Example",
        summary="SOL article is too old for daily sentiment scoring.",
    )
    matches = filter_relevant_articles([fresh, duplicate, short, stale], ["SOL/USD"])

    prepared = prepare_articles_for_scoring(matches, now=now)

    assert [article.url for article in prepared[0].articles] == ["https://example.test/sol"]


def test_crypto_rss_client_skips_failed_source(monkeypatch: MonkeyPatch) -> None:
    """One blocked RSS source should not kill the whole sentiment refresh."""

    class FakeResponse:
        text = RSS_DOCUMENT

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, **_: object) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: object,
        ) -> FakeResponse:
            if "coinbase" in url:
                raise httpx.ConnectError("blocked")
            return FakeResponse()

    monkeypatch.setattr(rss_module.httpx, "AsyncClient", FakeAsyncClient)
    client = CryptoRssClient(
        sources=(
            RssSource(name="Coinbase", url="https://www.coinbase.com/blog/rss.xml"),
            RssSource(name="CoinDesk", url="https://www.coindesk.com/rss"),
        )
    )

    articles = asyncio.run(client.fetch_articles())

    assert len(articles) == 2
    assert len(client.fetch_errors) == 1
    assert client.fetch_errors[0].source == "Coinbase"
