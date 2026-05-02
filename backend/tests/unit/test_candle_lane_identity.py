"""Tests for candle lane identity and coexistence."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config.constants import ML_CANDLE_USAGE, TRADING_CANDLE_USAGE
from app.db.models import CandleRow


def _row(*, usage: str, close: float) -> CandleRow:
    return CandleRow(
        symbol="BTC/USD",
        asset_class="crypto",
        timeframe="15m",
        time=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=close,
        volume=10.0,
        source="alpaca_training" if usage == ML_CANDLE_USAGE else "kraken",
        usage=usage,
    )


def test_ml_and_trading_candles_can_coexist_for_same_bar() -> None:
    """The ORM identity should include usage so merge does not collapse lanes."""

    engine = create_engine("sqlite:///:memory:")
    CandleRow.__table__.create(engine)

    with Session(engine) as session:
        session.merge(_row(usage=ML_CANDLE_USAGE, close=100.5))
        session.merge(_row(usage=TRADING_CANDLE_USAGE, close=100.7))
        session.commit()

        rows = list(
            session.scalars(
                select(CandleRow).order_by(CandleRow.usage.asc()),
            )
        )

    assert len(rows) == 2
    assert {row.usage for row in rows} == {ML_CANDLE_USAGE, TRADING_CANDLE_USAGE}
    assert {float(row.close or 0.0) for row in rows} == {100.5, 100.7}
