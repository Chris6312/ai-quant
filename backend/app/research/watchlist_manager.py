"""Watchlist promotion and demotion orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.config.constants import (
    MAX_WATCHLIST_SIZE,
    WATCHLIST_AUTO_ADD_THRESHOLD,
    WATCHLIST_DEMOTION_DAYS,
    WATCHLIST_DEMOTION_THRESHOLD,
    WATCHLIST_PROMOTION_THRESHOLD,
)
from app.db.models import WatchlistRow
from app.repositories.watchlist import WatchlistRepository
from app.research.models import ResearchScoreBreakdown, WatchlistCandidate
from app.research.scorer import WatchlistScorer


class WatchlistManager:
    """Manage watchlist promotions and demotions."""

    def __init__(
        self,
        repository: WatchlistRepository,
        scorer: WatchlistScorer,
    ) -> None:
        self.repository = repository
        self.scorer = scorer

    async def promote_candidate(
        self,
        candidate: WatchlistCandidate,
    ) -> bool:
        """Promote a candidate if it passes the threshold and there is capacity."""

        if candidate.breakdown.composite_score < WATCHLIST_PROMOTION_THRESHOLD:
            return False
        active_rows = await self.repository.list_active()
        if len(active_rows) >= MAX_WATCHLIST_SIZE:
            lowest = min(
                active_rows,
                key=lambda row: float(row.research_score or 0.0),
            )
            if float(lowest.research_score or 0.0) >= candidate.breakdown.composite_score:
                return False
            await self.demote_symbol(lowest.symbol)
        row = WatchlistRow(
            symbol=candidate.symbol,
            asset_class=candidate.asset_class,
            research_score=candidate.breakdown.composite_score,
            added_by=candidate.added_by,
            is_active=True,
            notes=self._build_notes(candidate.breakdown),
        )
        await self.repository.upsert(row)
        return True

    async def auto_add_candidate(
        self,
        candidate: WatchlistCandidate,
    ) -> bool:
        """Auto-add a candidate when it crosses the higher threshold."""

        if candidate.breakdown.composite_score < WATCHLIST_AUTO_ADD_THRESHOLD:
            return False
        return await self.promote_candidate(candidate)

    async def demote_symbol(self, symbol: str) -> bool:
        """Deactivate a symbol on the watchlist."""

        existing = await self.repository.get_by_symbol(symbol)
        if existing is None:
            return False
        existing.is_active = False
        existing.notes = self._append_demotion_note(existing.notes)
        await self.repository.upsert(existing)
        return True

    async def demote_stale_symbols(
        self,
        symbols: Sequence[str],
    ) -> list[str]:
        """Demote symbols whose score has stayed weak for the configured window."""

        demoted: list[str] = []
        now: datetime = datetime.now(tz=UTC)
        for symbol in symbols:
            existing = await self.repository.get_by_symbol(symbol)
            if existing is None:
                continue
            research_score = float(existing.research_score or 0.0)
            if research_score >= WATCHLIST_DEMOTION_THRESHOLD:
                if existing.low_score_since is not None:
                    existing.low_score_since = None
                    await self.repository.upsert(existing)
                continue
            if existing.low_score_since is None:
                existing.low_score_since = now
                await self.repository.upsert(existing)
                continue
            days_low = (now - existing.low_score_since).days
            if days_low >= WATCHLIST_DEMOTION_DAYS and await self.demote_symbol(symbol):
                demoted.append(symbol)
        return demoted

    def _build_notes(self, breakdown: ResearchScoreBreakdown) -> str:
        """Build a compact notes string for a promoted symbol."""

        return (
            f"news={breakdown.news_sentiment_7d:.2f}; congress={breakdown.congress_buy:.2f}; "
            f"insider={breakdown.insider_buy:.2f}; screener={breakdown.screener_pass:.2f}; "
            f"analyst={breakdown.analyst_upgrade:.2f}"
        )

    def _append_demotion_note(self, notes: str | None) -> str:
        """Append a demotion note to an existing watchlist note."""

        timestamp = datetime.now(tz=UTC).isoformat()
        if notes is None or not notes:
            return f"demoted at {timestamp}"
        return f"{notes}; demoted at {timestamp}"
