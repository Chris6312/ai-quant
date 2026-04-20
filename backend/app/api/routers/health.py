"""Health-check endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.config.constants import APP_NAME, APP_VERSION
from app.exceptions import DatabaseUnavailableError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a lightweight liveness response."""

    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION}


@router.get("/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, str]:
    """Verify database readiness."""

    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - readiness boundary
        raise DatabaseUnavailableError("Database readiness check failed") from exc
    return {"status": "ready"}


@router.get("/version")
async def version() -> dict[str, str]:
    """Return the application version."""

    return {"version": APP_VERSION}
