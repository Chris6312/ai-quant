"""Direction gating for long-only and short-eligible rules."""

from app.config.constants import STOCK_SHORT_BALANCE_THRESHOLD


class DirectionGate:
    """Enforce crypto long-only and stock short balance rules."""

    def passes(self, asset_class: str, direction: str, stock_balance: float) -> bool:
        """Return True when the proposed direction is allowed."""

        if asset_class == "crypto":
            return direction != "short"
        if asset_class == "stock" and direction == "short":
            return stock_balance > STOCK_SHORT_BALANCE_THRESHOLD
        return True
