"""Pure-Python contracts for ML model timeframe ownership."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    """Supported ML asset classes."""

    CRYPTO = "crypto"
    STOCK = "stock"


class ModelRole(StrEnum):
    """Canonical role a model plays in the multi-timeframe stack."""

    REGIME_FILTER = "regime_filter"
    DIRECTION = "direction"
    ENTRY_TIMING = "entry_timing"
    SETUP_TIMING = "setup_timing"
    EXECUTION_TIMING = "execution_timing"
    CONTEXT = "context"


@dataclass(frozen=True, slots=True)
class TimeframeContract:
    """Contract for one asset/timeframe pair in the ML stack."""

    asset_class: AssetClass
    timeframe: str
    model_role: ModelRole
    is_primary_trading_model: bool
    is_context_only: bool
    description: str


@dataclass(frozen=True, slots=True)
class MLTrainingContract:
    """Training-facing contract for a model slot."""

    asset_class: AssetClass
    timeframe: str
    model_role: ModelRole
    is_primary_trading_model: bool
    is_context_only: bool
    description: str

    @classmethod
    def from_timeframe_contract(
        cls,
        contract: TimeframeContract,
    ) -> MLTrainingContract:
        """Create a training contract from the canonical timeframe contract."""

        return cls(
            asset_class=contract.asset_class,
            timeframe=contract.timeframe,
            model_role=contract.model_role,
            is_primary_trading_model=contract.is_primary_trading_model,
            is_context_only=contract.is_context_only,
            description=contract.description,
        )
