"""Tradier live broker adapter for stocks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, cast

import httpx

from app.brokers.base import BaseBroker, Order, OrderSide, OrderStatus, OrderType
from app.models.domain import Position

TRADIER_DEFAULT_BASE_URL: Final[str] = "https://api.tradier.com/v1"


@dataclass(slots=True)
class TradierBrokerState:
    """Track local state mirrored from Tradier."""

    orders: dict[str, Order]
    positions: dict[str, Position]


class TradierBroker(BaseBroker):
    """REST-based live broker for stock trading."""

    def __init__(
        self,
        base_url: str = TRADIER_DEFAULT_BASE_URL,
        account_id: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
        cash_balance: float = 0.0,
        equity: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.account_id = account_id
        self.token = token
        self.client = client
        self.cash_balance = cash_balance
        self.equity = equity or cash_balance
        self._state = TradierBrokerState(orders={}, positions={})
        self._halted = False

    @property
    def halted(self) -> bool:
        """Return True when the broker is not accepting new orders."""

        return self._halted

    def halt(self) -> None:
        """Prevent new orders from being submitted."""

        self._halted = True

    def resume(self) -> None:
        """Allow new orders again."""

        self._halted = False

    async def submit_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str,
        limit_price: float | None = None,
    ) -> Order:
        """Submit an order via Tradier and mirror it locally."""

        if self._halted:
            return self._transition(
                Order.create(
                    symbol,
                    self._normalize_side(side),
                    size,
                    self._normalize_type(order_type),
                    limit_price,
                ),
                "rejected",
            )
        payload: dict[str, object] = {
            "symbol": symbol,
            "side": side,
            "quantity": size,
            "type": order_type,
        }
        if limit_price is not None:
            payload["limit"] = limit_price
        order = Order.create(
            symbol,
            self._normalize_side(side),
            size,
            self._normalize_type(order_type),
            limit_price,
        )
        remote = await self._request("POST", "/accounts/orders", data=payload)
        if remote is not None:
            order = self._order_from_payload(cast(Mapping[str, object], remote), order)
        order = self._transition(order, "submitted")
        self._state.orders[order.id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a Tradier order."""

        order = self._state.orders.get(order_id)
        if order is None:
            return False
        await self._request("DELETE", f"/accounts/orders/{order_id}")
        self._state.orders[order_id] = self._transition(order, "cancelled")
        return True

    async def get_position(self, symbol: str) -> Position | None:
        """Return a local mirror of an open position."""

        position = self._state.positions.get(symbol.upper())
        if position is not None:
            return position
        payload = await self._request("GET", f"/accounts/{self.account_id}/positions/{symbol}")
        if payload is None:
            return None
        return self._position_from_payload(cast(Mapping[str, object], payload))

    async def get_account_balance(self) -> dict[str, float]:
        """Return account balance data."""

        payload = await self._request("GET", f"/accounts/{self.account_id}/balances")
        if payload is None:
            return {"cash": self.cash_balance, "equity": self.equity}
        balance_payload = cast(Mapping[str, object], payload)
        cash = float(cast(float | int | str, balance_payload.get("cash", self.cash_balance)))
        equity = float(cast(float | int | str, balance_payload.get("equity", self.equity)))
        self.cash_balance = cash
        self.equity = equity
        return {"cash": cash, "equity": equity}

    async def get_open_orders(self) -> list[Order]:
        """Return the currently open orders."""

        payload = await self._request("GET", f"/accounts/{self.account_id}/orders")
        if payload is None:
            return list(self._state.orders.values())
        payload_map = cast(Mapping[str, object], payload)
        orders = payload_map.get("orders")
        if not isinstance(orders, list):
            return list(self._state.orders.values())
        parsed: list[Order] = []
        for item in orders:
            if isinstance(item, Mapping):
                parsed.append(
                    self._order_from_payload(
                        cast(Mapping[str, object], item),
                        Order.create("UNKNOWN", "buy", 0.0, "market"),
                    )
                )
        return parsed

    async def get_open_positions(self) -> list[Position]:
        """Return all open positions."""

        payload = await self._request("GET", f"/accounts/{self.account_id}/positions")
        if payload is None:
            return list(self._state.positions.values())
        payload_map = cast(Mapping[str, object], payload)
        positions = payload_map.get("positions")
        if not isinstance(positions, list):
            return list(self._state.positions.values())
        parsed: list[Position] = []
        for item in positions:
            if isinstance(item, Mapping):
                parsed.append(self._position_from_payload(cast(Mapping[str, object], item)))
        return parsed

    async def get_balance(self) -> dict[str, float]:
        """Compatibility helper for broker routers."""

        return await self.get_account_balance()

    def _transition(self, order: Order, status: OrderStatus) -> Order:
        """Return a new order with a status change."""

        return Order(
            id=order.id,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            order_type=order.order_type,
            limit_price=order.limit_price,
            status=status,
            filled_size=order.filled_size,
            average_fill_price=order.average_fill_price,
            created_at=order.created_at,
            updated_at=datetime.now(tz=UTC),
        )

    async def _request(
        self,
        method: str,
        path: str,
        data: Mapping[str, object] | None = None,
    ) -> object | None:
        """Perform an authenticated request when a client and token are configured."""

        if self.client is None or self.token is None or self.account_id is None:
            return None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        url = f"{self.base_url}{path}"
        response = await self.client.request(method, url, headers=headers, data=data)
        response.raise_for_status()
        try:
            return cast(object, response.json())
        except ValueError:
            return None

    def _normalize_side(self, side: str) -> OrderSide:
        """Normalize side names."""

        return "buy" if side.lower() in {"buy", "long"} else "sell"

    def _normalize_type(self, order_type: str) -> OrderType:
        """Normalize order types."""

        return "limit" if order_type.lower() == "limit" else "market"

    def _order_from_payload(self, payload: Mapping[str, object], fallback: Order) -> Order:
        """Convert a Tradier payload to an order."""

        order_id = str(payload.get("id", fallback.id))
        status = self._normalize_status(str(payload.get("status", fallback.status)))
        return Order(
            id=order_id,
            symbol=str(payload.get("symbol", fallback.symbol)),
            side=self._normalize_side(str(payload.get("side", fallback.side))),
            size=float(cast(float | int | str, payload.get("quantity", fallback.size))),
            order_type=self._normalize_type(str(payload.get("type", fallback.order_type))),
            limit_price=self._optional_float(payload, "limit", fallback.limit_price),
            status=status,
            filled_size=float(cast(float | int | str, payload.get("filled", fallback.filled_size))),
            average_fill_price=self._optional_float(
                payload,
                "price",
                fallback.average_fill_price,
            ),
            created_at=fallback.created_at,
            updated_at=datetime.now(tz=UTC),
        )

    def _position_from_payload(self, payload: Mapping[str, object]) -> Position:
        """Convert a Tradier payload to a domain position."""

        return Position(
            symbol=str(payload.get("symbol", "UNKNOWN")),
            asset_class="stock",
            side=str(payload.get("side", "long")),
            entry_price=float(cast(float | int | str, payload.get("entry_price", 0.0))),
            size=float(cast(float | int | str, payload.get("quantity", 0.0))),
            sl_price=self._optional_float(payload, "sl_price", None),
            tp_price=self._optional_float(payload, "tp_price", None),
            strategy_id=self._optional_str(payload, "strategy_id"),
            ml_confidence=self._optional_float(payload, "ml_confidence", None),
            research_score=self._optional_float(payload, "research_score", None),
            status=str(payload.get("status", "open")),
        )

    def _normalize_status(self, status: str) -> OrderStatus:
        """Normalize raw status strings."""

        value = status.lower()
        if value not in {"pending", "submitted", "partial", "filled", "cancelled", "rejected"}:
            return "submitted"
        return cast(OrderStatus, value)

    def _optional_float(
        self,
        payload: Mapping[str, object],
        key: str,
        default: float | None,
    ) -> float | None:
        """Read an optional float from a payload."""

        value = cast(float | int | str | bytes | bytearray | None, payload.get(key))
        return float(value) if value is not None else default

    def _optional_str(self, payload: Mapping[str, object], key: str) -> str | None:
        """Read an optional string from a payload."""

        value = payload.get(key)
        return str(value) if value is not None else None
