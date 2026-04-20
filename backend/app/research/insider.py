"""Insider filing ingestion and scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from uuid import uuid4

import httpx  # NEW DEP: httpx — reason: async research API clients for Phase 2

from app.config.constants import INSIDER_PROMOTION_THRESHOLD, MIN_INSIDER_PURCHASE_VALUE
from app.db.models import InsiderTradeRow, ResearchSignalRow
from app.exceptions import ResearchAPIError, ResearchParseError
from app.repositories.research import ResearchRepository
from app.research.models import InsiderTrade, utc_now

TITLE_WEIGHTS: dict[str, float] = {
    "CEO": 1.0,
    "CFO": 0.9,
    "Director": 0.7,
    "10% Owner": 0.6,
}


class InsiderTradingService:
    """Ingest SEC Form 4 filings and derive signals from them."""

    def __init__(
        self,
        repository: ResearchRepository,
        base_url: str,
        timeout_s: float = 10.0,
    ) -> None:
        self.repository = repository
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def sync_filings(self) -> list[InsiderTradeRow]:
        """Fetch and persist insider filings."""

        payload = await self._fetch_payload()
        return await self._persist_filings(payload)

    async def _fetch_payload(self) -> list[Mapping[str, object]]:
        """Fetch the raw insider payload from an HTTP API."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.get(f"{self.base_url}/form4")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResearchAPIError("Unable to fetch insider filings") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchParseError("Insider payload is not valid JSON") from exc
        if not isinstance(payload, list):
            raise ResearchParseError("Insider payload must be a list")
        return payload

    async def _persist_filings(
        self,
        payload: Sequence[Mapping[str, object]],
    ) -> list[InsiderTradeRow]:
        """Persist filings and corresponding signals."""

        rows: list[InsiderTradeRow] = []
        for item in payload:
            filing = self._parse_trade(item)
            row = self._row_from_trade(filing)
            await self.repository.add_insider_trade(row)
            rows.append(row)
            await self.repository.add_signal(self._build_signal_row(filing))
        return rows

    def _row_from_trade(self, trade: InsiderTrade) -> InsiderTradeRow:
        """Build an ORM row from a parsed insider trade."""

        return InsiderTradeRow(
            id=str(uuid4()),
            symbol=trade.symbol,
            insider_name=trade.insider_name,
            title=trade.title,
            transaction_type=trade.transaction_type,
            shares=None,
            price_per_share=None,
            total_value=trade.total_value,
            filing_date=trade.filing_date,
            transaction_date=trade.transaction_date,
            created_at=utc_now(),
        )

    def score_trade(self, trade: InsiderTrade) -> float:
        """Return a normalized insider buy score."""

        if trade.transaction_type != "P":
            return 0.0
        title_key = trade.title or ""
        weight = TITLE_WEIGHTS.get(title_key, 0.5)
        size_bonus = min(1.0, trade.total_value / (MIN_INSIDER_PURCHASE_VALUE * 2))
        return weight * size_bonus

    def should_promote(self, trade: InsiderTrade) -> bool:
        """Return True when the trade crosses the promotion threshold."""

        return self.score_trade(trade) >= INSIDER_PROMOTION_THRESHOLD

    def _build_signal_row(self, trade: InsiderTrade) -> ResearchSignalRow:
        """Build a research signal row from an insider filing."""

        score = self.score_trade(trade)
        direction = "bullish" if score > 0 else "neutral"
        return ResearchSignalRow(
            id=str(uuid4()),
            symbol=trade.symbol,
            signal_type="insider_buy",
            score=score,
            direction=direction,
            source="sec_edgar",
            raw_data={
                "insider_name": trade.insider_name,
                "title": trade.title,
                "transaction_type": trade.transaction_type,
                "total_value": trade.total_value,
            },
            created_at=utc_now(),
        )

    def _parse_trade(self, item: Mapping[str, object]) -> InsiderTrade:
        """Parse one filing payload."""

        symbol = str(item.get("symbol", "")).upper()
        insider_name = str(item.get("insider_name", ""))
        title_raw = item.get("title")
        title = str(title_raw) if title_raw is not None else None
        transaction_type = str(item.get("transaction_type", "")).upper()
        total_value_raw = item.get("total_value", 0.0)
        if not isinstance(total_value_raw, (int, float, str)):
            raise ResearchParseError("Invalid insider total_value")
        total_value = float(total_value_raw)
        filing_date = self._parse_date(item.get("filing_date"))
        transaction_date = self._parse_date(item.get("transaction_date"))
        return InsiderTrade(
            symbol=symbol,
            insider_name=insider_name,
            title=title,
            transaction_type=transaction_type,
            total_value=total_value,
            filing_date=filing_date,
            transaction_date=transaction_date,
        )

    def _parse_date(self, value: object) -> date | None:
        """Parse a date-like payload value."""

        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise ResearchParseError("Invalid insider date value")
