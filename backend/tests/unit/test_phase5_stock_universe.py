"""Phase 5 stock universe tests."""

from __future__ import annotations

import json
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from fastapi.testclient import TestClient

from app.api.routers import ml as ml_router
from app.main import app
from app.ml.stock_universe import StockUniverseLoader


def _write_universe_file(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    universe_file = tmp_path / "sp500.json"
    universe_file.write_text(
        json.dumps(
            {
                "index": "S&P 500",
                "as_of": "2026-04-22",
                "constituent_stock_count": len(rows),
                "constituents": rows,
            }
        ),
        encoding="utf-8",
    )
    return universe_file


def test_stock_universe_loader_reports_supported_and_unsupported_symbols(tmp_path: Path) -> None:
    """The S&P 500 loader should keep raw symbols and flag unsupported share classes."""

    universe_file = _write_universe_file(
        tmp_path,
        [
            {
                "Symbol": "AAPL",
                "Security": "Apple Inc.",
                "GICS Sector": "Information Technology",
                "GICS Sub-Industry": "Technology Hardware, Storage & Peripherals",
            },
            {
                "Symbol": "BRK.B",
                "Security": "Berkshire Hathaway",
                "GICS Sector": "Financials",
                "GICS Sub-Industry": "Multi-Sector Holdings",
            },
            {
                "Symbol": "MSFT",
                "Security": "Microsoft",
                "GICS Sector": "Information Technology",
                "GICS Sub-Industry": "Systems Software",
            },
        ],
    )

    snapshot = StockUniverseLoader(file_path=universe_file).load()

    assert snapshot.constituent_stock_count == 3
    assert [symbol.symbol for symbol in snapshot.supported_symbols] == ["AAPL", "MSFT"]
    assert [symbol.symbol for symbol in snapshot.unsupported_symbols] == ["BRK.B"]
    assert (
        snapshot.unsupported_symbols[0].unsupported_reason
        == "contains unsupported provider character '.'"
    )


def test_stock_universe_endpoint_returns_snapshot(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """The stock universe API should surface the hydrated snapshot metadata."""

    universe_file = _write_universe_file(
        tmp_path,
        [
            {
                "Symbol": "AAPL",
                "Security": "Apple Inc.",
                "GICS Sector": "Information Technology",
                "GICS Sub-Industry": "Technology Hardware, Storage & Peripherals",
            },
            {
                "Symbol": "BF.B",
                "Security": "Brown-Forman",
                "GICS Sector": "Consumer Staples",
                "GICS Sub-Industry": "Distillers & Vintners",
            },
        ],
    )
    snapshot = StockUniverseLoader(file_path=universe_file).load()
    monkeypatch.setattr(ml_router, "_load_stock_universe_snapshot", lambda: snapshot)

    client = TestClient(app)
    response = client.get("/ml/stock/universe")

    assert response.status_code == 200
    payload = response.json()
    assert payload["index"] == "S&P 500"
    assert payload["supported_symbol_count"] == 1
    assert payload["unsupported_symbol_count"] == 1
    assert payload["target_candles_per_symbol"] == 1000
    assert payload["minimum_candles_per_symbol"] == 750
