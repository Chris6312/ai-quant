"""Analyst upgrade ingestion and scoring."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

import httpx  # NEW DEP: httpx — reason: async research API clients for Phase 2

from app.db.models import ResearchSignalRow
from app.exceptions import ResearchAPIError, ResearchParseError
from app.repositories.research import ResearchRepository
from app.research.models import AnalystRating, utc_now

TOP_TIER_FIRMS: set[str] = {"Goldman", "Morgan Stanley", "JPM"}


class AnalystRatingsService:
    """Ingest analyst upgrades and price-target changes."""

    def __init__(
        self,
        repository: ResearchRepository,
        base_url: str,
        timeout_s: float = 10.0,
    ) -> None:
        self.repository = repository
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def sync_ratings(self) -> list[ResearchSignalRow]:
        """Fetch and persist analyst ratings."""

        payload = await self._fetch_payload()
        signals: list[ResearchSignalRow] = []
        for item in payload:
            rating = self._parse_rating(item)
            signal = self._build_signal_row(rating)
            await self.repository.add_signal(signal)
            signals.append(signal)
        return signals

    async def _fetch_payload(self) -> list[Mapping[str, object]]:
        """Fetch ratings from an HTTP API."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.get(f"{self.base_url}/ratings")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResearchAPIError("Unable to fetch analyst ratings") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchParseError("Analyst payload is not valid JSON") from exc
        if not isinstance(payload, list):
            raise ResearchParseError("Analyst payload must be a list")
        return payload

    def score_rating(self, rating: AnalystRating) -> float:
        """Return a normalized analyst score."""

        action = rating.action.lower()
        if action not in {"upgrade", "initiation", "raise"}:
            return 0.0
        score = 0.5
        if rating.firm in TOP_TIER_FIRMS:
            score = 0.9
        if (
            rating.old_price_target is not None
            and rating.new_price_target is not None
            and rating.old_price_target > 0.0
        ):
            raise_ratio = (
                rating.new_price_target - rating.old_price_target
            ) / rating.old_price_target
            if raise_ratio >= 0.15:
                score = max(score, 0.7)
        if rating.old_price_target is not None and rating.old_price_target > 0.0:
            distance_ratio = (
                abs(rating.current_price - rating.old_price_target)
                / rating.old_price_target
            )
            if distance_ratio > 0.10:
                return 0.0
        return min(1.0, score)

    def _build_signal_row(self, rating: AnalystRating) -> ResearchSignalRow:
        """Build a research signal row from an analyst rating."""

        score = self.score_rating(rating)
        return ResearchSignalRow(
            id=str(uuid4()),
            symbol=rating.symbol,
            signal_type="analyst_upgrade",
            score=score,
            direction="bullish" if score > 0 else "neutral",
            source=rating.firm,
            raw_data={
                "action": rating.action,
                "rating": rating.rating,
                "current_price": rating.current_price,
                "old_price_target": rating.old_price_target,
                "new_price_target": rating.new_price_target,
            },
            created_at=utc_now(),
        )

    def _parse_rating(self, item: Mapping[str, object]) -> AnalystRating:
        """Parse one rating payload."""

        symbol = str(item.get("symbol", "")).upper()
        firm = str(item.get("firm", ""))
        action = str(item.get("action", ""))
        rating = str(item.get("rating", ""))
        current_price = float(item.get("current_price", 0.0))
        old_price_target = self._parse_float(item.get("old_price_target"))
        new_price_target = self._parse_float(item.get("new_price_target"))
        published_at = self._parse_datetime(item.get("published_at"))
        return AnalystRating(
            symbol=symbol,
            firm=firm,
            action=action,
            current_price=current_price,
            old_price_target=old_price_target,
            new_price_target=new_price_target,
            rating=rating,
            published_at=published_at,
        )

    def _parse_float(self, value: object) -> float | None:
        """Parse an optional numeric payload value."""

        if value is None:
            return None
        return float(value)

    def _parse_datetime(self, value: object) -> datetime:
        """Parse a datetime payload value."""

        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        raise ResearchParseError("Invalid analyst datetime value")
