from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from lightgbm.basic import LightGBMError
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.brokers.alpaca import AlpacaTrainingFetcher
from app.config.constants import (
    ALPACA_DEFAULT_SOURCE,
    CRYPTO_CSV_TRAINING_SOURCE,
    ML_CANDLE_USAGE,
)
from app.config.crypto_scope import KRAKEN_UNIVERSE
from app.config.settings import Settings
from app.config.settings import get_settings as load_settings
from app.db.models import CandleRow, PredictionRow, PredictionShapRow
from app.db.session import build_engine as create_engine
from app.db.session import build_session_factory as create_session_factory
from app.exceptions import ResearchParseError
from app.ml import job_store, model_registry
from app.ml.crypto_csv_ingestion import CryptoCsvTrainingIngestor
from app.ml.features import (
    ALL_FEATURES,
    FeatureEngineer,
    FeatureVector,
    ResearchInputs,
    build_feature_contract_summary,
    validate_feature_vector,
)
from app.ml.freshness import MlFreshnessResult, evaluate_crypto_ml_freshness
from app.ml.predictor import ModelPredictor
from app.ml.sentiment_refresh import (
    parse_crypto_symbol_list,
    run_crypto_sentiment_refresh_training,
)
from app.ml.stock_universe import StockUniverseLoader, StockUniverseSnapshot
from app.ml.trainer import TrainerConfig, TrainResult
from app.ml.training_inputs import (
    CryptoTrainingInputAssembler,
)
from app.ml.training_inputs import (
    train_crypto_model_from_db as train_crypto_model_from_db_impl,
)
from app.ml.training_inputs import (
    train_stock_model_from_db as train_stock_model_from_db_impl,
)
from app.models.domain import Candle
from app.repositories.candles import CandleRepository

router = APIRouter(prefix="/ml", tags=["ml"])
logger = logging.getLogger(__name__)


_CRYPTO_ALPACA_REQUEST_ALIASES: dict[str, str] = {
    "XDG/USD": "DOGE/USD",
}



class GainersFetcher(Protocol):
    async def get_top_gainers(self, *, limit: int) -> list[dict[str, object]]: ...


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
        .where(CandleRow.usage == ML_CANDLE_USAGE)
        .group_by(
            CandleRow.symbol,
            CandleRow.asset_class,
            CandleRow.timeframe,
        )
        .order_by(
            CandleRow.asset_class.asc(),
            CandleRow.symbol.asc(),
            CandleRow.timeframe.asc(),
        )
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

STOCK_DAILY_CANDLE_TARGET = 1000
STOCK_DAILY_CANDLE_MINIMUM = 750
STOCK_DAILY_TIMEFRAME = "1Day"
STOCK_DAILY_LOOKBACK_DAYS = 1600
CRYPTO_DAILY_TIMEFRAME = "1Day"
CRYPTO_FRESHNESS_MAX_AGE_DAYS = 2
STOCK_FRESHNESS_MAX_AGE_DAYS = 5

def _crypto_csv_source_dir() -> Path:
    """Return the repo-level crypto-history folder used for manual ML CSV imports."""

    cwd = Path.cwd()
    repo_history_dir = cwd.parent / "crypto-history"
    nested_history_dir = cwd / "backend" / "crypto-history"
    candidates = [
        cwd / "crypto-history",
        repo_history_dir if cwd.name == "backend" else nested_history_dir,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]

def _serialize_stock_universe(snapshot: StockUniverseSnapshot) -> dict[str, object]:
    supported = snapshot.supported_symbols
    unsupported = snapshot.unsupported_symbols
    return {
        "index": snapshot.index_name,
        "as_of": snapshot.as_of,
        "source_file": str(snapshot.file_path),
        "constituent_stock_count": snapshot.constituent_stock_count,
        "supported_symbol_count": len(supported),
        "unsupported_symbol_count": len(unsupported),
        "target_candles_per_symbol": STOCK_DAILY_CANDLE_TARGET,
        "minimum_candles_per_symbol": STOCK_DAILY_CANDLE_MINIMUM,
        "timeframe": STOCK_DAILY_TIMEFRAME,
        "lookback_days": STOCK_DAILY_LOOKBACK_DAYS,
        "sample_symbols": [symbol.symbol for symbol in supported[:12]],
        "unsupported_symbols": [
            {
                "symbol": symbol.symbol,
                "reason": symbol.unsupported_reason,
            }
            for symbol in unsupported
        ],
    }

def _load_stock_universe_snapshot() -> StockUniverseSnapshot:
    return StockUniverseLoader().load()

def _build_backfill_job(job_type: str, symbols: list[str]) -> Mapping[str, object]:
    job = _new_job(job_type, symbols)
    job_id = str(job["job_id"])
    total_symbols = len(symbols)
    total_batches = (
        ceil(total_symbols / AlpacaTrainingFetcher.max_symbols_per_request)
        if total_symbols > 0
        else 0
    )
    job_store.update_job(
        job_id,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
        total_symbols=total_symbols,
        done_symbols=0,
        current_symbol=None,
        total_batches=total_batches,
        done_batches=0,
        rows_fetched=0,
        current_timeframe=STOCK_DAILY_TIMEFRAME,
        status_message="Starting universe hydration",
        progress_pct=0,
        error=None,
        result=None,
    )
    refreshed = job_store.get_job(job_id)
    return refreshed if refreshed is not None else job

async def _backfill_stock_universe(*, target_candles: int) -> Mapping[str, object]:
    settings = get_settings()
    snapshot = _load_stock_universe_snapshot()
    supported_symbols = [symbol.symbol for symbol in snapshot.supported_symbols]
    if not supported_symbols:
        raise HTTPException(
            status_code=400,
            detail="stock universe does not contain supported symbols",
        )

    job = _build_backfill_job("stock_sp500_backfill", supported_symbols)
    job_id = str(job["job_id"])

    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    rows_fetched = 0
    try:
        async with session_factory() as session:
            repository = CandleRepository(session)
            fetcher = AlpacaTrainingFetcher(
                repository=repository,
                api_key=settings.alpaca_api_key,
                api_secret=settings.alpaca_api_secret,
                lookback_days=max(STOCK_DAILY_LOOKBACK_DAYS, int(target_candles * 1.6)),
            )
            rows_fetched = await fetcher.sync_universe(
                symbols=supported_symbols,
                timeframes=[STOCK_DAILY_TIMEFRAME],
            )

        result = {
            "rows_fetched": rows_fetched,
            "requested_symbols": len(snapshot.symbols),
            "supported_symbols": len(snapshot.supported_symbols),
            "unsupported_symbols": len(snapshot.unsupported_symbols),
            "target_candles_per_symbol": target_candles,
            "minimum_candles_per_symbol": STOCK_DAILY_CANDLE_MINIMUM,
            "timeframe": STOCK_DAILY_TIMEFRAME,
            "lookback_days": max(STOCK_DAILY_LOOKBACK_DAYS, int(target_candles * 1.6)),
            "source_file": str(snapshot.file_path),
        }
        job_store.update_job(
            job_id,
            done_symbols=len(supported_symbols),
            current_symbol=None,
            done_batches=ceil(
                len(supported_symbols)
                / AlpacaTrainingFetcher.max_symbols_per_request
            ),
            rows_fetched=rows_fetched,
            status_message="Universe hydration completed",
            progress_pct=100,
        )
        finished = job_store.finish_job(job_id, status="done", result=result)
        return finished if finished is not None else {
            "job_id": job_id,
            "result": result,
        }
    except Exception as exc:
        job_store.update_job(
            job_id,
            rows_fetched=rows_fetched,
            status_message="Universe hydration failed",
            progress_pct=0,
        )
        finished = job_store.finish_job(job_id, status="error", error=str(exc))
        if finished is not None:
            return finished
        raise

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

    statement = (
        select(CandleRow)
        .where(CandleRow.asset_class == asset_class)
        .where(CandleRow.timeframe == "1Day")
        .order_by(CandleRow.symbol.asc(), CandleRow.time.asc())
    )

    statement = statement.where(CandleRow.usage == ML_CANDLE_USAGE)

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

    default_sources = [
        ALPACA_DEFAULT_SOURCE,
        CRYPTO_CSV_TRAINING_SOURCE,
    ]

    try:
        async with session_factory() as session:
            result = await _training_status_stmt(session)
    except Exception:
        return {
            "source": ",".join(default_sources),
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
        row_count = (
            row_count_raw
            if isinstance(row_count_raw, int)
            else int(str(row_count_raw))
        )
        earliest = row.earliest
        latest = row.latest

        detail: dict[str, object] = {
            "symbol": symbol,
            "asset_class": asset_class,
            "timeframe": timeframe,
            "candle_count": row_count,
            "earliest": (
                earliest.isoformat()
                if hasattr(earliest, "isoformat")
                else earliest
            ),
            "latest": (
                latest.isoformat()
                if hasattr(latest, "isoformat")
                else latest
            ),
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
        "source": ",".join(default_sources),
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
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        result, _dataset = await train_crypto_model_from_db_impl(session)

    return result


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

def _normalize_model_artifact_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        return path
    return Path.cwd() / path

def _candidate_model_artifact_paths(model: model_registry.ModelRecord) -> list[Path]:
    raw_candidates: list[str] = []

    artifact_path = model.get("artifact_path")
    if isinstance(artifact_path, str) and artifact_path:
        raw_candidates.append(artifact_path)

    raw_best_fold = model.get("best_fold")
    best_fold = raw_best_fold if isinstance(raw_best_fold, int) else None
    raw_folds = model.get("folds")
    if isinstance(raw_folds, list):
        for fold in raw_folds:
            if not isinstance(fold, dict):
                continue
            fold_path = fold.get("model_path")
            if isinstance(fold_path, str) and fold_path:
                if best_fold is not None and fold.get("fold_index") == best_fold:
                    raw_candidates.insert(0, fold_path)
                else:
                    raw_candidates.append(fold_path)

    candidates: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_candidates:
        candidate = _normalize_model_artifact_path(raw_path)
        if candidate.suffix.lower() != ".lgbm":
            logger.info(
                "Ignoring unsupported %s model artifact candidate for model_id=%s path=%s",
                model.get("asset_class", "unknown"),
                model.get("model_id"),
                candidate,
            )
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
    return candidates

def _resolve_model_artifact_path(model: model_registry.ModelRecord) -> str:
    candidates = _candidate_model_artifact_paths(model)
    if not candidates:
        return ""
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])

def _iter_prediction_model_candidates(
    asset_class: str,
) -> Iterator[tuple[model_registry.ModelRecord, str]]:
    seen_model_ids: set[str] = set()
    for model in model_registry.list_models(asset_class):
        model_id = model.get("model_id")
        if isinstance(model_id, str) and model_id in seen_model_ids:
            continue
        if isinstance(model_id, str):
            seen_model_ids.add(model_id)

        resolved_path = _resolve_model_artifact_path(model)
        if not resolved_path:
            logger.warning(
                "Skipping %s model with no artifact candidates (model_id=%s)",
                asset_class,
                model.get("model_id"),
            )
            continue

        path_obj = Path(resolved_path)
        if path_obj.exists():
            yield model, resolved_path
            continue

        logger.warning(
            "Model artifact missing for %s model_id=%s status=%s candidates=%s",
            asset_class,
            model.get("model_id"),
            model.get("status"),
            [str(candidate) for candidate in _candidate_model_artifact_paths(model)],
        )

def _prediction_action(
    asset_class: str,
    direction: str,
    confidence: float,
    threshold: float,
) -> str:
    if confidence < threshold:
        return "skip"
    if direction == "flat":
        return "skip"
    if asset_class == "crypto" and direction == "short":
        return "skip"
    return "signal"

def _format_driver_value(feature: str, value: float) -> str:
    if feature.startswith("returns_") or feature in {"gap_open", "atr_pct_14"}:
        return f"{value * 100:+.1f}%"
    if feature in {"rsi_14", "adx_14", "day_of_week", "day_of_month", "days_to_month_end"}:
        return f"{value:.1f}"
    if feature.startswith("news_sentiment"):
        return f"{value:+.2f}"
    return f"{value:+.2f}"

def _select_top_driver(
    features: FeatureVector,
    model: model_registry.ModelRecord,
) -> str:
    importances = model.get("feature_importances")
    if not isinstance(importances, dict) or not importances:
        return "n/a"

    ranked: list[tuple[str, float]] = []
    for name, raw_importance in importances.items():
        if not isinstance(name, str) or name not in features:
            continue
        ranked.append((name, _coerce_numeric(raw_importance)))
    if not ranked:
        return "n/a"

    ranked.sort(key=lambda item: item[1], reverse=True)
    feature_name = ranked[0][0]
    feature_value = features.get(feature_name, 0.0)
    return f"{feature_name} → {_format_driver_value(feature_name, feature_value)}"

def _prediction_freshness(
    asset_class: str,
    rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not rows:
        return {
            "latest_candle_time": None,
            "lag_days": None,
            "is_stale": True,
            "status": "no_data",
        }

    latest_candle_time = max(
        datetime.fromisoformat(str(row["candle_time"]))
        for row in rows
    )
    now = datetime.now(tz=UTC)
    lag_days = max(0.0, (now - latest_candle_time).total_seconds() / 86400.0)
    max_age_days = (
        CRYPTO_FRESHNESS_MAX_AGE_DAYS
        if asset_class == "crypto"
        else STOCK_FRESHNESS_MAX_AGE_DAYS
    )
    is_stale = lag_days > float(max_age_days)
    return {
        "latest_candle_time": latest_candle_time.isoformat(),
        "lag_days": round(lag_days, 2),
        "is_stale": is_stale,
        "status": "stale" if is_stale else "fresh",
    }

async def _import_crypto_csv_candles() -> Mapping[str, object]:
    csv_dir = _crypto_csv_source_dir()
    if not csv_dir.exists():
        raise HTTPException(
            status_code=400,
            detail=f"crypto CSV folder not found: {csv_dir}",
        )

    csv_files = sorted(csv_dir.glob("*_1440.csv"))
    if not csv_files:
        raise HTTPException(
            status_code=400,
            detail=f"no Kraken 1D crypto CSV files found in {csv_dir}; expected *_1440.csv",
        )

    symbols = [file.stem for file in csv_files]
    job = _build_backfill_job("crypto_csv_import", symbols)
    job_id = str(job["job_id"])

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    try:
        async with session_factory() as session:
            repository = CandleRepository(session)
            ingestor = CryptoCsvTrainingIngestor(
                repository=repository,
                csv_dir=csv_dir,
            )
            summaries = await ingestor.ingest_files(csv_files)
            await session.commit()
    except ResearchParseError as exc:
        job_store.update_job(
            job_id,
            status_message="Crypto CSV import failed validation",
            progress_pct=0,
        )
        finished = job_store.finish_job(job_id, status="error", error=str(exc))
        if finished is not None:
            return finished
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        job_store.update_job(
            job_id,
            status_message="Crypto CSV import failed",
            progress_pct=0,
        )
        finished = job_store.finish_job(job_id, status="error", error=str(exc))
        if finished is not None:
            return finished
        raise

    rows_read = sum(summary.rows_read for summary in summaries)
    rows_written = sum(summary.rows_written for summary in summaries)
    imported_symbols = [summary.symbol for summary in summaries]
    job_store.update_job(
        job_id,
        done_symbols=len(imported_symbols),
        total_symbols=len(symbols),
        done_batches=len(imported_symbols),
        total_batches=len(symbols),
        current_symbol=None,
        progress_pct=100,
        status_message="Crypto CSV import completed",
        current_timeframe=CRYPTO_DAILY_TIMEFRAME,
        rows_fetched=rows_written,
    )
    finished = job_store.finish_job(
        job_id,
        status="done",
        result={
            "source_dir": str(csv_dir),
            "source": CRYPTO_CSV_TRAINING_SOURCE,
            "timeframe": CRYPTO_DAILY_TIMEFRAME,
            "files_seen": len(csv_files),
            "symbols_imported": imported_symbols,
            "rows_read": rows_read,
            "rows_written": rows_written,
        },
    )
    if finished is None:
        raise HTTPException(status_code=500, detail="crypto CSV import job could not be finalized")
    return finished


async def _list_existing_crypto_ml_symbols(session: AsyncSession) -> list[str]:
    statement = (
        select(CandleRow.symbol)
        .where(
            CandleRow.asset_class == "crypto",
            CandleRow.timeframe == CRYPTO_DAILY_TIMEFRAME,
            CandleRow.usage == ML_CANDLE_USAGE,
        )
        .distinct()
        .order_by(CandleRow.symbol)
    )
    result = await session.scalars(statement)
    return [str(symbol) for symbol in result.all()]


def _build_crypto_catchup_request_symbols(
    storage_symbols: Sequence[str],
) -> tuple[list[str], dict[str, str]]:
    request_symbols: list[str] = []
    storage_symbol_by_request_symbol: dict[str, str] = {}

    for storage_symbol in storage_symbols:
        request_symbol = _CRYPTO_ALPACA_REQUEST_ALIASES.get(
            storage_symbol, storage_symbol
        )
        request_symbols.append(request_symbol)
        storage_symbol_by_request_symbol[request_symbol] = storage_symbol

    return request_symbols, storage_symbol_by_request_symbol


async def _catch_up_crypto_daily_candles() -> Mapping[str, object]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        storage_symbols = await _list_existing_crypto_ml_symbols(session)

    if not storage_symbols:
        raise HTTPException(
            status_code=409,
            detail="crypto ML catch-up requires existing 1D ML candles from CSV import",
        )

    request_symbols, storage_symbol_by_request_symbol = _build_crypto_catchup_request_symbols(
        storage_symbols
    )
    job = _build_backfill_job("crypto_daily_catchup", storage_symbols)
    job_id = str(job["job_id"])

    total_rows = 0

    def _on_progress(done_batches: int, total_batches: int, rows_fetched: int) -> None:
        nonlocal total_rows
        total_rows = rows_fetched
        progress_pct = 0
        if total_batches > 0:
            progress_pct = round((done_batches / total_batches) * 100)
        job_store.update_job(
            job_id,
            done_symbols=min(
                done_batches * AlpacaTrainingFetcher.max_symbols_per_request,
                len(storage_symbols),
            ),
            total_symbols=len(storage_symbols),
            done_batches=done_batches,
            total_batches=total_batches,
            current_symbol=None,
            progress_pct=progress_pct,
            status_message="Refreshing crypto 1Day ML candles from Alpaca",
            current_timeframe=CRYPTO_DAILY_TIMEFRAME,
            rows_fetched=rows_fetched,
        )

    try:
        async with session_factory() as session:
            repository = CandleRepository(session)
            fetcher = AlpacaTrainingFetcher(
                repository=repository,
                api_key=settings.alpaca_api_key,
                api_secret=settings.alpaca_api_secret,
                lookback_days=30,
                storage_symbol_by_request_symbol=storage_symbol_by_request_symbol,
                latest_source=None,
            )
            total_rows = await fetcher.sync_universe(
                request_symbols,
                [CRYPTO_DAILY_TIMEFRAME],
                asset_class="crypto",
                progress_callback=_on_progress,
            )
    except Exception as exc:
        job_store.update_job(
            job_id,
            rows_fetched=total_rows,
            status_message="Crypto 1Day Alpaca refresh failed",
        )
        finished = job_store.finish_job(job_id, status="error", error=str(exc))
        if finished is not None:
            return finished
        raise

    job_store.update_job(
        job_id,
        done_symbols=len(storage_symbols),
        total_symbols=len(storage_symbols),
        done_batches=ceil(len(storage_symbols) / AlpacaTrainingFetcher.max_symbols_per_request),
        total_batches=ceil(len(storage_symbols) / AlpacaTrainingFetcher.max_symbols_per_request),
        current_symbol=None,
        progress_pct=100,
        status_message="Crypto 1Day Alpaca refresh completed",
        rows_fetched=total_rows,
    )
    finished = job_store.finish_job(
        job_id,
        status="done",
        result={
            "rows_written": total_rows,
            "symbols_checked": len(storage_symbols),
            "timeframe": CRYPTO_DAILY_TIMEFRAME,
            "source": ALPACA_DEFAULT_SOURCE,
        },
    )
    if finished is None:
        raise HTTPException(status_code=500, detail="crypto catch-up job could not be finalized")
    return finished

async def _ensure_crypto_ml_can_score() -> MlFreshnessResult:
    """Block crypto scoring when the ML daily candle lane is stale or incomplete."""

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    async with session_factory() as session:
        freshness = await evaluate_crypto_ml_freshness(session)

    if freshness.can_score:
        return freshness

    raise HTTPException(
        status_code=409,
        detail={
            "reason": freshness.block_reason,
            "message": "Predictions paused: ML data is stale or incomplete.",
            **freshness.to_api_payload(),
        },
    )


def _prediction_gate_outcome(action: str) -> str:
    if action == "signal":
        return "passed"
    return "blocked"


def _prediction_signal_event(row: Mapping[str, object]) -> dict[str, object] | None:
    if row.get("action") != "signal":
        return None
    return {
        "event_type": "ml_prediction_signal",
        "prediction_id": row.get("prediction_id"),
        "model_id": row.get("model_id"),
        "symbol": row.get("symbol"),
        "asset_class": row.get("asset_class"),
        "direction": row.get("direction"),
        "confidence": row.get("confidence"),
        "candle_time": row.get("candle_time"),
    }




def _prediction_api_row_from_db(row: PredictionRow) -> dict[str, object]:
    """Serialize one persisted prediction row for the ML API."""

    return {
        "prediction_id": row.id,
        "model_id": row.model_id,
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "direction": row.direction,
        "confidence": row.confidence,
        "class_probabilities": {
            "down": row.probability_down,
            "flat": row.probability_flat,
            "up": row.probability_up,
        },
        "top_driver": row.top_driver or "n/a",
        "candle_time": row.candle_time.isoformat(),
        "action": row.action,
        "confidence_threshold": row.confidence_threshold,
    }


def _prediction_empty_freshness() -> dict[str, object]:
    """Return a stable no-data freshness payload for persisted prediction reads."""

    return {
        "latest_candle_time": None,
        "lag_days": None,
        "is_stale": True,
        "status": "no_data",
    }


async def _read_persisted_prediction_snapshot(
    *,
    limit: int,
    asset_class: str | None,
) -> Mapping[str, object]:
    """Read the latest persisted prediction rows without rebuilding them."""

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    assets = [asset_class] if asset_class is not None else ["crypto", "stock"]

    async with session_factory() as session:
        statement = select(PredictionRow)
        if asset_class is not None:
            statement = statement.where(PredictionRow.asset_class == asset_class)
        statement = statement.order_by(
            PredictionRow.created_at.desc(),
            PredictionRow.confidence.desc(),
            PredictionRow.symbol.asc(),
        ).limit(limit)
        result = await session.scalars(statement)
        prediction_rows = list(result.all())

    api_rows = [_prediction_api_row_from_db(row) for row in prediction_rows]
    freshness_by_asset: dict[str, object] = {}
    for asset in assets:
        asset_rows = [row for row in api_rows if row["asset_class"] == asset]
        freshness_by_asset[asset] = _prediction_freshness(asset, asset_rows)
        if not asset_rows:
            freshness_by_asset[asset] = _prediction_empty_freshness()

    return {
        "predictions": api_rows,
        "count": len(api_rows),
        "active_model_ids": {
            "crypto": _get_active_model_id("crypto"),
            "stock": _get_active_model_id("stock"),
        },
        "freshness_by_asset": freshness_by_asset,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "persisted",
    }



async def _read_persisted_prediction_shap(
    prediction_id: str,
    *,
    limit: int | None = 10,
) -> Mapping[str, object]:
    """Read persisted SHAP rows for a persisted prediction."""

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        prediction = cast(
            PredictionRow | None,
            await session.scalar(
                select(PredictionRow).where(PredictionRow.id == prediction_id)
            ),
        )
        if prediction is None:
            raise HTTPException(status_code=404, detail="Prediction not found")

        shap_result = await session.scalars(
            select(PredictionShapRow)
            .where(PredictionShapRow.prediction_id == prediction_id)
            .order_by(PredictionShapRow.rank.asc())
        )
        all_shap_rows = cast(list[PredictionShapRow], list(shap_result.all()))
        shap_rows = all_shap_rows if limit is None else all_shap_rows[:limit]

    return {
        "prediction_id": prediction.id,
        "model_id": prediction.model_id,
        "symbol": prediction.symbol,
        "asset_class": prediction.asset_class,
        "rows": [
            {
                "prediction_id": row.prediction_id,
                "model_id": prediction.model_id,
                "symbol": prediction.symbol,
                "feature_name": row.feature,
                "feature_value": row.feature_value,
                "contribution": row.shap_value,
                "rank": row.rank,
            }
            for row in shap_rows
        ],
        "count": len(all_shap_rows),
        "returned_count": len(shap_rows),
        "limit": limit,
        "source": "persisted",
    }


@router.get("/predictions/shap")
async def get_prediction_shap_by_query(
    prediction_id: str = Query(..., description="Persisted prediction id"),
    limit: int = Query(10, ge=1, le=200, description="Maximum persisted SHAP rows to return"),
    include_all: bool = Query(False, alias="all", description="Return every persisted SHAP row"),
) -> Mapping[str, object]:
    """Read persisted SHAP rows using a query parameter-safe prediction id."""

    return await _read_persisted_prediction_shap(
        prediction_id,
        limit=None if include_all else limit,
    )


@router.get("/predictions/{prediction_id}/shap")
async def get_prediction_shap(
    prediction_id: str,
    limit: int = Query(10, ge=1, le=200, description="Maximum persisted SHAP rows to return"),
    include_all: bool = Query(False, alias="all", description="Return every persisted SHAP row"),
) -> Mapping[str, object]:
    """Read persisted SHAP rows for a persisted prediction."""

    return await _read_persisted_prediction_shap(
        prediction_id,
        limit=None if include_all else limit,
    )


async def generate_prediction_snapshot(
    *,
    limit: int = 200,
    asset_class: str | None = None,
) -> Mapping[str, object]:
    """Generate and persist prediction rows on demand or from the ML worker."""

    if asset_class is not None and asset_class not in {"crypto", "stock"}:
        raise HTTPException(status_code=400, detail="asset_class must be crypto or stock")

    assets = [asset_class] if asset_class is not None else ["crypto", "stock"]
    crypto_freshness: MlFreshnessResult | None = None
    if "crypto" in assets:
        crypto_freshness = await _ensure_crypto_ml_can_score()

    rows_by_asset: dict[str, list[dict[str, object]]] = {}
    for asset in assets:
        rows_by_asset[asset] = await _build_asset_predictions(asset, limit=limit)

    rows: list[dict[str, object]] = []
    for asset_rows in rows_by_asset.values():
        rows.extend(asset_rows)

    rows.sort(
        key=lambda row: (
            _coerce_numeric(row.get("confidence")),
            str(row.get("symbol") or ""),
        ),
        reverse=True,
    )
    visible_rows = rows[:limit]
    persisted_count = await _persist_prediction_snapshot(visible_rows)
    api_rows = [_prediction_api_row(row) for row in visible_rows]
    return {
        "predictions": api_rows,
        "count": len(api_rows),
        "persisted_count": persisted_count,
        "active_model_ids": {
            "crypto": _get_active_model_id("crypto"),
            "stock": _get_active_model_id("stock"),
        },
        "freshness_by_asset": {
            asset: (
                crypto_freshness.to_api_payload()
                if asset == "crypto" and crypto_freshness is not None
                else _prediction_freshness(asset, asset_rows)
            )
            for asset, asset_rows in rows_by_asset.items()
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source": "generated",
    }

async def _persist_prediction_snapshot(
    rows: Sequence[Mapping[str, object]],
) -> int:
    if not rows:
        return 0

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    persisted = 0

    async with session_factory() as session:
        for row in rows:
            prediction_id = str(row["prediction_id"])
            probabilities = row.get("class_probabilities")
            if not isinstance(probabilities, Mapping):
                continue
            candle_time = datetime.fromisoformat(str(row["candle_time"]))
            if candle_time.tzinfo is None:
                candle_time = candle_time.replace(tzinfo=UTC)
            action = str(row.get("action") or "skip")
            signal_event = _prediction_signal_event(row)
            prediction_row = PredictionRow(
                id=prediction_id,
                symbol=str(row["symbol"]),
                asset_class=str(row["asset_class"]),
                model_id=cast(str | None, row.get("model_id")),
                direction=str(row["direction"]),
                confidence=_coerce_numeric(row.get("confidence")),
                probability_down=_coerce_numeric(probabilities.get("down")),
                probability_flat=_coerce_numeric(probabilities.get("flat")),
                probability_up=_coerce_numeric(probabilities.get("up")),
                confidence_threshold=_coerce_numeric(row.get("confidence_threshold")),
                gate_outcome=_prediction_gate_outcome(action),
                action=action,
                top_driver=cast(str | None, row.get("top_driver")),
                candle_time=candle_time,
                feature_version="v1",
                signal_event_published=signal_event is not None,
                signal_event=signal_event,
                created_at=datetime.now(tz=UTC),
            )
            await session.merge(prediction_row)
            await session.execute(
                delete(PredictionShapRow).where(
                    PredictionShapRow.prediction_id == prediction_id
                )
            )
            shap_values = row.get("shap_values")
            feature_values = row.get("feature_values")
            if isinstance(shap_values, Mapping) and isinstance(feature_values, Mapping):
                ranked_shap = sorted(
                    (
                        (str(feature), _coerce_numeric(value))
                        for feature, value in shap_values.items()
                    ),
                    key=lambda item: abs(item[1]),
                    reverse=True,
                )
                for rank, (feature, shap_value) in enumerate(ranked_shap, start=1):
                    session.add(
                        PredictionShapRow(
                            id=f"{prediction_id}:{feature}",
                            prediction_id=prediction_id,
                            feature=feature,
                            feature_value=_coerce_numeric(feature_values.get(feature)),
                            shap_value=shap_value,
                            abs_value=abs(shap_value),
                            rank=rank,
                            created_at=datetime.now(tz=UTC),
                        )
                    )
            persisted += 1
        await session.commit()

    return persisted

async def _build_crypto_prediction_research_lookup(
    latest_by_symbol: Mapping[str, Sequence[Candle]],
) -> Mapping[str | tuple[str, date], ResearchInputs]:
    """Load date-specific sentiment inputs for latest crypto prediction candles."""

    if not latest_by_symbol:
        return {}

    symbols: list[str] = []
    sentiment_dates: list[date] = []
    for symbol, history in latest_by_symbol.items():
        if not history:
            continue
        symbols.append(symbol)
        prediction_date = history[-1].time.date()
        sentiment_dates.extend(
            prediction_date - timedelta(days=offset) for offset in range(6, -1, -1)
        )

    if not symbols or not sentiment_dates:
        return {}

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            assembler = CryptoTrainingInputAssembler()
            lookup = await assembler._build_sentiment_lookup(
                session,
                symbols=symbols,
                sentiment_dates=sentiment_dates,
            )
    finally:
        await engine.dispose()

    return cast(Mapping[str | tuple[str, date], ResearchInputs], lookup)


def _prediction_research_inputs(
    research_lookup: Mapping[str | tuple[str, date], ResearchInputs],
    *,
    symbol: str,
    prediction_date: date,
) -> ResearchInputs | None:
    """Return prediction-time research inputs using the trainer lookup convention."""

    dated = research_lookup.get((symbol, prediction_date))
    if dated is not None:
        return dated
    return research_lookup.get(symbol)


async def _build_asset_predictions(
    asset_class: str,
    *,
    limit: int,
    history_size: int = 220,
) -> list[dict[str, object]]:
    active_model = model_registry.get_active_model(asset_class)
    if active_model is None:
        logger.info("No active %s model found for predictions", asset_class)
        return []

    candles = await _load_training_candles(asset_class)
    if not candles:
        logger.info("No %s candles available for prediction generation", asset_class)
        return []

    predictor: ModelPredictor | None = None
    selected_model: model_registry.ModelRecord | None = None
    selected_model_path: str | None = None
    for candidate_model, candidate_path in _iter_prediction_model_candidates(asset_class):
        try:
            predictor = ModelPredictor(candidate_path, min_confidence=0.0)
            selected_model = candidate_model
            selected_model_path = candidate_path
            break
        except (LightGBMError, FileNotFoundError, OSError) as exc:
            logger.warning(
                "Skipping unusable %s model_id=%s artifact=%s error=%s",
                asset_class,
                candidate_model.get("model_id"),
                candidate_path,
                exc,
            )

    if predictor is None or selected_model is None or selected_model_path is None:
        logger.warning(
            "No usable %s prediction model found. active_model_id=%s",
            asset_class,
            active_model.get("model_id"),
        )
        return []

    selected_model_id = selected_model.get("model_id")
    active_model_id = active_model.get("model_id")
    if selected_model_id != active_model_id:
        logger.warning(
            "Falling back from active %s model_id=%s to model_id=%s artifact=%s",
            asset_class,
            active_model_id,
            selected_model_id,
            selected_model_path,
        )
    else:
        logger.info(
            "Using %s prediction model_id=%s artifact=%s",
            asset_class,
            selected_model_id,
            selected_model_path,
        )

    engineer = FeatureEngineer()
    threshold = _coerce_numeric(selected_model.get("confidence_threshold")) or 0.60
    latest_by_symbol: dict[str, list[Candle]] = {}
    for candle in candles:
        bucket = latest_by_symbol.setdefault(candle.symbol, [])
        bucket.append(candle)
        if len(bucket) > history_size:
            del bucket[0]

    research_lookup: Mapping[str | tuple[str, date], ResearchInputs] = {}
    if asset_class == "crypto":
        research_lookup = await _build_crypto_prediction_research_lookup(latest_by_symbol)

    rows: list[dict[str, object]] = []
    model_id_value = selected_model_id if isinstance(selected_model_id, str) else None
    for symbol, history in latest_by_symbol.items():
        prediction_date = history[-1].time.date()
        research_inputs = _prediction_research_inputs(
            research_lookup,
            symbol=symbol,
            prediction_date=prediction_date,
        )
        features = engineer.build(history, asset_class, research_inputs)
        if features is None:
            continue
        prediction = predictor.predict(features)
        if prediction is None:
            continue
        candle_time = history[-1].time.isoformat()
        shap_values = predictor.explain(features, class_index=prediction.class_index)
        action = _prediction_action(
            asset_class,
            prediction.direction,
            prediction.confidence,
            threshold,
        )
        rows.append(
            {
                "prediction_id": f"{asset_class}:{symbol}:{candle_time}",
                "model_id": model_id_value,
                "symbol": symbol,
                "asset_class": asset_class,
                "direction": prediction.direction,
                "confidence": round(prediction.confidence, 6),
                "class_probabilities": {
                    "down": round(prediction.class_probs[0], 6),
                    "flat": round(prediction.class_probs[1], 6),
                    "up": round(prediction.class_probs[2], 6),
                },
                "top_driver": _select_top_driver(features, selected_model),
                "candle_time": candle_time,
                "action": action,
                "confidence_threshold": threshold,
                "feature_values": {name: float(features[name]) for name in ALL_FEATURES},
                "shap_values": shap_values,
            }
        )

    rows.sort(
        key=lambda row: (
            _coerce_numeric(row.get("confidence")),
            str(row.get("symbol") or ""),
        ),
        reverse=True,
    )
    logger.info(
        "Built %s prediction rows=%s using model_id=%s",
        asset_class,
        len(rows),
        model_id_value,
    )
    return rows[:limit]


def _prediction_api_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"feature_values", "shap_values"}
    }


@router.get("/predictions")
async def get_predictions(
    limit: int = Query(default=50, ge=1, le=200),
    asset_class: str | None = Query(default=None),
) -> Mapping[str, object]:
    if asset_class is not None and asset_class not in {"crypto", "stock"}:
        raise HTTPException(status_code=400, detail="asset_class must be crypto or stock")
    return await _read_persisted_prediction_snapshot(
        limit=limit,
        asset_class=asset_class,
    )


@router.post("/predictions/run")
async def run_predictions(
    limit: int = Query(default=200, ge=1, le=500),
    asset_class: str | None = Query(default=None),
) -> Mapping[str, object]:
    return await generate_prediction_snapshot(limit=limit, asset_class=asset_class)

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
        "source_dir": str(_crypto_csv_source_dir()),
    }

@router.get("/gainers")
async def get_gainers(limit: int = Query(default=100, ge=1, le=100)) -> Mapping[str, object]:
    settings = get_settings()
    fetcher = cast(
        GainersFetcher,
        AlpacaTrainingFetcher(
            api_key=settings.alpaca_api_key,
            api_secret=settings.alpaca_api_secret,
        ),
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

@router.get("/stock/universe")
def get_stock_universe() -> Mapping[str, object]:
    snapshot = _load_stock_universe_snapshot()
    return {
        **_serialize_stock_universe(snapshot),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }

@router.post("/import/crypto-csv")
async def import_crypto_csv() -> Mapping[str, object]:
    _ensure_no_running_job()
    return await _import_crypto_csv_candles()

@router.post("/backfill/stocks/sp500")
async def backfill_sp500_stock_universe(
    target_candles: int = Query(default=STOCK_DAILY_CANDLE_TARGET, ge=500, le=2000),
) -> Mapping[str, object]:
    _ensure_no_running_job()
    return await _backfill_stock_universe(target_candles=target_candles)

@router.post("/backfill/crypto/daily-catchup")
async def catch_up_crypto_daily() -> Mapping[str, object]:
    _ensure_no_running_job()
    return await _catch_up_crypto_daily_candles()

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


@router.post("/train/crypto/sentiment-refresh")
async def train_crypto_after_sentiment_backfill(
    start_date: str = Query(
        ...,
        description="Historical news backfill start date, YYYY-MM-DD",
    ),
    end_date: str = Query(
        ...,
        description="Historical news backfill end date, YYYY-MM-DD",
    ),
    symbols: str | None = Query(
        default=None,
        description=(
            "Optional comma-separated crypto symbols. "
            "Defaults to configured crypto universe."
        ),
    ),
    prediction_limit: int = Query(default=200, ge=1, le=500),
    min_sentiment_coverage: float = Query(default=0.01, ge=0.0, le=1.0),
) -> Mapping[str, object]:
    """
    Force historical sentiment fetch before crypto retraining.

    The retrain step is blocked when persisted sentiment coverage is below the
    requested minimum threshold.
    """

    _ensure_no_running_job()
    symbol_list = parse_crypto_symbol_list(symbols)
    if not symbol_list:
        raise HTTPException(status_code=400, detail="at least one crypto symbol is required")

    job = _new_job("crypto_sentiment_refresh_train", symbol_list)
    job_id = str(job["job_id"])
    try:
        return await run_crypto_sentiment_refresh_training(
            job_id=job_id,
            start_date=start_date,
            end_date=end_date,
            symbols=symbols,
            prediction_limit=prediction_limit,
            min_sentiment_coverage=min_sentiment_coverage,
            train_model=_run_registered_training_job,
            generate_predictions=generate_prediction_snapshot,
        )
    except HTTPException as exc:
        job_store.update_job(
            job_id,
            status="failed",
            progress_pct=100,
            error=str(exc.detail),
        )
        raise


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
