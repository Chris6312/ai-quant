"""Phase 8 news sentiment persistence and worker scaffold tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from pytest import MonkeyPatch

from app.config.constants import CELERY_RESEARCH_QUEUE
from app.db.models import CryptoDailySentimentRow
from app.research.crypto_sentiment import CryptoArticleSentiment
from app.research.rss_client import RssArticle
from app.tasks.news_sentiment import (
    build_daily_crypto_news_sentiment_payload,
    daily_crypto_news_sentiment_task,
    persist_daily_crypto_rss_sentiment,
)
from app.tasks.worker import celery_app


class FakeCryptoSentimentScorer:
    """Deterministic scorer used to avoid loading FinBERT in unit tests."""

    async def score_article(self, article: RssArticle) -> CryptoArticleSentiment:
        return CryptoArticleSentiment(
            positive_score=0.70,
            neutral_score=0.20,
            negative_score=0.10,
            compound_score=0.60,
            source=article.source,
        )


class FakeRssClient:
    """RSS client with one BTC article and one irrelevant macro article."""

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


class FakeSessionContext:
    """Async context manager shaped like an async SQLAlchemy session factory result."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        return None


def fake_session_factory() -> FakeSessionContext:
    """Return a fake async session context."""

    return FakeSessionContext()


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


def test_news_sentiment_task_persists_daily_sentiment(monkeypatch: MonkeyPatch) -> None:
    """The Celery entry point should call the persistence flow, not snapshot-only scoring."""

    captured: dict[str, object] = {}

    async def fake_persist_daily_crypto_rss_sentiment(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "status": "persisted",
            "task": "daily_crypto_news_sentiment",
            "rows_upserted": 2,
        }

    monkeypatch.setattr(
        "app.tasks.news_sentiment.persist_daily_crypto_rss_sentiment",
        fake_persist_daily_crypto_rss_sentiment,
    )

    result = daily_crypto_news_sentiment_task(
        symbols=["BTC/USD", "XDG/USD"],
        sentiment_date="2026-04-24",
    )

    assert result == {
        "status": "persisted",
        "task": "daily_crypto_news_sentiment",
        "rows_upserted": 2,
    }
    assert captured == {
        "symbols": ["BTC/USD", "XDG/USD"],
        "sentiment_date": "2026-04-24",
    }


async def test_persist_daily_crypto_rss_sentiment_upserts_one_row_per_symbol(
    monkeypatch: MonkeyPatch,
) -> None:
    """Prepared RSS sentiment should upsert one daily row for every requested symbol."""

    upserted_rows: list[CryptoDailySentimentRow] = []

    class FakeResearchRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def upsert_crypto_daily_sentiment(
            self,
            row: CryptoDailySentimentRow,
        ) -> CryptoDailySentimentRow:
            upserted_rows.append(row)
            return row

    monkeypatch.setattr("app.tasks.news_sentiment.ResearchRepository", FakeResearchRepository)

    result = await persist_daily_crypto_rss_sentiment(
        symbols=["BTC/USD", "XDG/USD"],
        sentiment_date="2026-04-24",
        client=FakeRssClient(),
        session_factory=fake_session_factory,
        scorer=FakeCryptoSentimentScorer(),
    )

    assert result["status"] == "persisted"
    assert result["rows_upserted"] == 2
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
        "finbert",
        "daily_aggregate",
        "crypto_daily_sentiment_upsert",
    ]
    assert [row.id for row in upserted_rows] == ["BTC/USD:2026-04-24", "XDG/USD:2026-04-24"]
    assert upserted_rows[0].compound_score == 0.60
    assert upserted_rows[0].article_count == 1
    assert upserted_rows[0].coverage_score == 0.29
    assert upserted_rows[1].compound_score is None
    assert upserted_rows[1].article_count == 0
    assert upserted_rows[1].coverage_score == 0.0


class FakeHistoricalResult:
    """Simple historical search result shaped like the GDELT client result."""

    def __init__(self, articles: tuple[RssArticle, ...]) -> None:
        self.articles = articles


class FakeHistoricalClient:
    """Historical client returning one BTC window article and no DOGE coverage."""

    async def search_articles(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> FakeHistoricalResult:
        assert start_date == date(2026, 4, 24)
        assert end_date == date(2026, 4, 25)
        if symbol == "BTC/USD":
            return FakeHistoricalResult(
                (
                    RssArticle(
                        title="Bitcoin ETF inflows rise",
                        url=f"https://example.test/btc/{start_date.isoformat()}",
                        published_at=datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
                        source="CoinDesk:Sitemap",
                        summary="BTC and crypto markets moved higher after inflows improved.",
                    ),
                )
            )
        return FakeHistoricalResult(())


class FailingHistoricalClient:
    """Historical client that fails provider calls for safety tests."""

    async def search_articles(
        self,
        *,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> FakeHistoricalResult:
        raise RuntimeError(f"provider failed for {symbol} {start_date.isoformat()}")


def test_historical_sentiment_payload_targets_backfill_task() -> None:
    """Historical backfill payload should target the research task with date bounds."""

    from app.tasks.news_sentiment import build_historical_crypto_news_sentiment_payload

    payload = build_historical_crypto_news_sentiment_payload(
        ["BTC/USD"],
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
    )

    assert payload.name == "tasks.news_sentiment.historical_crypto_backfill"
    assert payload.kwargs == {
        "symbols": ["BTC/USD"],
        "start_date": "2026-04-01",
        "end_date": "2026-04-02",
        "window_granularity": "yearly",
    }


async def test_backfill_historical_crypto_sentiment_upserts_symbol_date_rows(
    monkeypatch: MonkeyPatch,
) -> None:
    """Historical backfill should persist one aggregate row per symbol and date."""

    from app.tasks.news_sentiment import backfill_historical_crypto_sentiment

    upserted_rows: list[CryptoDailySentimentRow] = []

    class FakeResearchRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def upsert_crypto_daily_sentiment(
            self,
            row: CryptoDailySentimentRow,
        ) -> CryptoDailySentimentRow:
            upserted_rows.append(row)
            return row

    monkeypatch.setattr("app.tasks.news_sentiment.ResearchRepository", FakeResearchRepository)

    result = await backfill_historical_crypto_sentiment(
        symbols=["BTC/USD", "XDG/USD"],
        start_date="2026-04-24",
        end_date="2026-04-25",
        client=FakeHistoricalClient(),
        session_factory=fake_session_factory,
        scorer=FakeCryptoSentimentScorer(),
    )

    assert result["status"] == "completed"
    assert result["rows_upserted"] == 4
    assert result["failed_window_count"] == 0
    assert result["request_window_count"] == 2
    assert result["pipeline"] == [
        "coindesk_sitemap_archive_fetch",
        "yearly_symbol_window",
        "local_daily_grouping",
        "dedupe",
        "pre_scoring_filter",
        "finbert",
        "daily_aggregate",
        "crypto_daily_sentiment_upsert",
    ]
    assert [row.id for row in upserted_rows] == [
        "BTC/USD:2026-04-24",
        "BTC/USD:2026-04-25",
        "XDG/USD:2026-04-24",
        "XDG/USD:2026-04-25",
    ]
    assert upserted_rows[0].compound_score == 0.60
    assert upserted_rows[0].article_count == 1
    assert upserted_rows[1].compound_score is None
    assert upserted_rows[1].article_count == 0
    assert upserted_rows[2].compound_score is None
    assert upserted_rows[2].article_count == 0
    assert upserted_rows[2].coverage_score == 0.0


async def test_backfill_historical_crypto_sentiment_does_not_write_failed_windows(
    monkeypatch: MonkeyPatch,
) -> None:
    """Provider failures must not overwrite existing rows with empty sentiment."""

    from app.tasks.news_sentiment import backfill_historical_crypto_sentiment

    upserted_rows: list[CryptoDailySentimentRow] = []

    class FakeResearchRepository:
        def __init__(self, session: object) -> None:
            self.session = session

        async def upsert_crypto_daily_sentiment(
            self,
            row: CryptoDailySentimentRow,
        ) -> CryptoDailySentimentRow:
            upserted_rows.append(row)
            return row

    monkeypatch.setattr("app.tasks.news_sentiment.ResearchRepository", FakeResearchRepository)

    result = await backfill_historical_crypto_sentiment(
        symbols=["BTC/USD"],
        start_date="2026-04-24",
        end_date="2026-04-24",
        client=FailingHistoricalClient(),
        session_factory=fake_session_factory,
        scorer=FakeCryptoSentimentScorer(),
    )

    assert result["status"] == "completed_with_errors"
    assert result["rows_upserted"] == 0
    assert result["failed_window_count"] == 1
    assert upserted_rows == []
