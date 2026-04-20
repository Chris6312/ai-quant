"""News sentiment ingestion and scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

import httpx

from app.config.constants import NEWS_MIN_CONFIDENCE
from app.db.models import ResearchSignalRow
from app.exceptions import ResearchAPIError, ResearchParseError
from app.repositories.research import ResearchRepository
from app.research.models import NewsArticle, SentimentScore, utc_now


class SentimentClassifier(Protocol):
    """Define the contract for an async sentiment classifier."""

    async def classify(self, text: str) -> Mapping[str, float]:
        """Return label probabilities for a piece of text."""


class RuleBasedSentimentClassifier:
    """Fallback classifier used when FinBERT is not wired in yet."""

    async def classify(self, text: str) -> Mapping[str, float]:
        """Classify text using simple keyword heuristics."""

        lowered = text.lower()
        positive_hits = sum(word in lowered for word in ("beat", "bullish", "upgrade", "growth"))
        negative_hits = sum(word in lowered for word in ("miss", "bearish", "downgrade", "lawsuit"))
        neutral = 1.0
        positive = 1.0 + float(positive_hits)
        negative = 1.0 + float(negative_hits)
        total = positive + negative + neutral
        return {
            "positive": positive / total,
            "neutral": neutral / total,
            "negative": negative / total,
        }


class NewsSentimentPipeline:
    """Score and aggregate equity news sentiment."""

    def __init__(
        self,
        classifier: SentimentClassifier | None = None,
    ) -> None:
        self.classifier = classifier or RuleBasedSentimentClassifier()

    async def score_article(self, article: NewsArticle) -> SentimentScore:
        """Return a sentiment score for one article."""

        text = f"{article.title}. {article.summary}"[:512]
        label_scores = await self.classifier.classify(text)
        direction = max(label_scores, key=lambda label: label_scores[label])
        confidence = label_scores[direction]
        numeric = label_scores["positive"] - label_scores["negative"]
        if confidence < NEWS_MIN_CONFIDENCE:
            direction = "neutral"
            numeric = 0.0
        return SentimentScore(
            direction=direction,
            confidence=confidence,
            numeric=numeric,
            created_at=utc_now(),
        )

    async def score_articles(self, articles: Sequence[NewsArticle]) -> list[SentimentScore]:
        """Score a batch of articles sequentially."""

        return [await self.score_article(article) for article in articles]

    async def persist_articles(
        self,
        repository: ResearchRepository,
        articles: Sequence[NewsArticle],
    ) -> list[ResearchSignalRow]:
        """Score and persist a batch of news articles as research signals."""

        persisted: list[ResearchSignalRow] = []
        for article in articles:
            sentiment = await self.score_article(article)
            row = self.build_signal_row(article, sentiment)
            await repository.add_signal(row)
            persisted.append(row)
        return persisted

    def build_signal_row(
        self,
        article: NewsArticle,
        sentiment: SentimentScore,
    ) -> ResearchSignalRow:
        """Build a research signal row for one article."""

        return ResearchSignalRow(
            id=str(uuid4()),
            symbol=article.symbol.upper(),
            signal_type="news_sentiment",
            score=sentiment.numeric,
            direction=sentiment.direction,
            source=article.source,
            raw_data={
                "title": article.title,
                "summary": article.summary,
                "published_at": article.published_at.isoformat(),
                "confidence": sentiment.confidence,
            },
            created_at=sentiment.created_at,
        )

    def rolling_score(
        self,
        articles: Sequence[SentimentScore],
        decay_halflife_days: float = 3.0,
    ) -> float:
        """Return an exponentially weighted rolling sentiment score."""

        if not articles:
            return 0.0
        weights = [0.5 ** (index / decay_halflife_days) for index in range(len(articles))]
        weighted_sum = sum(
            score.numeric * weight for score, weight in zip(articles, weights, strict=True)
        )
        return float(weighted_sum / sum(weights))


class BenzingaNewsClient:
    """Fetch raw news articles from a Benzinga-style HTTP API."""

    def __init__(self, base_url: str, api_key: str, timeout_s: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def fetch_articles(self, symbol: str) -> list[NewsArticle]:
        """Fetch articles for one ticker."""

        headers = {"Authorization": f"Bearer {self.api_key}"}
        params = {"symbols": symbol}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.get(f"{self.base_url}/news", params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResearchAPIError("Unable to fetch news articles") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchParseError("News payload is not valid JSON") from exc
        return [self._parse_article(item) for item in payload]

    def _parse_article(self, item: Mapping[str, object]) -> NewsArticle:
        """Parse one article payload."""

        title = str(item.get("title", ""))
        summary = str(item.get("summary", ""))
        source = str(item.get("source", "benzinga"))
        published_raw = item.get("published_at")
        if not isinstance(published_raw, str):
            raise ResearchParseError("News article missing published_at")
        published_at = datetime.fromisoformat(published_raw)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=UTC)
        symbol = str(item.get("symbol", "")).upper()
        return NewsArticle(
            symbol=symbol,
            title=title,
            summary=summary,
            published_at=published_at,
            source=source,
        )
