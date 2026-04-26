"""Tests for Phase 5 stock training input assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import ml as ml_router
from app.config.constants import ML_CANDLE_USAGE
from app.db.models import (
    CandleRow,
    CongressTradeRow,
    InsiderTradeRow,
    ResearchSignalRow,
    WatchlistRow,
)
from app.ml.features import FeatureEngineer, ResearchInputs
from app.ml.trainer import TrainResult
from app.ml.training_inputs import (
    StockTrainingDataset,
    StockTrainingInputAssembler,
    train_stock_model_from_db,
)
from app.models.domain import Candle


def _build_domain_candles(symbol: str) -> tuple[Candle, ...]:
    """Build enough candles for the trainer to accept the sample set."""

    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(240):
        price = 100.0 + float(index)
        candles.append(
            Candle(
                time=start + timedelta(days=index),
                symbol=symbol,
                asset_class="stock",
                timeframe="1Day",
                open=price,
                high=price + 1.0,
                low=price - 1.0,
                close=price + 0.5,
                volume=1_000_000.0 + float(index * 1_000),
                source="alpaca_training",
            )
        )
    return tuple(candles)


@dataclass(slots=True, frozen=True)
class _TrainResultStub:
    """TrainResult-shaped stub that avoids constructor drift in tests."""

    asset_class: str
    validation_sharpe: float
    validation_accuracy: float
    n_train_samples: int
    n_test_samples: int
    feature_importances: dict[str, float]
    model_path: str


def _as_train_result(
    *,
    asset_class: str,
    validation_sharpe: float,
    validation_accuracy: float,
    n_train_samples: int,
    n_test_samples: int,
    feature_importances: dict[str, float],
    model_path: str,
) -> TrainResult:
    """Return a TrainResult-compatible stub without depending on constructor shape."""

    return cast(
        TrainResult,
        _TrainResultStub(
            asset_class=asset_class,
            validation_sharpe=validation_sharpe,
            validation_accuracy=validation_accuracy,
            n_train_samples=n_train_samples,
            n_test_samples=n_test_samples,
            feature_importances=feature_importances,
            model_path=model_path,
        ),
    )


@pytest.mark.asyncio
async def test_stock_training_input_assembler_builds_non_default_research_inputs() -> None:
    """Persisted research rows should assemble into non-default ResearchInputs values."""

    now = datetime(2026, 4, 21, tzinfo=UTC)

    candle_rows = [
        CandleRow(
            time=now - timedelta(days=220 - index),
            symbol="AAPL",
            asset_class="stock",
            timeframe="1Day",
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=Decimal("1000000"),
            source="alpaca_training",
            usage=ML_CANDLE_USAGE,
        )
        for index in range(220)
    ]
    signal_rows = [
        ResearchSignalRow(
            id="signal-news-1",
            symbol="AAPL",
            signal_type="news_sentiment",
            score=Decimal("0.80"),
            direction="long",
            source="news",
            raw_data={"article_count": 3},
            created_at=now - timedelta(hours=12),
        ),
        ResearchSignalRow(
            id="signal-news-2",
            symbol="AAPL",
            signal_type="news_sentiment",
            score=Decimal("0.40"),
            direction="long",
            source="news",
            raw_data={"article_count": 2},
            created_at=now - timedelta(days=3),
        ),
        ResearchSignalRow(
            id="signal-analyst-1",
            symbol="AAPL",
            signal_type="analyst_upgrade",
            score=Decimal("0.70"),
            direction="long",
            source="analyst",
            raw_data={"consensus_rating": 1.8},
            created_at=now - timedelta(days=4),
        ),
        ResearchSignalRow(
            id="signal-congress-1",
            symbol="AAPL",
            signal_type="congress_bullish",
            score=Decimal("0.90"),
            direction="long",
            source="congress",
            raw_data=None,
            created_at=now - timedelta(days=6),
        ),
        ResearchSignalRow(
            id="signal-insider-1",
            symbol="AAPL",
            signal_type="insider_bullish",
            score=Decimal("0.60"),
            direction="long",
            source="insider",
            raw_data=None,
            created_at=now - timedelta(days=8),
        ),
    ]
    congress_rows = [
        CongressTradeRow(
            id="congress-1",
            politician="Sample Member",
            chamber="House",
            symbol="AAPL",
            trade_type="buy",
            amount_range="$15,001-$50,000",
            trade_date=(now - timedelta(days=10)).date(),
            disclosure_date=(now - timedelta(days=7)).date(),
            days_to_disclose=3,
            created_at=now - timedelta(days=7),
        )
    ]
    insider_rows = [
        InsiderTradeRow(
            id="insider-1",
            symbol="AAPL",
            insider_name="Jane Executive",
            title="Chief Executive Officer",
            transaction_type="A",
            shares=Decimal("1000"),
            price_per_share=Decimal("150"),
            total_value=Decimal("150000"),
            filing_date=(now - timedelta(days=5)).date(),
            transaction_date=(now - timedelta(days=9)).date(),
            created_at=now - timedelta(days=5),
        )
    ]
    watchlist_rows = [
        WatchlistRow(
            symbol="AAPL",
            asset_class="stock",
            added_at=now,
            added_by="test",
            research_score=Decimal("88"),
            low_score_since=None,
            is_active=True,
            notes=None,
        )
    ]

    class StubAssembler(StockTrainingInputAssembler):
        async def _load_candle_rows(
            self,
            session: object,
            *,
            symbols: tuple[str, ...] | None,
            timeframe: str,
        ) -> list[CandleRow]:
            del session, symbols, timeframe
            return candle_rows

        async def _load_research_signal_rows(
            self,
            session: object,
            symbols: tuple[str, ...],
        ) -> list[ResearchSignalRow]:
            del session, symbols
            return signal_rows

        async def _load_congress_rows(
            self,
            session: object,
            symbols: tuple[str, ...],
        ) -> list[CongressTradeRow]:
            del session, symbols
            return congress_rows

        async def _load_insider_rows(
            self,
            session: object,
            symbols: tuple[str, ...],
        ) -> list[InsiderTradeRow]:
            del session, symbols
            return insider_rows

        async def _load_watchlist_rows(
            self,
            session: object,
            symbols: tuple[str, ...],
        ) -> list[WatchlistRow]:
            del session, symbols
            return watchlist_rows

    assembler = StubAssembler()
    dataset = await assembler.assemble(cast(object, None), symbols=["AAPL"])

    research = dataset.research_lookup["AAPL"]
    assert len(dataset.candles) == 220
    assert research.news_sentiment_1d > 0.0
    assert research.news_sentiment_7d > 0.0
    assert research.news_article_count_7d == 5
    assert research.congress_buy_score > 0.0
    assert research.congress_cluster_30d == 1
    assert research.days_since_last_congress < 999
    assert research.insider_buy_score > 0.0
    assert research.insider_cluster_60d == 1
    assert research.insider_value_60d == 150000.0
    assert research.ceo_bought_90d is True
    assert research.analyst_upgrade_score > 0.0
    assert research.consensus_rating == pytest.approx(1.8)
    assert research.watchlist_research_score == 88.0
    assert research.earnings_proximity_days == 999


@pytest.mark.asyncio
async def test_train_stock_model_from_db_passes_non_default_research_lookup() -> None:
    """The DB helper should pass assembled research inputs into the trainer."""

    dataset = StockTrainingDataset(
        candles=_build_domain_candles("AAPL"),
        research_lookup={
            "AAPL": ResearchInputs(
                news_sentiment_7d=0.6,
                watchlist_research_score=91.0,
            )
        },
    )

    class StubAssembler(StockTrainingInputAssembler):
        async def assemble(
            self,
            session: object,
            *,
            symbols: list[str] | None = None,
            timeframe: str = "1Day",
        ) -> StockTrainingDataset:
            del session, symbols, timeframe
            return dataset

    class StubTrainer:
        def __init__(self) -> None:
            self.captured_lookup: dict[str, ResearchInputs] | None = None

        async def train(
            self,
            candles: tuple[Candle, ...],
            asset_class: str,
            feature_engineer: FeatureEngineer,
            research_lookup: dict[str, ResearchInputs] | None = None,
        ) -> TrainResult:
            del candles, feature_engineer
            self.captured_lookup = research_lookup
            return _as_train_result(
                asset_class=asset_class,
                validation_sharpe=1.2,
                validation_accuracy=0.66,
                n_train_samples=123,
                n_test_samples=20,
                feature_importances={"watchlist_research_score": 10.0},
                model_path="models/model_stock_fold1.lgbm",
            )

    trainer = StubTrainer()
    result, returned_dataset = await train_stock_model_from_db(
        session=cast(object, None),
        trainer=cast(object, trainer),
        feature_engineer=FeatureEngineer(),
        assembler=StubAssembler(),
    )

    assert result.asset_class == "stock"
    assert trainer.captured_lookup is not None
    assert trainer.captured_lookup["AAPL"].watchlist_research_score == 91.0
    assert trainer.captured_lookup["AAPL"].news_sentiment_7d == 0.6
    assert returned_dataset.research_lookup["AAPL"].watchlist_research_score == 91.0


def test_train_stock_model_endpoint_returns_dataset_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stock train endpoint should expose dataset counts with model metrics."""

    async def fake_train_stock_model_from_db(
        session: object,
        *,
        symbols: list[str] | None = None,
        timeframe: str = "1Day",
    ) -> tuple[TrainResult, StockTrainingDataset]:
        del session
        assert symbols == ["AAPL", "MSFT"]
        assert timeframe == "1Day"
        return (
            _as_train_result(
                asset_class="stock",
                validation_sharpe=1.5,
                validation_accuracy=0.72,
                n_train_samples=200,
                n_test_samples=40,
                feature_importances={"news_sentiment_7d": 4.0},
                model_path="models/model_stock_fold1.lgbm",
            ),
            StockTrainingDataset(
                candles=_build_domain_candles("AAPL"),
                research_lookup={"AAPL": ResearchInputs(news_sentiment_7d=0.5)},
            ),
        )

    class _FakeSession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object,
        ) -> None:
            del exc_type, exc, tb
            return None

    monkeypatch.setattr(ml_router, "get_settings", lambda: object())
    monkeypatch.setattr(ml_router, "build_engine", lambda settings: object())
    monkeypatch.setattr(ml_router, "build_session_factory", lambda engine: lambda: _FakeSession())
    monkeypatch.setattr(ml_router, "train_stock_model_from_db", fake_train_stock_model_from_db)
    monkeypatch.setattr(ml_router, "load_jobs", lambda: [])

    app = FastAPI()
    app.include_router(ml_router.router)
    client = TestClient(app)

    response = client.post("/ml/train/stock?symbols=AAPL,MSFT&timeframe=1Day")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_class"] == "stock"
    assert payload["dataset_candles"] == 240
    assert payload["dataset_symbols"] == 1
    assert payload["research_symbols"] == 1
    assert payload["validation_sharpe"] == 1.5