"""Canonical ML timeframe map for model training and prediction contracts."""

from __future__ import annotations

from app.ml.model_contracts import AssetClass, ModelRole, TimeframeContract

_ML_LOOKBACK_DAYS: dict[AssetClass, dict[str, int]] = {
    AssetClass.CRYPTO: {
        "15m": 183,
        "1h": 274,
        "4h": 365,
        "1Day": 730,
    },
    AssetClass.STOCK: {
        "5m": 365,
        "15m": 365,
        "1h": 456,
        "4h": 548,
        "1Day": 1600,
    },
}

_PRODUCTION_CONTRACTS: dict[AssetClass, tuple[TimeframeContract, ...]] = {
    AssetClass.CRYPTO: (
        TimeframeContract(
            asset_class=AssetClass.CRYPTO,
            timeframe="4h",
            model_role=ModelRole.REGIME_FILTER,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Crypto regime filter for higher-timeframe market state.",
        ),
        TimeframeContract(
            asset_class=AssetClass.CRYPTO,
            timeframe="1h",
            model_role=ModelRole.DIRECTION,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Crypto directional model for intraday trade intent.",
        ),
        TimeframeContract(
            asset_class=AssetClass.CRYPTO,
            timeframe="15m",
            model_role=ModelRole.ENTRY_TIMING,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Crypto entry timing model for lower-timeframe confirmation.",
        ),
    ),
    AssetClass.STOCK: (
        TimeframeContract(
            asset_class=AssetClass.STOCK,
            timeframe="4h",
            model_role=ModelRole.REGIME_FILTER,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Stock regime filter for higher-timeframe market state.",
        ),
        TimeframeContract(
            asset_class=AssetClass.STOCK,
            timeframe="1h",
            model_role=ModelRole.DIRECTION,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Stock directional model for intraday trade intent.",
        ),
        TimeframeContract(
            asset_class=AssetClass.STOCK,
            timeframe="15m",
            model_role=ModelRole.SETUP_TIMING,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Stock setup timing model for trade setup confirmation.",
        ),
        TimeframeContract(
            asset_class=AssetClass.STOCK,
            timeframe="5m",
            model_role=ModelRole.EXECUTION_TIMING,
            is_primary_trading_model=True,
            is_context_only=False,
            description="Stock execution timing model for final entry precision.",
        ),
    ),
}

_CONTEXT_CONTRACTS: dict[AssetClass, tuple[TimeframeContract, ...]] = {
    asset_class: (
        TimeframeContract(
            asset_class=asset_class,
            timeframe="1Day",
            model_role=ModelRole.CONTEXT,
            is_primary_trading_model=False,
            is_context_only=True,
            description="Daily timeframe context only; not a production trading model.",
        ),
    )
    for asset_class in AssetClass
}


def get_ml_timeframes(asset_class: AssetClass | str) -> tuple[str, ...]:
    """Return production ML trading timeframes for an asset class."""

    normalized_asset_class = _normalize_asset_class(asset_class)
    return tuple(
        contract.timeframe
        for contract in _PRODUCTION_CONTRACTS[normalized_asset_class]
        if contract.is_primary_trading_model
    )


def get_ml_lookback_days(asset_class: AssetClass | str, timeframe: str) -> int:
    """Return the historical candle lookback for an ML asset/timeframe contract."""

    contract = get_timeframe_contract(asset_class, timeframe)
    return _ML_LOOKBACK_DAYS[contract.asset_class][contract.timeframe]


def get_model_role(asset_class: AssetClass | str, timeframe: str) -> ModelRole:
    """Return the canonical model role for an asset/timeframe pair."""

    return get_timeframe_contract(asset_class, timeframe).model_role


def get_timeframe_contract(
    asset_class: AssetClass | str,
    timeframe: str,
) -> TimeframeContract:
    """Return the complete timeframe contract for production or context slots."""

    normalized_asset_class = _normalize_asset_class(asset_class)
    normalized_timeframe = _normalize_timeframe(timeframe)
    contracts = (
        *_PRODUCTION_CONTRACTS[normalized_asset_class],
        *_CONTEXT_CONTRACTS[normalized_asset_class],
    )

    for contract in contracts:
        if contract.timeframe == normalized_timeframe:
            return contract

    supported_timeframes = ", ".join(contract.timeframe for contract in contracts)
    raise ValueError(
        "Unsupported ML timeframe "
        f"{normalized_timeframe!r} for asset class {normalized_asset_class.value!r}. "
        f"Supported timeframes: {supported_timeframes}."
    )


def is_supported_ml_timeframe(asset_class: AssetClass | str, timeframe: str) -> bool:
    """Return whether a timeframe has a production or context ML contract."""

    try:
        get_timeframe_contract(asset_class, timeframe)
    except ValueError:
        return False
    return True


def _normalize_asset_class(asset_class: AssetClass | str) -> AssetClass:
    if isinstance(asset_class, AssetClass):
        return asset_class

    normalized_asset_class = asset_class.strip().lower()
    try:
        return AssetClass(normalized_asset_class)
    except ValueError as exc:
        supported_asset_classes = ", ".join(asset_class.value for asset_class in AssetClass)
        raise ValueError(
            f"Unsupported ML asset class {asset_class!r}. "
            f"Supported asset classes: {supported_asset_classes}."
        ) from exc


def _normalize_timeframe(timeframe: str) -> str:
    return timeframe.strip()
