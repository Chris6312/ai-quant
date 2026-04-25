"""Phase 8 sentiment-to-ML feature join tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.db.models import CryptoDailySentimentRow
from app.ml.features import FeatureEngineer, ResearchInputs
from app.ml.trainer import WalkForwardTrainer
from app.ml.training_inputs import CryptoTrainingInputAssembler
from app.models.domain import Candle


def _daily_crypto_candles() -> list[Candle]:
    """Build enough crypto candles for feature engineering."""

    start = datetime(2025, 8, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(220):
        price = 100.0 + float(index)
        candles.append(
            Candle(
                time=start + timedelta(days=index),
                symbol="BTC/USD",
                asset_class="crypto",
                timeframe="1Day",
                open=price,
                high=price + 2.0,
                low=price - 2.0,
                close=price + 1.0,
                volume=10_000.0 + float(index),
                source="alpaca_training",
            )
        )
    return candles


def test_crypto_feature_engineer_uses_source_backed_sentiment_only() -> None:
    """Crypto should keep real sentiment fields while stock-only research stays defaulted."""

    features = FeatureEngineer().build(
        _daily_crypto_candles(),
        "crypto",
        ResearchInputs(
            news_sentiment_1d=0.45,
            news_sentiment_7d=0.20,
            news_article_count_7d=9,
            congress_buy_score=0.99,
            insider_buy_score=0.88,
            analyst_upgrade_score=0.77,
        ),
    )

    assert features is not None
    assert features["news_sentiment_1d"] == 0.45
    assert features["news_sentiment_7d"] == 0.20
    assert features["news_article_count_7d"] == 9.0
    assert features["congress_buy_score"] == 0.0
    assert features["insider_buy_score"] == 0.0
    assert features["analyst_upgrade_score"] == 0.0


def test_crypto_sentiment_rows_map_to_existing_research_contract() -> None:
    """Persisted daily sentiment should become date-specific ML research inputs."""

    assembler = CryptoTrainingInputAssembler()
    target_date = date(2026, 4, 24)
    rows = [
        CryptoDailySentimentRow(
            id="BTC/USD:2026-04-22",
            symbol="BTC/USD",
            asset_class="crypto",
            sentiment_date=date(2026, 4, 22),
            source_count=1,
            article_count=2,
            positive_score=0.70,
            neutral_score=0.20,
            negative_score=0.10,
            compound_score=0.60,
            coverage_score=0.29,
            created_at=datetime(2026, 4, 22, tzinfo=UTC),
            updated_at=datetime(2026, 4, 22, tzinfo=UTC),
        ),
        CryptoDailySentimentRow(
            id="BTC/USD:2026-04-24",
            symbol="BTC/USD",
            asset_class="crypto",
            sentiment_date=target_date,
            source_count=1,
            article_count=3,
            positive_score=0.20,
            neutral_score=0.30,
            negative_score=0.50,
            compound_score=-0.30,
            coverage_score=0.43,
            created_at=datetime(2026, 4, 24, tzinfo=UTC),
            updated_at=datetime(2026, 4, 24, tzinfo=UTC),
        ),
    ]

    research = assembler._sentiment_rows_to_research_inputs(
        one_day=rows[-1],
        trailing_rows=rows,
    )

    assert research.news_sentiment_1d == -0.30
    assert research.news_sentiment_7d == 0.15
    assert research.news_article_count_7d == 5


def test_missing_crypto_sentiment_does_not_create_fake_neutral_signal() -> None:
    """Zero-coverage sentiment rows should not be treated as observed neutral articles."""

    assembler = CryptoTrainingInputAssembler()
    missing_row = CryptoDailySentimentRow(
        id="BTC/USD:2026-04-25",
        symbol="BTC/USD",
        asset_class="crypto",
        sentiment_date=date(2026, 4, 25),
        source_count=0,
        article_count=0,
        positive_score=None,
        neutral_score=None,
        negative_score=None,
        compound_score=None,
        coverage_score=0.0,
        created_at=datetime(2026, 4, 25, tzinfo=UTC),
        updated_at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    research = assembler._sentiment_rows_to_research_inputs(
        one_day=missing_row,
        trailing_rows=[missing_row],
    )

    assert research.news_sentiment_1d == 0.0
    assert research.news_sentiment_7d == 0.0
    assert research.news_article_count_7d == 0
    assert assembler._observed_compound_score(missing_row) is None


def test_trainer_prefers_date_specific_research_lookup() -> None:
    """Walk-forward samples should use symbol/date sentiment before symbol fallback."""

    trainer = WalkForwardTrainer()
    dated = ResearchInputs(news_sentiment_1d=0.33)
    fallback = ResearchInputs(news_sentiment_1d=-0.50)

    selected = trainer._research_inputs_for_sample(
        {
            "BTC/USD": fallback,
            ("BTC/USD", date(2026, 4, 24)): dated,
        },
        symbol="BTC/USD",
        sample_date=date(2026, 4, 24),
    )

    assert selected == dated
