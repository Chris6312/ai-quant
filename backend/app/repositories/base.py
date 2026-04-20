"""Base repository abstractions."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import ColumnElement

from app.db.base import Base
from app.exceptions import RepositoryError


class BaseRepository:
    """Shared helpers for repository implementations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, row: Base) -> None:
        """Add a single ORM row."""

        try:
            self.session.add(row)
            await self.session.commit()
        except Exception as exc:  # pragma: no cover - defensive boundary
            await self.session.rollback()
            raise RepositoryError("Unable to add row") from exc

    async def add_all(self, rows: Sequence[Base]) -> None:
        """Add multiple ORM rows."""

        try:
            self.session.add_all(list(rows))
            await self.session.commit()
        except Exception as exc:  # pragma: no cover - defensive boundary
            await self.session.rollback()
            raise RepositoryError("Unable to add rows") from exc

    async def execute(self, statement: Executable) -> Result[tuple[object]]:
        """Execute a SQLAlchemy statement and return the result."""

        try:
            return await self.session.execute(statement)
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise RepositoryError("Unable to execute statement") from exc

    async def scalar_one_or_none(self, statement: Executable) -> object | None:
        """Return a scalar result or None."""

        result = await self.execute(statement)
        return result.scalar_one_or_none()

    async def list_all(self, model: type[Base]) -> list[Base]:
        """Load all rows for a model."""

        result = await self.execute(select(model))
        return list(result.scalars().all())

    async def get_latest_timestamp(
        self,
        model: type[Base],
        column: ColumnElement[datetime],
    ) -> datetime | None:
        """Return the latest timestamp from a model column."""

        result = await self.execute(select(column).order_by(column.desc()).limit(1))
        return result.scalar_one_or_none()
