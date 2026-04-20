"""Repository for research signal tables."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CongressTradeRow, InsiderTradeRow, ResearchSignalRow
from app.repositories.base import BaseRepository


class ResearchRepository(BaseRepository):
    """Access universe research records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_signals(self, symbol: str) -> list[ResearchSignalRow]:
        """Return research signals for a symbol."""

        statement = select(ResearchSignalRow).where(ResearchSignalRow.symbol == symbol)
        result = await self.session.scalars(statement)
        return list(result)

    async def list_congress_trades(self, symbol: str) -> list[CongressTradeRow]:
        """Return congress trades for a symbol."""

        statement = select(CongressTradeRow).where(CongressTradeRow.symbol == symbol)
        result = await self.session.scalars(statement)
        return list(result)

    async def list_insider_trades(self, symbol: str) -> list[InsiderTradeRow]:
        """Return insider trades for a symbol."""

        statement = select(InsiderTradeRow).where(InsiderTradeRow.symbol == symbol)
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
