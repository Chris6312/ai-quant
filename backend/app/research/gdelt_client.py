"""GDELT historical article ingestion helpers for crypto sentiment backfill."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Final
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.config.crypto_scope import canonicalize_crypto_ml_symbol
from app.research.rss_client import SYMBOL_KEYWORDS, RssArticle

GDELT_SYMBOL_ALIASES: Final[dict[str, str]] = {"XBT/USD": "BTC/USD"}
GDELT_DOC_BASE_URL: Final[str] = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_MAX_RECORDS: Final[int] = 250


@dataclass(frozen=True, slots=True)
class GdeltSearchWindow:
    """Date window for one historical GDELT article search."""

    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class GdeltArticleSearchRequest:
    """Symbol-scoped GDELT historical article search request."""

    symbol: str
    window: GdeltSearchWindow
    query: str
    max_records: int = GDELT_MAX_RECORDS


@dataclass(frozen=True, slots=True)
class GdeltArticleSearchResult:
    """Normalized historical articles returned for one GDELT search request."""

    symbol: str
    window: GdeltSearchWindow
    query: str
    articles: tuple[RssArticle, ...]


class GdeltHistoricalNewsClient:
    """Fetch normalized historical crypto articles from the GDELT DOC API."""

    def __init__(
        self,
        *,
        base_url: str = GDELT_DOC_BASE_URL,
        timeout_s: float = 15.0,
        max_records: int = GDELT_MAX_RECORDS,
    ) -> None:
        self.base_url = base_url
        self.timeout_s = timeout_s
        self.max_records = max_records

    async def search_articles(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> GdeltArticleSearchResult:
        """Search GDELT for one canonical symbol and inclusive date window."""

        request = build_gdelt_article_search_request(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            max_records=self.max_records,
        )
        async with httpx.AsyncClient(timeout=self.timeout_s, follow_redirects=True) as client:
            response = await client.get(self.base_url, params=build_gdelt_query_params(request))
            response.raise_for_status()
            payload = response.json()
        return GdeltArticleSearchResult(
            symbol=request.symbol,
            window=request.window,
            query=request.query,
            articles=parse_gdelt_articles(payload),
        )


def build_gdelt_article_search_request(
    *,
    symbol: str,
    start_date: date,
    end_date: date,
    max_records: int = GDELT_MAX_RECORDS,
) -> GdeltArticleSearchRequest:
    """Build a deterministic GDELT historical query for one crypto symbol."""

    if end_date < start_date:
        raise ValueError("GDELT end_date must be on or after start_date")

    canonical_symbol = _canonicalize_gdelt_symbol(symbol)
    return GdeltArticleSearchRequest(
        symbol=canonical_symbol,
        window=GdeltSearchWindow(start_date=start_date, end_date=end_date),
        query=_build_symbol_query(canonical_symbol),
        max_records=max_records,
    )


def build_gdelt_query_params(request: GdeltArticleSearchRequest) -> dict[str, str | int]:
    """Convert a search request into GDELT DOC API query parameters."""

    return {
        "query": request.query,
        "mode": "ArtList",
        "format": "json",
        "sort": "HybridRel",
        "maxrecords": request.max_records,
        "startdatetime": _gdelt_datetime(
            datetime.combine(request.window.start_date, time.min, tzinfo=UTC),
        ),
        "enddatetime": _gdelt_datetime(
            datetime.combine(request.window.end_date, time.max, tzinfo=UTC),
        ),
    }


def parse_gdelt_articles(payload: Mapping[str, object]) -> tuple[RssArticle, ...]:
    """Normalize GDELT article payloads into the existing article scoring contract."""

    raw_articles = payload.get("articles")
    if not isinstance(raw_articles, Sequence) or isinstance(raw_articles, str):
        return ()

    normalized: list[RssArticle] = []
    for raw_article in raw_articles:
        if not isinstance(raw_article, Mapping):
            continue
        article = _parse_gdelt_article(raw_article)
        if article is not None:
            normalized.append(article)
    return tuple(normalized)


def _parse_gdelt_article(raw_article: Mapping[str, object]) -> RssArticle | None:
    title = _clean_string(raw_article.get("title"))
    url = _clean_url(raw_article.get("url"))
    published_at = _parse_gdelt_datetime(raw_article.get("seendate"))
    if not title or not url or published_at is None:
        return None

    summary = _clean_string(raw_article.get("description")) or title
    domain = _clean_string(raw_article.get("domain"))
    source = f"GDELT:{domain}" if domain else "GDELT"
    return RssArticle(
        title=title,
        url=url,
        published_at=published_at,
        source=source,
        summary=summary,
    )


def _canonicalize_gdelt_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    return canonicalize_crypto_ml_symbol(GDELT_SYMBOL_ALIASES.get(normalized, normalized))


def _build_symbol_query(symbol: str) -> str:
    keywords = SYMBOL_KEYWORDS.get(symbol, _fallback_symbol_keywords(symbol))
    keyword_query = " OR ".join(f'"{keyword}"' for keyword in keywords)
    return f"({keyword_query}) (crypto OR cryptocurrency OR blockchain)"


def _fallback_symbol_keywords(symbol: str) -> tuple[str, ...]:
    base = symbol.split("/", maxsplit=1)[0].lower()
    return (base, symbol.lower())


def _gdelt_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%d%H%M%S")


def _parse_gdelt_datetime(value: object) -> datetime | None:
    raw = _clean_string(value)
    if not raw:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _clean_string(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _clean_url(value: object) -> str:
    raw = _clean_string(value)
    if not raw:
        return ""
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
