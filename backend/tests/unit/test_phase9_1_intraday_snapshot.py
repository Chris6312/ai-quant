"""Tests for Phase 9.1 intraday technical snapshot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.models import CandleRow
from app.decision.intraday import build_intraday_snapshot


def _make_candle(
    *,
    index: int,
    timeframe: str,
    close: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 100.0,
) -> CandleRow:
    candle_time = datetime(2026, 4, 26, 12, 0, tzinfo=UTC) + timedelta(minutes=index)
    effective_high = high if high is not None else close + 0.25
    effective_low = low if low is not None else close - 0.25
    return CandleRow(
        time=candle_time,
        symbol="SOL/USD",
        asset_class="crypto",
        timeframe=timeframe,
        open=Decimal(str(close - 0.1)),
        high=Decimal(str(effective_high)),
        low=Decimal(str(effective_low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
        source="kraken",
        usage="trading",
    )


def test_intraday_snapshot_surfaces_bullish_breakout_volume_confirmation() -> None:
    """Strong closed-candle structure produces visible intraday confirmation."""

    fifteen_minute = [
        _make_candle(index=index, timeframe="15m", close=100.0 + index, volume=100.0)
        for index in range(21)
    ]
    fifteen_minute[-1] = _make_candle(
        index=20,
        timeframe="15m",
        close=130.0,
        high=131.0,
        low=128.0,
        volume=260.0,
    )
    one_hour = [
        _make_candle(index=index, timeframe="1h", close=200.0 + index, volume=100.0)
        for index in range(21)
    ]
    four_hour = [
        _make_candle(index=index, timeframe="4h", close=300.0, volume=100.0)
        for index in range(21)
    ]

    snapshot = build_intraday_snapshot(
        {
            "15m": fifteen_minute,
            "1h": one_hour,
            "4h": four_hour,
        }
    )

    assert snapshot.confirmation.trend == "bullish"
    assert snapshot.confirmation.breakout is True
    assert snapshot.confirmation.volume_expansion is True
    assert snapshot.confirmation.volatility_state == "expanded"
    assert snapshot.confirmation.timeframes == ["15m", "1h"]
    assert snapshot.confirmation.as_of == fifteen_minute[-1].time


def test_intraday_snapshot_handles_missing_candles_as_unknown() -> None:
    """Sparse persisted candles do not create false technical proof."""

    snapshot = build_intraday_snapshot(
        {
            "15m": [_make_candle(index=0, timeframe="15m", close=100.0)],
            "1h": [],
            "4h": [],
        }
    )

    assert snapshot.confirmation.trend == "unknown"
    assert snapshot.confirmation.breakout is False
    assert snapshot.confirmation.volume_expansion is False
    assert snapshot.confirmation.volatility_state == "unknown"
    assert snapshot.confirmation.timeframes == []
    assert snapshot.timeframe_snapshots[0].candle_count == 1


def test_intraday_snapshot_can_show_mixed_trend_conflict() -> None:
    """Conflicting closed-candle trends stay visible for the composer slice."""

    bullish_rows = [
        _make_candle(index=index, timeframe="15m", close=100.0 + index)
        for index in range(21)
    ]
    bearish_rows = [
        _make_candle(index=index, timeframe="1h", close=200.0 - index)
        for index in range(21)
    ]

    snapshot = build_intraday_snapshot(
        {
            "15m": bullish_rows,
            "1h": bearish_rows,
            "4h": [],
        }
    )

    assert snapshot.confirmation.trend == "mixed"
    assert snapshot.confirmation.timeframes == ["15m", "1h"]
