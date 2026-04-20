"""Phase 2 research orchestration for manual and API-driven runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.repositories.research import ResearchRepository
from app.repositories.watchlist import WatchlistRepository
from app.research.analyst import AnalystRatingsService
from app.research.congress import CongressTradingService
from app.research.insider import InsiderTradingService
from app.research.models import (
    AnalystRating,
    CongressTrade,
    InsiderTrade,
    NewsArticle,
    ResearchScoreBreakdown,
    ScreeningMetrics,
    WatchlistCandidate,
)
from app.research.news_sentiment import NewsSentimentPipeline
from app.research.scorer import WatchlistScorer
from app.research.screener import StockScreenerService
from app.research.watchlist_manager import WatchlistManager


@dataclass(slots=True, frozen=True)
class ResearchOrchestrationResult:
    """Summary produced by one research run."""

    symbols_scored: list[str]
    promoted_symbols: list[str]
    demoted_symbols: list[str]
    persisted_signal_count: int
    breakdowns: list[ResearchScoreBreakdown]


class ResearchOrchestrator:
    """Coordinate research ingestion, scoring, and watchlist promotion."""

    def __init__(
        self,
        research_repository: ResearchRepository,
        watchlist_repository: WatchlistRepository,
        news_pipeline: NewsSentimentPipeline | None = None,
        screener_service: StockScreenerService | None = None,
        scorer: WatchlistScorer | None = None,
    ) -> None:
        self.research_repository = research_repository
        self.watchlist_repository = watchlist_repository
        self.news_pipeline = news_pipeline or NewsSentimentPipeline()
        self.screener_service = screener_service or StockScreenerService()
        self.scorer = scorer or WatchlistScorer()
        self.watchlist_manager = WatchlistManager(watchlist_repository, self.scorer)

    async def run_manual_research(
        self,
        *,
        news_articles: Sequence[NewsArticle] = (),
        congress_trades: Sequence[CongressTrade] = (),
        insider_trades: Sequence[InsiderTrade] = (),
        screener_metrics: Sequence[ScreeningMetrics] = (),
        analyst_ratings: Sequence[AnalystRating] = (),
        seed_symbols: Sequence[str] = (),
    ) -> ResearchOrchestrationResult:
        """Persist supplied research artifacts and update the watchlist."""

        persisted_signal_count = 0

        if news_articles:
            persisted_signal_count += len(
                await self.news_pipeline.persist_articles(self.research_repository, news_articles)
            )

        if congress_trades:
            congress_service = CongressTradingService(
                repository=self.research_repository,
                house_base_url="https://housestockwatcher.com/api",
                senate_base_url="https://senatestockwatcher.com/api",
            )
            for congress_trade in congress_trades:
                congress_row = congress_service._row_from_trade(congress_trade)
                await self.research_repository.add_congress_trade(congress_row)
                await self.research_repository.add_signal(
                    congress_service._build_signal_row(congress_trade)
                )
                persisted_signal_count += 1

        if insider_trades:
            insider_service = InsiderTradingService(
                repository=self.research_repository,
                base_url="https://api.secfilingdata.com",
            )
            for insider_trade in insider_trades:
                insider_row = insider_service._row_from_trade(insider_trade)
                await self.research_repository.add_insider_trade(insider_row)
                await self.research_repository.add_signal(
                    insider_service._build_signal_row(insider_trade)
                )
                persisted_signal_count += 1

        if screener_metrics:
            for metrics in screener_metrics:
                signal = self.screener_service.build_signal_row(metrics)
                await self.research_repository.add_signal(signal)
                persisted_signal_count += 1

        if analyst_ratings:
            analyst_service = AnalystRatingsService(
                repository=self.research_repository,
                base_url="https://api.benzinga.com/api/v2",
            )
            persisted_signal_count += len(await analyst_service.persist_ratings(analyst_ratings))

        active_symbols = [row.symbol for row in await self.watchlist_repository.list_active()]
        recent_symbols = await self.research_repository.list_recent_symbols()
        all_symbols = [*seed_symbols, *active_symbols, *recent_symbols]
        symbols = sorted({symbol.upper() for symbol in all_symbols})

        breakdowns = [await self._build_breakdown(symbol) for symbol in symbols]
        promoted_symbols: list[str] = []
        for breakdown in breakdowns:
            candidate = WatchlistCandidate(
                symbol=breakdown.symbol,
                asset_class="stock",
                breakdown=breakdown,
                added_by="phase2_research",
            )
            if await self.watchlist_manager.promote_candidate(candidate):
                promoted_symbols.append(candidate.symbol)

        demotion_symbols = [breakdown.symbol for breakdown in breakdowns]
        demoted_symbols = await self.watchlist_manager.demote_stale_symbols(demotion_symbols)

        return ResearchOrchestrationResult(
            symbols_scored=[breakdown.symbol for breakdown in breakdowns],
            promoted_symbols=promoted_symbols,
            demoted_symbols=demoted_symbols,
            persisted_signal_count=persisted_signal_count,
            breakdowns=self.scorer.rank_breakdowns(breakdowns),
        )

    async def _build_breakdown(self, symbol: str) -> ResearchScoreBreakdown:
        """Build a composite breakdown from persisted signals for one symbol."""

        signals = await self.research_repository.list_signals(symbol, limit=200)
        typed_scores: dict[str, list[float]] = {}
        for signal in signals:
            if signal.score is None:
                continue
            typed_scores.setdefault(signal.signal_type, []).append(float(signal.score))

        def latest_score(signal_type: str) -> float:
            values = typed_scores.get(signal_type, [])
            return values[0] if values else 0.0

        def average_score(signal_type: str) -> float:
            values = typed_scores.get(signal_type, [])
            return sum(values) / len(values) if values else 0.0

        return self.scorer.score_breakdown(
            symbol=symbol.upper(),
            news_sentiment_7d=average_score("news_sentiment"),
            congress_buy=latest_score("congress_buy"),
            insider_buy=latest_score("insider_buy"),
            screener_pass=latest_score("screener"),
            analyst_upgrade=latest_score("analyst_upgrade"),
        )
