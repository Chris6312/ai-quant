"""Machine learning and research pipeline triggers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, NamedTuple, Protocol, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_candle_repository
from app.brokers.alpaca import AlpacaTrainingFetcher
from app.candle.kraken_worker import KRAKEN_UNIVERSE
from app.config.constants import ALPACA_DEFAULT_SOURCE, CRYPTO_CSV_TRAINING_SOURCE
from app.config.settings import get_settings
from app.db.models import CandleRow
from app.db.session import build_engine, build_session_factory
from app.ml.crypto_csv_ingestion import CryptoCsvTrainingIngestor
from app.ml.features import ALL_FEATURES, FeatureEngineer, build_feature_contract_summary
from app.ml.job_store import create_job, finish_job, update_job
from app.ml.job_store import get_job as load_job
from app.ml.job_store import list_jobs as load_jobs
from app.ml.model_registry import (
    FoldSummaryRecord,
    ModelRecord,
    get_active_model,
    get_model,
    register_model,
)
from app.ml.model_registry import list_models as load_models
from app.ml.trainer import FoldResult, TrainerConfig, WalkForwardTrainer
from app.ml.training_status_cache import (
    get_or_build_training_status,
    mark_training_status_stale,
    rebuild_training_status,
)
from app.models.domain import Candle
from app.repositories.candles import CandleRepository

router = APIRouter(prefix="/ml", tags=["ml"])

_TRAINING_SOURCES = (ALPACA_DEFAULT_SOURCE, CRYPTO_CSV_TRAINING_SOURCE)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CRYPTO_HISTORY_DIR = _PROJECT_ROOT / "crypto-history"


class TrainingStatusRow(NamedTuple):
    symbol: str
    asset_class: str
    timeframe: str
    row_count: int
    earliest: datetime | None
    latest: datetime | None


RawTrainingStatusRow = tuple[object, object, object, object, object, object]


class TrainingStatusResult(Protocol):
    def all(self) -> list[object]:
        """Return grouped training status rows."""


class StockBackfillRequest(BaseModel):
    symbols: list[str]
    timeframe: str = "1Day"
    lookback_days: int = 365


class CryptoBackfillRequest(BaseModel):
    lookback_days: int = 0


class MlPersistenceResponse(BaseModel):
    jobs: list[dict[str, object]]
    active_job_id: str | None
    has_running_job: bool
    training: dict[str, object]
    persisted_at: str


class GainersResponse(BaseModel):
    gainers: list[dict[str, object]]
    count: int
    fetched_at: str
    error: str | None = None


class GainersSnapshotRow(NamedTuple):
    symbol: str
    price: float | None
    percent_change: float | None
    volume: float | None


class ModelRegistryResponse(BaseModel):
    models: list[ModelRecord]
    active_by_asset: dict[str, str | None]
    generated_at: str


class TrainModelResponse(BaseModel):
    job: dict[str, object]
    active_model_id: str | None = None


def _coerce_numeric(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0


async def _load_training_candles(asset_class: str) -> list[Candle]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        stmt = (
            select(CandleRow)
            .where(
                CandleRow.asset_class == asset_class,
                CandleRow.source.in_(_TRAINING_SOURCES),
            )
            .order_by(CandleRow.symbol.asc(), CandleRow.time.asc())
        )
        rows = list((await session.scalars(stmt)).all())

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


def _fold_record(fold: FoldResult) -> FoldSummaryRecord:
    return {
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


async def _run_training_job(job_id: str, asset_class: str) -> None:
    mark_training_status_stale(f"{asset_class}_train_started")
    update_job(
        job_id,
        current_timeframe="1Day",
        status_message="loading training candles",
        progress_pct=5,
    )

    try:
        candles = await _load_training_candles(asset_class)
        if not candles:
            raise ValueError(f"No {asset_class} training candles available")

        unique_symbols = sorted({candle.symbol for candle in candles})
        update_job(
            job_id,
            symbols=unique_symbols,
            total_symbols=len(unique_symbols),
            rows_fetched=len(candles),
            status_message=f"loaded {len(candles)} candles across {len(unique_symbols)} symbols",
            progress_pct=15,
        )

        trainer = WalkForwardTrainer(
            TrainerConfig(model_dir=str(_PROJECT_ROOT / "backend" / "models"))
        )

        def _progress_callback(
            current_fold: int,
            total_folds: int,
            message: str | None = None,
        ) -> None:
            pct = 20 + int((current_fold / max(total_folds, 1)) * 60)
            status_message = message or f"training fold {current_fold} of {total_folds}"
            update_job(
                job_id,
                current_symbol=f"fold {current_fold}/{total_folds}",
                total_batches=total_folds,
                done_batches=max(current_fold - 1, 0),
                progress_pct=pct,
                status_message=status_message,
            )

        result = await trainer.train(
            candles=candles,
            asset_class=asset_class,
            feature_engineer=FeatureEngineer(),
            progress_callback=_progress_callback,
        )

        model_id = f"{asset_class}-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}"
        record = register_model(
            {
                "model_id": model_id,
                "asset_class": asset_class,
                "status": "active",
                "artifact_path": result.model_path,
                "trained_at": datetime.now(tz=UTC).isoformat(),
                "fold_count": result.fold_count,
                "best_fold": result.best_fold_index,
                "validation_accuracy": result.validation_accuracy,
                "validation_sharpe": result.validation_sharpe,
                "train_samples": result.n_train_samples,
                "test_samples": result.n_test_samples,
                "feature_count": len(ALL_FEATURES),
                "confidence_threshold": trainer.config.min_confidence_threshold,
                "latest_job_id": job_id,
                "feature_importances": result.feature_importances,
                "folds": [_fold_record(fold) for fold in result.folds],
            }
        )

        finish_job(
            job_id,
            status="done",
            result={
                "asset_class": asset_class,
                "model_id": record["model_id"],
                "artifact_path": result.model_path,
                "fold_count": result.fold_count,
                "best_fold": result.best_fold_index,
                "validation_accuracy": result.validation_accuracy,
                "validation_sharpe": result.validation_sharpe,
                "train_samples": result.n_train_samples,
                "test_samples": result.n_test_samples,
            },
        )
        update_job(
            job_id,
            current_symbol=None,
            current_timeframe=None,
            done_batches=result.fold_count,
            total_batches=result.fold_count,
            progress_pct=100,
            status_message=f"completed {asset_class} training",
        )
    except Exception as exc:
        finish_job(job_id, status="error", error=str(exc))
        update_job(job_id, status_message="training failed")


@router.get("/features/contract")
async def get_feature_contract() -> dict[str, object]:
    """Return the canonical ML feature contract used by training and inference."""

    return build_feature_contract_summary()


def _resolve_asset_class(job_type: str) -> str:
    if "crypto" in job_type:
        return "crypto"
    if "stock" in job_type or "gainers" in job_type:
        return "stock"
    return "mixed"


def _new_job(job_type: str, symbols: list[str]) -> dict[str, object]:
    now = datetime.now(tz=UTC)
    job = create_job(
        {
            "job_id": f"{job_type}-{now.strftime('%Y%m%d-%H%M%S')}",
            "type": job_type,
            "asset_class": _resolve_asset_class(job_type),
            "symbols": symbols,
            "status": "running",
            "started_at": now.isoformat(),
            "finished_at": None,
            "total_symbols": len(symbols),
            "done_symbols": 0,
            "current_symbol": None,
            "current_timeframe": None,
            "total_batches": 0,
            "done_batches": 0,
            "rows_fetched": 0,
            "progress_pct": 0,
            "status_message": "Queued",
            "error": None,
            "result": None,
        }
    )
    return cast(dict[str, object], job)


def _sorted_jobs() -> list[dict[str, object]]:
    return [cast(dict[str, object], job) for job in load_jobs()]


def _active_job() -> dict[str, object] | None:
    return next((job for job in _sorted_jobs() if job.get("status") == "running"), None)


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _normalize_gainer_item(item: object) -> dict[str, object] | None:
    if isinstance(item, str):
        symbol = item.strip().upper()
        if not symbol:
            return None
        return {
            "symbol": symbol,
            "price": None,
            "percent_change": None,
            "volume": None,
        }

    if isinstance(item, Mapping):
        symbol_raw = item.get("symbol")
        symbol = str(symbol_raw).strip().upper() if symbol_raw is not None else ""
        if not symbol:
            return None

        return {
            "symbol": symbol,
            "price": _coerce_optional_float(item.get("price")),
            "percent_change": _coerce_optional_float(item.get("percent_change")),
            "volume": _coerce_optional_float(item.get("volume")),
        }

    return None


async def _training_status_stmt(session: AsyncSession) -> TrainingStatusResult:
    stmt = (
        select(
            CandleRow.symbol,
            CandleRow.asset_class,
            CandleRow.timeframe,
            func.count().label("row_count"),
            func.min(CandleRow.time).label("earliest"),
            func.max(CandleRow.time).label("latest"),
        )
        .where(CandleRow.source.in_(_TRAINING_SOURCES))
        .group_by(CandleRow.symbol, CandleRow.asset_class, CandleRow.timeframe)
        .order_by(
            CandleRow.asset_class.asc(),
            CandleRow.symbol.asc(),
            CandleRow.timeframe.asc(),
        )
    )
    result = await session.execute(stmt)
    return cast(TrainingStatusResult, result)


async def _load_training_status_rows(session: AsyncSession) -> list[TrainingStatusRow]:
    result = await _training_status_stmt(session)
    rows: list[TrainingStatusRow] = []

    for raw_row in result.all():
        if isinstance(raw_row, TrainingStatusRow):
            rows.append(raw_row)
            continue

        row = cast(RawTrainingStatusRow, raw_row)
        symbol, asset_class, timeframe, row_count, earliest, latest = row
        row_count_value = cast(int | str, row_count)
        rows.append(
            TrainingStatusRow(
                symbol=str(symbol),
                asset_class=str(asset_class),
                timeframe=str(timeframe),
                row_count=int(row_count_value),
                earliest=cast(datetime | None, earliest),
                latest=cast(datetime | None, latest),
            )
        )

    return rows


def _serialize_training_detail(row: TrainingStatusRow) -> dict[str, object]:
    return {
        "symbol": row.symbol,
        "asset_class": row.asset_class,
        "timeframe": row.timeframe,
        "candle_count": row.row_count,
        "earliest": row.earliest.isoformat() if row.earliest else None,
        "latest": row.latest.isoformat() if row.latest else None,
    }


async def _build_training_status() -> dict[str, object]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    async with session_factory() as session:
        rows = await _load_training_status_rows(session)

    crypto_detail: list[dict[str, object]] = []
    stock_detail: list[dict[str, object]] = []
    crypto_symbols: set[str] = set()
    stock_symbols: set[str] = set()
    crypto_candles = 0
    stock_candles = 0

    for row in rows:
        detail = _serialize_training_detail(row)

        if row.asset_class == "crypto":
            crypto_detail.append(detail)
            crypto_candles += row.row_count
            if row.row_count > 0:
                crypto_symbols.add(row.symbol)
        else:
            stock_detail.append(detail)
            stock_candles += row.row_count
            if row.row_count > 0:
                stock_symbols.add(row.symbol)

    return {
        "source": ",".join(_TRAINING_SOURCES),
        "total_candles": crypto_candles + stock_candles,
        "crypto_candles": crypto_candles,
        "stock_candles": stock_candles,
        "crypto_symbols": len(crypto_symbols),
        "stock_symbols": len(stock_symbols),
        "symbols_with_data": len(crypto_symbols | stock_symbols),
        "crypto_detail": crypto_detail,
        "stock_detail": stock_detail,
    }


async def _load_gainers(limit: int) -> GainersResponse:
    settings = get_settings()

    if not settings.alpaca_api_key:
        return GainersResponse(
            gainers=[],
            count=0,
            fetched_at=datetime.now(tz=UTC).isoformat(),
            error="alpaca key missing",
        )

    fetcher = AlpacaTrainingFetcher(
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
    )
    raw_items = await fetcher.fetch_most_active(top=limit)

    gainers: list[dict[str, object]] = []

    for item in raw_items:
        normalized = _normalize_gainer_item(item)
        if normalized is not None:
            gainers.append(normalized)

    return GainersResponse(
        gainers=gainers,
        count=len(gainers),
        fetched_at=datetime.now(tz=UTC).isoformat(),
    )


async def _run_stock_backfill(
    job_id: str,
    symbols: list[str],
    timeframe: str,
    lookback_days: int,
    candle_repo: CandleRepository,
    *,
    status_prefix: str = "stock",
    gainers_snapshot: list[dict[str, object]] | None = None,
) -> None:
    settings = get_settings()
    mark_training_status_stale(f"{status_prefix}_backfill_started")

    fetcher = AlpacaTrainingFetcher(
        repository=candle_repo,
        api_key=settings.alpaca_api_key,
        api_secret=settings.alpaca_api_secret,
        lookback_days=lookback_days,
    )

    total = max(len(symbols), 1)
    rows_written = 0

    try:
        if gainers_snapshot is not None:
            update_job(job_id, gainers_snapshot=gainers_snapshot)

        for i, symbol in enumerate(symbols, start=1):
            update_job(
                job_id,
                current_symbol=symbol,
                current_timeframe=timeframe,
                done_symbols=i - 1,
                total_batches=total,
                done_batches=i - 1,
                rows_fetched=rows_written,
                progress_pct=int(((i - 1) / total) * 100),
                status_message=f"fetching {symbol}",
            )

            written = await fetcher.sync_universe(
                symbols=[symbol],
                timeframes=[timeframe],
            )
            rows_written += int(written)

            update_job(
                job_id,
                done_symbols=i,
                total_batches=total,
                done_batches=i,
                rows_fetched=rows_written,
                progress_pct=int((i / total) * 100),
                status_message=f"completed {symbol}",
            )

        await rebuild_training_status(_build_training_status)
        finish_job(
            job_id,
            status="done",
            result={
                "rows_written": rows_written,
                "symbols": symbols,
                "timeframe": timeframe,
                "lookback_days": lookback_days,
            },
        )
        update_job(
            job_id,
            progress_pct=100,
            status_message="completed",
            current_symbol=None,
            current_timeframe=None,
        )
    except Exception as exc:
        finish_job(job_id, status="error", error=str(exc))
        update_job(job_id, status_message="failed")


async def _run_crypto_csv_backfill(
    job_id: str,
    candle_repo: CandleRepository,
) -> None:
    mark_training_status_stale("crypto_csv_backfill_started")

    if not _CRYPTO_HISTORY_DIR.exists():
        finish_job(
            job_id,
            status="error",
            error=f"crypto CSV folder not found: {_CRYPTO_HISTORY_DIR}",
        )
        update_job(job_id, status_message="crypto-history folder missing")
        return

    ingestor = CryptoCsvTrainingIngestor(
        repository=candle_repo,
        csv_dir=_CRYPTO_HISTORY_DIR,
    )

    try:
        csv_files = sorted(_CRYPTO_HISTORY_DIR.glob("*.csv"))
        total = max(len(csv_files), 1)

        update_job(
            job_id,
            total_symbols=total,
            total_batches=total,
            done_symbols=0,
            done_batches=0,
            rows_fetched=0,
            progress_pct=0,
            status_message="reading crypto CSV files",
        )

        summaries = await ingestor.ingest_all()
        rows_written = 0

        for i, summary in enumerate(summaries, start=1):
            rows_written += summary.rows_written
            update_job(
                job_id,
                current_symbol=summary.symbol,
                current_timeframe="1Day",
                done_symbols=i,
                total_batches=total,
                done_batches=i,
                rows_fetched=rows_written,
                progress_pct=int((i / total) * 100),
                status_message=f"imported {summary.symbol} CSV",
            )

        await rebuild_training_status(_build_training_status)
        finish_job(
            job_id,
            status="done",
            result={
                "rows_written": rows_written,
                "symbols": [summary.symbol for summary in summaries],
                "source_dir": str(_CRYPTO_HISTORY_DIR),
            },
        )
        update_job(
            job_id,
            progress_pct=100,
            status_message="completed",
            current_symbol=None,
            current_timeframe=None,
        )
    except Exception as exc:
        finish_job(job_id, status="error", error=str(exc))
        update_job(job_id, status_message="failed")


@router.get("/training/status")
async def training_status() -> dict[str, object]:
    status = await get_or_build_training_status(
        _build_training_status,
        allow_stale=_active_job() is not None,
    )
    return cast(dict[str, object], status)


@router.get("/persistence")
async def ml_persistence() -> MlPersistenceResponse:
    jobs = _sorted_jobs()
    active_job = _active_job()
    training = await get_or_build_training_status(
        _build_training_status,
        allow_stale=active_job is not None,
    )
    return MlPersistenceResponse(
        jobs=jobs,
        active_job_id=cast(str | None, active_job.get("job_id") if active_job else None),
        has_running_job=active_job is not None,
        training=cast(dict[str, object], training),
        persisted_at=datetime.now(tz=UTC).isoformat(),
    )


@router.get("/jobs")
async def list_jobs() -> list[dict[str, object]]:
    return _sorted_jobs()


@router.get("/jobs/active")
async def active_job() -> dict[str, object]:
    return {"job": _active_job()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, object]:
    job = load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return cast(dict[str, object], job)


@router.get("/gainers")
async def get_top_gainers(
    limit: int = Query(default=100, ge=1, le=100),
) -> dict[str, object]:
    response = await _load_gainers(limit)
    return response.model_dump()


@router.post("/backfill/gainers")
async def backfill_gainers(
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    limit: int = Query(default=100, ge=1, le=100),
    lookback_days: int = Query(default=365, ge=1, le=730),
) -> dict[str, object]:
    gainers = await _load_gainers(limit)
    if gainers.error:
        raise HTTPException(status_code=400, detail=gainers.error)

    symbols: list[str] = []

    for row in gainers.gainers:
        symbol = row.get("symbol")
        if isinstance(symbol, str) and symbol:
            symbols.append(symbol)
    if not symbols:
        raise HTTPException(status_code=400, detail="no gainers returned")

    job = _new_job("gainers_backfill", symbols)
    update_job(str(job["job_id"]), gainers_snapshot=gainers.gainers)

    background_tasks.add_task(
        _run_stock_backfill,
        str(job["job_id"]),
        symbols,
        "1Day",
        lookback_days,
        candle_repo,
        status_prefix="gainers",
        gainers_snapshot=gainers.gainers,
    )

    return job


@router.post("/backfill/stocks")
async def backfill_stocks(
    payload: StockBackfillRequest,
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
) -> dict[str, object]:
    symbols = [s.strip().upper() for s in payload.symbols if s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="no symbols provided")

    job = _new_job("stock_backfill", symbols)

    background_tasks.add_task(
        _run_stock_backfill,
        str(job["job_id"]),
        symbols,
        payload.timeframe,
        payload.lookback_days,
        candle_repo,
    )

    return job


@router.post("/backfill/crypto")
async def backfill_crypto(
    payload: CryptoBackfillRequest,
    background_tasks: BackgroundTasks,
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
) -> dict[str, object]:
    del payload
    symbols = sorted(KRAKEN_UNIVERSE)
    job = _new_job("crypto_csv_backfill", symbols)
    update_job(
        str(job["job_id"]),
        current_timeframe="1Day",
        status_message="queued crypto CSV import",
    )

    background_tasks.add_task(
        _run_crypto_csv_backfill,
        str(job["job_id"]),
        candle_repo,
    )

    return job


@router.get("/crypto/universe")
async def crypto_universe() -> dict[str, object]:
    return {
        "symbols": sorted(KRAKEN_UNIVERSE),
        "count": len(KRAKEN_UNIVERSE),
        "source_dir": str(_CRYPTO_HISTORY_DIR),
    }


@router.post("/train/{asset_class}")
async def train_model(
    asset_class: str,
    background_tasks: BackgroundTasks,
) -> TrainModelResponse:
    normalized_asset_class = asset_class.strip().lower()
    if normalized_asset_class not in {"crypto", "stock"}:
        raise HTTPException(status_code=400, detail="asset_class must be crypto or stock")

    active_job = _active_job()
    if active_job is not None:
        raise HTTPException(status_code=409, detail="another ML job is already running")

    latest_status = await get_or_build_training_status(_build_training_status)
    detail_key = f"{normalized_asset_class}_detail"
    detail_rows = latest_status.get(detail_key)
    if not isinstance(detail_rows, list) or len(detail_rows) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"No {normalized_asset_class} training data is ready yet",
        )

    symbols = sorted(
        {
            str(row.get("symbol"))
            for row in detail_rows
            if isinstance(row, Mapping) and row.get("symbol")
        }
    )
    job = _new_job(f"{normalized_asset_class}_train", symbols)
    update_job(
        str(job["job_id"]),
        status_message=f"queued {normalized_asset_class} training",
        current_timeframe="1Day",
    )

    background_tasks.add_task(_run_training_job, str(job["job_id"]), normalized_asset_class)
    active_model = get_active_model(normalized_asset_class)
    return TrainModelResponse(
        job=job,
        active_model_id=active_model.get("model_id") if active_model else None,
    )


@router.get("/models")
async def list_registered_models(
    asset_class: str | None = Query(default=None),
) -> ModelRegistryResponse:
    normalized_asset_class = asset_class.strip().lower() if asset_class else None
    if normalized_asset_class not in {None, "crypto", "stock"}:
        raise HTTPException(status_code=400, detail="asset_class must be crypto or stock")

    models = load_models(normalized_asset_class)
    return ModelRegistryResponse(
        models=models,
        active_by_asset={
            "crypto": (get_active_model("crypto") or {}).get("model_id"),
            "stock": (get_active_model("stock") or {}).get("model_id"),
        },
        generated_at=datetime.now(tz=UTC).isoformat(),
    )


@router.get("/models/{model_id}")
async def get_registered_model(model_id: str) -> dict[str, object]:
    record = get_model(model_id)
    if record is None:
        raise HTTPException(status_code=404, detail="model not found")
    return cast(dict[str, object], record)