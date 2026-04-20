"""Repository for research signal tables."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CongressTradeRow, InsiderTradeRow, ResearchSignalRow
from app.repositories.base import BaseRepository


class ResearchRepository(BaseRepository):
    """Access universe research records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_signals(
        self,
        symbol: str,
        *,
        signal_type: str | None = None,
        limit: int = 100,
    ) -> list[ResearchSignalRow]:
        """Return research signals for a symbol sorted newest first."""

        statement = select(ResearchSignalRow).where(ResearchSignalRow.symbol == symbol.upper())
        if signal_type is not None:
            statement = statement.where(ResearchSignalRow.signal_type == signal_type)
        statement = statement.order_by(ResearchSignalRow.created_at.desc()).limit(limit)
        result = await self.session.scalars(statement)
        return list(result)

    async def list_congress_trades(self, symbol: str, *, limit: int = 50) -> list[CongressTradeRow]:
        """Return congress trades for a symbol sorted newest first."""

        statement = (
            select(CongressTradeRow)
            .where(CongressTradeRow.symbol == symbol.upper())
            .order_by(CongressTradeRow.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def list_insider_trades(self, symbol: str, *, limit: int = 50) -> list[InsiderTradeRow]:
        """Return insider trades for a symbol sorted newest first."""

        statement = (
            select(InsiderTradeRow)
            .where(InsiderTradeRow.symbol == symbol.upper())
            .order_by(InsiderTradeRow.created_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def list_recent_symbols(self, *, limit: int = 200) -> list[str]:
        """Return distinct symbols that have recent research activity."""

        statement = (
            select(ResearchSignalRow.symbol)
            .distinct()
            .order_by(ResearchSignalRow.symbol)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def add_signal(self, row: ResearchSignalRow) -> None:
        """Persist a research signal."""

        await self.add(row)

    async def add_congress_trade(self, row: CongressTradeRow) -> None:
        """Persist a congressional trade disclosure."""

        await self.add(row)

    async def add_insider_trade(self, row: InsiderTradeRow) -> None:
        """Persist an insider trade disclosure."""

        await self.add(row)
