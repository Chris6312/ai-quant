"""RSS ingestion helpers for crypto news sentiment."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape

import httpx

from app.config.crypto_scope import canonicalize_crypto_ml_symbol

CRYPTO_NEWS_KEYWORDS: tuple[str, ...] = (
    "crypto",
    "cryptocurrency",
    "bitcoin",
    "ethereum",
    "blockchain",
    "digital asset",
    "stablecoin",
)

SYMBOL_KEYWORDS: Mapping[str, tuple[str, ...]] = {
    "BTC/USD": ("btc", "bitcoin", "xbt"),
    "ETH/USD": ("eth", "ethereum", "ether"),
    "SOL/USD": ("sol", "solana"),
    "LTC/USD": ("ltc", "litecoin"),
    "BCH/USD": ("bch", "bitcoin cash"),
    "LINK/USD": ("link", "chainlink"),
    "UNI/USD": ("uni", "uniswap"),
    "AVAX/USD": ("avax", "avalanche"),
    "DOGE/USD": ("doge", "dogecoin", "xdg"),
    "XDG/USD": ("doge", "dogecoin", "xdg"),
    "DOT/USD": ("dot", "polkadot"),
    "AAVE/USD": ("aave",),
    "CRV/USD": ("crv", "curve"),
    "SUSHI/USD": ("sushi", "sushiswap"),
    "SHIB/USD": ("shib", "shiba inu"),
    "XTZ/USD": ("xtz", "tezos"),
}

RSS_NAMESPACES: dict[str, str] = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}


@dataclass(frozen=True, slots=True)
class RssSource:
    """RSS source definition for crypto news ingestion."""

    name: str
    url: str


@dataclass(frozen=True, slots=True)
class RssArticle:
    """Normalized article parsed from an RSS or Atom feed."""

    title: str
    url: str
    published_at: datetime
    source: str
    summary: str


@dataclass(frozen=True, slots=True)
class SymbolArticleMatches:
    """Filtered article matches for one canonical crypto symbol."""

    symbol: str
    articles: tuple[RssArticle, ...]


DEFAULT_RSS_SOURCES: tuple[RssSource, ...] = (
    RssSource(name="Coinbase", url="https://www.coinbase.com/blog/rss.xml"),
    RssSource(name="CoinDesk", url="https://www.coindesk.com/arc/outboundfeeds/rss/"),
)

_TAG_RE = re.compile(r"<[^>]+>")
_WORD_RE = re.compile(r"[a-z0-9]+(?:/[a-z0-9]+)?")


class CryptoRssClient:
    """Fetch and normalize crypto RSS articles."""

    def __init__(
        self,
        sources: Sequence[RssSource] = DEFAULT_RSS_SOURCES,
        timeout_s: float = 10.0,
    ) -> None:
        self.sources = tuple(sources)
        self.timeout_s = timeout_s

    async def fetch_articles(self) -> list[RssArticle]:
        """Fetch all configured RSS sources and return normalized articles."""

        articles: list[RssArticle] = []
        async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
            for source in self.sources:
                response = await client.get(source.url)
                response.raise_for_status()
                articles.extend(parse_rss_document(response.text, source.name))
        return articles


def parse_rss_document(document: str, source_name: str) -> list[RssArticle]:
    """Parse an RSS or Atom document into normalized articles."""

    root = ET.fromstring(document)
    rss_items = root.findall("./channel/item")
    if rss_items:
        return [_parse_rss_item(item, source_name) for item in rss_items]

    atom_entries = root.findall("./atom:entry", RSS_NAMESPACES)
    return [_parse_atom_entry(entry, source_name) for entry in atom_entries]


def filter_relevant_articles(
    articles: Sequence[RssArticle],
    symbols: Sequence[str],
) -> list[SymbolArticleMatches]:
    """Return symbol-specific article matches using lightweight keyword rules."""

    matches: list[SymbolArticleMatches] = []
    for symbol in symbols:
        canonical_symbol = canonicalize_crypto_ml_symbol(symbol.upper())
        keywords = _symbol_keywords(symbol, canonical_symbol)
        symbol_articles = tuple(
            article for article in articles if _article_matches(article, keywords)
        )
        matches.append(SymbolArticleMatches(symbol=canonical_symbol, articles=symbol_articles))
    return matches


def summarize_article_matches(matches: Sequence[SymbolArticleMatches]) -> dict[str, object]:
    """Build a compact task summary from filtered article matches."""

    per_symbol = {
        match.symbol: {
            "article_count": len(match.articles),
            "sources": sorted({article.source for article in match.articles}),
        }
        for match in matches
    }
    return {
        "symbol_count": len(matches),
        "matched_article_count": sum(len(match.articles) for match in matches),
        "per_symbol": per_symbol,
    }


def _parse_rss_item(item: ET.Element, source_name: str) -> RssArticle:
    title = _child_text(item, "title")
    url = _child_text(item, "link") or _child_text(item, "guid")
    summary = _child_text(item, "description") or _child_text(item, "content:encoded")
    published_raw = _child_text(item, "pubDate") or _child_text(item, "dc:date")
    return RssArticle(
        title=_clean_text(title),
        url=url.strip(),
        published_at=_parse_datetime(published_raw),
        source=source_name,
        summary=_clean_text(summary),
    )


def _parse_atom_entry(entry: ET.Element, source_name: str) -> RssArticle:
    title = _child_text(entry, "atom:title")
    summary = _child_text(entry, "atom:summary") or _child_text(entry, "atom:content")
    published_raw = _child_text(entry, "atom:published") or _child_text(entry, "atom:updated")
    url = ""
    for link in entry.findall("atom:link", RSS_NAMESPACES):
        href = link.attrib.get("href")
        if href:
            url = href
            break
    return RssArticle(
        title=_clean_text(title),
        url=url.strip(),
        published_at=_parse_datetime(published_raw),
        source=source_name,
        summary=_clean_text(summary),
    )


def _child_text(element: ET.Element, path: str) -> str:
    child = element.find(path, RSS_NAMESPACES)
    if child is None or child.text is None:
        return ""
    return child.text


def _clean_text(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", value)
    return " ".join(unescape(without_tags).split())


def _parse_datetime(value: str) -> datetime:
    if not value.strip():
        return datetime.now(tz=UTC)

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _symbol_keywords(symbol: str, canonical_symbol: str) -> tuple[str, ...]:
    normalized_symbols = {
        symbol.upper(),
        canonical_symbol.upper(),
        symbol.upper().replace("/", ""),
        canonical_symbol.upper().replace("/", ""),
        symbol.upper().split("/")[0],
        canonical_symbol.upper().split("/")[0],
    }
    mapped = (
        SYMBOL_KEYWORDS.get(symbol.upper(), ())
        + SYMBOL_KEYWORDS.get(canonical_symbol.upper(), ())
    )
    return tuple(sorted({keyword.lower() for keyword in (*normalized_symbols, *mapped)}))


def _article_matches(article: RssArticle, symbol_keywords: Iterable[str]) -> bool:
    searchable = f"{article.title} {article.summary}".lower()
    tokens = set(_WORD_RE.findall(searchable))
    return any(_keyword_matches(searchable, tokens, keyword) for keyword in symbol_keywords)


def _keyword_matches(searchable: str, tokens: set[str], keyword: str) -> bool:
    lowered = keyword.lower()
    if " " in lowered:
        return lowered in searchable
    return lowered in tokens