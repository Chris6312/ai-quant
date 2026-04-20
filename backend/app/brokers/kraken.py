"""Kraken live broker adapter for crypto."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import httpx

from app.brokers.base import BaseBroker, Order, OrderStatus
from app.models.domain import Position

KRAKEN_DEFAULT_BASE_URL: Final[str] = "https://api.kraken.com/0/public"
KRAKEN_ORDER_BASE_URL: Final[str] = "https://api.kraken.com/0/private"


@dataclass(slots=True)
class KrakenBrokerState:
    """Track local state mirrored from Kraken."""

    orders: dict[str, Order]
    positions: dict[str, Position]


class KrakenBroker(BaseBroker):
    """REST/WS broker adapter for crypto execution."""

    def __init__(
        self,
        base_url: str = KRAKEN_DEFAULT_BASE_URL,
        private_base_url: str = KRAKEN_ORDER_BASE_URL,
        api_key: str | None = None,
        api_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
        usd_balance: float = 0.0,
        crypto_usd_equiv: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.private_base_url = private_base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.client = client
        self.usd_balance = usd_balance
        self.crypto_usd_equiv = crypto_usd_equiv
        self._state = KrakenBrokerState(orders={}, positions={})
        self._halted = False

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
        """Submit a Kraken order."""

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
            "pair": symbol.replace("/", ""),
            "type": self._normalize_side(side),
            "ordertype": self._normalize_type(order_type),
            "volume": size,
        }
        if limit_price is not None:
            payload["price"] = limit_price
        order = Order.create(
            symbol,
            self._normalize_side(side),
            size,
            self._normalize_type(order_type),
            limit_price,
        )
        remote = await self._request("POST", "/AddOrder", data=payload)
        if remote is not None:
            order = self._order_from_payload(remote, order)
        order = self._transition(order, "submitted")
        self._state.orders[order.id] = order
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a Kraken order."""

        order = self._state.orders.get(order_id)
        if order is None:
            return False
        await self._request("POST", "/CancelOrder", data={"txid": order_id})
        self._state.orders[order_id] = self._transition(order, "cancelled")
        return True

    async def get_position(self, symbol: str) -> Position | None:
        """Return a local position mirror or fetch from Kraken."""

        position = self._state.positions.get(symbol.upper())
        if position is not None:
            return position
        payload = await self._request("POST", "/OpenPositions", data={"txid": symbol})
        if payload is None:
            return None
        return self._position_from_payload(symbol, payload)

    async def get_account_balance(self) -> dict[str, float]:
        """Return Kraken balances."""

        payload = await self._request("POST", "/Balance")
        if payload is None:
            return {"usd": self.usd_balance, "crypto_usd_equiv": self.crypto_usd_equiv}
        usd = float(payload.get("ZUSD", self.usd_balance))
        crypto = float(payload.get("crypto_usd_equiv", self.crypto_usd_equiv))
        self.usd_balance = usd
        self.crypto_usd_equiv = crypto
        return {"usd": usd, "crypto_usd_equiv": crypto}

    async def get_open_orders(self) -> list[Order]:
        """Return all open orders."""

        payload = await self._request("POST", "/OpenOrders")
        if payload is None:
            return list(self._state.orders.values())
        orders = payload.get("open", {}) if isinstance(payload, Mapping) else {}
        parsed: list[Order] = []
        if isinstance(orders, Mapping):
            for order_id, item in orders.items():
                if isinstance(item, Mapping):
                    parsed.append(
                        self._order_from_payload(
                            {"id": order_id, **item},
                            Order.create("UNKNOWN", "buy", 0.0, "market"),
                        )
                    )
        return parsed

    async def get_open_positions(self) -> list[Position]:
        """Return all open positions."""

        payload = await self._request("POST", "/OpenPositions")
        if payload is None:
            return list(self._state.positions.values())
        parsed: list[Position] = []
        if isinstance(payload, Mapping):
            for symbol, item in payload.items():
                if isinstance(item, Mapping):
                    parsed.append(self._position_from_payload(symbol, item))
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
        """Perform an authenticated request when a client and credentials are configured."""

        if self.client is None or self.api_key is None or self.api_secret is None:
            return None
        headers = {
            "API-Key": self.api_key,
            "API-Secret": self.api_secret,
            "Accept": "application/json",
        }
        url = f"{self.private_base_url}{path}"
        response = await self.client.request(method, url, headers=headers, data=data)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return None

    def _normalize_side(self, side: str) -> str:
        """Normalize order side strings."""

        return "buy" if side.lower() in {"buy", "long"} else "sell"

    def _normalize_type(self, order_type: str) -> str:
        """Normalize order type strings."""

        return "limit" if order_type.lower() == "limit" else "market"

    def _order_from_payload(self, payload: Mapping[str, object], fallback: Order) -> Order:
        """Convert a Kraken payload to an order."""

        order_id = str(payload.get("id", fallback.id))
        status = self._normalize_status(str(payload.get("status", fallback.status)))
        return Order(
            id=order_id,
            symbol=str(payload.get("symbol", fallback.symbol)),
            side=self._normalize_side(str(payload.get("side", fallback.side))),
            size=float(payload.get("volume", fallback.size)),
            order_type=self._normalize_type(str(payload.get("ordertype", fallback.order_type))),
            limit_price=self._optional_float(payload, "price", fallback.limit_price),
            status=status,
            filled_size=float(payload.get("filled", fallback.filled_size)),
            average_fill_price=self._optional_float(
                payload,
                "avg_price",
                fallback.average_fill_price,
            ),
            created_at=fallback.created_at,
            updated_at=datetime.now(tz=UTC),
        )

    def _position_from_payload(self, symbol: str, payload: Mapping[str, object]) -> Position:
        """Convert a Kraken payload to a domain position."""

        return Position(
            symbol=symbol.replace("X", "").replace("Z", ""),
            asset_class="crypto",
            side=str(payload.get("side", "long")),
            entry_price=float(payload.get("entry_price", 0.0)),
            size=float(payload.get("size", 0.0)),
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
        return value  # type: ignore[return-value]

    def _optional_float(
        self,
        payload: Mapping[str, object],
        key: str,
        default: float | None,
    ) -> float | None:
        """Read an optional float from a payload."""

        value = payload.get(key)
        return float(value) if value is not None else default

    def _optional_str(self, payload: Mapping[str, object], key: str) -> str | None:
        """Read an optional string from a payload."""

        value = payload.get(key)
        return str(value) if value is not None else None
