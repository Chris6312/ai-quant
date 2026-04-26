"""Phase 9 Slice 8 manual sentiment-risk verification endpoint tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.routers.sentiment_risk import verify_sentiment_risk_layer
from app.main import app


def test_sentiment_risk_verify_payload_proves_macro_pressure_rule() -> None:
    """Manual verification should prove macro sentiment is not a universal gate."""

    payload = verify_sentiment_risk_layer()
    scenarios = {item["name"]: item for item in payload["scenarios"]}

    assert payload["status"] == "pass"
    assert payload["principle"] == (
        "Macro sentiment is a risk-pressure layer, not a universal gate."
    )
    assert scenarios["bearish_macro_strong_long"]["gate"]["state"] == "downgraded"
    assert scenarios["bearish_macro_strong_long"]["pre_trade"]["state"] == "scaled"
    assert scenarios["bearish_macro_strong_long"]["pre_trade"]["adjusted_size"] == 75.0


def test_sentiment_risk_verify_payload_proves_weak_conflicts_block() -> None:
    """Weak conflicting crypto setups should still be blocked before execution."""

    payload = verify_sentiment_risk_layer()
    scenarios = {item["name"]: item for item in payload["scenarios"]}
    weak_long = scenarios["bearish_macro_weak_long"]

    assert weak_long["gate"]["state"] == "blocked"
    assert weak_long["gate"]["allowed"] is False
    assert weak_long["pre_trade"]["state"] == "blocked"
    assert weak_long["pre_trade"]["adjusted_size"] == 0.0


def test_sentiment_risk_verify_payload_proves_stock_scope_is_unchanged() -> None:
    """BTC/ETH crypto macro sentiment must not block stock orders."""

    payload = verify_sentiment_risk_layer()
    scenarios = {item["name"]: item for item in payload["scenarios"]}
    stock = scenarios["stock_unscoped_from_crypto_macro_sentiment"]

    assert stock["passed"] is True
    assert stock["pre_trade"]["state"] == "unscoped"
    assert stock["pre_trade"]["adjusted_size"] == 100.0


def test_sentiment_risk_verify_endpoint_is_registered() -> None:
    """The manual verification endpoint should be reachable from FastAPI."""

    client = TestClient(app)
    response = client.get("/risk/sentiment/verify")

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "Phase 9"
    assert payload["slice"] == "Slice 8"
    assert payload["status"] == "pass"
