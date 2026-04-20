"""Administrative trading controls."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_broker_router, get_position_repository
from app.brokers.router import BrokerRouter
from app.repositories.positions import PositionRepository

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/halt")
async def halt_trading(
    router_dep: Annotated[BrokerRouter, Depends(get_broker_router)],
) -> dict[str, object]:
    """Halt all live trading routes."""

    return {"status": "halted", "brokers": await router_dep.halt_all()}


@router.get("/reconcile")
async def reconcile(
    router_dep: Annotated[BrokerRouter, Depends(get_broker_router)],
    position_repository: Annotated[PositionRepository, Depends(get_position_repository)],
) -> dict[str, object]:
    """Return a lightweight reconciliation snapshot."""

    internal_positions = await position_repository.list_open()
    snapshot = await router_dep.get_account_snapshot()
    open_orders = await router_dep.get_open_orders()
    return {
        "internal_open_positions": len(internal_positions),
        "open_orders": {broker: len(orders) for broker, orders in open_orders.items()},
        "balances": snapshot,
    }
