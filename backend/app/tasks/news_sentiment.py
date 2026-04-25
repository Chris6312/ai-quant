"""Celery task scaffold for crypto news sentiment ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config.crypto_scope import list_crypto_watchlist_symbols
from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.repositories.research import ResearchRepository
from app.research.crypto_sentiment import (
    aggregate_to_summary,
    build_crypto_daily_sentiment_row,
    build_daily_crypto_sentiment_aggregate,
)
from app.research.rss_client import (
    CryptoRssClient,
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


@celery_app.task(name="tasks.news_sentiment.daily_crypto_sync")
def daily_crypto_news_sentiment_task(
    symbols: list[str] | None = None,
    sentiment_date: str | None = None,
) -> dict[str, object]:
    """Fetch RSS articles and prepare them for daily sentiment storage."""

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_date = sentiment_date or date.today().isoformat()
    return asyncio.run(
        collect_daily_crypto_rss_snapshot(
            symbols=requested_symbols,
            sentiment_date=requested_date,
        )
    )


async def collect_daily_crypto_rss_snapshot(
    symbols: Sequence[str],
    sentiment_date: str,
    client: CryptoRssClient | None = None,
) -> dict[str, object]:
    """Fetch, filter, deduplicate, and score RSS articles without DB writes."""

    rss_client = client or CryptoRssClient()
    articles = await rss_client.fetch_articles()
    raw_matches = filter_relevant_articles(articles, symbols)
    prepared_matches = prepare_articles_for_scoring(raw_matches)
    raw_summary = summarize_article_matches(raw_matches)
    prepared_summary = summarize_article_matches(prepared_matches)
    target_date = date.fromisoformat(sentiment_date)
    aggregates = [
        await build_daily_crypto_sentiment_aggregate(
            symbol=match.symbol,
            sentiment_date=target_date,
            articles=match.articles,
        )
        for match in prepared_matches
    ]
    return {
        "status": "rss_scoring_ready",
        "task": "daily_crypto_news_sentiment",
        "asset_class": "crypto",
        "sentiment_date": sentiment_date,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "raw_article_count": len(articles),
        "raw_match_summary": raw_summary,
        "prepared_match_summary": prepared_summary,
        "sentiment_summary": {
            aggregate.symbol: dict(aggregate_to_summary(aggregate)) for aggregate in aggregates
        },
        "pipeline": [
            "rss_fetch",
            "symbol_filter",
            "dedupe",
            "pre_scoring_filter",
            "article_scoring",
            "daily_storage",
            "gdelt",
            "structured_api",
            "fallback_api",
            "finbert",
        ],
        "message": "RSS articles are scored into daily aggregates; storage is explicit.",
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }


async def persist_daily_crypto_rss_sentiment(
    *,
    symbols: Sequence[str],
    sentiment_date: str,
    client: CryptoRssClient | None = None,
    session_factory: async_sessionmaker[Any] | None = None,
) -> dict[str, object]:
    """Fetch RSS, score daily aggregates, and upsert crypto sentiment rows."""

    rss_client = client or CryptoRssClient()
    articles = await rss_client.fetch_articles()
    raw_matches = filter_relevant_articles(articles, symbols)
    prepared_matches = prepare_articles_for_scoring(raw_matches)
    target_date = date.fromisoformat(sentiment_date)
    aggregates = [
        await build_daily_crypto_sentiment_aggregate(
            symbol=match.symbol,
            sentiment_date=target_date,
            articles=match.articles,
        )
        for match in prepared_matches
    ]

    owns_engine = session_factory is None
    engine = None
    active_session_factory = session_factory
    if active_session_factory is None:
        settings = get_settings()
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
        "status": "ok",
        "task": "daily_crypto_news_sentiment_persist",
        "asset_class": "crypto",
        "sentiment_date": sentiment_date,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "raw_article_count": len(articles),
        "prepared_match_summary": summarize_article_matches(prepared_matches),
        "sentiment_summary": {
            aggregate.symbol: dict(aggregate_to_summary(aggregate)) for aggregate in aggregates
        },
        "rows_upserted": len(aggregates),
        "finished_at": datetime.now(tz=UTC).isoformat(),
    }


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
