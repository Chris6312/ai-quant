"""Shared ML candle freshness checks for scoring guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import ALPACA_DEFAULT_TIMEFRAME, ML_CANDLE_USAGE
from app.config.crypto_scope import list_crypto_ml_symbols
from app.repositories.candles import CandleRepository


@dataclass(frozen=True, slots=True)
class MlFreshnessResult:
    """Typed ML-lane freshness result shared by runtime and scoring paths."""

    freshness: str
    latest_ml_candle_at: datetime | None
    latest_ml_candle_date: date | None
    tracked_symbol_count: int
    symbols_with_ml_candles: int
    missing_or_stale_symbols: tuple[str, ...]
    can_score: bool
    block_reason: str | None

    def to_api_payload(self) -> dict[str, object]:
        """Serialize the result for API responses."""

        return {
            "freshness": self.freshness,
            "latest_ml_candle_at": (
                self.latest_ml_candle_at.isoformat()
                if self.latest_ml_candle_at is not None
                else None
            ),
            "latest_ml_candle_date": (
                self.latest_ml_candle_date.isoformat()
                if self.latest_ml_candle_date is not None
                else None
            ),
            "tracked_symbol_count": self.tracked_symbol_count,
            "symbols_with_ml_candles": self.symbols_with_ml_candles,
            "missing_or_stale_symbols": list(self.missing_or_stale_symbols),
            "can_score": self.can_score,
            "block_reason": self.block_reason,
        }


def classify_ml_freshness(
    latest_candle_at: datetime | None,
    *,
    has_missing_or_stale_symbols: bool = False,
    current_date: date | None = None,
) -> str:
    """Classify daily ML data freshness by candle date, not heartbeat age."""

    if latest_candle_at is None:
        return "missing"

    latest_date = ml_candle_date(latest_candle_at)
    if latest_date is None:
        return "missing"

    eastern = ZoneInfo("America/New_York")
    comparison_date = current_date if current_date is not None else datetime.now(tz=eastern).date()
    age_days = (comparison_date - latest_date).days
    if age_days <= 0:
        return "stale" if has_missing_or_stale_symbols else "fresh"
    if age_days == 1:
        return "stale"
    return "dead"


def ml_candle_date(value: datetime | None) -> date | None:
    """Return the ML daily candle's stored date without timezone shifting."""

    if value is None:
        return None
    return value.date()


async def evaluate_crypto_ml_freshness(
    session: AsyncSession,
    *,
    current_date: date | None = None,
) -> MlFreshnessResult:
    """Evaluate whether canonical crypto ML daily candles are complete enough for scoring."""

    symbols = list_crypto_ml_symbols()
    latest_by_symbol = await CandleRepository(session).get_latest_candle_times(
        symbols=symbols,
        timeframe=ALPACA_DEFAULT_TIMEFRAME,
        usage=ML_CANDLE_USAGE,
    )
    latest_values = [value for value in latest_by_symbol.values() if value is not None]
    latest_candle_at = max(latest_values) if latest_values else None
    latest_candle_date = ml_candle_date(latest_candle_at)
    stale_symbols = [symbol for symbol, value in latest_by_symbol.items() if value is None]

    if latest_candle_date is not None:
        stale_symbols.extend(
            symbol
            for symbol, value in latest_by_symbol.items()
            if value is not None and ml_candle_date(value) != latest_candle_date
        )

    missing_or_stale_symbols = tuple(sorted(set(stale_symbols)))
    freshness = classify_ml_freshness(
        latest_candle_at,
        has_missing_or_stale_symbols=bool(missing_or_stale_symbols),
        current_date=current_date,
    )
    symbols_with_ml_candles = len(latest_values)
    tracked_symbol_count = len(symbols)
    can_score = (
        freshness == "fresh"
        and symbols_with_ml_candles == tracked_symbol_count
        and not missing_or_stale_symbols
    )
    block_reason = None if can_score else "ML candles are stale or incomplete"

    return MlFreshnessResult(
        freshness=freshness,
        latest_ml_candle_at=latest_candle_at,
        latest_ml_candle_date=latest_candle_date,
        tracked_symbol_count=tracked_symbol_count,
        symbols_with_ml_candles=symbols_with_ml_candles,
        missing_or_stale_symbols=missing_or_stale_symbols,
        can_score=can_score,
        block_reason=block_reason,
    )
