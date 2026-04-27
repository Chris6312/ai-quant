"""Tests for Phase 9.1 Research intraday decision visibility wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.routers.research import build_research_intraday_decision
from app.db.models import CandleRow


class _FakeCandleRepository:
    def __init__(self, rows_by_timeframe: dict[str, list[CandleRow]]) -> None:
        self.rows_by_timeframe = rows_by_timeframe
        self.calls: list[tuple[str, str, int, str | None]] = []

    async def list_recent(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        usage: str | None = "trading",
    ) -> list[CandleRow]:
        self.calls.append((symbol, timeframe, limit, usage))
        return self.rows_by_timeframe.get(timeframe, [])


def _row(
    *,
    symbol: str,
    timeframe: str,
    index: int,
    close: Decimal,
    volume: Decimal,
) -> CandleRow:
    high = close + Decimal("1.0")
    if index == 24:
        high = close + Decimal("4.0")
    return CandleRow(
        time=datetime(2026, 4, 26, 17, 0, tzinfo=UTC) + timedelta(minutes=index),
        symbol=symbol,
        asset_class="crypto",
        timeframe=timeframe,
        open=close - Decimal("0.5"),
        high=high,
        low=close - Decimal("1.0"),
        close=close,
        volume=volume,
        source="kraken",
        usage="trading",
    )


def _bullish_rows(symbol: str, timeframe: str) -> list[CandleRow]:
    rows: list[CandleRow] = []
    for index in range(25):
        close = Decimal("100") + Decimal(index)
        volume = Decimal("100")
        if index == 24:
            close = Decimal("130")
            volume = Decimal("250")
        rows.append(
            _row(
                symbol=symbol,
                timeframe=timeframe,
                index=index,
                close=close,
                volume=volume,
            )
        )
    return rows


@pytest.mark.asyncio
async def test_research_intraday_decision_reads_stored_trading_candles() -> None:
    """Research decision visibility should expose real intraday proof."""

    symbol = "BTC/USD"
    repository = _FakeCandleRepository(
        {
            "15m": _bullish_rows(symbol, "15m"),
            "1h": _bullish_rows(symbol, "1h"),
            "4h": _bullish_rows(symbol, "4h"),
        }
    )

    payload = await build_research_intraday_decision(
        repository,  # type: ignore[arg-type]
        symbol,
        generated_at=datetime(2026, 4, 26, 21, 48, tzinfo=UTC),
    )

    assert payload["symbol"] == symbol
    assert payload["source"] == "stored_trading_candles"
    assert payload["usage"] == "trading"
    assert payload["confirmation"] == {
        "trend": "bullish",
        "breakout": True,
        "volume_expansion": True,
        "volatility_state": "expanded",
        "timeframes": ["15m", "1h", "4h"],
        "as_of": "2026-04-26T17:24:00+00:00",
    }
    assert payload["timeframe_snapshots"][0]["timeframe"] == "15m"
    assert payload["timeframe_snapshots"][0]["candle_count"] == 25
    assert repository.calls == [
        (symbol, "15m", 60, "trading"),
        (symbol, "1h", 60, "trading"),
        (symbol, "4h", 60, "trading"),
    ]
