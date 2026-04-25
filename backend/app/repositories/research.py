"""Repository for research signal tables."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CongressTradeRow,
    CryptoDailySentimentRow,
    InsiderTradeRow,
    ResearchSignalRow,
)
from app.repositories.base import BaseRepository


class ResearchRepository(BaseRepository):
    """Access universe research records."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def list_signals(self, symbol: str, *, limit: int = 50) -> list[ResearchSignalRow]:
        """Return research signals for a symbol sorted newest first."""

        statement = (
            select(ResearchSignalRow)
            .where(ResearchSignalRow.symbol == symbol.upper())
            .order_by(ResearchSignalRow.created_at.desc())
            .limit(limit)
        )
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

    async def get_crypto_daily_sentiment(
        self,
        symbol: str,
        sentiment_date: date,
    ) -> CryptoDailySentimentRow | None:
        """Return daily crypto sentiment for a canonical symbol and date."""

        statement = select(CryptoDailySentimentRow).where(
            CryptoDailySentimentRow.symbol == symbol.upper(),
            CryptoDailySentimentRow.asset_class == "crypto",
            CryptoDailySentimentRow.sentiment_date == sentiment_date,
        )
        result = await self.session.scalars(statement)
        return result.first()

    async def list_crypto_daily_sentiment(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 30,
    ) -> list[CryptoDailySentimentRow]:
        """Return daily crypto sentiment rows for a canonical symbol."""

        statement = select(CryptoDailySentimentRow).where(
            CryptoDailySentimentRow.symbol == symbol.upper(),
            CryptoDailySentimentRow.asset_class == "crypto",
        )
        if start_date is not None:
            statement = statement.where(CryptoDailySentimentRow.sentiment_date >= start_date)
        if end_date is not None:
            statement = statement.where(CryptoDailySentimentRow.sentiment_date <= end_date)

        statement = statement.order_by(CryptoDailySentimentRow.sentiment_date.desc()).limit(limit)
        result = await self.session.scalars(statement)
        return list(result)

    async def upsert_crypto_daily_sentiment(
        self,
        row: CryptoDailySentimentRow,
    ) -> CryptoDailySentimentRow:
        """Create or replace a daily crypto sentiment aggregate."""

        existing = await self.get_crypto_daily_sentiment(row.symbol, row.sentiment_date)
        if existing is None:
            await self.add(row)
            return row

        existing.source_count = row.source_count
        existing.article_count = row.article_count
        existing.positive_score = row.positive_score
        existing.neutral_score = row.neutral_score
        existing.negative_score = row.negative_score
        existing.compound_score = row.compound_score
        existing.coverage_score = row.coverage_score
        await self.session.commit()
        return existing

    async def add_signal(self, row: ResearchSignalRow) -> None:
        """Persist a research signal."""

        await self.add(row)

    async def add_congress_trade(self, row: CongressTradeRow) -> None:
        """Persist a congressional trade disclosure."""

        await self.add(row)

    async def add_insider_trade(self, row: InsiderTradeRow) -> None:
        """Persist an insider trade disclosure."""

        await self.add(row)