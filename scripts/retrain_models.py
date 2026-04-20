"""CLI stub for retraining ML models.

This script reserves the CLI contract for the ML trainer. It is a stub and will
exit 0 with a clear message until the `app.ml` module is implemented.

TODO:
    - import and call app.ml.trainer.WalkForwardTrainer
    - compare validation Sharpe vs deployed model
    - write model to models/model_{asset_class}.lgbm if improved or --force

"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final
from datetime import datetime, UTC

ROOT: Path = Path(__file__).resolve().parents[1]
BACKEND_DIR: Path = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import structlog  # type: ignore

    logger = structlog.get_logger()
except Exception:  # pragma: no cover - fallback when structlog not installed
    class _FallbackLogger:
        """Tiny fallback logger that prints to stdout when structlog is unavailable."""

        def info(self, *args: object, **kwargs: object) -> None:
            print("INFO:", *args)

        def warning(self, *args: object, **kwargs: object) -> None:
            print("WARN:", *args)

        def error(self, *args: object, **kwargs: object) -> None:
            print("ERROR:", *args)

    logger = _FallbackLogger()  # type: ignore


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Optional list of arguments for testing; defaults to sys.argv[1:]

    Returns:
        Parsed namespace with attributes: asset_class, dry_run, force.
    """

    parser = argparse.ArgumentParser(description="Retrain ML models (stub)")
    parser.add_argument(
        "--asset-class",
        choices=["stock", "crypto", "both"],
        default="both",
        help="Which asset class to train (stock|crypto|both)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate but do not write model files")
    parser.add_argument("--force", action="store_true", help="Deploy even if validation Sharpe does not improve")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the retrain CLI.

    This stub prints a clear message and exits 0. When implemented the trainer
    will be invoked here.

    Returns:
        Exit code integer.
    """

    args = parse_args(argv)
    logger.info("retrain_models called", asset_class=args.asset_class, dry_run=bool(args.dry_run), force=bool(args.force))

    now_iso: str = datetime.now(tz=UTC).isoformat()
    logger.warning("ML module not yet implemented", timestamp=now_iso)

    # TODO: Wire into app.ml.trainer.WalkForwardTrainer
    # TODO: Load historical candles via repositories and build FeatureEngineer
    # TODO: Run trainer.train(...) and compare TrainResult.validation_sharpe
    # TODO: Save model file to models/model_{asset_class}.lgbm if improved or --force

    print("ML module not yet implemented — this is a stub. See TODOs in script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
