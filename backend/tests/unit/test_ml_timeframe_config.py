"""ML multi-timeframe contract tests."""

from __future__ import annotations

import pytest

from app.ml.model_contracts import AssetClass, ModelRole
from app.ml.timeframe_config import (
    get_ml_timeframes,
    get_model_role,
    get_timeframe_contract,
    is_supported_ml_timeframe,
)


def test_crypto_supports_expected_production_timeframes() -> None:
    """Crypto production ML models should be intraday only."""

    assert set(get_ml_timeframes(AssetClass.CRYPTO)) == {"15m", "1h", "4h"}


def test_stock_supports_expected_production_timeframes() -> None:
    """Stock production ML models should include execution timing."""

    assert set(get_ml_timeframes("stock")) == {"5m", "15m", "1h", "4h"}


def test_crypto_daily_timeframe_is_context_only() -> None:
    """Daily crypto candles are context, not the production trading model."""

    contract = get_timeframe_contract(AssetClass.CRYPTO, "1Day")

    assert contract.model_role == ModelRole.CONTEXT
    assert contract.is_context_only is True
    assert contract.is_primary_trading_model is False
    assert "1Day" not in get_ml_timeframes(AssetClass.CRYPTO)


def test_stock_daily_timeframe_is_context_only() -> None:
    """Daily stock candles are context, not the production trading model."""

    contract = get_timeframe_contract("stock", "1Day")

    assert contract.model_role == ModelRole.CONTEXT
    assert contract.is_context_only is True
    assert contract.is_primary_trading_model is False
    assert "1Day" not in get_ml_timeframes("stock")


def test_unsupported_asset_raises_clean_error() -> None:
    """Unknown asset classes should fail before trainer or DB code is involved."""

    with pytest.raises(ValueError, match="Unsupported ML asset class"):
        get_ml_timeframes("forex")


def test_unsupported_timeframe_raises_clean_error() -> None:
    """Unknown timeframe contracts should report the supported set."""

    with pytest.raises(ValueError, match="Unsupported ML timeframe"):
        get_timeframe_contract(AssetClass.CRYPTO, "30m")


def test_crypto_has_no_5m_production_model() -> None:
    """Crypto should not silently inherit the stock execution timeframe."""

    assert "5m" not in get_ml_timeframes(AssetClass.CRYPTO)
    assert is_supported_ml_timeframe(AssetClass.CRYPTO, "5m") is False


def test_model_roles_map_correctly() -> None:
    """Each production timeframe should expose the canonical model role."""

    assert get_model_role("crypto", "4h") == ModelRole.REGIME_FILTER
    assert get_model_role("crypto", "1h") == ModelRole.DIRECTION
    assert get_model_role("crypto", "15m") == ModelRole.ENTRY_TIMING
    assert get_model_role("stock", "4h") == ModelRole.REGIME_FILTER
    assert get_model_role("stock", "1h") == ModelRole.DIRECTION
    assert get_model_role("stock", "15m") == ModelRole.SETUP_TIMING
    assert get_model_role("stock", "5m") == ModelRole.EXECUTION_TIMING
