"""Phase 8 crypto RSS ingestion tests."""

from __future__ import annotations

from app.research.rss_client import (
    RssArticle,
    filter_relevant_articles,
    parse_rss_document,
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
