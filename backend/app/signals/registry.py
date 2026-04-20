"""YAML-driven strategy registry."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.signals.base import BaseStrategy
from app.strategies.breakout import BreakoutStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.strategies.momentum import MomentumStrategy
from app.strategies.vwap import VWAPStrategy


@dataclass(slots=True, frozen=True)
class StrategyDefinition:
    """Describe one strategy entry in the registry."""

    name: str
    enabled: bool = True
    params: Mapping[str, Any] = field(default_factory=dict)
    risk_multiplier: float = 1.0


class StrategyRegistry:
    """Load strategy definitions and build strategy instances."""

    def __init__(self, definitions: Sequence[StrategyDefinition]) -> None:
        self._definitions = list(definitions)
        self._factories: dict[str, Callable[[Mapping[str, Any]], BaseStrategy]] = {
            "momentum": MomentumStrategy.from_config,
            "mean_reversion": MeanReversionStrategy.from_config,
            "vwap": VWAPStrategy.from_config,
            "breakout": BreakoutStrategy.from_config,
        }

    @classmethod
    def from_file(cls, path: str | Path) -> StrategyRegistry:
        """Load strategy definitions from a YAML file."""

        with Path(path).open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> StrategyRegistry:
        """Load strategy definitions from a mapping."""

        strategies = payload.get("strategies", [])
        definitions = [
            StrategyDefinition(
                name=str(item["name"]),
                enabled=bool(item.get("enabled", True)),
                params=dict(item.get("params", {})),
                risk_multiplier=float(item.get("risk_multiplier", 1.0)),
            )
            for item in strategies
        ]
        return cls(definitions)

    def build_enabled_strategies(self) -> list[BaseStrategy]:
        """Instantiate all enabled strategies in declaration order."""

        strategies: list[BaseStrategy] = []
        for definition in self._definitions:
            if not definition.enabled:
                continue
            factory = self._factories.get(definition.name)
            if factory is None:
                continue
            strategies.append(factory(definition.params))
        return strategies

    @property
    def definitions(self) -> list[StrategyDefinition]:
        """Expose the configured strategy definitions."""

        return list(self._definitions)
