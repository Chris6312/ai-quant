"""Typed schema for Phase 9.1 dynamic decision visibility.

This module is intentionally schema-first. It gives the backend and UI one
shared object shape for separating daily ML bias from live decision context.
It does not execute trades, rerun ML, fetch open candles, or mutate paper-ledger
state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

DecisionDirection = Literal["long", "short", "neutral", "unknown"]
DecisionAction = Literal["watch", "allow", "reduce", "boost", "block", "no_trade"]
DecisionRiskMode = Literal["normal", "reduced", "boosted", "blocked", "watch_only"]
FreshnessState = Literal["fresh", "stale", "missing", "unknown"]
SentimentBias = Literal["bullish", "bearish", "neutral", "unknown"]
SentimentEffect = Literal["tailwind", "headwind", "neutral", "unknown"]
IntradayTrend = Literal["bullish", "bearish", "mixed", "neutral", "unknown"]
VolatilityState = Literal["compressed", "normal", "expanded", "unknown"]
DecisionExpiry = Literal["next_closed_candle", "end_of_day", "manual_refresh"]


class MlBiasDecision(BaseModel):
    """Daily ML bias, not a direct trade instruction."""

    direction: DecisionDirection
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    freshness: FreshnessState = "unknown"
    model_id: int | None = Field(default=None, ge=1)
    candle_time: datetime | None = None


class MacroSentimentDecision(BaseModel):
    """BTC/ETH macro weather flowing into crypto decisions."""

    bias: SentimentBias
    score: float | None = Field(default=None, ge=-1.0, le=1.0)
    effect: SentimentEffect = "unknown"
    article_count: int = Field(default=0, ge=0)
    source_symbols: list[str] = Field(default_factory=list)
    as_of: datetime | None = None


class SymbolSentimentDecision(BaseModel):
    """Local symbol forecast when symbol-level sentiment exists."""

    bias: SentimentBias
    score: float | None = Field(default=None, ge=-1.0, le=1.0)
    article_count: int = Field(default=0, ge=0)
    as_of: datetime | None = None


class IntradayConfirmation(BaseModel):
    """Closed-candle live technical proof for 15m/1h/4h context."""

    trend: IntradayTrend
    breakout: bool = False
    volume_expansion: bool = False
    volatility_state: VolatilityState = "unknown"
    timeframes: list[str] = Field(default_factory=list)
    as_of: datetime | None = None

    @model_validator(mode="after")
    def validate_timeframes(self) -> Self:
        """Require explicit closed-candle timeframe labels when proof is present."""

        if (self.breakout or self.volume_expansion) and not self.timeframes:
            message = "timeframes are required when breakout or volume expansion is true"
            raise ValueError(message)
        return self


class FinalDecision(BaseModel):
    """Visible decision result consumed by Research UI and later candidates."""

    action: DecisionAction
    direction: DecisionDirection
    risk_mode: DecisionRiskMode
    size_multiplier: float = Field(ge=0.0, le=1.25)
    reason: str = Field(min_length=1)
    expires_at: DecisionExpiry = "next_closed_candle"
    conflicts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_contract(self) -> Self:
        """Keep the action and size/risk language internally truthful."""

        if self.action in {"block", "no_trade"} and self.size_multiplier != 0.0:
            message = "block and no_trade decisions must use size_multiplier 0.0"
            raise ValueError(message)
        if self.action == "boost" and self.risk_mode != "boosted":
            message = "boost decisions must use boosted risk_mode"
            raise ValueError(message)
        if self.action == "reduce" and self.risk_mode != "reduced":
            message = "reduce decisions must use reduced risk_mode"
            raise ValueError(message)
        return self


class DynamicDecision(BaseModel):
    """Phase 9.1 envelope: daily brain, weather, live eyes, visible decision."""

    symbol: str = Field(min_length=1)
    asset_class: Literal["crypto", "stock"] = "crypto"
    ml_bias: MlBiasDecision
    macro_sentiment: MacroSentimentDecision
    symbol_sentiment: SymbolSentimentDecision
    intraday_confirmation: IntradayConfirmation
    final_decision: FinalDecision
    generated_at: datetime


def build_no_trade_decision(symbol: str, reason: str, generated_at: datetime) -> DynamicDecision:
    """Build an explicit empty/live-unready decision without hiding the symbol."""

    return DynamicDecision(
        symbol=symbol,
        ml_bias=MlBiasDecision(direction="unknown", freshness="unknown"),
        macro_sentiment=MacroSentimentDecision(bias="unknown"),
        symbol_sentiment=SymbolSentimentDecision(bias="unknown"),
        intraday_confirmation=IntradayConfirmation(trend="unknown"),
        final_decision=FinalDecision(
            action="no_trade",
            direction="unknown",
            risk_mode="blocked",
            size_multiplier=0.0,
            reason=reason,
        ),
        generated_at=generated_at,
    )
