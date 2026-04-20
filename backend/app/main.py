"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.admin import router as admin_router
from app.api.routers.candles import router as candles_router
from app.api.routers.config import router as config_router
from app.api.routers.health import router as health_router
from app.api.routers.ml import router as ml_router
from app.api.routers.orders import router as orders_router
from app.api.routers.paper import router as paper_router
from app.api.routers.watchlist import router as watchlist_router
from app.config.constants import APP_NAME, APP_VERSION
from app.config.settings import get_settings
from app.core.logging import configure_logging


def _load_instrumentator() -> type[object]:
    """Load the Prometheus instrumentator or a no-op fallback."""

    try:
        from prometheus_fastapi_instrumentator import Instrumentator
    except ImportError:
        class Instrumentator:
            """No-op fallback when the Prometheus instrumentator package is unavailable."""

            def instrument(self, app: FastAPI) -> "Instrumentator":
                return self

            def expose(self, app: FastAPI, endpoint: str) -> None:
                return None

    return Instrumentator


Instrumentator = _load_instrumentator()


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

    # CORS — allow Vite dev server on port 5173
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")
    app.include_router(health_router)
    app.include_router(candles_router)
    app.include_router(admin_router)
    app.include_router(watchlist_router)
    app.include_router(paper_router)
    app.include_router(ml_router)
    app.include_router(orders_router)
    app.include_router(config_router)
    app.state.settings = settings
    return app


app = create_app()
