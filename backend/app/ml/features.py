"""Feature engineering for ML training and inference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite

from app.indicators.library import IndicatorLib
from app.models.domain import Candle

type FeatureVector = dict[str, float]

TECHNICAL_FEATURES: list[str] = [
    "returns_1",
    "returns_2",
    "returns_3",
    "returns_5",
    "returns_10",
    "returns_20",
    "returns_50",
    "returns_100",
    "returns_200",
    "price_to_sma_20",
    "price_to_sma_50",
    "price_to_sma_200",
    "sma_20_slope",
    "sma_50_slope",
    "sma_200_slope",
    "price_to_ema_12",
    "price_to_ema_26",
    "ema_12_26_spread",
    "macd",
    "macd_signal",
    "macd_hist",
    "rsi_14",
    "atr_14",
    "atr_pct_14",
    "bollinger_width_20",
    "bollinger_percent_b_20",
    "volume_20",
    "volume_ratio_20",
    "vwap_distance",
    "adx_14",
    "high_low_range",
    "close_open_range",
    "gap_open",
    "day_of_week",
    "day_of_month",
    "days_to_month_end",
]

RESEARCH_FEATURES: list[str] = [
    "news_sentiment_1d",
    "news_sentiment_7d",
    "news_article_count_7d",
    "earnings_proximity_days",
    "congress_buy_score",
    "congress_cluster_30d",
    "days_since_last_congress",
    "insider_buy_score",
    "insider_cluster_60d",
    "insider_value_60d",
    "ceo_bought_90d",
    "analyst_upgrade_score",
    "consensus_rating",
    "watchlist_research_score",
]

ALL_FEATURES: list[str] = TECHNICAL_FEATURES + RESEARCH_FEATURES


@dataclass(slots=True, frozen=True)
class ResearchInputs:
    """Auxiliary research features supplied alongside candle history."""

    news_sentiment_1d: float = 0.0
    news_sentiment_7d: float = 0.0
    news_article_count_7d: int = 0
    earnings_proximity_days: int = 999
    congress_buy_score: float = 0.0
    congress_cluster_30d: int = 0
    days_since_last_congress: int = 999
    insider_buy_score: float = 0.0
    insider_cluster_60d: int = 0
    insider_value_60d: float = 0.0
    ceo_bought_90d: bool = False
    analyst_upgrade_score: float = 0.0
    consensus_rating: float = 3.0
    watchlist_research_score: float = 0.0


@dataclass(slots=True, frozen=True)
class FeatureValidationResult:
    """Describe whether a feature vector matches the ML contract."""

    missing: tuple[str, ...]
    extra: tuple[str, ...]
    nonfinite: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        """Return true when the vector exactly matches the expected contract."""

        return not self.missing and not self.extra and not self.nonfinite


def validate_feature_vector(features: Mapping[str, float]) -> FeatureValidationResult:
    """Validate a feature vector against the canonical ML contract."""

    feature_names = set(features)
    expected_names = set(ALL_FEATURES)
    missing = tuple(sorted(expected_names - feature_names))
    extra = tuple(sorted(feature_names - expected_names))
    nonfinite = tuple(
        sorted(
            name
            for name, value in features.items()
            if not isinstance(value, (int, float)) or not isfinite(value)
        )
    )
    return FeatureValidationResult(missing=missing, extra=extra, nonfinite=nonfinite)


def ordered_feature_row(features: Mapping[str, float]) -> list[float]:
    """Return a strictly ordered numeric feature row for downstream ML code."""

    validation = validate_feature_vector(features)
    if not validation.is_valid:
        details: list[str] = []
        if validation.missing:
            details.append(f"missing={list(validation.missing)}")
        if validation.extra:
            details.append(f"extra={list(validation.extra)}")
        if validation.nonfinite:
            details.append(f"nonfinite={list(validation.nonfinite)}")
        detail_text = ", ".join(details)
        raise ValueError(f"Feature vector does not match ML contract: {detail_text}")
    return [float(features[name]) for name in ALL_FEATURES]


def build_feature_contract_summary() -> dict[str, object]:
    """Return a compact summary of the canonical feature contract."""

    return {
        "feature_count": len(ALL_FEATURES),
        "technical_feature_count": len(TECHNICAL_FEATURES),
        "research_feature_count": len(RESEARCH_FEATURES),
        "all_features": list(ALL_FEATURES),
        "technical_features": list(TECHNICAL_FEATURES),
        "research_features": list(RESEARCH_FEATURES),
        "stock_research_policy": "stock feature vectors may include non-zero research features",
        "crypto_research_policy": (
            "crypto feature vectors keep research feature keys but use the "
            "default research placeholders"
        ),
    }


class FeatureEngineer:
    """Build flat feature vectors from candle history and research signals."""

    def __init__(self, indicator_lib: IndicatorLib | None = None) -> None:
        self.indicator_lib = indicator_lib or IndicatorLib()

    def build(
        self,
        history: Sequence[Candle],
        asset_class: str,
        research_signals: ResearchInputs | None = None,
    ) -> FeatureVector | None:
        """Return a feature vector or None when history is too short."""

        if len(history) < 200:
            return None
        candles = list(history)
        closes = self.indicator_lib.closes(candles)
        highs = self.indicator_lib.highs(candles)
        lows = self.indicator_lib.lows(candles)
        volumes = self.indicator_lib.volumes(candles)
        latest = candles[-1]
        previous = candles[-2]
        sma_20 = self.indicator_lib.sma(closes, 20)
        sma_50 = self.indicator_lib.sma(closes, 50)
        sma_200 = self.indicator_lib.sma(closes, 200)
        ema_12 = self.indicator_lib.ema(closes, 12)
        ema_26 = self.indicator_lib.ema(closes, 26)
        rsi_14 = self.indicator_lib.rsi(closes, 14)
        atr_14 = self.indicator_lib.atr(candles, 14)
        bollinger_20 = self.indicator_lib.bollinger_bands(closes, 20)
        vwap = self.indicator_lib.vwap(candles)
        volume_20 = self.indicator_lib.average_volume(candles, 20)
        adx_14 = self.indicator_lib.adx(candles, 14)
        macd_line = self._series_difference(ema_12, ema_26)
        macd_signal = self.indicator_lib.ema(macd_line, 9)

        features: FeatureVector = {}
        for name, value in self._technical_feature_items(
            candles=candles,
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            latest=latest,
            previous=previous,
            sma_20=sma_20,
            sma_50=sma_50,
            sma_200=sma_200,
            ema_12=ema_12,
            ema_26=ema_26,
            macd_line=macd_line,
            macd_signal=macd_signal,
            rsi_14=rsi_14,
            atr_14=atr_14,
            bollinger_20=bollinger_20,
            vwap=vwap,
            volume_20=volume_20,
            adx_14=adx_14,
        ):
            features[name] = value

        research = research_signals or ResearchInputs()
        if asset_class != "stock":
            research = ResearchInputs()
        for name, value in self._research_feature_items(research):
            features[name] = value
        return features

    def _technical_feature_items(
        self,
        *,
        candles: Sequence[Candle],
        closes: list[float],
        highs: list[float],
        lows: list[float],
        volumes: list[float],
        latest: Candle,
        previous: Candle,
        sma_20: list[float],
        sma_50: list[float],
        sma_200: list[float],
        ema_12: list[float],
        ema_26: list[float],
        macd_line: list[float],
        macd_signal: list[float],
        rsi_14: list[float],
        atr_14: list[float],
        bollinger_20: list[tuple[float, float, float]],
        vwap: float,
        volume_20: float,
        adx_14: float,
    ) -> list[tuple[str, float]]:
        """Assemble the technical feature values in a stable order."""

        latest_close = closes[-1]
        latest_open = latest.open
        latest_high = highs[-1]
        latest_low = lows[-1]
        latest_volume = volumes[-1]
        return [
            ("returns_1", self._return_over_horizon(closes, 1)),
            ("returns_2", self._return_over_horizon(closes, 2)),
            ("returns_3", self._return_over_horizon(closes, 3)),
            ("returns_5", self._return_over_horizon(closes, 5)),
            ("returns_10", self._return_over_horizon(closes, 10)),
            ("returns_20", self._return_over_horizon(closes, 20)),
            ("returns_50", self._return_over_horizon(closes, 50)),
            ("returns_100", self._return_over_horizon(closes, 100)),
            ("returns_200", self._return_over_horizon(closes, 200)),
            ("price_to_sma_20", self._price_to_series(sma_20, latest_close)),
            ("price_to_sma_50", self._price_to_series(sma_50, latest_close)),
            ("price_to_sma_200", self._price_to_series(sma_200, latest_close)),
            ("sma_20_slope", self._series_slope(sma_20)),
            ("sma_50_slope", self._series_slope(sma_50)),
            ("sma_200_slope", self._series_slope(sma_200)),
            ("price_to_ema_12", self._price_to_series(ema_12, latest_close)),
            ("price_to_ema_26", self._price_to_series(ema_26, latest_close)),
            (
                "ema_12_26_spread",
                self._spread(self._last_or_zero(ema_12), self._last_or_zero(ema_26)),
            ),
            ("macd", self._last_or_zero(macd_line)),
            ("macd_signal", self._last_or_zero(macd_signal)),
            (
                "macd_hist",
                self._spread(self._last_or_zero(macd_line), self._last_or_zero(macd_signal)),
            ),
            ("rsi_14", self._last_or_zero(rsi_14)),
            ("atr_14", self._last_or_zero(atr_14)),
            ("atr_pct_14", self._ratio(self._last_or_zero(atr_14), latest_close)),
            ("bollinger_width_20", self._bollinger_width(bollinger_20)),
            ("bollinger_percent_b_20", self._bollinger_percent_b(bollinger_20, latest_close)),
            ("volume_20", volume_20),
            ("volume_ratio_20", self._ratio(latest_volume, volume_20)),
            ("vwap_distance", self._ratio(latest_close - vwap, vwap)),
            ("adx_14", adx_14),
            ("high_low_range", self._ratio(latest_high - latest_low, latest_close)),
            ("close_open_range", self._ratio(latest_close - latest_open, latest_open)),
            ("gap_open", self._ratio(latest_open - previous.close, previous.close)),
            ("day_of_week", float(latest.time.weekday())),
            ("day_of_month", float(latest.time.day)),
            ("days_to_month_end", float(self._days_to_month_end(latest.time))),
        ]

    def _research_feature_items(self, research: ResearchInputs) -> list[tuple[str, float]]:
        """Convert research inputs into flat feature values."""

        return [
            ("news_sentiment_1d", self._finite(research.news_sentiment_1d)),
            ("news_sentiment_7d", self._finite(research.news_sentiment_7d)),
            ("news_article_count_7d", float(research.news_article_count_7d)),
            ("earnings_proximity_days", float(research.earnings_proximity_days)),
            ("congress_buy_score", self._finite(research.congress_buy_score)),
            ("congress_cluster_30d", float(research.congress_cluster_30d)),
            ("days_since_last_congress", float(research.days_since_last_congress)),
            ("insider_buy_score", self._finite(research.insider_buy_score)),
            ("insider_cluster_60d", float(research.insider_cluster_60d)),
            ("insider_value_60d", self._finite(research.insider_value_60d)),
            ("ceo_bought_90d", 1.0 if research.ceo_bought_90d else 0.0),
            ("analyst_upgrade_score", self._finite(research.analyst_upgrade_score)),
            ("consensus_rating", self._finite(research.consensus_rating)),
            ("watchlist_research_score", self._finite(research.watchlist_research_score)),
        ]

    def _return_over_horizon(self, closes: Sequence[float], horizon: int) -> float:
        """Return percentage change across a fixed lookback horizon."""

        if horizon <= 0 or len(closes) <= horizon:
            return 0.0
        previous_close = float(closes[-(horizon + 1)])
        current_close = float(closes[-1])
        return self._ratio(current_close - previous_close, previous_close)

    def _price_to_series(self, series: Sequence[float], price: float) -> float:
        """Return the price relative to the latest value of a series."""

        return self._ratio(price - self._last_or_zero(series), self._last_or_zero(series))

    def _series_slope(self, series: Sequence[float]) -> float:
        """Return the fractional change between the last two points of a series."""

        if len(series) < 2:
            return 0.0
        previous_value = self._finite(series[-2])
        current_value = self._finite(series[-1])
        return self._ratio(current_value - previous_value, previous_value)

    def _bollinger_width(self, bands: Sequence[tuple[float, float, float]]) -> float:
        """Return the relative Bollinger band width."""

        if not bands:
            return 0.0
        middle, upper, lower = bands[-1]
        return self._ratio(upper - lower, middle)

    def _bollinger_percent_b(
        self,
        bands: Sequence[tuple[float, float, float]],
        price: float,
    ) -> float:
        """Return Bollinger %B for the latest candle."""

        if not bands:
            return 0.0
        _middle, upper, lower = bands[-1]
        band_width = upper - lower
        if band_width == 0.0:
            return 0.0
        return self._finite((price - lower) / band_width)

    def _series_difference(self, left: Sequence[float], right: Sequence[float]) -> list[float]:
        """Subtract two equally ordered series, truncating to the shortest length."""

        length = min(len(left), len(right))
        return [self._finite(left[index] - right[index]) for index in range(length)]

    def _last_or_zero(self, series: Sequence[float]) -> float:
        """Return the latest series value or 0.0 when unavailable."""

        if not series:
            return 0.0
        return self._finite(series[-1])

    def _ratio(self, numerator: float, denominator: float) -> float:
        """Safely compute a ratio as a finite float."""

        if denominator == 0.0:
            return 0.0
        return self._finite(numerator / denominator)

    def _spread(self, left: float, right: float) -> float:
        """Return a simple difference between two values."""

        return self._finite(left - right)

    def _finite(self, value: float) -> float:
        """Normalize non-finite values to zero."""

        return float(value) if isfinite(value) else 0.0

    def _days_to_month_end(self, moment: object) -> int:
        """Return the number of days remaining in the month for a datetime."""

        from datetime import datetime, timedelta

        if not isinstance(moment, datetime):
            return 0
        next_month = (moment.replace(day=28) + timedelta(days=4)).replace(day=1)
        return (next_month.date() - moment.date()).days
