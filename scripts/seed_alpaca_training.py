"""Seed Alpaca training candles into the TimescaleDB candle table."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.config.constants import ALPACA_DEFAULT_TIMEFRAME
from app.config.settings import Settings
from app.db.session import build_engine, build_session_factory
from app.repositories.candles import CandleRepository


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the seeding script."""

    parser = argparse.ArgumentParser(description="Seed Alpaca training candles")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbol list")
    parser.add_argument(
        "--timeframes",
        default=ALPACA_DEFAULT_TIMEFRAME,
        help="Comma-separated timeframe list",
    )
    return parser.parse_args()


async def run(symbols: list[str], timeframes: list[str]) -> int:
    """Run the one-time sync job."""

    settings = Settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            repository = CandleRepository(session)
            fetcher = AlpacaTrainingFetcher(
                repository=repository,
                base_url=settings.alpaca_base_url,
                api_key=settings.alpaca_api_key,
                api_secret=settings.alpaca_api_secret,
            )
            return await fetcher.sync_universe(symbols, timeframes)
    finally:
        await engine.dispose()


def main() -> None:
    """Run the Alpaca seeding script."""

    args = parse_args()
    symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    timeframes = [timeframe.strip() for timeframe in args.timeframes.split(",") if timeframe.strip()]
    total_rows = asyncio.run(run(symbols, timeframes))
    print(f"Seeded {total_rows} Alpaca training candles")


if __name__ == "__main__":
    main()
