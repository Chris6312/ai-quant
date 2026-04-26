"""FastAPI dependencies for repositories and services."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.brokers.kraken import KrakenBroker
from app.brokers.router import BrokerRouter
from app.brokers.tradier import TradierBroker
from app.config.settings import Settings, get_settings
from app.db.session import build_engine, build_session_factory
from app.paper.ledger_repository import PaperLedgerRepository
from app.paper.ledger_service import PaperLedgerService
from app.repositories.candles import CandleRepository
from app.repositories.positions import PositionRepository
from app.repositories.research import ResearchRepository
from app.repositories.watchlist import WatchlistRepository
from app.services.direction_gate import DirectionGate
from app.services.portfolio_manager import PortfolioManager


def get_engine(settings: Annotated[Settings, Depends(get_settings)]) -> AsyncEngine:
    """Create the async database engine."""

    return build_engine(settings)


def get_session_factory(
    settings: Annotated[Settings, Depends(get_settings)],
) -> async_sessionmaker[AsyncSession]:
    """Create a session factory for request handlers."""

    engine = build_engine(settings)
    return build_session_factory(engine)


async def get_session(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[AsyncSession]:
    """Yield an async database session."""

    async with session_factory() as session:
        yield session


def get_candle_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CandleRepository:
    """Dependency for the candle repository."""

    return CandleRepository(session)


def get_watchlist_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WatchlistRepository:
    """Dependency for the watchlist repository."""

    return WatchlistRepository(session)


def get_position_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PositionRepository:
    """Dependency for the position repository."""

    return PositionRepository(session)


def get_research_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResearchRepository:
    """Dependency for the research repository."""

    return ResearchRepository(session)


def get_paper_ledger_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaperLedgerRepository:
    """Dependency for durable paper ledger persistence."""

    return PaperLedgerRepository(session)


def get_paper_ledger_service(
    repository: Annotated[PaperLedgerRepository, Depends(get_paper_ledger_repository)],
) -> PaperLedgerService:
    """Dependency for durable paper ledger orchestration."""

    return PaperLedgerService(repository)


def get_direction_gate() -> DirectionGate:
    """Dependency for the direction gate."""

    return DirectionGate()


def get_portfolio_manager(
    position_repository: Annotated[PositionRepository, Depends(get_position_repository)],
) -> PortfolioManager:
    """Dependency for the portfolio manager."""

    return PortfolioManager(position_repository)


def get_broker_router() -> BrokerRouter:
    """Create a live broker router from settings."""

    settings = get_settings()
    return BrokerRouter(
        kraken=KrakenBroker(
            api_key=getattr(settings, "kraken_api_key", None),
            api_secret=getattr(settings, "kraken_api_secret", None),
            usd_balance=0.0,
            crypto_usd_equiv=0.0,
        ),
        tradier=TradierBroker(
            token=getattr(settings, "tradier_api_key", None),
            account_id=getattr(settings, "tradier_account_id", None),
            cash_balance=0.0,
            equity=0.0,
        ),
    )
