"""Tests for Phase 9.1 Research macro weather visibility."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.api.routers.research import build_research_macro_sentiment_decision
from app.db.models import CryptoDailySentimentRow


class _FakeResearchRepository:
    def __init__(
        self,
        rows_by_symbol: dict[str, list[CryptoDailySentimentRow]],
    ) -> None:
        self.rows_by_symbol = rows_by_symbol
        self.calls: list[tuple[str, int]] = []

    async def list_crypto_daily_sentiment(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
    ) -> list[CryptoDailySentimentRow]:
        del start_date, end_date
        self.calls.append((symbol, limit))
        return self.rows_by_symbol.get(symbol, [])[:limit]


def _sentiment_row(
    *,
    symbol: str,
    compound_score: float,
    article_count: int,
) -> CryptoDailySentimentRow:
    return CryptoDailySentimentRow(
        id=f"{symbol}-2026-04-26",
        symbol=symbol,
        asset_class="crypto",
        sentiment_date=date(2026, 4, 26),
        source_count=2,
        article_count=article_count,
        positive_score=0.4,
        neutral_score=0.4,
        negative_score=0.2,
        compound_score=compound_score,
        coverage_score=1.0,
        created_at=datetime(2026, 4, 26, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 26, 16, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_research_macro_sentiment_reads_btc_eth_weather() -> None:
    repository = _FakeResearchRepository(
        {
            "BTC/USD": [
                _sentiment_row(
                    symbol="BTC/USD",
                    compound_score=-0.20,
                    article_count=30,
                )
            ],
            "ETH/USD": [
                _sentiment_row(
                    symbol="ETH/USD",
                    compound_score=0.10,
                    article_count=20,
                )
            ],
        }
    )

    payload = await build_research_macro_sentiment_decision(
        repository,  # type: ignore[arg-type]
        generated_at=datetime(2026, 4, 26, 21, 48, tzinfo=UTC),
    )

    assert payload["status"] == "available"
    assert payload["bias"] in {"bearish", "neutral"}
    assert payload["effect"] in {"headwind", "neutral"}
    assert payload["article_count"] == 50
    assert payload["source_symbols"] == ["BTC/USD", "ETH/USD"]
    assert payload["as_of"] == "2026-04-26T16:00:00+00:00"
    assert repository.calls == [("BTC/USD", 1), ("ETH/USD", 1)]


@pytest.mark.asyncio
async def test_research_macro_sentiment_falls_back_to_neutral_not_unknown() -> None:
    repository = _FakeResearchRepository({})

    payload = await build_research_macro_sentiment_decision(
        repository,  # type: ignore[arg-type]
        generated_at=datetime(2026, 4, 26, 21, 48, tzinfo=UTC),
    )

    assert payload["status"] == "neutral_fallback"
    assert payload["bias"] == "neutral"
    assert payload["effect"] == "neutral"
    assert payload["article_count"] == 0
    assert payload["source_symbols"] == []
    assert payload["as_of"] is None
    assert "neutral" in str(payload["reason"])
