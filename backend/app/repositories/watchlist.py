"""Repository for the active watchlist."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WatchlistRow
from app.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository):
    """Access active watchlist rows."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_active(self) -> list[WatchlistRow]:
        """Return active watchlist symbols ordered alphabetically."""

        statement = (
            select(WatchlistRow)
            .where(WatchlistRow.is_active.is_(True))
            .order_by(WatchlistRow.symbol)
        )
        result = await self.execute(statement)
        return list(result.scalars().all())

    async def upsert(self, row: WatchlistRow) -> None:
        """Insert or update a watchlist row."""

        existing = await self.session.get(WatchlistRow, row.symbol)
        if existing is None:
            self.session.add(row)
        else:
            existing.asset_class = row.asset_class
            existing.added_by = row.added_by
            existing.research_score = row.research_score
            existing.is_active = row.is_active
            existing.notes = row.notes
        await self.session.commit()
