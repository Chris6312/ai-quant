"""Base broker contract and shared order model."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from app.models.domain import Position

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["pending", "submitted", "partial", "filled", "cancelled", "rejected"]


@dataclass(slots=True, frozen=True)
class Order:
    """Represent an order in the broker abstraction."""

    id: str
    symbol: str
    side: OrderSide
    size: float
    order_type: OrderType
    limit_price: float | None
    status: OrderStatus
    filled_size: float
    average_fill_price: float | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        symbol: str,
        side: OrderSide,
        size: float,
        order_type: OrderType,
        limit_price: float | None = None,
    ) -> Order:
        """Create a new pending order."""

        now = datetime.now(tz=UTC)
        return cls(
            id=str(uuid4()),
            symbol=symbol,
            side=side,
            size=size,
            order_type=order_type,
            limit_price=limit_price,
            status="pending",
            filled_size=0.0,
            average_fill_price=None,
            created_at=now,
            updated_at=now,
        )


class BaseBroker(ABC):
    """Define the broker interface used by the trading engine."""

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: float | None = None,
    ) -> Order:
        """Submit an order to the broker."""

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order if possible."""

    @abstractmethod
    async def get_position(self, symbol: str) -> Position | None:
        """Return a current open position for a symbol."""

    @abstractmethod
    async def get_account_balance(self) -> dict[str, float]:
        """Return the account balance snapshot."""

    @abstractmethod
    async def get_open_orders(self) -> list[Order]:
        """Return all open orders."""


__all__ = ["BaseBroker", "Order", "OrderSide", "OrderStatus", "OrderType"]
