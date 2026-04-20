"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.admin import router as admin_router
from app.api.routers.candles import router as candles_router
from app.api.routers.health import router as health_router
from app.api.routers.watchlist import router as watchlist_router
from app.config.constants import APP_NAME, APP_VERSION
from app.config.settings import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure process-wide resources for the app lifetime."""

    settings = get_settings()
    configure_logging(settings.log_level)
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(candles_router)
    app.include_router(admin_router)
    app.include_router(watchlist_router)
    app.state.settings = settings
    return app


app = create_app()
