"""Tests for Slice 5.4 Kraken DOGE/XDG symbol mapping."""

from __future__ import annotations

from app.api.routers.candles import KRAKEN_TICKER_PAIR_MAP
from app.candle.kraken_rest import KRAKEN_PAIR_MAP, KrakenRestCandleClient


def test_doge_uses_kraken_xdg_pair_where_btc_uses_xbt_pair() -> None:
    """DOGE should reuse the same existing pair-map pattern as BTC/XBT."""

    assert KRAKEN_PAIR_MAP["BTC/USD"] == "XBTUSD"
    assert KRAKEN_PAIR_MAP["DOGE/USD"] == "XDGUSD"
    assert KRAKEN_TICKER_PAIR_MAP["BTC/USD"] == "XBTUSD"
    assert KRAKEN_TICKER_PAIR_MAP["DOGE/USD"] == "XDGUSD"


def test_kraken_rest_normalizes_xdg_to_doge_without_new_mapper() -> None:
    """The existing Kraken client normalization accepts Kraken's XDG display."""

    client = KrakenRestCandleClient()

    assert client._normalize_symbol("XBT/USD") == "BTC/USD"
    assert client._normalize_symbol("XDG/USD") == "DOGE/USD"
