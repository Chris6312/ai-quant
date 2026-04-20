"""Repository for portfolio positions."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PositionRow
from app.repositories.base import BaseRepository


class PositionRepository(BaseRepository):
    """Access position records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_open(self) -> list[PositionRow]:
        """Return all open positions."""

        statement = (
            select(PositionRow)
            .where(PositionRow.status == "open")
            .order_by(PositionRow.opened_at.desc())
        )
        result = await self.execute(statement)
        return list(result.scalars().all())

    async def count_open(self) -> int:
        """Return the number of open positions."""

        result = await self.execute(select(PositionRow.id).where(PositionRow.status == "open"))
        return len(list(result.scalars().all()))

    async def get_by_symbol(self, symbol: str) -> PositionRow | None:
        """Return the first open position for a symbol."""

        statement = select(PositionRow).where(
            and_(PositionRow.symbol == symbol, PositionRow.status == "open")
        )
        result = await self.execute(statement)
        return result.scalar_one_or_none()

    async def add_position(self, row: PositionRow) -> None:
        """Persist a new position row."""

        await self.add(row)

    async def upsert_position(self, row: PositionRow) -> None:
        """Merge a position row into the database."""

        await self.session.merge(row)
        await self.session.commit()

    async def list_all(self) -> list[PositionRow]:
        """Return all position rows."""

        result = await self.execute(select(PositionRow).order_by(PositionRow.opened_at.desc()))
        return list(result.scalars().all())
