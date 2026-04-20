"""Tests for application settings."""

from app.config.settings import Settings


def test_settings_defaults() -> None:
    """Settings expose the expected defaults."""

    settings = Settings()
    assert settings.app_name == "ml-trading-bot"
    assert settings.environment == "dev"
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
