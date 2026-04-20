"""Async database session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the async SQLAlchemy engine."""

    return create_async_engine(
        settings.database_url,
        echo=settings.enable_sql_echo,
        pool_pre_ping=True,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to the engine."""

    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield a database session for request handlers."""

    async with session_factory() as session:
        yield session
