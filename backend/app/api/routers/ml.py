from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.candle.kraken_worker import KRAKEN_UNIVERSE
from app.config.constants import ALPACA_DEFAULT_SOURCE, CRYPTO_CSV_TRAINING_SOURCE
from app.config.settings import Settings
from app.config.settings import get_settings as load_settings
from app.db.models import CandleRow
from app.db.session import build_engine as create_engine
from app.db.session import build_session_factory as create_session_factory
from app.ml import job_store, model_registry
from app.ml.features import (
    FeatureEngineer,
    ResearchInputs,
    build_feature_contract_summary,
    validate_feature_vector,
)
from app.ml.trainer import TrainerConfig, TrainResult, WalkForwardTrainer
from app.ml.training_inputs import train_stock_model_from_db as train_stock_model_from_db_impl
from app.models.domain import Candle

router = APIRouter(prefix="/ml", tags=["ml"])


class TrainingStatusRow(Protocol):
    symbol: object
    asset_class: object
    timeframe: object
    row_count: object
    earliest: object
    latest: object


class TrainingStatusResult(Protocol):
    def all(self) -> list[TrainingStatusRow]: ...


class TrainingDataset(Protocol):
    candles: Sequence[Candle]
    research_lookup: Mapping[str, object]


class FloatLike(Protocol):
    def __float__(self) -> float: ...


class SortableValue(Protocol):
    def __lt__(self, other: object) -> bool: ...


class FoldLike(Protocol):
    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    validation_sharpe: float
    validation_accuracy: float
    n_train_samples: int
    n_test_samples: int
    model_path: str


def get_settings() -> Settings:
    return load_settings()


def build_engine(settings: Settings) -> AsyncEngine:
    return create_engine(settings)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


async def _training_status_stmt(session: AsyncSession) -> TrainingStatusResult:
    statement = (
        select(
            CandleRow.symbol.label("symbol"),
            CandleRow.asset_class.label("asset_class"),
            CandleRow.timeframe.label("timeframe"),
            func.count().label("row_count"),
            func.min(CandleRow.time).label("earliest"),
            func.max(CandleRow.time).label("latest"),
        )
        .where(CandleRow.source.in_((ALPACA_DEFAULT_SOURCE, CRYPTO_CSV_TRAINING_SOURCE)))
        .group_by(CandleRow.symbol, CandleRow.asset_class, CandleRow.timeframe)
        .order_by(CandleRow.asset_class.asc(), CandleRow.symbol.asc(), CandleRow.timeframe.asc())
    )
    result = await session.execute(statement)
    return cast(TrainingStatusResult, result)


async def train_stock_model_from_db(
    session: AsyncSession,
    *,
    symbols: list[str] | None = None,
    timeframe: str = "1Day",
) -> tuple[TrainResult, object]:
    return await train_stock_model_from_db_impl(
        session,
        symbols=symbols,
        timeframe=timeframe,
    )


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


def _coerce_numeric(value: object | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (float, int)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    if hasattr(value, "__float__"):
        return float(cast(FloatLike, value))
    raise TypeError("numeric value could not be coerced to float")


async def _load_training_candles(asset_class: str) -> list[Candle]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    source = CRYPTO_CSV_TRAINING_SOURCE if asset_class == "crypto" else ALPACA_DEFAULT_SOURCE

    statement = (
        select(CandleRow)
        .where(CandleRow.asset_class == asset_class)
        .where(CandleRow.source == source)
        .where(CandleRow.timeframe == "1Day")
        .order_by(CandleRow.symbol.asc(), CandleRow.time.asc())
    )

    async with session_factory() as session:
        result: Result[tuple[CandleRow]] = await session.execute(statement)
        rows = list(result.scalars().all())

    return [
        Candle(
            time=row.time,
            symbol=row.symbol,
            asset_class=row.asset_class,
            timeframe=row.timeframe,
            open=_coerce_numeric(row.open),
            high=_coerce_numeric(row.high),
            low=_coerce_numeric(row.low),
            close=_coerce_numeric(row.close),
            volume=_coerce_numeric(row.volume),
            source=row.source,
        )
        for row in rows
    ]


async def _build_training_status() -> dict[str, object]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    try:
        async with session_factory() as session:
            result = await _training_status_stmt(session)
    except Exception:
        return {
            "source": "alpaca_training,crypto_csv_training",
            "total_candles": 0,
            "crypto_candles": 0,
            "stock_candles": 0,
            "crypto_symbols": 0,
            "stock_symbols": 0,
            "symbols_with_data": 0,
            "crypto_detail": [],
            "stock_detail": [],
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "cache_state": "fallback_empty",
        }

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
            "candle_count": row_count,
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
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "cache_state": "live",
    }


def _build_sample_history(symbol: str, asset_class: str) -> list[Candle]:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles: list[Candle] = []
    for index in range(220):
        base_price = 100.0 + (index * 0.75)
        open_price = base_price + ((index % 3) * 0.1)
        close_price = base_price + ((index % 5) * 0.2)
        high_price = close_price + 0.8
        low_price = open_price - 0.7
        candles.append(
            Candle(
                time=start + timedelta(days=index),
                symbol=symbol,
                asset_class=asset_class,
                timeframe="1Day",
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=1_000.0 + (index * 10.0),
                source="feature_contract_preview",
            )
        )
    return candles


def _build_feature_parity_report() -> Mapping[str, object]:
    engineer = FeatureEngineer()
    stock_features = engineer.build(
        _build_sample_history("AAPL", "stock"),
        "stock",
        ResearchInputs(
            news_sentiment_1d=0.8,
            news_sentiment_7d=0.6,
            news_article_count_7d=12,
            congress_buy_score=0.4,
            insider_buy_score=0.7,
            analyst_upgrade_score=0.5,
            watchlist_research_score=88.0,
        ),
    )
    crypto_features = engineer.build(
        _build_sample_history("BTC/USD", "crypto"),
        "crypto",
        ResearchInputs(
            news_sentiment_1d=0.8,
            news_sentiment_7d=0.6,
            news_article_count_7d=12,
            congress_buy_score=0.4,
            insider_buy_score=0.7,
            analyst_upgrade_score=0.5,
            watchlist_research_score=88.0,
        ),
    )

    if stock_features is None or crypto_features is None:
        raise ValueError("unable to build representative feature vectors")

    stock_validation = validate_feature_vector(stock_features)
    crypto_validation = validate_feature_vector(crypto_features)
    parity_keys_match = tuple(stock_features) == tuple(crypto_features)
    contract = build_feature_contract_summary()
    research_features = cast(list[str], contract["research_features"])
    all_features = cast(list[str], contract["all_features"])

    stock_non_default_research = sorted(
        name
        for name, value in stock_features.items()
        if name in research_features and value not in {0.0, 3.0, 999.0}
    )
    crypto_non_default_research = sorted(
        name
        for name, value in crypto_features.items()
        if name in research_features and value not in {0.0, 3.0, 999.0}
    )

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "feature_count": contract["feature_count"],
        "parity_ok": parity_keys_match and stock_validation.is_valid and crypto_validation.is_valid,
        "same_feature_order": parity_keys_match,
        "stock_contract_valid": stock_validation.is_valid,
        "crypto_contract_valid": crypto_validation.is_valid,
        "stock_missing": list(stock_validation.missing),
        "stock_extra": list(stock_validation.extra),
        "stock_nonfinite": list(stock_validation.nonfinite),
        "crypto_missing": list(crypto_validation.missing),
        "crypto_extra": list(crypto_validation.extra),
        "crypto_nonfinite": list(crypto_validation.nonfinite),
        "stock_research_features_with_signal": stock_non_default_research,
        "crypto_research_features_with_signal": crypto_non_default_research,
        "stock_preview": {name: stock_features[name] for name in all_features[:5]},
        "crypto_preview": {name: crypto_features[name] for name in all_features[:5]},
    }


def _serialize_folds(result: TrainResult) -> list[model_registry.FoldSummaryRecord]:
    raw_folds = getattr(result, "folds", [])
    if not isinstance(raw_folds, list):
        return []

    serialized: list[model_registry.FoldSummaryRecord] = []
    for raw_fold in raw_folds:
        fold = cast(FoldLike, raw_fold)
        serialized.append(
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
        )
    return serialized


def _register_training_result(
    *,
    asset_class: str,
    result: TrainResult,
    latest_job_id: str | None,
) -> model_registry.ModelRecord:
    trained_at = datetime.now(tz=UTC).isoformat()
    model_id = f"{asset_class}-{uuid4()}"
    trainer_config = TrainerConfig()
    serialized_folds = _serialize_folds(result)
    fold_count = getattr(result, "fold_count", len(serialized_folds))
    best_fold = getattr(result, "best_fold_index", 0)

    record: model_registry.ModelRecord = {
        "model_id": model_id,
        "asset_class": asset_class,
        "status": "active",
        "artifact_path": result.model_path,
        "trained_at": trained_at,
        "fold_count": int(fold_count),
        "best_fold": int(best_fold),
        "validation_accuracy": result.validation_accuracy,
        "validation_sharpe": result.validation_sharpe,
        "train_samples": result.n_train_samples,
        "test_samples": result.n_test_samples,
        "feature_count": len(result.feature_importances),
        "confidence_threshold": trainer_config.min_confidence_threshold,
        "latest_job_id": latest_job_id,
        "feature_importances": result.feature_importances,
        "folds": serialized_folds,
        "created_at": trained_at,
    }

    model_registry.register_model(record)
    return record


async def _train_crypto_result() -> TrainResult:
    candles = await _load_training_candles("crypto")
    trainer = WalkForwardTrainer(TrainerConfig())
    return await trainer.train(
        candles,
        "crypto",
        FeatureEngineer(),
    )


async def _train_stock_result(
    *,
    symbols: list[str] | None,
    timeframe: str,
) -> tuple[TrainResult, TrainingDataset]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        result, dataset_obj = await train_stock_model_from_db(
            session,
            symbols=symbols,
            timeframe=timeframe,
        )

    return result, cast(TrainingDataset, dataset_obj)


async def _run_registered_training_job(
    *,
    asset_class: str,
    latest_job_id: str | None,
    symbols: list[str] | None = None,
    timeframe: str = "1Day",
) -> tuple[model_registry.ModelRecord, Mapping[str, object] | None]:
    if latest_job_id is not None:
        job_store.update_job(
            latest_job_id,
            status="running",
            progress_pct=10,
            error=None,
        )

    try:
        if asset_class == "crypto":
            result = await _train_crypto_result()
            training_meta: Mapping[str, object] | None = None
        else:
            result, dataset = await _train_stock_result(
                symbols=symbols,
                timeframe=timeframe,
            )
            candles = list(dataset.candles)
            research_lookup = dataset.research_lookup
            training_meta = {
                "dataset_candles": len(candles),
                "dataset_symbols": len({candle.symbol for candle in candles}),
                "research_symbols": len(research_lookup),
                "timeframe": timeframe,
            }

        record = _register_training_result(
            asset_class=asset_class,
            result=result,
            latest_job_id=latest_job_id,
        )
    except Exception as exc:
        if latest_job_id is not None:
            job_store.update_job(
                latest_job_id,
                status="failed",
                progress_pct=100,
                error=str(exc),
            )
        raise

    if latest_job_id is not None:
        model_id_value = record.get("model_id")
        best_fold_value = record.get("best_fold")
        job_store.update_job(
            latest_job_id,
            status="done",
            progress_pct=100,
            result={
                "model_id": model_id_value if isinstance(model_id_value, str) else None,
                "best_fold": best_fold_value,
            },
        )

    return record, training_meta


async def _run_training_job(
    job_id: str,
    asset_class: str,
) -> None:
    await _run_registered_training_job(
        asset_class=asset_class,
        latest_job_id=job_id,
    )


def _ensure_no_running_job() -> None:
    for job in load_jobs():
        if job.get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail="another ML job is already running",
            )


def _get_active_model_id(asset_class: str) -> str | None:
    model = model_registry.get_active_model(asset_class)
    if model is None:
        return None
    model_id = model.get("model_id")
    return model_id if isinstance(model_id, str) else None


def _get_model_importance_rows(model: model_registry.ModelRecord) -> list[dict[str, object]]:
    raw_importances = model.get("feature_importances")
    if not isinstance(raw_importances, dict):
        return []

    rows: list[dict[str, object]] = []
    for feature, importance in raw_importances.items():
        if not isinstance(feature, str):
            continue
        rows.append({"feature": feature, "importance": _coerce_numeric(importance)})

    rows.sort(
        key=lambda row: cast(SortableValue, row["importance"]),
        reverse=True,
    )
    return rows


@router.get("/jobs")
def get_jobs() -> list[Mapping[str, object]]:
    return list(load_jobs())


@router.get("/jobs/active")
def get_active_job() -> Mapping[str, object]:
    for job in load_jobs():
        if job.get("status") == "running":
            return {"job": job}
    return {"job": None}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> Mapping[str, object]:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.get("/persistence")
async def get_persistence() -> Mapping[str, object]:
    jobs = list(load_jobs())
    active_job = next((job for job in jobs if job.get("status") == "running"), None)
    training = await _build_training_status()
    active_job_id = active_job.get("job_id") if active_job is not None else None
    return {
        "jobs": jobs,
        "active_job_id": active_job_id if isinstance(active_job_id, str) else None,
        "has_running_job": active_job is not None,
        "training": training,
        "persisted_at": datetime.now(tz=UTC).isoformat(),
    }


@router.get("/training/status")
async def get_training_status() -> Mapping[str, object]:
    return await _build_training_status()


@router.get("/features/contract")
def get_feature_contract() -> Mapping[str, object]:
    return build_feature_contract_summary()


@router.get("/features/parity")
def get_feature_parity() -> Mapping[str, object]:
    return _build_feature_parity_report()


@router.get("/crypto/universe")
def get_crypto_universe() -> Mapping[str, object]:
    return {
        "symbols": list(KRAKEN_UNIVERSE),
        "count": len(KRAKEN_UNIVERSE),
        "source_dir": str(Path("crypto-history")),
    }


@router.get("/gainers")
async def get_gainers(limit: int = Query(default=100, ge=1, le=100)) -> Mapping[str, object]:
    settings = get_settings()
    fetcher = AlpacaTrainingFetcher(
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
    )
    try:
        gainers = await fetcher.get_top_gainers(limit=limit)
        error: str | None = None
    except Exception as exc:
        gainers = []
        error = str(exc)

    response: dict[str, object] = {
        "gainers": gainers,
        "count": len(gainers),
        "fetched_at": datetime.now(tz=UTC).isoformat(),
    }
    if error is not None:
        response["error"] = error
    return response


@router.get("/models")
def get_models(asset_class: str | None = Query(default=None)) -> Mapping[str, object]:
    if asset_class is not None and asset_class not in {"crypto", "stock"}:
        raise HTTPException(status_code=400, detail="asset_class must be crypto or stock")

    models = model_registry.list_models(asset_class)
    return {
        "models": models,
        "active_by_asset": {
            "crypto": _get_active_model_id("crypto"),
            "stock": _get_active_model_id("stock"),
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


@router.get("/models/{model_id}")
def get_model(model_id: str) -> Mapping[str, object]:
    model = model_registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")
    return model


@router.get("/models/{model_id}/importances")
def get_model_importances(model_id: str) -> Mapping[str, object]:
    model = model_registry.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="model not found")

    sorted_rows = _get_model_importance_rows(model)
    return {
        "model_id": model_id,
        "asset_class": model.get("asset_class"),
        "feature_count": len(sorted_rows),
        "importances": sorted_rows,
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


@router.post("/train/crypto")
async def train_crypto() -> Mapping[str, object]:
    _ensure_no_running_job()
    job = _new_job("crypto_train", ["BTC/USD"])
    record, _ = await _run_registered_training_job(
        asset_class="crypto",
        latest_job_id=str(job["job_id"]),
    )

    return {
        "job_id": job["job_id"],
        "model_id": record["model_id"],
        "asset_class": "crypto",
        "artifact_path": record["artifact_path"],
        "best_fold": record["best_fold"],
        "fold_count": record["fold_count"],
        "validation_accuracy": record["validation_accuracy"],
        "validation_sharpe": record["validation_sharpe"],
        "train_samples": record["train_samples"],
        "test_samples": record["test_samples"],
        "feature_count": record["feature_count"],
        "status": record["status"],
    }


@router.post("/train/stock")
async def train_stock(
    symbols: str | None = None,
    timeframe: str = "1Day",
) -> Mapping[str, object]:
    _ensure_no_running_job()

    if symbols:
        parsed_symbols = [
            item.strip()
            for item in symbols.split(",")
            if item.strip()
        ]
    else:
        parsed_symbols = None

    symbol_list = parsed_symbols if parsed_symbols is not None else ["TOP100"]
    job = _new_job("stock_train", symbol_list)

    record, training_meta = await _run_registered_training_job(
        asset_class="stock",
        latest_job_id=str(job["job_id"]),
        symbols=parsed_symbols,
        timeframe=timeframe,
    )

    meta = training_meta if training_meta is not None else {}

    return {
        "job_id": job["job_id"],
        "model_id": record["model_id"],
        "asset_class": "stock",
        "dataset_candles": meta.get("dataset_candles"),
        "dataset_symbols": meta.get("dataset_symbols"),
        "research_symbols": meta.get("research_symbols"),
        "timeframe": meta.get("timeframe"),
        "validation_sharpe": record["validation_sharpe"],
        "validation_accuracy": record["validation_accuracy"],
        "n_train_samples": record["train_samples"],
        "n_test_samples": record["test_samples"],
        "feature_importances": record["feature_importances"],
        "model_path": record["artifact_path"],
        "best_fold": record["best_fold"],
        "fold_count": record["fold_count"],
        "status": record["status"],
    }


@router.get("/health")
async def ml_health() -> Mapping[str, str]:
    return {"status": "ok"}