"""Phase 8 news sentiment persistence and worker scaffold tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from pytest import MonkeyPatch

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


def test_news_sentiment_task_returns_rss_ingestion_snapshot(monkeypatch: MonkeyPatch) -> None:
    """The research task should fetch RSS and stop before scoring/storage."""

    from app.research.rss_client import RssArticle

    class FakeRssClient:
        async def fetch_articles(self) -> list[RssArticle]:
            return [
                RssArticle(
                    title="Bitcoin ETF inflows rise",
                    url="https://example.test/btc",
                    published_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
                    source="Example",
                    summary="BTC and crypto markets moved higher after inflows improved.",
                ),
                RssArticle(
                    title="Macro rates update",
                    url="https://example.test/macro",
                    published_at=datetime(2026, 4, 24, 13, 0, tzinfo=UTC),
                    source="Example",
                    summary="No symbol-specific digital asset details.",
                ),
            ]

    monkeypatch.setattr("app.tasks.news_sentiment.CryptoRssClient", FakeRssClient)

    result = daily_crypto_news_sentiment_task(
        symbols=["BTC/USD", "XDG/USD"],
        sentiment_date="2026-04-24",
    )

    assert result["status"] == "rss_ingestion_ready"
    assert result["asset_class"] == "crypto"
    assert result["sentiment_date"] == "2026-04-24"
    assert result["symbols"] == ["BTC/USD", "XDG/USD"]
    assert result["raw_article_count"] == 2
    assert result["prepared_match_summary"] == {
        "symbol_count": 2,
        "matched_article_count": 1,
        "per_symbol": {
            "BTC/USD": {"article_count": 1, "sources": ["Example"]},
            "XDG/USD": {"article_count": 0, "sources": []},
        },
    }
    assert result["pipeline"] == [
        "rss_fetch",
        "symbol_filter",
        "dedupe",
        "pre_scoring_filter",
        "gdelt",
        "structured_api",
        "fallback_api",
        "finbert",
        "daily_storage",
    ]
