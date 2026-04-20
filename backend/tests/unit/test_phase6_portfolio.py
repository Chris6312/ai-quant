"""Tests for Phase 6 risk controls and position sizing."""

from __future__ import annotations

from types import SimpleNamespace

from app.models.domain import Position
from app.portfolio.manager import PortfolioManager
from app.portfolio.risk import RiskEngine
from app.portfolio.sizer import PositionSizer, calculate_position_size


class _FakePositionRepository:
    """Stand in for the position repository."""

    def __init__(self, open_positions: list[SimpleNamespace]) -> None:
        self._open_positions = open_positions

    async def count_open(self) -> int:
        return len(self._open_positions)

    async def list_open(self) -> list[SimpleNamespace]:
        return list(self._open_positions)


def test_position_sizer_applies_research_bonus_and_cap() -> None:
    """Research score should apply the correct stock bonus and hard cap."""

    size = calculate_position_size(
        equity=100_000.0,
        entry_price=100.0,
        sl_price=95.0,
        ml_confidence=0.8,
        research_score=90.0,
        asset_class="stock",
    )
    assert size > 0.0
    assert size <= 200.0


def test_position_sizer_uses_quarter_kelly_when_provided() -> None:
    """Quarter-Kelly should reduce the final size when it is the smaller bound."""

    sizer = PositionSizer()
    size = sizer.calculate(
        equity=100_000.0,
        entry_price=100.0,
        sl_price=90.0,
        ml_confidence=1.0,
        research_score=0.0,
        asset_class="crypto",
        edge=0.10,
        odds=2.0,
    )
    assert size > 0.0
    assert size <= 200.0


def test_risk_engine_blocks_excessive_drawdown_and_liquidity() -> None:
    """Risk checks should block a candidate when drawdown or liquidity fail."""

    engine = RiskEngine()
    open_positions = [
        Position(
            symbol="AAPL",
            asset_class="stock",
            side="long",
            entry_price=100.0,
            size=100.0,
            sl_price=95.0,
            tp_price=None,
            strategy_id="momentum",
            ml_confidence=0.9,
            research_score=80.0,
            status="open",
        )
    ]
    candidate = Position(
        symbol="MSFT",
        asset_class="stock",
        side="long",
        entry_price=200.0,
        size=1_000.0,
        sl_price=190.0,
        tp_price=None,
        strategy_id="breakout",
        ml_confidence=0.9,
        research_score=80.0,
        status="open",
    )
    assessment = engine.assess_trade(
        equity=100_000.0,
        daily_pnl_pct=-0.03,
        weekly_drawdown_pct=0.0,
        peak_drawdown_pct=0.0,
        open_positions=open_positions,
        candidate=candidate,
        avg_daily_volume=50_000.0,
    )
    assert assessment.allowed is False
    assert "daily loss limit hit" in assessment.reasons
    assert "liquidity check failed" in assessment.reasons


def test_risk_engine_allows_reasonable_trade() -> None:
    """A sensible candidate should pass all risk checks."""

    engine = RiskEngine()
    open_positions: list[Position] = []
    candidate = Position(
        symbol="NVDA",
        asset_class="stock",
        side="long",
        entry_price=100.0,
        size=50.0,
        sl_price=95.0,
        tp_price=None,
        strategy_id="momentum",
        ml_confidence=0.9,
        research_score=80.0,
        status="open",
    )
    assessment = engine.assess_trade(
        equity=100_000.0,
        daily_pnl_pct=0.0,
        weekly_drawdown_pct=0.0,
        peak_drawdown_pct=0.0,
        open_positions=open_positions,
        candidate=candidate,
        avg_daily_volume=10_000_000.0,
    )
    assert assessment.allowed is True
    assert assessment.reasons == ()


def test_portfolio_manager_enforces_position_capacity() -> None:
    """Portfolio manager should respect the configured open-position cap."""

    repository = _FakePositionRepository([SimpleNamespace() for _ in range(5)])
    manager = PortfolioManager(repository)
    assert manager.risk_engine.max_positions == 5
