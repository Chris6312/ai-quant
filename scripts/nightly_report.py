"""CLI stub for generating the nightly trading report.

This script prints a small placeholder report to stdout and exits 0. It is a
stub until real data sources and formatting are implemented.

TODO:
    - query portfolio_snapshots for date
    - query trades for date
    - query app.ml.drift_monitor for feature importance delta

"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime, UTC
from typing import Final

ROOT: Path = Path(__file__).resolve().parents[1]
BACKEND_DIR: Path = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import structlog  # type: ignore

    logger = structlog.get_logger()
except Exception:  # pragma: no cover - fallback when structlog not installed
    class _FallbackLogger:
        def info(self, *args: object, **kwargs: object) -> None:
            print("INFO:", *args)

        def warning(self, *args: object, **kwargs: object) -> None:
            print("WARN:", *args)

        def error(self, *args: object, **kwargs: object) -> None:
            print("ERROR:", *args)

    logger = _FallbackLogger()  # type: ignore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the nightly report.

    Args:
        argv: Optional arg list for testing.
    Returns:
        Parsed namespace with date and output.
    """

    parser = argparse.ArgumentParser(description="Nightly trading report (stub)")
    parser.add_argument("--date", default=datetime.now(tz=UTC).date().isoformat(), help="ISO date string (YYYY-MM-DD)")
    parser.add_argument("--output", choices=['stdout', 'slack', 'email'], default='stdout', help="Where to send the report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the nightly report generator (stub).

    Returns:
        Exit status code.
    """

    args = parse_args(argv)
    logger.info("nightly_report called", date=args.date, output=args.output)

    # TODO: query portfolio_snapshots for date
    # TODO: query trades for date
    # TODO: query app.ml.drift_monitor for feature importance delta

    print(f"Nightly Report for {args.date}")
    print("Total NAV: TBD")
    print("Daily P&L: TBD")
    print("Open positions: TBD")
    print("Model drift status: TBD")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
