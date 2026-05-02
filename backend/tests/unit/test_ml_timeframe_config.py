"""ML multi-timeframe contract tests."""

from __future__ import annotations

import pytest

from app.ml.model_contracts import AssetClass, ModelRole
from app.ml.timeframe_config import (
    get_ml_lookback_days,
    get_ml_timeframes,
    get_model_role,
    get_timeframe_contract,
    get_trade_label_config,
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


def test_timeframe_lookbacks_are_contract_driven() -> None:
    """Each production and context timeframe should expose a sync lookback."""

    assert get_ml_lookback_days("crypto", "15m") == 183
    assert get_ml_lookback_days("crypto", "1h") == 274
    assert get_ml_lookback_days("crypto", "4h") == 365
    assert get_ml_lookback_days("crypto", "1Day") == 730
    assert get_ml_lookback_days("stock", "5m") == 365
    assert get_ml_lookback_days("stock", "15m") == 365
    assert get_ml_lookback_days("stock", "1h") == 456
    assert get_ml_lookback_days("stock", "4h") == 548


def test_timeframe_label_configs_match_phase_tf3_contract() -> None:
    """Production timeframes should expose fee-aware label barriers."""

    crypto_15m = get_trade_label_config("crypto", "15m")
    crypto_1h = get_trade_label_config("crypto", "1h")
    crypto_4h = get_trade_label_config("crypto", "4h")
    stock_5m = get_trade_label_config("stock", "5m")
    stock_15m = get_trade_label_config("stock", "15m")
    stock_1h = get_trade_label_config("stock", "1h")
    stock_4h = get_trade_label_config("stock", "4h")

    assert crypto_15m.use_atr_barriers is True
    assert crypto_15m.profit_target_atr_multiplier == 1.8
    assert crypto_15m.stop_loss_atr_multiplier == 1.1
    assert crypto_15m.max_holding_candles == 6
    assert crypto_15m.min_profitable_move_pct == 0.013
    assert crypto_1h.profit_target_atr_multiplier == 2.2
    assert crypto_1h.stop_loss_atr_multiplier == 1.4
    assert crypto_1h.max_holding_candles == 8
    assert crypto_4h.use_atr_barriers is False
    assert crypto_4h.profit_target_pct == 0.035
    assert crypto_4h.stop_loss_pct == 0.022
    assert crypto_4h.max_holding_candles == 6

    assert stock_5m.use_atr_barriers is True
    assert stock_5m.profit_target_atr_multiplier == 1.6
    assert stock_5m.stop_loss_atr_multiplier == 1.0
    assert stock_5m.max_holding_candles == 12
    assert stock_5m.min_profitable_move_pct == 0.002
    assert stock_15m.profit_target_atr_multiplier == 1.8
    assert stock_15m.stop_loss_atr_multiplier == 1.1
    assert stock_15m.max_holding_candles == 8
    assert stock_1h.profit_target_atr_multiplier == 2.0
    assert stock_1h.stop_loss_atr_multiplier == 1.2
    assert stock_1h.max_holding_candles == 6
    assert stock_4h.use_atr_barriers is False
    assert stock_4h.profit_target_pct == 0.020
    assert stock_4h.stop_loss_pct == 0.012
    assert stock_4h.max_holding_candles == 4


def test_context_timeframe_has_no_trade_label_config() -> None:
    with pytest.raises(ValueError, match="Context-only ML timeframe"):
        get_trade_label_config("crypto", "1Day")
