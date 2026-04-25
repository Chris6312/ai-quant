"""Celery task scaffold for crypto news sentiment ingestion."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.config.crypto_scope import list_crypto_watchlist_symbols
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
    """Reserve the research queue task for daily crypto sentiment ingestion.

    The ingestion sources and FinBERT scoring are intentionally not wired in this
    storage slice. This task keeps orchestration isolated from ML candle and
    prediction work before RSS/GDELT/API clients are added.
    """

    requested_symbols = symbols or list_crypto_watchlist_symbols()
    requested_date = sentiment_date or date.today().isoformat()
    return {
        "status": "scaffold",
        "task": "daily_crypto_news_sentiment",
        "asset_class": "crypto",
        "sentiment_date": requested_date,
        "symbol_count": len(requested_symbols),
        "symbols": requested_symbols,
        "pipeline": [
            "rss",
            "gdelt",
            "structured_api",
            "fallback_api",
            "dedupe",
            "finbert",
            "daily_storage",
        ],
        "message": "storage contract is ready; source ingestion is next slice",
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
