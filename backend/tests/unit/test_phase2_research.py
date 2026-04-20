"""Tests for Phase 2 research scoring modules."""

from datetime import UTC, date, datetime

import pytest

from app.research.analyst import AnalystRatingsService
from app.research.congress import CongressTradingService
from app.research.models import (
    AnalystRating,
    CongressTrade,
    InsiderTrade,
    NewsArticle,
    ScreeningMetrics,
)
from app.research.news_sentiment import NewsSentimentPipeline
from app.research.scorer import WatchlistScorer
from app.research.screener import StockScreenerService


@pytest.mark.asyncio
async def test_news_sentiment_pipeline_scores_positive_article() -> None:
    """News sentiment should respond to bullish wording."""

    pipeline = NewsSentimentPipeline()
    article = NewsArticle(
        symbol="NVDA",
        title="NVDA beats estimates and raises guidance",
        summary="The company posted strong growth and an upgrade followed.",
        published_at=datetime.now(tz=UTC),
        source="benzinga",
    )
    score = await pipeline.score_article(article)
    assert score.confidence > 0.0
    assert score.created_at.tzinfo is not None


def test_congress_trade_score_uses_committee_relevance() -> None:
    """Congress scoring should reward relevant committee exposure."""

    scorer = CongressTradingService.__new__(CongressTradingService)
    trade = CongressTrade(
        symbol="LMT",
        trade_type="purchase",
        chamber="house",
        days_to_disclose=10,
        politician="Jane Doe",
        committee="Armed Services",
        amount_range=None,
        trade_date=date(2026, 4, 1),
        disclosure_date=date(2026, 4, 11),
    )
    score = CongressTradingService.score_trade(scorer, trade, ["Armed Services"])
    assert score > 0.0


def test_insider_trade_detection_requires_material_purchase() -> None:
    """Insider trades should only pass when they are large open-market buys."""

    trade = InsiderTrade(
        symbol="AAPL",
        insider_name="Jane Smith",
        title="CEO",
        transaction_type="P",
        total_value=75_000.0,
        filing_date=date(2026, 4, 1),
        transaction_date=date(2026, 3, 30),
    )
    from app.research.insider import InsiderTradingService

    service = InsiderTradingService.__new__(InsiderTradingService)
    score = InsiderTradingService.score_trade(service, trade)
    assert score > 0.0


def test_screener_filters_and_scores_candidates() -> None:
    """The screener should filter invalid symbols and score valid ones."""

    screener = StockScreenerService()
    metrics = ScreeningMetrics(
        symbol="MSFT",
        avg_volume=2_000_000.0,
        price=400.0,
        market_cap=3_000_000_000_000.0,
        pe_ratio=35.0,
        relative_volume=2.0,
        float_shares=20_000_000.0,
        sector="Technology",
        above_50d_ema=True,
        earnings_blocked=False,
    )
    assert screener.passes_criteria(metrics) is True
    assert screener.score_candidate(metrics) > 0.0
    signal = screener.build_signal_row(metrics)
    assert signal.signal_type == "screener"


def test_watchlist_scorer_combines_signals() -> None:
    """Composite watchlist scoring should produce a bounded score."""

    scorer = WatchlistScorer()
    score = scorer.score_breakdown(
        symbol="NVDA",
        news_sentiment_7d=0.8,
        congress_buy=0.9,
        insider_buy=0.7,
        screener_pass=0.6,
        analyst_upgrade=0.5,
    )
    assert 0.0 <= score.composite_score <= 100.0
    assert score.symbol == "NVDA"


@pytest.mark.asyncio
async def test_news_pipeline_can_build_persistable_signal() -> None:
    """News sentiment should build a research signal row for persistence."""

    pipeline = NewsSentimentPipeline()
    article = NewsArticle(
        symbol="AAPL",
        title="AAPL upgrade sparks bullish momentum",
        summary="Analysts raised targets after strong growth.",
        published_at=datetime.now(tz=UTC),
        source="benzinga",
    )
    sentiment = await pipeline.score_article(article)
    row = pipeline.build_signal_row(article, sentiment)
    assert row.signal_type == "news_sentiment"
    assert row.source == "benzinga"


@pytest.mark.asyncio
async def test_analyst_service_persists_existing_ratings() -> None:
    """Analyst service should convert parsed ratings into signals."""

    class StubRepo:
        def __init__(self) -> None:
            self.rows: list[object] = []

        async def add_signal(self, row: object) -> None:
            self.rows.append(row)

    repo = StubRepo()
    service = AnalystRatingsService(repository=repo, base_url="https://example.test")
    ratings = [
        AnalystRating(
            symbol="NVDA",
            firm="Goldman",
            action="upgrade",
            current_price=900.0,
            old_price_target=850.0,
            new_price_target=1050.0,
            rating="buy",
            published_at=datetime.now(tz=UTC),
        )
    ]
    signals = await service.persist_ratings(ratings)
    assert len(signals) == 1
    assert len(repo.rows) == 1
    assert signals[0].signal_type == "analyst_upgrade"
