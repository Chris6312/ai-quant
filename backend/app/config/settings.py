"""Runtime configuration for the ML trading bot backend."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = Field(default="ml-trading-bot")
    environment: str = Field(default="dev")
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/trading_bot")
    redis_url: str = Field(default="redis://localhost:6379/0")
    log_level: str = Field(default="INFO")
    enable_sql_echo: bool = Field(default=False)
    alpaca_base_url: str = Field(default="https://data.alpaca.markets/v2")
    alpaca_api_key: str | None = Field(default=None)
    alpaca_api_secret: str | None = Field(default=None)
    tradier_base_url: str = Field(default="https://api.tradier.com/v1")
    tradier_account_id: str | None = Field(default=None)
    tradier_api_key: str | None = Field(default=None)
    kraken_base_url: str = Field(default="https://api.kraken.com/0/public")
    kraken_private_base_url: str = Field(default="https://api.kraken.com/0/private")
    kraken_api_key: str | None = Field(default=None)
    kraken_api_secret: str | None = Field(default=None)

    research_news_base_url: str = Field(default="https://api.benzinga.com/api/v2")
    research_news_api_key: str | None = Field(default=None)
    research_finbert_model_name: str = Field(default="ProsusAI/finbert")
    research_house_base_url: str = Field(default="https://housestockwatcher.com")
    research_senate_base_url: str = Field(default="https://senatestockwatcher.com")
    research_insider_base_url: str = Field(default="https://api.secfilingdata.com")
    research_insider_api_key: str | None = Field(default=None)
    research_analyst_base_url: str = Field(default="https://api.benzinga.com/api/v2")
    coingecko_base_url: str = Field(default="https://api.coingecko.com/api/v3")
    coingecko_api_key: str | None = Field(default=None)
    coingecko_api_key_header: str = Field(default="x-cg-demo-api-key")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
