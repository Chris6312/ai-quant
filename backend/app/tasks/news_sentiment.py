"""Celery task scaffold for crypto news sentiment ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.repositories.research import ResearchRepository
from app.research.coindesk_sitemap_client import CoinDeskSitemapNewsClient
from app.research.crypto_sentiment import (
    CryptoArticleSentimentScorer,
    CryptoDailySentimentAggregate,
    FinbertCryptoSentimentScorer,
    aggregate_to_summary,
    build_crypto_daily_sentiment_row,
    build_daily_crypto_sentiment_aggregate,
)
from app.research.rss_client import (
    CryptoRssClient,
    RssArticle,
    SymbolArticleMatches,
    filter_relevant_articles,
    prepare_articles_for_scoring,
    summarize_article_matches,
)
from app.tasks.worker import celery_app


@dataclass(frozen=True, slots=True)
class NewsSentimentTaskPayload:
    """Typed Celery task submission payload for news sentiment jobs."""

    name: str
    kwargs: dict[str, object]


class HistoricalCryptoNewsClient(Protocol):
    """Client contract for historical crypto news search providers."""

    async def search_articles(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> object:
        """Return a historical search result with an articles sequence."""
        ...


@celery_app.task(name="tasks.news_sentiment.daily_crypto_sync")
def daily_crypto_news_sentiment_task(
    symbols: list[str] | None = None,
    sentiment_date: str | None = None,
) -> dict[str, object]:
    """Fetch RSS articles, score daily sentiment, and persist daily aggregates."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_date = sentiment_date or date.today().isoformat()
    return asyncio.run(
        persist_daily_crypto_rss_sentiment(
            symbols=requested_symbols,
            sentiment_date=requested_date,
        )
    )


@celery_app.task(name="tasks.news_sentiment.historical_crypto_backfill")
def historical_crypto_news_sentiment_backfill_task(
    symbols: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    window_granularity: str = "yearly",
) -> dict[str, object]:
    """Backfill historical crypto sentiment aggregates into persistence."""

    if start_date is None or end_date is None:
        raise ValueError("Historical sentiment backfill requires start_date and end_date")

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    return asyncio.run(
        backfill_historical_crypto_sentiment(
            symbols=requested_symbols,
            start_date=start_date,
            end_date=end_date,
            window_granularity=window_granularity,
        )
    )


async def collect_daily_crypto_rss_snapshot(
    symbols: Sequence[str],
    sentiment_date: str,
    client: CryptoRssClient | None = None,
    scorer: CryptoArticleSentimentScorer | None = None,
) -> dict[str, object]:
    """Fetch, filter, deduplicate, and score RSS articles without DB writes."""

    rss_client = client or CryptoRssClient()
    articles = await rss_client.fetch_articles()
    raw_matches = filter_relevant_articles(articles, symbols)
    prepared_matches = prepare_articles_for_scoring(raw_matches)
    target_date = date.fromisoformat(sentiment_date)
    aggregates = await _build_daily_aggregates(
        matches=prepared_matches,
        sentiment_date=target_date,
        scorer=scorer,
    )
    return {
        "status": "rss_scoring_ready",
        "task": "daily_crypto_news_sentiment_snapshot",
        "asset_class": "crypto",
        "sentiment_date": sentiment_date,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "raw_article_count": len(articles),
        "raw_match_summary": summarize_article_matches(raw_matches),
        "prepared_match_summary": summarize_article_matches(prepared_matches),
        "sentiment_summary": {
            aggregate.symbol: dict(aggregate_to_summary(aggregate)) for aggregate in aggregates
        },
        "pipeline": [
            "rss_fetch",
            "symbol_filter",
            "dedupe",
            "pre_scoring_filter",
            "article_scoring",
            "daily_aggregate",
        ],
        "message": "RSS articles were scored into daily aggregates without storage.",
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }


async def persist_daily_crypto_rss_sentiment(
    *,
    symbols: Sequence[str],
    sentiment_date: str,
    client: CryptoRssClient | None = None,
    session_factory: async_sessionmaker[Any] | None = None,
    scorer: CryptoArticleSentimentScorer | None = None,
) -> dict[str, object]:
    """Fetch RSS, score daily aggregates, and upsert crypto sentiment rows."""

    settings = get_settings()
    active_scorer = scorer or FinbertCryptoSentimentScorer(
        model_name=settings.research_finbert_model_name,
    )
    rss_client = client or CryptoRssClient()
    articles = await rss_client.fetch_articles()
    raw_matches = filter_relevant_articles(articles, symbols)
    prepared_matches = prepare_articles_for_scoring(raw_matches)
    target_date = date.fromisoformat(sentiment_date)
    aggregates = await _build_daily_aggregates(
        matches=prepared_matches,
        sentiment_date=target_date,
        scorer=active_scorer,
    )

    owns_engine = session_factory is None
    engine = None
    active_session_factory = session_factory
    if active_session_factory is None:
        engine = build_engine(settings)
        active_session_factory = build_session_factory(engine)

    try:
        async with active_session_factory() as session:
            repository = ResearchRepository(session)
            for aggregate in aggregates:
                row = build_crypto_daily_sentiment_row(aggregate)
                await repository.upsert_crypto_daily_sentiment(row)
    finally:
        if owns_engine and engine is not None:
            await engine.dispose()

    return {
        "status": "persisted",
        "task": "daily_crypto_news_sentiment",
        "asset_class": "crypto",
        "sentiment_date": sentiment_date,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "raw_article_count": len(articles),
        "raw_match_summary": summarize_article_matches(raw_matches),
        "prepared_match_summary": summarize_article_matches(prepared_matches),
        "sentiment_summary": {
            aggregate.symbol: dict(aggregate_to_summary(aggregate)) for aggregate in aggregates
        },
        "rows_upserted": len(aggregates),
        "pipeline": [
            "rss_fetch",
            "symbol_filter",
            "dedupe",
            "pre_scoring_filter",
            "finbert",
            "daily_aggregate",
            "crypto_daily_sentiment_upsert",
        ],
        "message": "RSS articles were scored and persisted to crypto_daily_sentiment.",
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }


async def backfill_historical_crypto_sentiment(
    *,
    symbols: Sequence[str],
    start_date: str,
    end_date: str,
    window_granularity: str = "yearly",
    client: HistoricalCryptoNewsClient | None = None,
    session_factory: async_sessionmaker[Any] | None = None,
    scorer: CryptoArticleSentimentScorer | None = None,
) -> dict[str, object]:
    """Backfill historical crypto daily sentiment rows from historical articles."""

    settings = get_settings()
    active_scorer = scorer or FinbertCryptoSentimentScorer(
        model_name=settings.research_finbert_model_name,
    )
    historical_client = client or CoinDeskSitemapNewsClient()
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("Historical sentiment backfill end_date must be on or after start_date")

    owns_engine = session_factory is None
    engine = None
    active_session_factory = session_factory
    if active_session_factory is None:
        engine = build_engine(settings)
        active_session_factory = build_session_factory(engine)

    aggregates: list[CryptoDailySentimentAggregate] = []
    failed_windows: list[dict[str, str]] = []
    backfill_dates = _inclusive_dates(start, end)
    normalized_symbols = [symbol.upper() for symbol in symbols]

    try:
        async with active_session_factory() as session:
            repository = ResearchRepository(session)
            for symbol in normalized_symbols:
                try:
                    search_result = await historical_client.search_articles(
                        symbol=symbol,
                        start_date=start,
                        end_date=end,
                    )
                except Exception as exc:
                    failed_windows.append(
                        {
                            "symbol": symbol,
                            "start_date": start.isoformat(),
                            "end_date": end.isoformat(),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    continue

                articles = tuple(_extract_articles(search_result))
                symbol_aggregates = await _build_historical_window_aggregates(
                    symbol=symbol,
                    backfill_dates=backfill_dates,
                    articles=articles,
                    scorer=active_scorer,
                )
                for aggregate in symbol_aggregates:
                    row = build_crypto_daily_sentiment_row(aggregate)
                    await repository.upsert_crypto_daily_sentiment(row)
                    aggregates.append(aggregate)
    finally:
        if owns_engine and engine is not None:
            await engine.dispose()

    return {
        "status": "completed" if not failed_windows else "completed_with_errors",
        "task": "historical_crypto_news_sentiment_backfill",
        "asset_class": "crypto",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "symbol_count": len(normalized_symbols),
        "symbols": normalized_symbols,
        "date_count": len(backfill_dates),
        "window_granularity": window_granularity,
        "request_window_count": len(normalized_symbols),
        "rows_upserted": len(aggregates),
        "failed_window_count": len(failed_windows),
        "failed_windows": failed_windows,
        "sentiment_summary": {
            f"{aggregate.symbol}:{aggregate.sentiment_date.isoformat()}": dict(
                aggregate_to_summary(aggregate)
            )
            for aggregate in aggregates
        },
        "pipeline": [
            "coindesk_sitemap_archive_fetch",
            "yearly_symbol_window",
            "local_daily_grouping",
            "dedupe",
            "pre_scoring_filter",
            "finbert",
            "daily_aggregate",
            "crypto_daily_sentiment_upsert",
        ],
        "message": "CoinDesk sitemap titles were scored and persisted to crypto_daily_sentiment.",
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }

async def _build_daily_aggregates(
    *,
    matches: Sequence[SymbolArticleMatches],
    sentiment_date: date,
    scorer: CryptoArticleSentimentScorer | None,
) -> list[CryptoDailySentimentAggregate]:
    """Build one daily aggregate per symbol, including no-coverage rows."""

    return [
        await build_daily_crypto_sentiment_aggregate(
            symbol=match.symbol,
            sentiment_date=sentiment_date,
            articles=match.articles,
            scorer=scorer,
        )
        for match in matches
    ]


async def _build_historical_window_aggregates(
    *,
    symbol: str,
    backfill_dates: Sequence[date],
    articles: Sequence[RssArticle],
    scorer: CryptoArticleSentimentScorer,
) -> list[CryptoDailySentimentAggregate]:
    """Build one aggregate per requested date using locally grouped historical articles."""

    grouped_articles: dict[date, list[RssArticle]] = {
        target_date: [] for target_date in backfill_dates
    }
    backfill_date_set = set(backfill_dates)
    for article in articles:
        article_date = article.published_at.date()
        if article_date in backfill_date_set:
            grouped_articles.setdefault(article_date, []).append(article)

    aggregates: list[CryptoDailySentimentAggregate] = []
    for target_date in backfill_dates:
        daily_articles = tuple(grouped_articles.get(target_date, []))
        raw_matches = [SymbolArticleMatches(symbol=symbol, articles=daily_articles)]
        prepared_matches = prepare_articles_for_scoring(
            raw_matches,
            now=datetime.combine(target_date, time.max, tzinfo=UTC),
            max_age_days=1,
        )
        aggregates.append(
            await build_daily_crypto_sentiment_aggregate(
                symbol=prepared_matches[0].symbol,
                sentiment_date=target_date,
                articles=prepared_matches[0].articles,
                scorer=scorer,
            )
        )
    return aggregates


async def _build_historical_daily_aggregate(
    *,
    client: HistoricalCryptoNewsClient,
    symbol: str,
    sentiment_date: date,
    scorer: CryptoArticleSentimentScorer,
) -> CryptoDailySentimentAggregate:
    search_result = await client.search_articles(
        symbol=symbol,
        start_date=sentiment_date,
        end_date=sentiment_date,
    )
    articles = tuple(_extract_articles(search_result))
    raw_matches = [SymbolArticleMatches(symbol=symbol, articles=articles)]
    prepared_matches = prepare_articles_for_scoring(
        raw_matches,
        now=datetime.combine(sentiment_date, time.max, tzinfo=UTC),
        max_age_days=1,
    )
    return await build_daily_crypto_sentiment_aggregate(
        symbol=prepared_matches[0].symbol,
        sentiment_date=sentiment_date,
        articles=prepared_matches[0].articles,
        scorer=scorer,
    )


def _extract_articles(search_result: object) -> Sequence[RssArticle]:
    articles = getattr(search_result, "articles", ())
    if isinstance(articles, Sequence) and not isinstance(articles, str):
        return tuple(article for article in articles if isinstance(article, RssArticle))
    return ()


def _inclusive_dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def build_daily_crypto_news_sentiment_payload(
    symbols: Sequence[str],
    sentiment_date: date,
) -> NewsSentimentTaskPayload:
    """Return the daily crypto news sentiment task payload."""

    return NewsSentimentTaskPayload(
        name="tasks.news_sentiment.daily_crypto_sync",
        kwargs={
            "symbols": list(symbols),
            "sentiment_date": sentiment_date.isoformat(),
        },
    )


def build_historical_crypto_news_sentiment_payload(
    symbols: Sequence[str],
    *,
    start_date: date,
    end_date: date,
) -> NewsSentimentTaskPayload:
    """Return the historical crypto news sentiment backfill task payload."""

    return NewsSentimentTaskPayload(
        name="tasks.news_sentiment.historical_crypto_backfill",
        kwargs={
            "symbols": list(symbols),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "window_granularity": "yearly",
        },
    )
