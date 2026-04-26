"""CoinDesk sitemap archive ingestion for historical crypto sentiment backfill."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from html import unescape
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.config.crypto_scope import canonicalize_crypto_ml_symbol
from app.research.rss_client import SYMBOL_KEYWORDS, RssArticle

COINDESK_ARCHIVE_BASE_URL: Final[str] = "https://www.coindesk.com/sitemap/archive"
COINDESK_SOURCE_NAME: Final[str] = "CoinDesk:Sitemap"
COINDESK_DEFAULT_MAX_PAGES_PER_YEAR: Final[int] = 30
COINDESK_POLITE_USER_AGENT: Final[str] = (
    "AI-Quant research sentiment backfill; contact=local-development; purpose=title-date-indexing"
)
_DATE_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")
_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class CoinDeskSitemapArticleSearchResult:
    """Normalized historical articles returned for a CoinDesk sitemap search."""

    symbol: str
    start_date: date
    end_date: date
    articles: tuple[RssArticle, ...]
    page_count: int


@dataclass(frozen=True, slots=True)
class _ArchiveLink:
    title: str
    url: str


class CoinDeskSitemapNewsClient:
    """Fetch title/date rows from CoinDesk public sitemap archive pages."""

    def __init__(
        self,
        *,
        base_url: str = COINDESK_ARCHIVE_BASE_URL,
        timeout_s: float = 20.0,
        max_pages_per_year: int = COINDESK_DEFAULT_MAX_PAGES_PER_YEAR,
        user_agent: str = COINDESK_POLITE_USER_AGENT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_pages_per_year = max_pages_per_year
        self.user_agent = user_agent

    async def search_articles(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> CoinDeskSitemapArticleSearchResult:
        """Search CoinDesk archive pages for one canonical symbol and date range."""

        if end_date < start_date:
            raise ValueError("CoinDesk sitemap end_date must be on or after start_date")

        canonical_symbol = canonicalize_crypto_ml_symbol(symbol.upper())
        keywords = SYMBOL_KEYWORDS.get(
            canonical_symbol,
            _fallback_symbol_keywords(canonical_symbol),
        )
        articles: list[RssArticle] = []
        page_count = 0
        years = range(start_date.year, end_date.year + 1)
        headers = {"User-Agent": self.user_agent}
        async with httpx.AsyncClient(
            timeout=self.timeout_s,
            follow_redirects=True,
            headers=headers,
        ) as client:
            for year in years:
                for page in range(1, self.max_pages_per_year + 1):
                    page_url = build_coindesk_archive_page_url(
                        base_url=self.base_url,
                        year=year,
                        page=page,
                    )
                    response = await client.get(page_url)
                    if response.status_code == 404:
                        break
                    response.raise_for_status()
                    page_articles = parse_coindesk_archive_page(
                        response.text,
                        source_url=page_url,
                    )
                    if not page_articles:
                        break
                    page_count += 1
                    in_window = tuple(
                        article
                        for article in page_articles
                        if start_date <= article.published_at.date() <= end_date
                    )
                    articles.extend(
                        article
                        for article in in_window
                        if _article_matches_keywords(article, keywords)
                    )

                    oldest_date = min(article.published_at.date() for article in page_articles)
                    if oldest_date < start_date and year == start_date.year:
                        break

        return CoinDeskSitemapArticleSearchResult(
            symbol=canonical_symbol,
            start_date=start_date,
            end_date=end_date,
            articles=tuple(articles),
            page_count=page_count,
        )


def build_coindesk_archive_page_url(*, base_url: str, year: int, page: int) -> str:
    """Build the public CoinDesk sitemap archive page URL."""

    clean_base = base_url.rstrip("/")
    if page <= 1:
        return f"{clean_base}/{year}"
    return f"{clean_base}/{year}/{page}"


def parse_coindesk_archive_page(document: str, *, source_url: str) -> tuple[RssArticle, ...]:
    """Parse a CoinDesk archive page into title/date article records."""

    parser = _CoinDeskArchiveParser(source_url=source_url)
    parser.feed(document)
    parser.close()
    return parser.to_articles()


class _CoinDeskArchiveParser(HTMLParser):
    """Tiny permissive parser for CoinDesk archive title/date rows."""

    def __init__(self, *, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.text_parts: list[str] = []
        self.links: list[_ArchiveLink] = []
        self._active_href: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._active_href = urljoin(self.source_url, href)
            self._active_text = []

    def handle_data(self, data: str) -> None:
        for raw_line in data.splitlines():
            text = _clean_text(raw_line)
            if not text:
                continue
            self.text_parts.append(text)
            if self._active_href is not None:
                self._active_text.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._active_href is None:
            return
        title = _clean_text(" ".join(self._active_text))
        if title and not _DATE_RE.match(title):
            self.links.append(_ArchiveLink(title=title, url=_clean_url(self._active_href)))
        self._active_href = None
        self._active_text = []

    def to_articles(self) -> tuple[RssArticle, ...]:
        lines = [_clean_text(part) for part in self.text_parts if _clean_text(part)]
        title_by_link = {_normalize_title(link.title): link.url for link in self.links}
        articles: list[RssArticle] = []
        for index, line in enumerate(lines):
            if not _DATE_RE.match(line) or index == 0:
                continue
            title = _previous_title(lines, index)
            if not title:
                continue
            published_date = date.fromisoformat(line)
            url = title_by_link.get(_normalize_title(title)) or _synthetic_archive_url(
                source_url=self.source_url,
                title=title,
                published_date=published_date,
            )
            articles.append(
                RssArticle(
                    title=title,
                    url=url,
                    published_at=datetime.combine(published_date, time.min, tzinfo=UTC),
                    source=COINDESK_SOURCE_NAME,
                    summary=title,
                )
            )
        return tuple(_dedupe_articles(articles))


def _previous_title(lines: Sequence[str], date_index: int) -> str:
    for candidate in reversed(lines[:date_index]):
        if _DATE_RE.match(candidate):
            continue
        if candidate.lower() in {"news", "video", "prices", "research", "page", "of"}:
            continue
        if candidate.isdigit():
            continue
        return candidate
    return ""


def _dedupe_articles(articles: Sequence[RssArticle]) -> tuple[RssArticle, ...]:
    selected: dict[str, RssArticle] = {}
    for article in articles:
        key = f"{article.published_at.date().isoformat()}:{_normalize_title(article.title)}"
        selected.setdefault(key, article)
    return tuple(selected.values())


def _article_matches_keywords(article: RssArticle, keywords: Sequence[str]) -> bool:
    text = f"{article.title} {article.summary}".lower()
    return any(_keyword_matches(text, keyword.lower()) for keyword in keywords)


def _keyword_matches(text: str, keyword: str) -> bool:
    if " " in keyword or "/" in keyword:
        return keyword in text
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None


def _fallback_symbol_keywords(symbol: str) -> tuple[str, ...]:
    base = symbol.split("/", maxsplit=1)[0].lower()
    return (base, symbol.lower())


def _clean_text(value: str) -> str:
    return _SPACE_RE.sub(" ", unescape(value).strip())


def _clean_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return ""
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", "")
    )


def _normalize_title(value: str) -> str:
    return _SLUG_RE.sub("-", value.lower()).strip("-")


def _synthetic_archive_url(*, source_url: str, title: str, published_date: date) -> str:
    parts = urlsplit(source_url)
    host = parts.netloc.lower() or "www.coindesk.com"
    slug = _normalize_title(title) or "archive-entry"
    return f"https://{host}/sitemap/archive/{published_date.isoformat()}/{slug}"
