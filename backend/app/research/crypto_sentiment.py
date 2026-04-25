"""Crypto news sentiment scoring and daily aggregation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from app.db.models import CryptoDailySentimentRow
from app.research.rss_client import RssArticle

POSITIVE_TERMS: frozenset[str] = frozenset(
    {
        "adoption",
        "approval",
        "bullish",
        "breakout",
        "growth",
        "inflow",
        "inflows",
        "rally",
        "record",
        "upgrade",
    }
)
NEGATIVE_TERMS: frozenset[str] = frozenset(
    {
        "bearish",
        "crackdown",
        "decline",
        "downgrade",
        "exploit",
        "hack",
        "lawsuit",
        "outflow",
        "outflows",
        "selloff",
    }
)


@dataclass(frozen=True, slots=True)
class CryptoArticleSentiment:
    """Sentiment probabilities for one prepared crypto article."""

    positive_score: float
    neutral_score: float
    negative_score: float
    compound_score: float
    source: str


@dataclass(frozen=True, slots=True)
class CryptoDailySentimentAggregate:
    """Daily aggregate sentiment for one canonical crypto symbol."""

    symbol: str
    sentiment_date: date
    source_count: int
    article_count: int
    positive_score: float | None
    neutral_score: float | None
    negative_score: float | None
    compound_score: float | None
    coverage_score: float


class CryptoArticleSentimentScorer(Protocol):
    """Contract for FinBERT-compatible article sentiment scorers."""

    async def score_article(self, article: RssArticle) -> CryptoArticleSentiment:
        """Return sentiment probabilities for one prepared article."""


class LexiconCryptoSentimentScorer:
    """Deterministic fallback scorer until the FinBERT runtime dependency is added."""

    async def score_article(self, article: RssArticle) -> CryptoArticleSentiment:
        """Score an article with a small finance/crypto term lexicon."""

        text = f"{article.title} {article.summary}".lower()
        positive_hits = _count_term_hits(text, POSITIVE_TERMS)
        negative_hits = _count_term_hits(text, NEGATIVE_TERMS)

        positive_raw = 1.0 + float(positive_hits)
        negative_raw = 1.0 + float(negative_hits)
        neutral_raw = 1.0
        total = positive_raw + neutral_raw + negative_raw
        positive = positive_raw / total
        neutral = neutral_raw / total
        negative = negative_raw / total
        return CryptoArticleSentiment(
            positive_score=positive,
            neutral_score=neutral,
            negative_score=negative,
            compound_score=positive - negative,
            source=article.source,
        )


async def build_daily_crypto_sentiment_aggregate(
    *,
    symbol: str,
    sentiment_date: date,
    articles: Sequence[RssArticle],
    scorer: CryptoArticleSentimentScorer | None = None,
) -> CryptoDailySentimentAggregate:
    """Score prepared articles and aggregate them into one daily symbol value."""

    if not articles:
        return CryptoDailySentimentAggregate(
            symbol=symbol.upper(),
            sentiment_date=sentiment_date,
            source_count=0,
            article_count=0,
            positive_score=None,
            neutral_score=None,
            negative_score=None,
            compound_score=None,
            coverage_score=0.0,
        )

    active_scorer = scorer or LexiconCryptoSentimentScorer()
    article_scores = [await active_scorer.score_article(article) for article in articles]
    article_count = len(article_scores)
    source_count = len({score.source for score in article_scores})
    return CryptoDailySentimentAggregate(
        symbol=symbol.upper(),
        sentiment_date=sentiment_date,
        source_count=source_count,
        article_count=article_count,
        positive_score=_average(score.positive_score for score in article_scores),
        neutral_score=_average(score.neutral_score for score in article_scores),
        negative_score=_average(score.negative_score for score in article_scores),
        compound_score=_average(score.compound_score for score in article_scores),
        coverage_score=_coverage_score(article_count=article_count, source_count=source_count),
    )


def build_crypto_daily_sentiment_row(
    aggregate: CryptoDailySentimentAggregate,
    *,
    now: datetime | None = None,
) -> CryptoDailySentimentRow:
    """Convert a crypto sentiment aggregate into its persistence row."""

    timestamp = now or datetime.now(tz=UTC)
    return CryptoDailySentimentRow(
        id=f"{aggregate.symbol}:{aggregate.sentiment_date.isoformat()}",
        symbol=aggregate.symbol,
        asset_class="crypto",
        sentiment_date=aggregate.sentiment_date,
        source_count=aggregate.source_count,
        article_count=aggregate.article_count,
        positive_score=aggregate.positive_score,
        neutral_score=aggregate.neutral_score,
        negative_score=aggregate.negative_score,
        compound_score=aggregate.compound_score,
        coverage_score=aggregate.coverage_score,
        created_at=timestamp,
        updated_at=timestamp,
    )


def aggregate_to_summary(aggregate: CryptoDailySentimentAggregate) -> Mapping[str, object]:
    """Return a task-safe summary without article text."""

    return {
        "symbol": aggregate.symbol,
        "sentiment_date": aggregate.sentiment_date.isoformat(),
        "source_count": aggregate.source_count,
        "article_count": aggregate.article_count,
        "positive_score": aggregate.positive_score,
        "neutral_score": aggregate.neutral_score,
        "negative_score": aggregate.negative_score,
        "compound_score": aggregate.compound_score,
        "coverage_score": aggregate.coverage_score,
    }


def _count_term_hits(text: str, terms: frozenset[str]) -> int:
    return sum(1 for term in terms if term in text)


def _average(values: Iterable[float]) -> float:
    value_list = tuple(values)
    return sum(value_list) / len(value_list)




def _coverage_score(*, article_count: int, source_count: int) -> float:
    article_component = min(float(article_count) / 5.0, 1.0)
    source_component = min(float(source_count) / 2.0, 1.0)
    return round((article_component * 0.7) + (source_component * 0.3), 4)
