"""Operator workflow for historical crypto sentiment refresh and retraining."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, date, datetime
from typing import Protocol, cast

from fastapi import HTTPException
from sqlalchemy import func, select

from app.config.crypto_scope import KRAKEN_UNIVERSE
from app.config.settings import get_settings
from app.db.models import CryptoDailySentimentRow, PredictionRow, PredictionShapRow
from app.db.session import build_engine, build_session_factory
from app.tasks.news_sentiment import backfill_historical_crypto_sentiment

SENTIMENT_FEATURES: tuple[str, ...] = (
    "news_sentiment_1d",
    "news_sentiment_7d",
    "news_article_count_7d",
)

type TrainModelCallback = Callable[
    ...,
    Awaitable[tuple[Mapping[str, object], Mapping[str, object] | None]],
]
type GeneratePredictionsCallback = Callable[..., Awaitable[Mapping[str, object]]]
type CoverageValidatorCallback = Callable[
    [list[str], date, date, float],
    Awaitable[Mapping[str, Mapping[str, object]]],
]
type ShapSummaryCallback = Callable[[str], Awaitable[Mapping[str, object]]]


class FloatLike(Protocol):
    """Protocol helper for SQL numeric values."""

    def __float__(self) -> float: ...


def parse_crypto_symbol_list(raw_symbols: str | None) -> list[str]:
    """Parse a comma-separated symbol list into stable uppercase crypto symbols."""

    if raw_symbols is None:
        return list(KRAKEN_UNIVERSE)

    symbols: list[str] = []
    seen: set[str] = set()
    for raw_symbol in raw_symbols.split(","):
        symbol = raw_symbol.strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def parse_sentiment_refresh_window(start_date: str, end_date: str) -> tuple[date, date]:
    """Validate the historical sentiment refresh date window."""

    start = _parse_iso_date(start_date, "start_date")
    end = _parse_iso_date(end_date, "end_date")
    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    return start, end


async def validate_sentiment_coverage(
    symbols: list[str],
    start: date,
    end: date,
    min_coverage: float,
) -> Mapping[str, Mapping[str, object]]:
    """Verify sentiment rows exist before allowing sentiment-aware retraining."""

    if min_coverage < 0.0 or min_coverage > 1.0:
        raise HTTPException(
            status_code=400,
            detail="min_sentiment_coverage must be between 0.0 and 1.0",
        )

    total_days = (end - start).days + 1
    if total_days <= 0:
        raise HTTPException(status_code=400, detail="sentiment coverage window is empty")

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    coverage: dict[str, Mapping[str, object]] = {}
    low_coverage_symbols: list[str] = []

    try:
        async with session_factory() as session:
            for symbol in symbols:
                total_statement = (
                    select(func.count())
                    .select_from(CryptoDailySentimentRow)
                    .where(CryptoDailySentimentRow.symbol == symbol)
                    .where(CryptoDailySentimentRow.sentiment_date >= start)
                    .where(CryptoDailySentimentRow.sentiment_date <= end)
                )
                covered_statement = total_statement.where(
                    CryptoDailySentimentRow.coverage_score > 0.0,
                )
                article_statement = (
                    select(func.coalesce(func.sum(CryptoDailySentimentRow.article_count), 0))
                    .select_from(CryptoDailySentimentRow)
                    .where(CryptoDailySentimentRow.symbol == symbol)
                    .where(CryptoDailySentimentRow.sentiment_date >= start)
                    .where(CryptoDailySentimentRow.sentiment_date <= end)
                )

                total_rows = int((await session.execute(total_statement)).scalar_one())
                covered_days = int((await session.execute(covered_statement)).scalar_one())
                article_count = int((await session.execute(article_statement)).scalar_one())
                coverage_ratio = covered_days / total_days

                coverage[symbol] = {
                    "total_days": total_days,
                    "sentiment_rows": total_rows,
                    "covered_days": covered_days,
                    "article_count": article_count,
                    "coverage_ratio": round(coverage_ratio, 6),
                    "min_required_coverage": min_coverage,
                }
                if coverage_ratio < min_coverage:
                    low_coverage_symbols.append(symbol)
    finally:
        await engine.dispose()

    if low_coverage_symbols:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "insufficient_sentiment_coverage",
                "message": (
                    "Historical sentiment coverage is too sparse for retraining. "
                    "Run/expand the historical backfill window before training."
                ),
                "symbols": low_coverage_symbols,
                "coverage": coverage,
            },
        )

    return coverage


async def build_sentiment_shap_summary(model_id: str) -> Mapping[str, object]:
    """Summarize persisted sentiment SHAP rows for a refreshed crypto model."""

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    try:
        async with session_factory() as session:
            statement = (
                select(
                    PredictionShapRow.feature,
                    func.count(PredictionShapRow.id),
                    func.avg(PredictionShapRow.abs_value),
                    func.avg(PredictionShapRow.feature_value),
                )
                .join(PredictionRow, PredictionRow.id == PredictionShapRow.prediction_id)
                .where(PredictionRow.asset_class == "crypto")
                .where(PredictionRow.model_id == model_id)
                .where(PredictionShapRow.feature.in_(SENTIMENT_FEATURES))
                .group_by(PredictionShapRow.feature)
                .order_by(PredictionShapRow.feature.asc())
            )
            result = await session.execute(statement)
            rows = result.all()
    finally:
        await engine.dispose()

    features: dict[str, dict[str, object]] = {
        feature: {
            "row_count": 0,
            "avg_abs_shap": 0.0,
            "avg_feature_value": 0.0,
        }
        for feature in SENTIMENT_FEATURES
    }
    for feature, row_count, avg_abs_shap, avg_feature_value in rows:
        feature_name = str(feature)
        features[feature_name] = {
            "row_count": int(row_count),
            "avg_abs_shap": round(_coerce_numeric(avg_abs_shap), 8),
            "avg_feature_value": round(_coerce_numeric(avg_feature_value), 8),
        }

    return {
        "model_id": model_id,
        "features": features,
        "sentiment_feature_count": len(SENTIMENT_FEATURES),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


async def run_crypto_sentiment_refresh_training(
    *,
    job_id: str,
    start_date: str,
    end_date: str,
    symbols: str | None,
    prediction_limit: int,
    min_sentiment_coverage: float,
    train_model: TrainModelCallback,
    generate_predictions: GeneratePredictionsCallback,
    coverage_validator: CoverageValidatorCallback = validate_sentiment_coverage,
    shap_summary_builder: ShapSummaryCallback = build_sentiment_shap_summary,
) -> Mapping[str, object]:
    """Force historical sentiment backfill before retraining crypto ML."""

    start, end = parse_sentiment_refresh_window(start_date, end_date)
    symbol_list = parse_crypto_symbol_list(symbols)
    if not symbol_list:
        raise HTTPException(status_code=400, detail="at least one crypto symbol is required")

    backfill_result = await backfill_historical_crypto_sentiment(
        symbols=symbol_list,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    coverage = await coverage_validator(symbol_list, start, end, min_sentiment_coverage)

    record, _ = await train_model(
        asset_class="crypto",
        latest_job_id=job_id,
    )
    model_id = str(record["model_id"])
    prediction_result = await generate_predictions(
        limit=prediction_limit,
        asset_class="crypto",
    )
    shap_summary = await shap_summary_builder(model_id)

    return {
        "job_id": job_id,
        "asset_class": "crypto",
        "model_id": model_id,
        "artifact_path": record["artifact_path"],
        "best_fold": record["best_fold"],
        "fold_count": record["fold_count"],
        "validation_accuracy": record["validation_accuracy"],
        "validation_sharpe": record["validation_sharpe"],
        "train_samples": record["train_samples"],
        "test_samples": record["test_samples"],
        "feature_count": record["feature_count"],
        "backfill": backfill_result,
        "sentiment_coverage": coverage,
        "predictions": {
            "count": prediction_result.get("count"),
            "persisted_count": prediction_result.get("persisted_count"),
            "active_model_ids": prediction_result.get("active_model_ids"),
        },
        "sentiment_shap_summary": shap_summary,
        "status": "completed",
    }


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be an ISO date formatted as YYYY-MM-DD",
        ) from exc


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
