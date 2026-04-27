"""Assemble persisted stock candles and research rows into trainable ML inputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import ALPACA_DEFAULT_SOURCE, ML_CANDLE_USAGE
from app.db.models import (
    CandleRow,
    CongressTradeRow,
    CryptoDailySentimentRow,
    InsiderTradeRow,
    ResearchSignalRow,
    WatchlistRow,
)
from app.ml.features import FeatureEngineer, ResearchInputs
from app.ml.macro_sentiment import (
    DailyMacroSentimentSource,
    build_macro_sentiment_features,
)
from app.ml.trainer import TrainResult, WalkForwardTrainer
from app.models.domain import Candle

CRYPTO_MACRO_PRIOR_WEIGHT = 0.35


@dataclass(slots=True, frozen=True)
class StockTrainingDataset:
    """Concrete stock training inputs assembled from persisted DB rows."""

    candles: tuple[Candle, ...]
    research_lookup: Mapping[str | tuple[str, date], ResearchInputs]


class StockTrainingInputAssembler:
    """Load stock candles plus persisted research rows and map them into ResearchInputs."""

    async def assemble(
        self,
        session: AsyncSession,
        *,
        symbols: Sequence[str] | None = None,
        timeframe: str = "1Day",
    ) -> StockTrainingDataset:
        """Return DB-backed candles and research inputs for stock model training."""

        normalized_symbols = self._normalize_symbols(symbols)
        candle_rows = await self._load_candle_rows(
            session,
            symbols=normalized_symbols,
            timeframe=timeframe,
        )
        candles = tuple(self._row_to_candle(row) for row in candle_rows)
        candle_symbols = tuple(
            self._ordered_unique_symbols(candle.symbol for candle in candles)
        )
        research_lookup = cast(
            Mapping[str | tuple[str, date], ResearchInputs],
            await self._build_research_lookup(session, candle_symbols),
        )
        return StockTrainingDataset(candles=candles, research_lookup=research_lookup)

    async def _load_candle_rows(
        self,
        session: AsyncSession,
        *,
        symbols: tuple[str, ...] | None,
        timeframe: str,
    ) -> list[CandleRow]:
        """Load persisted stock candles for the requested timeframe and symbols."""

        statement = (
            select(CandleRow)
            .where(CandleRow.asset_class == "stock")
            .where(CandleRow.source == ALPACA_DEFAULT_SOURCE)
            .where(CandleRow.timeframe == timeframe)
            .where(CandleRow.usage == ML_CANDLE_USAGE)
            .order_by(CandleRow.symbol.asc(), CandleRow.time.asc())
        )
        if symbols is not None:
            statement = statement.where(CandleRow.symbol.in_(symbols))
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def _build_research_lookup(
        self,
        session: AsyncSession,
        symbols: Sequence[str],
    ) -> dict[str, ResearchInputs]:
        """Build per-symbol ResearchInputs from persisted research tables."""

        if not symbols:
            return {}

        normalized_symbols = tuple(self._ordered_unique_symbols(symbols))
        signal_rows = await self._load_research_signal_rows(session, normalized_symbols)
        congress_rows = await self._load_congress_rows(session, normalized_symbols)
        insider_rows = await self._load_insider_rows(session, normalized_symbols)
        watchlist_rows = await self._load_watchlist_rows(session, normalized_symbols)

        signals_by_symbol: dict[str, list[ResearchSignalRow]] = defaultdict(list)
        congress_by_symbol: dict[str, list[CongressTradeRow]] = defaultdict(list)
        insider_by_symbol: dict[str, list[InsiderTradeRow]] = defaultdict(list)
        watchlist_by_symbol: dict[str, WatchlistRow] = {}

        for signal_row in signal_rows:
            signals_by_symbol[signal_row.symbol.upper()].append(signal_row)
        for congress_row in congress_rows:
            congress_by_symbol[congress_row.symbol.upper()].append(congress_row)
        for insider_row in insider_rows:
            insider_by_symbol[insider_row.symbol.upper()].append(insider_row)
        for watchlist_row in watchlist_rows:
            watchlist_by_symbol[watchlist_row.symbol.upper()] = watchlist_row

        reference_now = self._reference_now(
            signal_rows=signal_rows,
            congress_rows=congress_rows,
            insider_rows=insider_rows,
            watchlist_rows=watchlist_rows,
        )
        research_lookup: dict[str, ResearchInputs] = {}
        for symbol in normalized_symbols:
            research_lookup[symbol] = self._assemble_symbol_research(
                signals=signals_by_symbol.get(symbol, []),
                congress_trades=congress_by_symbol.get(symbol, []),
                insider_trades=insider_by_symbol.get(symbol, []),
                watchlist_row=watchlist_by_symbol.get(symbol),
                now=reference_now,
            )
        return research_lookup

    async def _load_research_signal_rows(
        self,
        session: AsyncSession,
        symbols: Sequence[str],
    ) -> list[ResearchSignalRow]:
        """Load persisted research signal rows for the requested stock symbols."""

        result = await session.execute(
            select(ResearchSignalRow)
            .where(ResearchSignalRow.symbol.in_(symbols))
            .order_by(ResearchSignalRow.symbol.asc(), ResearchSignalRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def _load_congress_rows(
        self,
        session: AsyncSession,
        symbols: Sequence[str],
    ) -> list[CongressTradeRow]:
        """Load persisted congress trade rows for the requested stock symbols."""

        result = await session.execute(
            select(CongressTradeRow)
            .where(CongressTradeRow.symbol.in_(symbols))
            .order_by(CongressTradeRow.symbol.asc(), CongressTradeRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def _load_insider_rows(
        self,
        session: AsyncSession,
        symbols: Sequence[str],
    ) -> list[InsiderTradeRow]:
        """Load persisted insider trade rows for the requested stock symbols."""

        result = await session.execute(
            select(InsiderTradeRow)
            .where(InsiderTradeRow.symbol.in_(symbols))
            .order_by(InsiderTradeRow.symbol.asc(), InsiderTradeRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def _load_watchlist_rows(
        self,
        session: AsyncSession,
        symbols: Sequence[str],
    ) -> list[WatchlistRow]:
        """Load active watchlist rows for the requested stock symbols."""

        result = await session.execute(
            select(WatchlistRow)
            .where(WatchlistRow.symbol.in_(symbols))
            .where(WatchlistRow.asset_class == "stock")
            .where(WatchlistRow.is_active.is_(True))
            .order_by(WatchlistRow.symbol.asc())
        )
        return list(result.scalars().all())

    def _assemble_symbol_research(
        self,
        *,
        signals: Sequence[ResearchSignalRow],
        congress_trades: Sequence[CongressTradeRow],
        insider_trades: Sequence[InsiderTradeRow],
        watchlist_row: WatchlistRow | None,
        now: datetime,
    ) -> ResearchInputs:
        """Aggregate persisted signal/trade rows into one ResearchInputs payload."""

        one_day_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)
        ninety_days_ago = now - timedelta(days=90)

        news_rows = [row for row in signals if "news" in row.signal_type.lower()]
        analyst_rows = [row for row in signals if "analyst" in row.signal_type.lower()]
        congress_signal_rows = [
            row for row in signals if "congress" in row.signal_type.lower()
        ]
        insider_signal_rows = [
            row for row in signals if "insider" in row.signal_type.lower()
        ]

        recent_news_1d = [row for row in news_rows if row.created_at >= one_day_ago]
        recent_news_7d = [row for row in news_rows if row.created_at >= seven_days_ago]
        recent_analyst_rows = [
            row for row in analyst_rows if row.created_at >= thirty_days_ago
        ]
        recent_congress_signal_rows = [
            row for row in congress_signal_rows if row.created_at >= thirty_days_ago
        ]
        recent_insider_signal_rows = [
            row for row in insider_signal_rows if row.created_at >= sixty_days_ago
        ]
        recent_congress_rows = [
            row
            for row in congress_trades
            if self._congress_event_datetime(row) >= thirty_days_ago
        ]
        recent_insider_rows = [
            row
            for row in insider_trades
            if self._insider_event_datetime(row) >= sixty_days_ago
        ]
        recent_ceo_rows = [
            row
            for row in insider_trades
            if self._insider_event_datetime(row) >= ninety_days_ago
            and self._is_ceo_title(row.title)
            and self._looks_like_buy_transaction(row.transaction_type)
        ]

        latest_congress_event = self._latest_datetime(
            self._congress_event_datetime(row) for row in congress_trades
        )

        return ResearchInputs(
            news_sentiment_1d=self._average_signal_score(recent_news_1d),
            news_sentiment_7d=self._average_signal_score(recent_news_7d),
            news_article_count_7d=self._news_article_count(recent_news_7d),
            earnings_proximity_days=999,
            congress_buy_score=self._average_signal_score(recent_congress_signal_rows),
            congress_cluster_30d=len(recent_congress_rows),
            days_since_last_congress=self._days_since(now, latest_congress_event),
            insider_buy_score=self._average_signal_score(recent_insider_signal_rows),
            insider_cluster_60d=len(recent_insider_rows),
            insider_value_60d=self._sum_insider_value(recent_insider_rows),
            ceo_bought_90d=bool(recent_ceo_rows),
            analyst_upgrade_score=self._average_signal_score(recent_analyst_rows),
            consensus_rating=self._consensus_rating(recent_analyst_rows),
            watchlist_research_score=self._watchlist_score(watchlist_row),
        )

    def _normalize_symbols(self, symbols: Sequence[str] | None) -> tuple[str, ...] | None:
        """Normalize optional symbol filters into a stable uppercase tuple."""

        if symbols is None:
            return None
        normalized = tuple(self._ordered_unique_symbols(symbols))
        return normalized if normalized else None

    def _ordered_unique_symbols(self, symbols: Iterable[str]) -> list[str]:
        """Return stable uppercase symbols without blanks or duplicates."""

        ordered: list[str] = []
        seen: set[str] = set()
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            ordered.append(symbol)
        return ordered

    def _reference_now(
        self,
        *,
        signal_rows: Sequence[ResearchSignalRow],
        congress_rows: Sequence[CongressTradeRow],
        insider_rows: Sequence[InsiderTradeRow],
        watchlist_rows: Sequence[WatchlistRow],
    ) -> datetime:
        """Anchor rolling windows to the freshest persisted research timestamp."""

        timestamps: list[datetime] = [row.created_at for row in signal_rows]
        timestamps.extend(row.created_at for row in congress_rows)
        timestamps.extend(row.created_at for row in insider_rows)
        timestamps.extend(row.added_at for row in watchlist_rows)
        latest_timestamp = self._latest_datetime(timestamps)
        return latest_timestamp if latest_timestamp is not None else datetime.now(tz=UTC)

    def _row_to_candle(self, row: CandleRow) -> Candle:
        """Convert a persisted candle row into a domain candle."""

        return Candle(
            time=row.time,
            symbol=row.symbol,
            asset_class=row.asset_class,
            timeframe=row.timeframe,
            open=self._required_float(row.open, "open"),
            high=self._required_float(row.high, "high"),
            low=self._required_float(row.low, "low"),
            close=self._required_float(row.close, "close"),
            volume=self._required_float(row.volume, "volume"),
            source=row.source,
        )

    def _average_signal_score(self, rows: Sequence[ResearchSignalRow]) -> float:
        """Return the arithmetic mean of available signal scores."""

        scores = [self._coerce_float(row.score) for row in rows]
        values = [score for score in scores if score is not None]
        if not values:
            return 0.0
        return sum(values) / float(len(values))

    def _news_article_count(self, rows: Sequence[ResearchSignalRow]) -> int:
        """Count available news rows, using raw article_count when present."""

        explicit_count = 0
        fallback_count = 0
        for row in rows:
            article_count = self._raw_int(row.raw_data, "article_count")
            if article_count is not None:
                explicit_count += article_count
            else:
                fallback_count += 1
        if explicit_count > 0:
            return explicit_count
        return fallback_count

    def _consensus_rating(self, rows: Sequence[ResearchSignalRow]) -> float:
        """Return a best-effort consensus analyst rating, defaulting to neutral."""

        rating_values: list[float] = []
        for row in rows:
            direct_rating = self._raw_float(row.raw_data, "consensus_rating")
            if direct_rating is not None:
                rating_values.append(direct_rating)
                continue

            signal_type = row.signal_type.lower()
            if "strong_buy" in signal_type:
                rating_values.append(1.0)
            elif "buy" in signal_type:
                rating_values.append(2.0)
            elif "hold" in signal_type:
                rating_values.append(3.0)
            elif "sell" in signal_type:
                rating_values.append(4.0)
        if not rating_values:
            return 3.0
        return sum(rating_values) / float(len(rating_values))

    def _watchlist_score(self, row: WatchlistRow | None) -> float:
        """Return the active watchlist research score when available."""

        if row is None:
            return 0.0
        score = self._coerce_float(row.research_score)
        return score if score is not None else 0.0

    def _sum_insider_value(self, rows: Sequence[InsiderTradeRow]) -> float:
        """Return total insider traded value across the supplied rows."""

        values = [self._coerce_float(row.total_value) for row in rows]
        return sum(value for value in values if value is not None)

    def _days_since(self, now: datetime, event_at: datetime | None) -> int:
        """Return whole days since the most recent event, using 999 when absent."""

        if event_at is None:
            return 999
        delta = now - event_at
        if delta.days < 0:
            return 0
        return delta.days

    def _latest_datetime(self, datetimes: Iterable[datetime]) -> datetime | None:
        """Return the latest datetime from an iterable, or None when empty."""

        latest: datetime | None = None
        for value in datetimes:
            if latest is None or value > latest:
                latest = value
        return latest

    def _congress_event_datetime(self, row: CongressTradeRow) -> datetime:
        """Return the best available event datetime for a congress trade row."""

        event_date = row.trade_date or row.disclosure_date
        if event_date is None:
            return row.created_at
        return self._date_to_utc_datetime(event_date)

    def _insider_event_datetime(self, row: InsiderTradeRow) -> datetime:
        """Return the best available event datetime for an insider trade row."""

        event_date = row.transaction_date or row.filing_date
        if event_date is None:
            return row.created_at
        return self._date_to_utc_datetime(event_date)

    def _date_to_utc_datetime(self, value: date) -> datetime:
        """Convert a date into a UTC midnight datetime."""

        return datetime(value.year, value.month, value.day, tzinfo=UTC)

    def _is_ceo_title(self, title: str | None) -> bool:
        """Return true when the optional insider title maps to a CEO role."""

        if title is None:
            return False
        normalized = " ".join(title.lower().split())
        ceo_tokens = (
            "ceo",
            "chief executive officer",
            "chief exec officer",
        )
        return any(token in normalized for token in ceo_tokens)

    def _looks_like_buy_transaction(self, transaction_type: str | None) -> bool:
        """Return true when a transaction type looks like a buy/acquisition."""

        if transaction_type is None:
            return False
        normalized = transaction_type.strip().lower()
        return normalized in {"a", "acquisition", "buy", "purchase"}

    def _raw_float(self, raw_data: Mapping[str, object] | None, key: str) -> float | None:
        """Read an optional float-like value from raw research payload data."""

        if raw_data is None:
            return None
        return self._coerce_float(raw_data.get(key))

    def _raw_int(self, raw_data: Mapping[str, object] | None, key: str) -> int | None:
        """Read an optional int-like value from raw research payload data."""

        if raw_data is None:
            return None
        value = raw_data.get(key)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, Decimal):
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return int(float(stripped))
            except ValueError:
                return None
        return None

    def _required_float(self, value: float | Decimal | None, field_name: str) -> float:
        """Convert a DB numeric field into float and reject missing candle components."""

        converted = self._coerce_float(value)
        if converted is None:
            raise ValueError(f"Candle row missing required numeric field: {field_name}")
        return converted

    def _coerce_float(self, value: object) -> float | None:
        """Convert supported scalar values into float."""

        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, Decimal):
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


@dataclass(slots=True, frozen=True)
class CryptoTrainingDataset:
    """Concrete crypto training inputs assembled from ML candles and sentiment rows."""

    candles: tuple[Candle, ...]
    research_lookup: Mapping[str | tuple[str, date], ResearchInputs]


class CryptoTrainingInputAssembler:
    """Load crypto ML candles and map source-backed sentiment into crypto inputs."""

    async def assemble(
        self,
        session: AsyncSession,
        *,
        symbols: Sequence[str] | None = None,
        timeframe: str = "1Day",
    ) -> CryptoTrainingDataset:
        """Return DB-backed crypto candles plus shared BTC/ETH macro sentiment inputs."""

        normalized_symbols = self._normalize_symbols(symbols)
        candle_rows = await self._load_candle_rows(
            session,
            symbols=normalized_symbols,
            timeframe=timeframe,
        )
        candles = tuple(self._row_to_candle(row) for row in candle_rows)
        candle_symbols = tuple(
            self._ordered_unique_symbols(candle.symbol for candle in candles)
        )
        candle_dates = tuple({candle.time.date() for candle in candles})
        research_lookup = await self._build_sentiment_lookup(
            session,
            symbols=candle_symbols,
            sentiment_dates=candle_dates,
        )
        typed_research_lookup = cast(
            Mapping[str | tuple[str, date], ResearchInputs],
            research_lookup,
        )
        return CryptoTrainingDataset(candles=candles, research_lookup=typed_research_lookup)

    async def _load_candle_rows(
        self,
        session: AsyncSession,
        *,
        symbols: tuple[str, ...] | None,
        timeframe: str,
    ) -> list[CandleRow]:
        """Load persisted crypto ML candles for the requested timeframe and symbols."""

        statement = (
            select(CandleRow)
            .where(CandleRow.asset_class == "crypto")
            .where(CandleRow.timeframe == timeframe)
            .where(CandleRow.usage == ML_CANDLE_USAGE)
            .order_by(CandleRow.symbol.asc(), CandleRow.time.asc())
        )
        if symbols is not None:
            statement = statement.where(CandleRow.symbol.in_(symbols))
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def _build_sentiment_lookup(
        self,
        session: AsyncSession,
        *,
        symbols: Sequence[str],
        sentiment_dates: Sequence[date],
    ) -> dict[tuple[str, date], ResearchInputs]:
        """Build date-specific crypto sentiment inputs.

        Per-symbol rows are used when available. BTC/ETH sentiment is only a
        reduced macro prior for symbols without source-backed symbol coverage.
        """

        if not symbols or not sentiment_dates:
            return {}

        normalized_symbols = tuple(self._ordered_unique_symbols(symbols))
        unique_dates = tuple(sorted(set(sentiment_dates)))
        if not unique_dates:
            return {}

        start_date = unique_dates[0] - timedelta(days=6)
        end_date = unique_dates[-1]
        sentiment_symbols = tuple(
            self._ordered_unique_symbols((*normalized_symbols, "BTC/USD", "ETH/USD"))
        )
        result = await session.execute(
            select(CryptoDailySentimentRow)
            .where(CryptoDailySentimentRow.symbol.in_(sentiment_symbols))
            .where(CryptoDailySentimentRow.asset_class == "crypto")
            .where(CryptoDailySentimentRow.sentiment_date >= start_date)
            .where(CryptoDailySentimentRow.sentiment_date <= end_date)
            .order_by(
                CryptoDailySentimentRow.symbol.asc(),
                CryptoDailySentimentRow.sentiment_date.asc(),
            )
        )
        rows = list(result.scalars().all())
        rows_by_symbol = self._sentiment_rows_by_symbol(rows)

        macro_by_date: dict[date, ResearchInputs] = {}
        for sentiment_date in unique_dates:
            macro_by_date[sentiment_date] = self._macro_rows_to_research_inputs(
                sentiment_date=sentiment_date,
                btc_rows=rows_by_symbol.get("BTC/USD", []),
                eth_rows=rows_by_symbol.get("ETH/USD", []),
            )

        lookup: dict[tuple[str, date], ResearchInputs] = {}
        for symbol in normalized_symbols:
            symbol_rows = rows_by_symbol.get(symbol, [])
            for sentiment_date in unique_dates:
                macro_research = macro_by_date[sentiment_date]
                lookup[(symbol, sentiment_date)] = self._crypto_symbol_research_inputs(
                    symbol=symbol,
                    sentiment_date=sentiment_date,
                    symbol_rows=symbol_rows,
                    macro_research=macro_research,
                )
        return lookup

    def _macro_rows_by_symbol(
        self,
        rows: Sequence[CryptoDailySentimentRow],
    ) -> dict[str, list[CryptoDailySentimentRow]]:
        """Group source-backed macro sentiment rows by BTC/ETH symbol."""

        grouped = self._sentiment_rows_by_symbol(rows)
        return {
            "BTC/USD": grouped.get("BTC/USD", []),
            "ETH/USD": grouped.get("ETH/USD", []),
        }

    def _sentiment_rows_by_symbol(
        self,
        rows: Sequence[CryptoDailySentimentRow],
    ) -> dict[str, list[CryptoDailySentimentRow]]:
        """Group source-backed sentiment rows by normalized symbol."""

        grouped: dict[str, list[CryptoDailySentimentRow]] = defaultdict(list)
        for row in rows:
            grouped[row.symbol.upper()].append(row)
        return {symbol: list(symbol_rows) for symbol, symbol_rows in grouped.items()}

    def _crypto_symbol_research_inputs(
        self,
        *,
        symbol: str,
        sentiment_date: date,
        symbol_rows: Sequence[CryptoDailySentimentRow],
        macro_research: ResearchInputs,
    ) -> ResearchInputs:
        """Return per-symbol sentiment or a reduced BTC/ETH macro prior."""

        symbol_research = self._symbol_rows_to_research_inputs(
            sentiment_date=sentiment_date,
            rows=symbol_rows,
        )
        if symbol_research.news_article_count_7d > 0:
            return symbol_research

        if symbol in {"BTC/USD", "ETH/USD"}:
            return symbol_research

        return self._soften_macro_research_inputs(macro_research)

    def _symbol_rows_to_research_inputs(
        self,
        *,
        sentiment_date: date,
        rows: Sequence[CryptoDailySentimentRow],
    ) -> ResearchInputs:
        """Convert source-backed rows for one symbol into research inputs."""

        trailing_start = sentiment_date - timedelta(days=6)
        trailing_rows = [
            row
            for row in rows
            if trailing_start <= row.sentiment_date <= sentiment_date
            and row.article_count > 0
            and row.coverage_score > 0.0
        ]
        one_day = next(
            (row for row in trailing_rows if row.sentiment_date == sentiment_date),
            None,
        )
        if not trailing_rows:
            return ResearchInputs()

        weighted_total = 0.0
        article_count = 0
        for row in trailing_rows:
            observed = self._observed_compound_score(row)
            if observed is None:
                continue
            row_articles = max(0, int(row.article_count))
            weighted_total += observed * row_articles
            article_count += row_articles

        one_day_score = self._observed_compound_score(one_day)
        trailing_score = weighted_total / article_count if article_count > 0 else 0.0
        return ResearchInputs(
            news_sentiment_1d=self._feature_float(one_day_score),
            news_sentiment_7d=self._feature_float(trailing_score),
            news_article_count_7d=article_count,
        )

    def _soften_macro_research_inputs(self, macro_research: ResearchInputs) -> ResearchInputs:
        """Return BTC/ETH macro sentiment as a low-weight prior for uncovered alts."""

        return ResearchInputs(
            news_sentiment_1d=(
                macro_research.news_sentiment_1d * CRYPTO_MACRO_PRIOR_WEIGHT
            ),
            news_sentiment_7d=(
                macro_research.news_sentiment_7d * CRYPTO_MACRO_PRIOR_WEIGHT
            ),
            news_article_count_7d=round(
                macro_research.news_article_count_7d * CRYPTO_MACRO_PRIOR_WEIGHT
            ),
        )

    def _macro_rows_to_research_inputs(
        self,
        *,
        sentiment_date: date,
        btc_rows: Sequence[CryptoDailySentimentRow],
        eth_rows: Sequence[CryptoDailySentimentRow],
    ) -> ResearchInputs:
        """Convert BTC/ETH source rows into the existing crypto research feature contract."""

        macro_features = build_macro_sentiment_features(
            sentiment_date=sentiment_date,
            btc_rows=self._to_macro_sources(btc_rows),
            eth_rows=self._to_macro_sources(eth_rows),
        )
        return ResearchInputs(
            news_sentiment_1d=self._feature_float(macro_features.news_sentiment_1d),
            news_sentiment_7d=self._feature_float(macro_features.news_sentiment_7d),
            news_article_count_7d=macro_features.news_article_count_7d,
        )

    def _sentiment_rows_to_research_inputs(
        self,
        *,
        one_day: CryptoDailySentimentRow | None,
        trailing_rows: Sequence[CryptoDailySentimentRow],
    ) -> ResearchInputs:
        """Compatibility helper for legacy sentiment feature join tests."""

        if one_day is None and not trailing_rows:
            return ResearchInputs()
        target_date = (
            one_day.sentiment_date
            if one_day is not None
            else max(row.sentiment_date for row in trailing_rows)
        )
        return self._macro_rows_to_research_inputs(
            sentiment_date=target_date,
            btc_rows=trailing_rows,
            eth_rows=(),
        )

    def _to_macro_sources(
        self,
        rows: Sequence[CryptoDailySentimentRow],
    ) -> list[DailyMacroSentimentSource]:
        """Convert DB sentiment rows into macro blend source rows."""

        sources: list[DailyMacroSentimentSource] = []
        for row in rows:
            sources.append(
                DailyMacroSentimentSource(
                    symbol=row.symbol.upper(),
                    sentiment_date=row.sentiment_date,
                    compound_score=self._observed_compound_score(row),
                    article_count=max(0, int(row.article_count)),
                    coverage_score=max(
                        0.0,
                        self._coerce_float(row.coverage_score) or 0.0,
                    ),
                )
            )
        return sources

    def _feature_float(self, value: float | None) -> float:
        """Convert optional macro sentiment into the current non-null feature contract."""

        return value if value is not None else 0.0

    def _observed_compound_score(self, row: CryptoDailySentimentRow | None) -> float | None:
        """Return compound sentiment only when the row has source-backed coverage."""

        if row is None or row.article_count <= 0 or row.coverage_score <= 0.0:
            return None
        return self._coerce_float(row.compound_score)

    def _normalize_symbols(self, symbols: Sequence[str] | None) -> tuple[str, ...] | None:
        """Normalize optional symbol filters into a stable uppercase tuple."""

        if symbols is None:
            return None
        normalized = tuple(self._ordered_unique_symbols(symbols))
        return normalized if normalized else None

    def _ordered_unique_symbols(self, symbols: Iterable[str]) -> list[str]:
        """Return stable uppercase symbols without blanks or duplicates."""

        ordered: list[str] = []
        seen: set[str] = set()
        for raw_symbol in symbols:
            symbol = raw_symbol.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            ordered.append(symbol)
        return ordered

    def _row_to_candle(self, row: CandleRow) -> Candle:
        """Convert a persisted candle row into a domain candle."""

        return Candle(
            time=row.time,
            symbol=row.symbol,
            asset_class=row.asset_class,
            timeframe=row.timeframe,
            open=self._required_float(row.open, "open"),
            high=self._required_float(row.high, "high"),
            low=self._required_float(row.low, "low"),
            close=self._required_float(row.close, "close"),
            volume=self._required_float(row.volume, "volume"),
            source=row.source,
        )

    def _required_float(self, value: float | Decimal | None, field_name: str) -> float:
        """Convert a DB numeric field into float and reject missing candle components."""

        converted = self._coerce_float(value)
        if converted is None:
            raise ValueError(f"Candle row missing required numeric field: {field_name}")
        return converted

    def _coerce_float(self, value: object) -> float | None:
        """Convert supported scalar values into float."""

        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, Decimal):
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


async def train_crypto_model_from_db(
    session: AsyncSession,
    *,
    symbols: Sequence[str] | None = None,
    timeframe: str = "1Day",
    assembler: CryptoTrainingInputAssembler | None = None,
    trainer: WalkForwardTrainer | None = None,
    feature_engineer: FeatureEngineer | None = None,
) -> tuple[TrainResult, CryptoTrainingDataset]:
    """Assemble crypto candles/sentiment inputs from DB and train a model."""

    dataset_assembler = assembler or CryptoTrainingInputAssembler()
    model_trainer = trainer or WalkForwardTrainer()
    engineer = feature_engineer or FeatureEngineer()

    dataset = await dataset_assembler.assemble(session, symbols=symbols, timeframe=timeframe)
    if not dataset.candles:
        raise ValueError("No persisted crypto candles found for training")

    result = await model_trainer.train(
        dataset.candles,
        "crypto",
        engineer,
        research_lookup=dataset.research_lookup,
    )
    return result, dataset


async def train_stock_model_from_db(
    session: AsyncSession,
    *,
    symbols: Sequence[str] | None = None,
    timeframe: str = "1Day",
    assembler: StockTrainingInputAssembler | None = None,
    trainer: WalkForwardTrainer | None = None,
    feature_engineer: FeatureEngineer | None = None,
) -> tuple[TrainResult, StockTrainingDataset]:
    """Assemble stock candles/research inputs from DB and train a real walk-forward model."""

    dataset_assembler = assembler or StockTrainingInputAssembler()
    model_trainer = trainer or WalkForwardTrainer()
    engineer = feature_engineer or FeatureEngineer()

    dataset = await dataset_assembler.assemble(session, symbols=symbols, timeframe=timeframe)
    if not dataset.candles:
        raise ValueError("No persisted stock candles found for training")

    result = await model_trainer.train(
        dataset.candles,
        "stock",
        engineer,
        research_lookup=dataset.research_lookup,
    )
    return result, dataset