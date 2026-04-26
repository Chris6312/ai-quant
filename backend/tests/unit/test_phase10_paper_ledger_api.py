"""Phase 10 durable paper ledger API checks."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_paper_ledger_service
from app.api.routers.paper import router as paper_router
from app.db.models import PaperAccountRow, PaperFillRow, PaperOrderRow, PaperPositionRow
from app.paper.ledger_service import PaperExecutionResult


class _FakePaperLedgerService:
    """Small service double for paper API serialization and routing checks."""

    def __init__(self) -> None:
        now = datetime(2026, 4, 26, 15, 0, tzinfo=UTC)
        self.accounts = [
            PaperAccountRow(
                id=str(uuid4()),
                asset_class="crypto",
                cash_balance=75_000.0,
                default_cash_balance=100_000.0,
                realized_pnl=125.0,
                reset_count=1,
                last_reset_at=None,
                created_at=now,
                updated_at=now,
            ),
            PaperAccountRow(
                id=str(uuid4()),
                asset_class="stock",
                cash_balance=100_000.0,
                default_cash_balance=100_000.0,
                realized_pnl=0.0,
                reset_count=0,
                last_reset_at=None,
                created_at=now,
                updated_at=now,
            ),
        ]
        self.position = PaperPositionRow(
            id=str(uuid4()),
            symbol="BTC/USD",
            asset_class="crypto",
            side="long",
            size=0.5,
            average_entry_price=50_000.0,
            realized_pnl=0.0,
            status="open",
            strategy_id="phase10-api",
            opened_at=now,
            updated_at=now,
            closed_at=None,
        )
        self.order = PaperOrderRow(
            id=str(uuid4()),
            symbol="BTC/USD",
            asset_class="crypto",
            side="buy",
            order_type="market",
            requested_size=0.5,
            limit_price=None,
            status="filled",
            filled_size=0.5,
            average_fill_price=50_000.0,
            remaining_size=0.0,
            strategy_id="phase10-api",
            source="paper",
            reject_reason=None,
            created_at=now,
            updated_at=now,
            closed_at=now,
        )
        self.fill = PaperFillRow(
            id=str(uuid4()),
            order_id=self.order.id,
            position_id=self.position.id,
            symbol="BTC/USD",
            asset_class="crypto",
            side="buy",
            fill_size=0.5,
            fill_price=50_000.0,
            gross=25_000.0,
            commission=40.0,
            realized_pnl=0.0,
            cash_after=74_960.0,
            source="paper",
            filled_at=now,
        )

    async def list_accounts(self) -> list[PaperAccountRow]:
        """Return fake durable accounts."""

        return self.accounts

    async def set_account_balance(
        self,
        asset_class: str,
        cash_balance: float,
        update_default: bool = True,
    ) -> PaperAccountRow:
        """Update fake durable account cash."""

        del update_default
        for account in self.accounts:
            if account.asset_class == asset_class:
                account.cash_balance = cash_balance
                account.default_cash_balance = cash_balance
                return account
        raise ValueError("missing fake account")

    async def reset_account(self, asset_class: str) -> list[PaperAccountRow]:
        """Reset fake durable accounts."""

        selected = self.accounts if asset_class == "all" else [
            account for account in self.accounts if account.asset_class == asset_class
        ]
        for account in selected:
            account.cash_balance = account.default_cash_balance
            account.reset_count += 1
        return selected

    async def list_open_positions(
        self,
        asset_class: str | None = None,
    ) -> list[PaperPositionRow]:
        """Return fake open positions."""

        if asset_class is not None and asset_class != self.position.asset_class:
            return []
        return [self.position]

    async def list_orders(self, symbol: str | None = None) -> list[PaperOrderRow]:
        """Return fake durable orders."""

        if symbol is not None and symbol.upper() != self.order.symbol:
            return []
        return [self.order]

    async def list_fills(self, symbol: str | None = None) -> list[PaperFillRow]:
        """Return fake durable fills."""

        if symbol is not None and symbol.upper() != self.fill.symbol:
            return []
        return [self.fill]

    async def execute_market_fill(
        self,
        symbol: str,
        asset_class: str,
        side: str,
        size: float,
        fill_price: float,
        strategy_id: str | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
    ) -> PaperExecutionResult:
        """Return a fake durable execution result."""

        del symbol, asset_class, side, size, fill_price, strategy_id, order_type, limit_price
        return PaperExecutionResult(
            order=self.order,
            fill=self.fill,
            position=self.position,
            account=self.accounts[0],
        )


def _build_client(service: _FakePaperLedgerService) -> TestClient:
    app = FastAPI()
    app.include_router(paper_router)
    app.dependency_overrides[get_paper_ledger_service] = lambda: service
    return TestClient(app)


def test_paper_balance_reads_from_durable_service() -> None:
    """Paper balance API should expose database-backed account state."""

    service = _FakePaperLedgerService()
    with _build_client(service) as client:
        response = client.get("/paper/balance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["crypto_balance"] == 75_000.0
    assert payload["stock_balance"] == 100_000.0
    assert payload["nav"] == 175_000.0
    assert len(payload["accounts"]) == 2


def test_paper_state_includes_positions_orders_and_fills() -> None:
    """Durable paper state API should provide restart-verification data."""

    service = _FakePaperLedgerService()
    with _build_client(service) as client:
        response = client.get("/paper/state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["positions"][0]["symbol"] == "BTC/USD"
    assert payload["orders"][0]["status"] == "filled"
    assert payload["fills"][0]["cash_after"] == 74_960.0


def test_paper_order_add_uses_durable_execution_result() -> None:
    """Manual paper order endpoint should route through durable ledger execution."""

    service = _FakePaperLedgerService()
    with _build_client(service) as client:
        response = client.post(
            "/paper/orders/add",
            params={
                "symbol": "BTC/USD",
                "asset_class": "crypto",
                "side": "buy",
                "size": 0.5,
                "price": 50_000.0,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["order"]["symbol"] == "BTC/USD"
    assert payload["fill"]["commission"] == 40.0
    assert payload["position"]["status"] == "open"


def test_paper_position_and_fill_filters_are_available() -> None:
    """Paper read paths should expose focused durable state queries."""

    service = _FakePaperLedgerService()
    with _build_client(service) as client:
        positions = client.get("/paper/positions", params={"asset_class": "crypto"})
        fills = client.get("/paper/fills", params={"symbol": "BTC/USD"})

    assert positions.status_code == 200
    assert fills.status_code == 200
    assert positions.json()[0]["average_entry_price"] == 50_000.0
    assert fills.json()[0]["symbol"] == "BTC/USD"
