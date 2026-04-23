"""Repository for candle persistence and reads."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast

from sqlalchemy import and_, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import ML_CANDLE_USAGE, TRADING_CANDLE_USAGE
from app.db.models import CandleRow
from app.repositories.base import BaseRepository


class CandleRepository(BaseRepository):
    """Access candles stored in TimescaleDB."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_latest_candle_time(
        self,
        symbol: str,
        timeframe: str,
        source: str | None = None,
    ) -> datetime | None:
        """Return the latest stored candle time for a symbol and timeframe."""

        conditions = [CandleRow.symbol == symbol, CandleRow.timeframe == timeframe]
        if source is not None:
            conditions.append(CandleRow.source == source)

        statement = select(func.max(CandleRow.time)).where(*conditions)
        result = await self.execute(statement)
        return cast(datetime | None, result.scalar_one_or_none())

    async def get_latest_candle_times(
        self,
        symbols: Sequence[str],
        timeframe: str,
        source: str | None = None,
    ) -> dict[str, datetime | None]:
        """Return the latest candle time per symbol for a timeframe."""

        if not symbols:
            return {}
        conditions = [CandleRow.symbol.in_(symbols), CandleRow.timeframe == timeframe]
        if source is not None:
            conditions.append(CandleRow.source == source)
        statement = (
            select(CandleRow.symbol, func.max(CandleRow.time))
            .where(*conditions)
            .group_by(CandleRow.symbol)
        )
        result = await self.execute(statement)
        latest_by_symbol: dict[str, datetime | None] = dict.fromkeys(symbols, None)
        for symbol, latest_time in result.all():
            latest_by_symbol[str(symbol)] = cast(datetime | None, latest_time)
        return latest_by_symbol

    async def bulk_upsert(self, rows: Sequence[CandleRow]) -> None:
        """Upsert candles one row at a time for the initial scaffold."""

        valid_usages = {ML_CANDLE_USAGE, TRADING_CANDLE_USAGE}
        for row in rows:
            if row.usage not in valid_usages:
                raise ValueError(
                    f"candle usage must be one of {sorted(valid_usages)}; got {row.usage!r}"
                )
            await self.session.merge(row)
        await self.session.commit()

    async def list_recent(self, symbol: str, timeframe: str, limit: int = 100) -> list[CandleRow]:
        """Return the most recent candles for a symbol and timeframe."""

        statement = (
            select(CandleRow)
            .where(and_(CandleRow.symbol == symbol, CandleRow.timeframe == timeframe))
            .order_by(CandleRow.time.desc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result)

    async def delete_symbol(self, symbol: str) -> int:
        """Delete candles for a symbol and return row count."""

        result = await self.session.execute(delete(CandleRow).where(CandleRow.symbol == symbol))
        await self.session.commit()
        cursor_result = cast(CursorResult[object], result)
        return int(cursor_result.rowcount or 0)
