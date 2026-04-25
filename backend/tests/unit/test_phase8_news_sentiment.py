"""Phase 8 news sentiment persistence and worker scaffold tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.config.constants import CELERY_RESEARCH_QUEUE
from app.db.models import CryptoDailySentimentRow
from app.tasks.news_sentiment import (
    build_daily_crypto_news_sentiment_payload,
    daily_crypto_news_sentiment_task,
)
from app.tasks.worker import celery_app


def test_crypto_daily_sentiment_row_preserves_missing_sentiment_as_null() -> None:
    """Missing crypto sentiment should remain NULL with zero coverage."""

    created_at = datetime(2026, 4, 24, 8, 40, tzinfo=UTC)
    row = CryptoDailySentimentRow(
        id="XDG/USD:2026-04-24",
        symbol="XDG/USD",
        asset_class="crypto",
        sentiment_date=date(2026, 4, 24),
        source_count=0,
        article_count=0,
        positive_score=None,
        neutral_score=None,
        negative_score=None,
        compound_score=None,
        coverage_score=0.0,
        created_at=created_at,
        updated_at=created_at,
    )

    assert row.compound_score is None
    assert row.positive_score is None
    assert row.neutral_score is None
    assert row.negative_score is None
    assert row.coverage_score == 0.0
    assert row.article_count == 0


def test_news_sentiment_payload_targets_research_task() -> None:
    """Daily crypto sentiment payload should target the isolated research task."""

    payload = build_daily_crypto_news_sentiment_payload(
        ["BTC/USD", "XDG/USD"],
        date(2026, 4, 24),
    )

    assert payload.name == "tasks.news_sentiment.daily_crypto_sync"
    assert payload.kwargs == {
        "symbols": ["BTC/USD", "XDG/USD"],
        "sentiment_date": "2026-04-24",
    }


def test_news_sentiment_task_uses_research_queue() -> None:
    """News sentiment work should not share the ML candle/prediction queue."""

    routes = celery_app.conf.task_routes

    assert routes["tasks.news_sentiment.*"] == {"queue": CELERY_RESEARCH_QUEUE}


def test_news_sentiment_task_scaffold_returns_pipeline_contract() -> None:
    """The first news slice should expose the agreed ingestion order without doing IO."""

    result = daily_crypto_news_sentiment_task(
        symbols=["BTC/USD", "XDG/USD"],
        sentiment_date="2026-04-24",
    )

    assert result["status"] == "scaffold"
    assert result["asset_class"] == "crypto"
    assert result["sentiment_date"] == "2026-04-24"
    assert result["symbols"] == ["BTC/USD", "XDG/USD"]
    assert result["pipeline"] == [
        "rss",
        "gdelt",
        "structured_api",
        "fallback_api",
        "dedupe",
        "finbert",
        "daily_storage",
    ]
