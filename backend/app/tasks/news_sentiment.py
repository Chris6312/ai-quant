"""Celery task scaffold for crypto news sentiment ingestion."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.config.crypto_scope import list_crypto_watchlist_symbols
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
    """Fetch RSS articles and prepare them for later sentiment scoring."""

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
    """Fetch, filter, and deduplicate RSS articles before scoring is wired."""

    rss_client = client or CryptoRssClient()
    articles = await rss_client.fetch_articles()
    raw_matches = filter_relevant_articles(articles, symbols)
    prepared_matches = prepare_articles_for_scoring(raw_matches)
    raw_summary = summarize_article_matches(raw_matches)
    prepared_summary = summarize_article_matches(prepared_matches)
    return {
        "status": "rss_ingestion_ready",
        "task": "daily_crypto_news_sentiment",
        "asset_class": "crypto",
        "sentiment_date": sentiment_date,
        "symbol_count": len(symbols),
        "symbols": list(symbols),
        "raw_article_count": len(articles),
        "raw_match_summary": raw_summary,
        "prepared_match_summary": prepared_summary,
        "pipeline": [
            "rss_fetch",
            "symbol_filter",
            "dedupe",
            "pre_scoring_filter",
            "gdelt",
            "structured_api",
            "fallback_api",
            "finbert",
            "daily_storage",
        ],
        "message": "RSS articles are filtered and deduped; scoring/storage comes next",
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
