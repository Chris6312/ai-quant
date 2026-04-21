"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.admin import router as admin_router
from app.api.routers.candles import router as candles_router
from app.api.routers.config import router as config_router
from app.api.routers.health import router as health_router
from app.api.routers.ml import router as ml_router
from app.api.routers.orders import router as orders_router
from app.api.routers.paper import router as paper_router
from app.api.routers.research import router as research_router
from app.api.routers.runtime import router as runtime_router
from app.api.routers.watchlist import router as watchlist_router
from app.config.constants import APP_NAME, APP_VERSION
from app.config.settings import get_settings
from app.core.logging import configure_logging
from app.workers.worker_health_service import WorkerHealthService
from app.workers.worker_registry import WorkerRegistry


class PrometheusFastApiInstrumentator(Protocol):
    """Protocol for the optional Prometheus instrumentator."""

    def instrument(self, app: FastAPI) -> PrometheusFastApiInstrumentator:
        """Attach instrumentation to the app."""

    def expose(self, app: FastAPI, endpoint: str) -> None:
        """Expose the metrics endpoint."""


class _NoOpInstrumentator:
    """No-op fallback when the Prometheus instrumentator package is unavailable."""

    def instrument(self, app: FastAPI) -> _NoOpInstrumentator:
        del app
        return self

    def expose(self, app: FastAPI, endpoint: str) -> None:
        del app, endpoint


class _AppStateProtocol(Protocol):
    """Typed view of app.state for worker runtime services."""

    worker_registry: WorkerRegistry
    worker_health_service: WorkerHealthService
    settings: Any


def _load_instrumentator() -> type[Any]:
    """Load the Prometheus instrumentator or a no-op fallback."""

    try:
        from prometheus_fastapi_instrumentator import (
            Instrumentator as PrometheusInstrumentator,
        )

        return cast(type[Any], PrometheusInstrumentator)
    except ImportError:
        return _NoOpInstrumentator


InstrumentatorClass = _load_instrumentator()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure process-wide resources for the app lifetime."""

    settings = get_settings()
    configure_logging(settings.log_level)

    state = cast(_AppStateProtocol, app.state)
    state.worker_registry = WorkerRegistry()
    state.worker_health_service = WorkerHealthService(state.worker_registry)
    state.settings = settings
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    InstrumentatorClass().instrument(app).expose(app, endpoint="/metrics")
    app.include_router(health_router)
    app.include_router(runtime_router)
    app.include_router(candles_router)
    app.include_router(admin_router)
    app.include_router(watchlist_router)
    app.include_router(paper_router)
    app.include_router(research_router)
    app.include_router(ml_router)
    app.include_router(orders_router)
    app.include_router(config_router)
    return app


app = create_app()