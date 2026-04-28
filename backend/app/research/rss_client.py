"""RSS ingestion helpers for crypto news sentiment."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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

TRACKING_QUERY_PREFIXES: tuple[str, ...] = ("utm_",)
TRACKING_QUERY_KEYS: frozenset[str] = frozenset(
    {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}
)

RSS_NAMESPACES: dict[str, str] = {
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

RSS_REQUEST_HEADERS: Mapping[str, str] = {
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
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
class RssFetchError:
    """Non-fatal fetch error for one RSS source."""

    source: str
    url: str
    message: str


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
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


class CryptoRssClient:
    """Fetch and normalize crypto RSS articles."""

    def __init__(
        self,
        sources: Sequence[RssSource] = DEFAULT_RSS_SOURCES,
        timeout_s: float = 10.0,
    ) -> None:
        self.sources = tuple(sources)
        self.timeout_s = timeout_s
        self.fetch_errors: tuple[RssFetchError, ...] = ()

    async def fetch_articles(self) -> list[RssArticle]:
        """Fetch configured RSS sources and skip sources that fail transiently."""

        articles: list[RssArticle] = []
        errors: list[RssFetchError] = []
        async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
            for source in self.sources:
                try:
                    response = await client.get(source.url, headers=RSS_REQUEST_HEADERS)
                    response.raise_for_status()
                    articles.extend(parse_rss_document(response.text, source.name))
                except (httpx.HTTPError, ET.ParseError) as exc:
                    errors.append(
                        RssFetchError(
                            source=source.name,
                            url=source.url,
                            message=str(exc),
                        )
                    )
        self.fetch_errors = tuple(errors)
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


def prepare_articles_for_scoring(
    matches: Sequence[SymbolArticleMatches],
    *,
    now: datetime | None = None,
    max_age_days: int = 14,
    min_text_chars: int = 40,
    max_articles_per_symbol: int = 25,
) -> list[SymbolArticleMatches]:
    """Apply deduplication and quality filters before expensive sentiment scoring."""

    reference_time = now or datetime.now(tz=UTC)
    prepared: list[SymbolArticleMatches] = []
    for match in matches:
        filtered = (
            article
            for article in match.articles
            if _passes_prescoring_filter(
                article,
                now=reference_time,
                max_age_days=max_age_days,
                min_text_chars=min_text_chars,
            )
        )
        deduped = deduplicate_articles(filtered)
        ordered = tuple(
            sorted(deduped, key=lambda article: article.published_at, reverse=True)[
                :max_articles_per_symbol
            ]
        )
        prepared.append(SymbolArticleMatches(symbol=match.symbol, articles=ordered))
    return prepared


def deduplicate_articles(articles: Iterable[RssArticle]) -> tuple[RssArticle, ...]:
    """Remove RSS syndication duplicates while preserving the richest article body."""

    selected: dict[str, RssArticle] = {}
    for article in articles:
        key = _dedupe_key(article)
        current = selected.get(key)
        if current is None or _article_text_length(article) > _article_text_length(current):
            selected[key] = article
    return tuple(selected.values())


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


def _passes_prescoring_filter(
    article: RssArticle,
    *,
    now: datetime,
    max_age_days: int,
    min_text_chars: int,
) -> bool:
    if not article.url.strip():
        return False
    if _article_text_length(article) < min_text_chars:
        return False
    earliest = now - timedelta(days=max_age_days)
    latest = now + timedelta(days=1)
    return earliest <= article.published_at <= latest


def _article_text_length(article: RssArticle) -> int:
    return len(f"{article.title} {article.summary}".strip())


def _dedupe_key(article: RssArticle) -> str:
    normalized_url = normalize_article_url(article.url)
    if normalized_url:
        return f"url:{normalized_url}"
    title_key = _NON_ALNUM_RE.sub("-", article.title.lower()).strip("-")
    published_key = article.published_at.isoformat(timespec="minutes")
    return f"fallback:{article.source.lower()}:{published_key}:{title_key}"


def normalize_article_url(url: str) -> str:
    """Return a stable URL key without common tracking parameters."""

    stripped = url.strip()
    if not stripped:
        return ""
    parts = urlsplit(stripped)
    filtered_query = tuple(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_query_key(key)
    )
    normalized_path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            normalized_path,
            urlencode(filtered_query),
            "",
        )
    )


def _is_tracking_query_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in TRACKING_QUERY_KEYS or lowered.startswith(TRACKING_QUERY_PREFIXES)
