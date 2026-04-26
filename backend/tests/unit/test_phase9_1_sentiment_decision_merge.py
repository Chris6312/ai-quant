"""Tests for Phase 9.1 sentiment decision merge."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.db.models import CryptoDailySentimentRow
from app.decision.sentiment import (
    build_macro_sentiment_decision,
    build_symbol_sentiment_decision,
    classify_sentiment_bias,
    merge_sentiment_decisions,
)


def _sentiment_row(
    *,
    symbol: str,
    score: float | None,
    article_count: int,
    coverage_score: float = 1.0,
) -> CryptoDailySentimentRow:
    now = datetime(2026, 4, 26, 7, 0, tzinfo=UTC)
    return CryptoDailySentimentRow(
        id=f"{symbol}-2026-04-26",
        symbol=symbol,
        asset_class="crypto",
        sentiment_date=date(2026, 4, 26),
        source_count=1 if article_count > 0 else 0,
        article_count=article_count,
        positive_score=None,
        neutral_score=None,
        negative_score=None,
        compound_score=score,
        coverage_score=coverage_score,
        created_at=now,
        updated_at=now,
    )


def test_classify_sentiment_bias_uses_visible_thresholds() -> None:
    """Small scores remain neutral instead of creating noisy weather flips."""

    assert classify_sentiment_bias(0.25) == "bullish"
    assert classify_sentiment_bias(-0.25) == "bearish"
    assert classify_sentiment_bias(0.02) == "neutral"
    assert classify_sentiment_bias(None) == "unknown"


def test_macro_sentiment_blends_btc_eth_as_weather() -> None:
    """BTC/ETH macro sentiment becomes weather context, not a trade action."""

    macro = build_macro_sentiment_decision(
        btc_row=_sentiment_row(symbol="BTC/USD", score=-0.40, article_count=12),
        eth_row=_sentiment_row(symbol="ETH/USD", score=-0.20, article_count=8),
    )

    assert macro.bias == "bearish"
    assert macro.effect == "headwind"
    assert macro.article_count == 20
    assert macro.source_symbols == ["BTC/USD", "ETH/USD"]


def test_symbol_sentiment_preserves_local_forecast() -> None:
    """Symbol sentiment stays separate from BTC/ETH macro weather."""

    symbol = build_symbol_sentiment_decision(
        _sentiment_row(symbol="SOL/USD", score=0.34, article_count=18)
    )

    assert symbol.bias == "bullish"
    assert symbol.score == 0.34
    assert symbol.article_count == 18


def test_merge_keeps_bullish_symbol_visible_against_bearish_macro() -> None:
    """Local strength against bad market weather remains mixed, not hidden."""

    macro = build_macro_sentiment_decision(
        btc_row=_sentiment_row(symbol="BTC/USD", score=-0.35, article_count=15),
        eth_row=_sentiment_row(symbol="ETH/USD", score=-0.15, article_count=10),
    )
    symbol = build_symbol_sentiment_decision(
        _sentiment_row(symbol="SOL/USD", score=0.31, article_count=9)
    )

    merged = merge_sentiment_decisions(
        macro_sentiment=macro,
        symbol_sentiment=symbol,
    )

    assert merged.macro_sentiment_bias == "bearish"
    assert merged.symbol_sentiment_bias == "bullish"
    assert merged.final_sentiment_decision == "mixed"
    assert merged.effect == "headwind"
    assert merged.conflicts == ["macro_symbol_conflict"]


def test_merge_aligned_bullish_sentiment_is_tailwind() -> None:
    """Aligned macro and symbol sentiment can later support allow or boost."""

    macro = build_macro_sentiment_decision(
        btc_row=_sentiment_row(symbol="BTC/USD", score=0.45, article_count=20),
        eth_row=_sentiment_row(symbol="ETH/USD", score=0.20, article_count=10),
    )
    symbol = build_symbol_sentiment_decision(
        _sentiment_row(symbol="ETH/USD", score=0.40, article_count=10)
    )

    merged = merge_sentiment_decisions(
        macro_sentiment=macro,
        symbol_sentiment=symbol,
    )

    assert merged.final_sentiment_decision == "aligned"
    assert merged.effect == "tailwind"
    assert merged.conflicts == []


def test_merge_unknown_sentiment_is_explicit_empty_state() -> None:
    """Missing sentiment is visible instead of being converted into neutral signal."""

    merged = merge_sentiment_decisions(
        macro_sentiment=build_macro_sentiment_decision(btc_row=None, eth_row=None),
        symbol_sentiment=build_symbol_sentiment_decision(None),
    )

    assert merged.final_sentiment_decision == "unknown"
    assert merged.effect == "unknown"
    assert merged.reason == "No macro or symbol sentiment is available yet."
