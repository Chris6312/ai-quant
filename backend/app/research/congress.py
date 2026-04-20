"""Congressional trading ingestion and scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from uuid import uuid4

import httpx  # NEW DEP: httpx — reason: async research API clients for Phase 2

from app.config.constants import CONGRESS_PROMOTION_THRESHOLD
from app.db.models import CongressTradeRow, ResearchSignalRow
from app.exceptions import ResearchAPIError, ResearchParseError
from app.repositories.research import ResearchRepository
from app.research.models import CongressTrade, utc_now

COMMITTEE_SECTOR_MAP: dict[str, list[str]] = {
    "Armed Services": ["LMT", "RTX", "NOC", "GD", "BA"],
    "Energy and Commerce": ["XOM", "CVX", "COP", "SLB"],
    "Financial Services": ["JPM", "GS", "BAC", "MS", "C"],
    "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL"],
    "Health": ["UNH", "JNJ", "PFE", "ABBV"],
}


class CongressTradingService:
    """Ingest congressional trades and derive signals from them."""

    def __init__(
        self,
        repository: ResearchRepository,
        house_base_url: str,
        senate_base_url: str,
        timeout_s: float = 10.0,
    ) -> None:
        self.repository = repository
        self.house_base_url = house_base_url.rstrip("/")
        self.senate_base_url = senate_base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def sync_house_trades(self) -> list[CongressTradeRow]:
        """Fetch and persist house disclosures."""

        payload = await self._fetch_payload(self.house_base_url)
        return await self._persist_trades(payload, chamber="house")

    async def sync_senate_trades(self) -> list[CongressTradeRow]:
        """Fetch and persist senate disclosures."""

        payload = await self._fetch_payload(self.senate_base_url)
        return await self._persist_trades(payload, chamber="senate")

    async def _fetch_payload(self, base_url: str) -> list[Mapping[str, object]]:
        """Fetch a list of trade payloads from an HTTP API."""

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.get(f"{base_url}/disclosures")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ResearchAPIError("Unable to fetch congressional disclosures") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResearchParseError("Congress payload is not valid JSON") from exc
        if not isinstance(payload, list):
            raise ResearchParseError("Congress payload must be a list")
        return payload

    async def _persist_trades(
        self,
        payload: Sequence[Mapping[str, object]],
        chamber: str,
    ) -> list[CongressTradeRow]:
        """Persist trades and corresponding signals."""

        rows: list[CongressTradeRow] = []
        for item in payload:
            trade = self._parse_trade(item, chamber)
            row = self._row_from_trade(trade)
            await self.repository.add_congress_trade(row)
            rows.append(row)
            await self.repository.add_signal(self._build_signal_row(trade))
        return rows

    def _row_from_trade(self, trade: CongressTrade) -> CongressTradeRow:
        """Build an ORM row from a parsed congressional trade."""

        return CongressTradeRow(
            id=str(uuid4()),
            politician=trade.politician,
            chamber=trade.chamber,
            symbol=trade.symbol,
            trade_type=trade.trade_type,
            amount_range=trade.amount_range,
            trade_date=trade.trade_date,
            disclosure_date=trade.disclosure_date,
            days_to_disclose=trade.days_to_disclose,
            created_at=utc_now(),
        )

    def score_trade(self, trade: CongressTrade, politician_committees: Sequence[str]) -> float:
        """Score one congressional trade."""

        base = 0.5 if trade.trade_type == "purchase" else -0.5
        recency = max(0.0, 1 - (trade.days_to_disclose / 45))
        relevance = 1.0 if any(
            trade.symbol in COMMITTEE_SECTOR_MAP.get(committee, [])
            for committee in politician_committees
        ) else 0.6
        return base * recency * relevance

    def _parse_trade(self, item: Mapping[str, object], chamber: str) -> CongressTrade:
        """Parse one trade disclosure payload."""

        symbol = str(item.get("symbol", "")).upper()
        trade_type = str(item.get("trade_type", "")).lower()
        politician = str(item.get("politician", ""))
        committee = item.get("committee")
        committee_value = str(committee) if committee is not None else None
        amount_range = item.get("amount_range")
        amount_value = str(amount_range) if amount_range is not None else None
        days_to_disclose_raw = item.get("days_to_disclose", 45)
        if not isinstance(days_to_disclose_raw, (int, str)):
            raise ResearchParseError("Invalid congress days_to_disclose")
        days_to_disclose = int(days_to_disclose_raw)
        trade_date = self._parse_date(item.get("trade_date"))
        disclosure_date = self._parse_date(item.get("disclosure_date"))
        return CongressTrade(
            symbol=symbol,
            trade_type=trade_type,
            chamber=chamber,
            days_to_disclose=days_to_disclose,
            politician=politician,
            committee=committee_value,
            amount_range=amount_value,
            trade_date=trade_date,
            disclosure_date=disclosure_date,
        )

    def _build_signal_row(self, trade: CongressTrade) -> ResearchSignalRow:
        """Build a research signal row from a trade."""

        score = self.score_trade(trade, [trade.committee] if trade.committee is not None else [])
        direction = "bullish" if score >= 0 else "bearish"
        return ResearchSignalRow(
            id=str(uuid4()),
            symbol=trade.symbol,
            signal_type="congress_buy",
            score=score,
            direction=direction,
            source="house_stock_watcher" if trade.chamber == "house" else "senate_stock_watcher",
            raw_data={
                "politician": trade.politician,
                "committee": trade.committee,
                "amount_range": trade.amount_range,
                "trade_type": trade.trade_type,
            },
            created_at=utc_now(),
        )

    def _parse_date(self, value: object) -> date | None:
        """Parse a date-like payload value."""

        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        raise ResearchParseError("Invalid congress date value")

    def should_promote(self, trade: CongressTrade, politician_committees: Sequence[str]) -> bool:
        """Return True when the trade crosses the promotion threshold."""

        return self.score_trade(trade, politician_committees) >= CONGRESS_PROMOTION_THRESHOLD
