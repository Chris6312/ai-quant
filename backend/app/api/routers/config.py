"""Configuration status endpoint — shows which API keys are configured."""

from __future__ import annotations

from fastapi import APIRouter

from app.config.settings import get_settings

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/keys")
async def get_key_status() -> dict[str, object]:
    """Return which API keys are set in .env — never returns values."""

    settings = get_settings()

    def _status(val: str | None) -> dict[str, object]:
        if not val:
            return {"configured": False, "hint": "Set in backend/.env"}
        # Show last 4 chars only for confirmation
        return {"configured": True, "preview": f"···{val[-4:]}"}

    return {
        "alpaca": {
            "api_key":    _status(settings.alpaca_api_key),
            "api_secret": _status(settings.alpaca_api_secret),
            "base_url":   settings.alpaca_base_url,
        },
        "tradier": {
            "api_key":    _status(settings.tradier_api_key),
            "account_id": _status(settings.tradier_account_id),
            "base_url":   settings.tradier_base_url,
        },
        "kraken": {
            "api_key":    _status(settings.kraken_api_key),
            "api_secret": _status(settings.kraken_api_secret),
            "base_url":   settings.kraken_base_url,
        },
        "env_file": "backend/.env",
        "note": "Restart the backend after editing .env for changes to take effect.",
    }
