"""Portfolio management orchestration for Phase 6."""

from __future__ import annotations

from app.config.constants import (
    DEFAULT_MAX_CRYPTO_POSITIONS,
    DEFAULT_MAX_STOCK_POSITIONS,
    MAX_OPEN_POSITIONS,
)
from app.models.domain import Position
from app.portfolio.risk import RiskAssessment, RiskEngine
from app.repositories.positions import PositionRepository


class PortfolioManager:
    """Track portfolio capacity and evaluate Phase 6 constraints."""

    def __init__(
        self,
        position_repository: PositionRepository,
        risk_engine: RiskEngine | None = None,
    ) -> None:
        self.position_repository = position_repository
        self.risk_engine = risk_engine or RiskEngine()

    async def can_open_new_position(self) -> bool:
        """Return True when the portfolio has spare position capacity."""

        return await self.position_repository.count_open() < MAX_OPEN_POSITIONS

    async def current_open_positions(self) -> list[Position]:
        """Return open positions in domain form."""

        rows = await self.position_repository.list_open()
        return [
            Position(
                symbol=row.symbol,
                asset_class=row.asset_class,
                side=row.side,
                entry_price=float(row.entry_price),
                size=float(row.size),
                sl_price=float(row.sl_price) if row.sl_price is not None else None,
                tp_price=float(row.tp_price) if row.tp_price is not None else None,
                strategy_id=row.strategy_id,
                ml_confidence=row.ml_confidence,
                research_score=row.research_score,
                status=row.status,
            )
            for row in rows
        ]

    async def can_open_position(
        self,
        candidate: Position,
        *,
        equity: float,
        stock_balance: float | None = None,
        daily_pnl_pct: float = 0.0,
        weekly_drawdown_pct: float = 0.0,
        peak_drawdown_pct: float = 0.0,
        avg_daily_volume: float = 0.0,
        correlation_lookup: dict[str, float] | None = None,
        max_position_slots: dict[str, int] | None = None,
    ) -> RiskAssessment:
        """Evaluate whether the portfolio can accept a new position."""

        open_positions = await self.current_open_positions()
        slot_limits = max_position_slots or {
            "stock": DEFAULT_MAX_STOCK_POSITIONS,
            "crypto": DEFAULT_MAX_CRYPTO_POSITIONS,
        }
        return self.risk_engine.assess_trade(
            equity=equity,
            stock_balance=stock_balance,
            daily_pnl_pct=daily_pnl_pct,
            weekly_drawdown_pct=weekly_drawdown_pct,
            peak_drawdown_pct=peak_drawdown_pct,
            open_positions=open_positions,
            candidate=candidate,
            avg_daily_volume=avg_daily_volume,
            correlation_lookup=correlation_lookup,
            max_position_slots=slot_limits,
        )
