from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.ml import job_store, model_registry
from app.ml.features import FeatureEngineer
from app.ml.trainer import TrainerConfig, TrainResult, WalkForwardTrainer
from app.models.domain import Candle

router = APIRouter(prefix="/ml", tags=["ml"])


class AsyncSessionContext(Protocol):
    async def __aenter__(self) -> object: ...
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None: ...


class TrainingStatusRow(Protocol):
    symbol: object
    asset_class: object
    timeframe: object
    row_count: object
    earliest: object
    latest: object


class TrainingStatusResult(Protocol):
    def all(self) -> list[TrainingStatusRow]: ...


class _PlaceholderSession:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        del exc_type, exc, tb


def get_settings() -> object:
    return object()


def build_engine(settings: object) -> object:
    del settings
    return object()


def build_session_factory(engine: object) -> Callable[[], AsyncSessionContext]:
    del engine

    def _factory() -> AsyncSessionContext:
        return _PlaceholderSession()

    return _factory


async def _training_status_stmt(session: object) -> TrainingStatusResult:
    del session
    raise NotImplementedError


async def train_stock_model_from_db(
    session: object,
    *,
    symbols: list[str] | None = None,
    timeframe: str = "1Day",
) -> tuple[TrainResult, object]:
    del session, symbols, timeframe
    raise NotImplementedError


def load_jobs() -> Sequence[Mapping[str, object]]:
    return job_store.list_jobs()


def _new_job(job_type: str, symbols: list[str]) -> Mapping[str, object]:
    job_id = str(uuid4())
    record: job_store.JobRecord = {
        "job_id": job_id,
        "type": job_type,
        "asset_class": "crypto" if "crypto" in job_type else "stock",
        "symbols": symbols,
        "status": "pending",
    }
    job_store.create_job(record)
    return record


async def _load_training_candles(asset_class: str) -> list[Candle]:
    del asset_class
    raise NotImplementedError


async def _build_training_status() -> dict[str, object]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        result = await _training_status_stmt(session)

    rows = result.all()

    total_candles = 0
    crypto_candles = 0
    stock_candles = 0
    crypto_symbols = 0
    stock_symbols = 0
    crypto_detail: list[dict[str, object]] = []
    stock_detail: list[dict[str, object]] = []

    for row in rows:
        symbol = str(row.symbol)
        asset_class = str(row.asset_class)
        timeframe = str(row.timeframe)
        row_count_raw = row.row_count
        row_count = row_count_raw if isinstance(row_count_raw, int) else int(str(row_count_raw))
        earliest = row.earliest
        latest = row.latest

        detail: dict[str, object] = {
            "symbol": symbol,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "row_count": row_count,
            "earliest": earliest.isoformat() if hasattr(earliest, "isoformat") else earliest,
            "latest": latest.isoformat() if hasattr(latest, "isoformat") else latest,
        }

        total_candles += row_count
        if asset_class == "crypto":
            crypto_candles += row_count
            crypto_symbols += 1
            crypto_detail.append(detail)
        else:
            stock_candles += row_count
            stock_symbols += 1
            stock_detail.append(detail)

    return {
        "source": "alpaca_training,crypto_csv_training",
        "total_candles": total_candles,
        "crypto_candles": crypto_candles,
        "stock_candles": stock_candles,
        "crypto_symbols": crypto_symbols,
        "stock_symbols": stock_symbols,
        "symbols_with_data": crypto_symbols + stock_symbols,
        "crypto_detail": crypto_detail,
        "stock_detail": stock_detail,
    }


async def _run_training_job(
    job_id: str,
    asset_class: str,
) -> Mapping[str, object]:
    job_store.update_job(
        job_id,
        status="running",
        progress_pct=10,
        error=None,
    )

    candles = await _load_training_candles(asset_class)

    trainer = WalkForwardTrainer(TrainerConfig())

    result: TrainResult = await trainer.train(
        candles,
        asset_class,
        FeatureEngineer(),
    )

    trained_at = datetime.now(tz=UTC).isoformat()
    model_id = f"{asset_class}-{job_id}"
    best_fold = result.best_fold_index

    folds: list[model_registry.FoldSummaryRecord] = [
        {
            "fold_index": fold.fold_index,
            "train_start": fold.train_start.isoformat(),
            "train_end": fold.train_end.isoformat(),
            "test_start": fold.test_start.isoformat(),
            "test_end": fold.test_end.isoformat(),
            "validation_sharpe": fold.validation_sharpe,
            "validation_accuracy": fold.validation_accuracy,
            "n_train_samples": fold.n_train_samples,
            "n_test_samples": fold.n_test_samples,
            "model_path": fold.model_path,
        }
        for fold in result.folds
    ]

    record: model_registry.ModelRecord = {
        "model_id": model_id,
        "asset_class": asset_class,
        "status": "active",
        "artifact_path": result.model_path,
        "trained_at": trained_at,
        "fold_count": result.fold_count,
        "best_fold": best_fold,
        "validation_accuracy": result.validation_accuracy,
        "validation_sharpe": result.validation_sharpe,
        "train_samples": result.n_train_samples,
        "test_samples": result.n_test_samples,
        "feature_count": len(result.feature_importances),
        "confidence_threshold": TrainerConfig().min_confidence_threshold,
        "latest_job_id": job_id,
        "feature_importances": result.feature_importances,
        "folds": folds,
        "created_at": trained_at,
    }

    model_registry.register_model(record)

    job_store.update_job(
        job_id,
        status="done",
        progress_pct=100,
        result={
            "model_id": model_id,
            "best_fold": best_fold,
        },
    )

    return {
        "model_id": model_id,
        "best_fold": best_fold,
    }


@router.get("/jobs/active")
def get_active_job() -> Mapping[str, object]:
    for job in load_jobs():
        if job.get("status") == "running":
            return {"job": job}
    return {"job": None}


def _ensure_no_running_job() -> None:
    for job in load_jobs():
        if job.get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail="another ML job is already running",
            )


@router.post("/train/crypto")
async def train_crypto() -> Mapping[str, object]:
    _ensure_no_running_job()
    job = _new_job("crypto_train", ["BTC/USD"])
    return await _run_training_job(str(job["job_id"]), "crypto")


@router.post("/train/stock")
async def train_stock(
    symbols: str | None = None,
    timeframe: str = "1Day",
) -> Mapping[str, object]:
    _ensure_no_running_job()

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    parsed_symbols = (
        [item.strip() for item in symbols.split(",") if item.strip()]
        if symbols
        else None
    )

    async with session_factory() as session:
        result, dataset = await train_stock_model_from_db(
            session,
            symbols=parsed_symbols,
            timeframe=timeframe,
        )

    candles = getattr(dataset, "candles", [])
    research_lookup = getattr(dataset, "research_lookup", {})

    dataset_symbols = len({candle.symbol for candle in candles})

    return {
        "asset_class": "stock",
        "dataset_candles": len(candles),
        "dataset_symbols": dataset_symbols,
        "research_symbols": len(research_lookup),
        "validation_sharpe": result.validation_sharpe,
        "validation_accuracy": result.validation_accuracy,
        "n_train_samples": result.n_train_samples,
        "n_test_samples": result.n_test_samples,
        "feature_importances": result.feature_importances,
        "model_path": result.model_path,
    }


@router.get("/health")
async def ml_health() -> Mapping[str, str]:
    return {"status": "ok"}