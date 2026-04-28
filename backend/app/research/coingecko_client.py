"""CoinGecko global market helpers for crypto macro weather."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

DominanceBias = Literal["bullish", "bearish", "neutral", "unknown"]
DominanceEffect = Literal["tailwind", "headwind", "neutral", "unknown"]
DominanceSeverity = Literal["mild", "moderate", "severe", "unknown"]


@dataclass(frozen=True, slots=True)
class BitcoinDominanceReading:
    """Normalized Bitcoin dominance reading for altcoin macro weather."""

    value: float | None
    bias: DominanceBias
    effect: DominanceEffect
    severity: DominanceSeverity
    source: str
    as_of: datetime
    status: str
    reason: str


class CoinGeckoGlobalClient:
    """Fetch global crypto market state from CoinGecko."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        api_key_header: str = "x-cg-demo-api-key",
        timeout_seconds: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_key_header = api_key_header
        self._timeout_seconds = timeout_seconds

    async def fetch_bitcoin_dominance(self) -> BitcoinDominanceReading:
        """Return the latest BTC dominance reading from CoinGecko global data."""

        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "AI-Quant/1.0",
        }
        if self._api_key:
            headers[self._api_key_header] = self._api_key

        url = f"{self._base_url}/global"
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        value = _extract_btc_dominance(payload)
        return classify_bitcoin_dominance(value=value, as_of=datetime.now(tz=UTC))


def classify_bitcoin_dominance(
    *,
    value: float | None,
    as_of: datetime | None = None,
) -> BitcoinDominanceReading:
    """Classify BTC.D as a crypto macro vane for altcoin risk."""

    timestamp = as_of or datetime.now(tz=UTC)
    if value is None:
        return BitcoinDominanceReading(
            value=None,
            bias="unknown",
            effect="unknown",
            severity="unknown",
            source="coingecko_global",
            as_of=timestamp,
            status="unavailable",
            reason="BTC dominance was unavailable from CoinGecko global data.",
        )

    if value >= 62.0:
        return _reading(
            value=value,
            bias="bearish",
            effect="headwind",
            severity="severe",
            as_of=timestamp,
            reason="BTC dominance is very elevated, so altcoin risk is strongly suppressed.",
        )
    if value >= 60.0:
        return _reading(
            value=value,
            bias="bearish",
            effect="headwind",
            severity="moderate",
            as_of=timestamp,
            reason="BTC dominance is above 60%, so Bitcoin is absorbing market share from alts.",
        )
    if value >= 57.0:
        return _reading(
            value=value,
            bias="bearish",
            effect="headwind",
            severity="mild",
            as_of=timestamp,
            reason="BTC dominance is elevated enough to be a mild altcoin headwind.",
        )
    if value <= 50.0:
        return _reading(
            value=value,
            bias="bullish",
            effect="tailwind",
            severity="moderate",
            as_of=timestamp,
            reason="BTC dominance is low, which can indicate broader altcoin rotation.",
        )
    if value <= 53.0:
        return _reading(
            value=value,
            bias="bullish",
            effect="tailwind",
            severity="mild",
            as_of=timestamp,
            reason="BTC dominance is soft, which is a mild altcoin rotation tailwind.",
        )

    return _reading(
        value=value,
        bias="neutral",
        effect="neutral",
        severity="mild",
        as_of=timestamp,
        reason="BTC dominance is in the neutral middle band.",
    )


def _reading(
    *,
    value: float,
    bias: DominanceBias,
    effect: DominanceEffect,
    severity: DominanceSeverity,
    as_of: datetime,
    reason: str,
) -> BitcoinDominanceReading:
    return BitcoinDominanceReading(
        value=value,
        bias=bias,
        effect=effect,
        severity=severity,
        source="coingecko_global",
        as_of=as_of,
        status="available",
        reason=reason,
    )


def _extract_btc_dominance(payload: dict[str, Any]) -> float | None:
    market_cap_percentage = payload.get("data", {}).get("market_cap_percentage", {})
    raw_value = market_cap_percentage.get("btc")
    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None
