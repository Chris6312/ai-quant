"""Phase 8 crypto sentiment scoring and aggregation tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.research.crypto_sentiment import (
    build_crypto_daily_sentiment_row,
    build_daily_crypto_sentiment_aggregate,
)
from app.research.rss_client import RssArticle


async def test_empty_daily_sentiment_aggregate_preserves_missing_as_null() -> None:
    """No prepared articles should create missing sentiment with zero coverage."""

    aggregate = await build_daily_crypto_sentiment_aggregate(
        symbol="BTC/USD",
        sentiment_date=date(2026, 4, 25),
        articles=[],
    )

    assert aggregate.symbol == "BTC/USD"
    assert aggregate.article_count == 0
    assert aggregate.source_count == 0
    assert aggregate.positive_score is None
    assert aggregate.neutral_score is None
    assert aggregate.negative_score is None
    assert aggregate.compound_score is None
    assert aggregate.coverage_score == 0.0


async def test_daily_sentiment_aggregate_scores_prepared_articles() -> None:
    """Prepared RSS articles should aggregate into daily scores."""

    article = RssArticle(
        title="Bitcoin ETF inflows rally as adoption grows",
        url="https://example.test/btc",
        published_at=datetime(2026, 4, 25, 12, 0, tzinfo=UTC),
        source="Example",
        summary="BTC shows bullish growth after strong inflows.",
    )

    aggregate = await build_daily_crypto_sentiment_aggregate(
        symbol="BTC/USD",
        sentiment_date=date(2026, 4, 25),
        articles=[article],
    )

    assert aggregate.article_count == 1
    assert aggregate.source_count == 1
    assert aggregate.positive_score is not None
    assert aggregate.negative_score is not None
    assert aggregate.positive_score > aggregate.negative_score
    assert aggregate.compound_score is not None
    assert aggregate.compound_score > 0.0
    assert aggregate.coverage_score == 0.29


async def test_crypto_daily_sentiment_row_uses_canonical_daily_id() -> None:
    """Aggregate persistence rows should use deterministic symbol/date ids."""

    created_at = datetime(2026, 4, 25, 13, 0, tzinfo=UTC)
    article = RssArticle(
        title="Solana hack concerns fade",
        url="https://example.test/sol",
        published_at=created_at,
        source="Example",
        summary="SOL recovers after exploit risk declines.",
    )
    aggregate = await build_daily_crypto_sentiment_aggregate(
        symbol="SOL/USD",
        sentiment_date=date(2026, 4, 25),
        articles=[article],
    )

    row = build_crypto_daily_sentiment_row(aggregate, now=created_at)

    assert row.id == "SOL/USD:2026-04-25"
    assert row.symbol == "SOL/USD"
    assert row.asset_class == "crypto"
    assert row.sentiment_date == date(2026, 4, 25)
    assert row.created_at == created_at
    assert row.updated_at == created_at
