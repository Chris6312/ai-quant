"""Import Bitcoin dominance CSV history for crypto ML features."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.config.settings import get_settings
from app.db.session import build_engine, build_session_factory
from app.ml.btc_dominance_loader import (
    BitcoinDominanceImportResult,
    import_btc_dominance_csv,
)


def main() -> None:
    """Run the BTC dominance CSV import command."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-path", required=True, help="Path to BTC dominance CSV")
    args = parser.parse_args()
    result = asyncio.run(_run(Path(args.csv_path)))
    print(
        "Imported BTC dominance rows: "
        f"{result.row_count} ({result.start_date} to {result.end_date})"
    )


async def _run(csv_path: Path) -> BitcoinDominanceImportResult:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    async with session_factory() as session:
        result = await import_btc_dominance_csv(session, csv_path)
    await engine.dispose()
    return result


if __name__ == "__main__":
    main()
