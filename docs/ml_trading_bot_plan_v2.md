# ML Trading Bot — Engineering Plan & Phase Checklist (v2)

> **Stack:** Python (FastAPI) · React (Vite) · Kraken (crypto live) · Tradier (stocks live + watchlist candles) · Alpaca (ML training OHLCV only) · TimescaleDB · Redis · LightGBM  
> **Constraints:** Single candle worker per symbol/timeframe · Max 5 open positions · Internal paper trading gate · Long-only unless stock balance > $2,500 · Crypto long-only always

---

## Broker & Data Source Responsibilities

| Broker / API | Role | What It Does |
|---|---|---|
| **Kraken** | Live crypto execution | Orders, WS price feed, fixed USD crypto universe |
| **Tradier** | Live stock execution + watchlist candles | Orders, quotes, OHLCV candles for active watchlist |
| **Alpaca** | ML training data only | Batch OHLCV fetch for stock universe and supported crypto overlap (no live orders) |
| **Alpaca** | Stock universe screening | Historical data for backtesting new watchlist candidates |

### Kraken / Alpaca Overlap — Top 15 USD Pairs (Fixed Universe)

```python
KRAKEN_UNIVERSE = [
    "BTC/USD",   "ETH/USD",  "SOL/USD",   "LTC/USD",  "BCH/USD",
    "LINK/USD",  "UNI/USD",  "AVAX/USD",  "DOGE/USD", "DOT/USD",
    "AAVE/USD",  "CRV/USD",  "SUSHI/USD", "SHIB/USD", "XTZ/USD",
]
# All 15 are always monitored. Candles via Tradier-equivalent Kraken REST.
# Crypto: long trades ONLY, no exceptions regardless of balance.
```

### Trade Direction Rules

```python
def can_go_short(asset_class: str, stock_balance: float) -> bool:
    if asset_class == "crypto":
        return False                    # Crypto: long only, always
    if asset_class == "stock":
        return stock_balance > 2500.0   # Stock: short allowed only if balance > $2,500
    return False
```

---

## Architecture Overview

| Layer | Technology | Purpose |
|---|---|---|
| API server | FastAPI + asyncpg | REST endpoints, WebSocket feeds, order routing |
| Time-series DB | TimescaleDB (Postgres ext.) | OHLCV candle storage, partitioned by symbol + timeframe |
| Cache / pub-sub | Redis | Candle close events, distributed locks, price cache |
| ML engine | LightGBM + scikit-learn | Signal classification, feature pipeline, walk-forward validation |
| Universe research | NLP + alternative data pipeline | News sentiment, congressional trades, insider filings, screeners |
| Task queue | Celery + Redis broker | Retrains, nightly reports, universe refresh, reconciliation |
| Frontend | React + Vite + lightweight-charts | Dashboard, watchlist manager, universe research panel |
| Monitoring | Prometheus + Grafana | System health, trading KPIs, latency tracking |
| Alerting | Telegram / PagerDuty | Circuit breakers, worker failures, new watchlist additions |

### Key Architectural Rules

- **One candle worker per (symbol, timeframe)** — Redis `SETNX` distributed lock, never duplicated
- **Candle fetch delay: ~15–20s after close** — default 17s, configurable per symbol, prevents dirty data
- **Tradier supplies watchlist candles** — only active watchlist symbols get live candle workers
- **Alpaca is batch-only, offline** — used exclusively for ML training data pulls, never for live signals
- **Max 5 concurrent positions per asset** — hard limit in `PortfolioManager` before any order submission
- **Paper trading gate** — 30-day minimum with quantitative thresholds before live capital

---

## Phase 1 — Core Infrastructure & Project Scaffold

**Timeline:** Week 1–2  
**Goal:** Monorepo, environment configs, full database schema including universe research tables, logging, CI/CD.

### Project Structure

- [ ] Initialize monorepo: `/backend` (FastAPI), `/frontend` (React + Vite), `/shared`, `/scripts`, `/research`
- [ ] Docker Compose: app, Postgres + TimescaleDB, Redis, Celery worker, Flower (Celery monitor)
- [ ] Environment config system: `.env` per stage (dev / paper / live), Pydantic settings model
- [ ] Structured JSON logging with correlation IDs (`structlog` or `loguru`)
- [ ] GitHub Actions CI: lint (`ruff`), type-check (`mypy`), pytest, coverage report on every PR
- [ ] Secrets management: broker API keys, Alpaca keys, news API keys via environment — never hardcoded

### Data Layer Schema

- [ ] TimescaleDB hypertable `candles` — partition by `(symbol, timeframe)`
- [ ] Redis pub/sub channels: `candle_closed:{symbol}:{tf}`, `signal:{symbol}`, `order_update`, `watchlist_updated`
- [ ] Async SQLAlchemy + asyncpg session factory with connection pooling
- [ ] Base repository pattern — CRUD + bulk upsert for candles and research records

```sql
-- Candles hypertable (TimescaleDB)
CREATE TABLE candles (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT        NOT NULL,
    asset_class TEXT        NOT NULL,  -- 'stock' | 'crypto'
    timeframe   TEXT        NOT NULL,
    open        NUMERIC,
    high        NUMERIC,
    low         NUMERIC,
    close       NUMERIC,
    volume      NUMERIC,
    source      TEXT        NOT NULL   -- 'tradier' | 'kraken' | 'alpaca_training'
);
SELECT create_hypertable('candles', 'time');
CREATE INDEX ON candles (symbol, timeframe, time DESC);

-- Watchlist — stocks currently being traded/monitored
CREATE TABLE watchlist (
    symbol          TEXT PRIMARY KEY,
    asset_class     TEXT NOT NULL,       -- 'stock' | 'crypto'
    added_at        TIMESTAMPTZ DEFAULT now(),
    added_by        TEXT,                -- 'ml_screener' | 'congress_signal' | 'insider_signal' | 'manual'
    research_score  NUMERIC,             -- composite score from universe research (0-100)
    is_active       BOOLEAN DEFAULT TRUE,
    notes           TEXT
);

-- Universe research signals
CREATE TABLE research_signals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    signal_type     TEXT NOT NULL,       -- 'news_sentiment' | 'congress_buy' | 'insider_buy' | 'screener' | 'analyst_upgrade'
    score           NUMERIC,             -- normalized signal strength (0-1)
    direction       TEXT,                -- 'bullish' | 'bearish' | 'neutral'
    source          TEXT,                -- 'benzinga' | 'house_stock_watcher' | 'sec_edgar' | 'finviz' etc.
    raw_data        JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON research_signals (symbol, signal_type, created_at DESC);

-- Congressional trade disclosures
CREATE TABLE congress_trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    politician      TEXT NOT NULL,
    chamber         TEXT,                -- 'house' | 'senate'
    symbol          TEXT NOT NULL,
    trade_type      TEXT,                -- 'purchase' | 'sale'
    amount_range    TEXT,                -- e.g. '$1,001 - $15,000'
    trade_date      DATE,
    disclosure_date DATE,
    days_to_disclose INT,                -- disclosure_date - trade_date (lower = more timely signal)
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Insider trading filings (SEC Form 4)
CREATE TABLE insider_trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    insider_name    TEXT NOT NULL,
    title           TEXT,                -- CEO | CFO | Director | 10% Owner, etc.
    transaction_type TEXT,              -- 'P' = purchase | 'S' = sale
    shares          NUMERIC,
    price_per_share NUMERIC,
    total_value     NUMERIC,
    filing_date     DATE,
    transaction_date DATE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Positions table
CREATE TABLE positions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol      TEXT NOT NULL,
    asset_class TEXT NOT NULL,
    side        TEXT NOT NULL,           -- 'long' | 'short'
    entry_price NUMERIC NOT NULL,
    size        NUMERIC NOT NULL,
    sl_price    NUMERIC,
    tp_price    NUMERIC,
    strategy_id TEXT,
    ml_confidence NUMERIC,
    research_score NUMERIC,              -- universe score at time of entry
    opened_at   TIMESTAMPTZ DEFAULT now(),
    closed_at   TIMESTAMPTZ,
    status      TEXT DEFAULT 'open'      -- 'open' | 'closed' | 'cancelled'
);
```

---

## Phase 2 — Stock Universe Research Engine

**Timeline:** Week 2–4 (runs in parallel with Phase 3)  
**Goal:** Build an async, fully typed research pipeline that scores stock candidates and
promotes only the best candidates into the watchlist. All Phase 2 Python code must follow
the strict Python 3.12 rules: explicit annotations, built-in generics, `X | None` unions,
`@dataclass(slots=True, frozen=True)` for value objects, and async I/O for all external calls.

### 2A — Shared Research Primitives

- [ ] Define common models in `backend/app/research/models.py` using Python 3.12 syntax
- [ ] Keep API-bound payloads in Pydantic v2 models; keep internal value objects as frozen dataclasses
- [ ] Persist all research records through repositories only; no inline SQL in services or routers
- [ ] Add `source` to every persisted candle or research record to prevent data contamination
- [ ] Keep business thresholds in `backend/app/config/constants.py` or YAML, never hardcode them in services
- [ ] Make every network-bound research client async and wrap failures in named domain exceptions

```python
"""Shared research value objects."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class SentimentScore:
    """Represent one article sentiment result."""

    direction: str
    confidence: float
    numeric: float
    created_at: datetime


@dataclass(slots=True, frozen=True)
class ResearchScoreBreakdown:
    """Represent a composite watchlist score and its contributors."""

    symbol: str
    news_sentiment_7d: float
    congress_buy: float
    insider_buy: float
    screener_pass: float
    analyst_upgrade: float
    composite_score: float
```

### 2B — News Sentiment Pipeline

- [ ] Integrate **Benzinga Pro API** (or Finnhub news) for real-time equity news by ticker
- [ ] **FinBERT** model (HuggingFace `ProsusAI/finbert`) — financial-domain BERT for sentiment scoring
- [ ] Score each article: `bullish` / `neutral` / `bearish` + confidence (0–1), persist to `research_signals`
- [ ] Aggregate rolling sentiment: 24h, 3-day, 7-day weighted average (recency-weighted)
- [ ] Volume-weighted signal: more articles = stronger signal, diminishing returns above N articles/day
- [ ] Filter noise: ignore articles with < 0.65 FinBERT confidence; ignore boilerplate earnings reminders
- [ ] **Earnings event flag:** suppress sentiment signal 48h before and 24h after earnings (high noise window)
- [ ] Celery task: poll news every 15 minutes during market hours, store and score incrementally

```python
"""News sentiment scoring pipeline."""

from collections.abc import Sequence
from datetime import UTC, datetime


class NewsSentimentPipeline:
    """Score equity news with FinBERT."""

    def __init__(self, model_name: str = "ProsusAI/finbert") -> None:
        self.model_name = model_name
        self.model = pipeline(
            "text-classification",
            model=model_name,
            return_all_scores=True,
        )

    def score_article(self, title: str, summary: str) -> SentimentScore:
        """Return a sentiment score for one article."""

        text = f"{title}. {summary}"[:512]
        scores = self.model(text)[0]
        score_map = {score["label"]: score["score"] for score in scores}
        direction = max(score_map, key=score_map.get)
        confidence = score_map[direction]
        numeric = score_map["positive"] - score_map["negative"]
        return SentimentScore(
            direction=direction,
            confidence=confidence,
            numeric=numeric,
            created_at=datetime.now(tz=UTC),
        )

    def rolling_score(
        self,
        articles: Sequence[SentimentScore],
        decay_halflife_days: float = 3.0,
    ) -> float:
        """Return an exponentially weighted rolling sentiment score."""

        if not articles:
            return 0.0
        weights = [0.5 ** (index / decay_halflife_days) for index in range(len(articles))]
        return sum(a.numeric * w for a, w in zip(articles, weights)) / sum(weights)
```

### 2C — Congressional Trading Signals

- [ ] **House Stock Watcher API** (`housestockwatcher.com/api`) — free, daily disclosure scrape
- [ ] **Senate Stock Watcher API** (`senatestockwatcher.com/api`) — Senate STOCK Act disclosures
- [ ] Parse: politician name, chamber, symbol, trade type (purchase/sale), amount range, dates
- [ ] Compute `days_to_disclose` — politicians must file within 45 days; shorter lag = more urgent signal
- [ ] Score logic: purchase by committee-relevant member → high score; sale → negative signal
- [ ] Committee relevance map: Armed Services → defense stocks; Finance → banks; Energy → energy stocks
- [ ] Cluster detection: ≥ 3 politicians buying same stock within 30 days = strong correlated signal
- [ ] Celery daily task: sync new disclosures at 6 AM ET, upsert to `congress_trades`
- [ ] Watchlist promotion: symbol with composite congress score > 70 → auto-add to watchlist candidates

```python
"""Congress trading scoring helpers."""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CongressTrade:
    """Represent one congressional trade disclosure."""

    symbol: str
    trade_type: str
    days_to_disclose: int


COMMITTEE_SECTOR_MAP = {
    "Armed Services": ["LMT", "RTX", "NOC", "GD", "BA"],
    "Energy and Commerce":      ["XOM", "CVX", "COP", "SLB"],
    "Financial Services":       ["JPM", "GS", "BAC", "MS", "C"],
    "Technology":               ["AAPL", "MSFT", "NVDA", "GOOGL"],
    "Health":                   ["UNH", "JNJ", "PFE", "ABBV"],
}

def score_congress_trade(trade: CongressTrade, politician_committees: list[str]) -> float:
    """Score a congressional trade using recency and committee relevance."""

    base = 0.5 if trade.trade_type == "purchase" else -0.5
    recency = max(0, 1 - (trade.days_to_disclose / 45))
    relevance = 1.0 if any(trade.symbol in COMMITTEE_SECTOR_MAP.get(c, [])
                           for c in politician_committees) else 0.6
    return base * recency * relevance
```

### 2D — Insider Trading Signals (SEC Form 4)

- [ ] **SEC EDGAR Form 4 RSS feed** — free, real-time filings at `https://www.sec.gov/cgi-bin/browse-edgar`
- [ ] Alternative: **OpenInsider API** or **SEC API** (`sec-api.io`) for structured Form 4 data
- [ ] Parse: insider name, title, transaction type (P/S), shares, price, filing date, transaction date
- [ ] **Signal weighting by insider title:**
  - CEO purchase → weight 1.0 (strongest signal)
  - CFO purchase → weight 0.9
  - Director purchase → weight 0.7
  - 10%+ Owner purchase → weight 0.6 (less informative — may be strategic)
- [ ] **Cluster signal:** ≥ 2 C-suite insiders buying same stock within 60 days → score boost
- [ ] **Size filter:** only flag purchases > $50,000 total value (eliminates noise from token grants)
- [ ] **Open-market only:** exclude option exercises and gifted shares (set `transaction_type = 'P'` only)
- [ ] Celery task: poll EDGAR RSS every 30 minutes, parse and score Form 4 filings
- [ ] Watchlist promotion: insider buy score > 0.75 on a stock not in watchlist → trigger review

```python
"""Insider trade scoring helpers."""

from dataclasses import dataclass

from app.config.constants import MIN_INSIDER_PURCHASE_VALUE


@dataclass(slots=True, frozen=True)
class InsiderTrade:
    """Represent one insider filing."""

    symbol: str
    title: str
    transaction_type: str
    total_value: float


def is_material_purchase(trade: InsiderTrade) -> bool:
    """Return True when the filing is a meaningful open-market purchase."""

    return trade.transaction_type == "P" and trade.total_value > MIN_INSIDER_PURCHASE_VALUE
```

### 2E — Quantitative Stock Screener

- [ ] **FinViz Elite screener** or **Finviz API** for daily screening pass (fallback: yfinance batch)
- [ ] **Alpaca batch OHLCV** — fetch 2-year history for all screener candidates in one API call
- [ ] Screening criteria (all must pass):

```python
SCREENER_CRITERIA = {
    "min_avg_volume":       1_000_000,    # 20-day avg daily volume > 1M shares
    "min_price":            5.0,          # Price > $5 (avoids penny stock noise)
    "max_price":            500.0,        # Under $500 (position sizing headroom)
    "min_market_cap":       2e9,          # Large/mid cap only (> $2B)
    "max_pe_ratio":         60,           # Not absurdly valued
    "min_relative_volume":  1.5,          # Today's volume > 1.5× 20-day avg (interest spike)
    "float_min":            10e6,         # Float > 10M shares (avoid illiquid micro-cap)
    "sectors_allowed": [                  # Tradeable sectors only
        "Technology", "Healthcare", "Financials", "Consumer Discretionary",
        "Industrials", "Energy", "Communication Services", "Materials",
    ],
}
```

- [ ] **Technical pre-filter:** symbol must be above its 50-day EMA on daily chart (trending up)
- [ ] **Earnings exclusion:** remove any symbol with earnings within next 5 trading days
- [ ] Daily screener run at 8:30 AM ET (1 hour before open), results scored and ranked

### 2F — Analyst Upgrades & Price Target Changes

- [ ] **Benzinga analyst ratings API** or **Tipranks** — parse upgrades, initiations, price target raises
- [ ] Score: strong buy initiation from top-tier firm (Goldman, Morgan Stanley, JPM) → score 0.9
- [ ] Score: price target raise > 15% from current price → score 0.7
- [ ] Filter: only act on upgrades where current price is within 10% of old PT (room to run)
- [ ] Persist to `research_signals` with `signal_type = 'analyst_upgrade'`

### 2G — Composite Watchlist Score & Promotion Engine

- [ ] `WatchlistScorer` — combines all signals into a single composite score (0–100)
- [ ] Weighting (tunable via YAML config and loaded into a typed settings model):

```python
SIGNAL_WEIGHTS = {
    "news_sentiment_7d":    0.20,   # Rolling 7-day FinBERT score
    "congress_buy":         0.30,   # Congressional purchase signal
    "insider_buy":          0.25,   # SEC Form 4 open-market purchase
    "screener_pass":        0.15,   # Quantitative screener score
    "analyst_upgrade":      0.10,   # Analyst upgrade/initiation
}
# Composite = weighted sum, normalized to 0-100
# Promotion threshold: composite score ≥ 65 → candidate for watchlist
# Auto-add threshold: composite score ≥ 80 → auto-add, notify via Telegram
```

- [ ] `WatchlistManager` service: maintains active list, handles promotions and demotions
- [ ] Auto-demotion: symbol's composite score drops below 30 for 5 consecutive days → remove from watchlist
- [ ] Max watchlist size: 20 stocks at any time (beyond that, only highest-scoring candidates in)
- [ ] Telegram alert on every watchlist add/remove with score breakdown
- [ ] React panel: shows each symbol's signal breakdown — news bar, congress timeline, insider table

```python
"""Composite research scoring."""

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class WatchlistScore:
    """Represent a normalized watchlist score."""

    symbol: str
    score: float


def calculate_composite_score(
    news_sentiment_7d: float,
    congress_buy: float,
    insider_buy: float,
    screener_pass: float,
    analyst_upgrade: float,
) -> float:
    """Return a weighted composite score in the 0-100 range."""

    weights = {
        "news_sentiment_7d": 0.20,
        "congress_buy": 0.30,
        "insider_buy": 0.25,
        "screener_pass": 0.15,
        "analyst_upgrade": 0.10,
    }
    composite = (
        news_sentiment_7d * weights["news_sentiment_7d"]
        + congress_buy * weights["congress_buy"]
        + insider_buy * weights["insider_buy"]
        + screener_pass * weights["screener_pass"]
        + analyst_upgrade * weights["analyst_upgrade"]
    )
    return max(0.0, min(100.0, composite * 100.0))
```

---

## Phase 3 — Alpaca Training Data Pipeline

**Timeline:** Week 3–4  
**Goal:** Use Alpaca's batch API exclusively to pull historical OHLCV for ML model training. Never used for live signals or orders.

### Alpaca Batch OHLCV Fetcher

- [ ] `AlpacaTrainingFetcher` — isolated module, no integration with live trading path
- [ ] Fetch up to 200 symbols in a single Alpaca batch request (respects their bulk endpoint)
- [ ] Timeframes: `1Min`, `5Min`, `15Min`, `1Hour`, `1Day` — stored with `source = 'alpaca_training'`
- [ ] Pull 2-year history for all watchlist candidates + S&P 500 universe on initial seed
- [ ] Weekly incremental sync: fetch only the delta since last stored candle
- [ ] Validate: no gaps > 3 candles, no zero-volume days on trading days, OHLC sanity checks
- [ ] Store in `candles` table with `source = 'alpaca_training'` — query-time filter prevents mixing with live data

```python
class AlpacaTrainingFetcher:
    """Batch historical OHLCV fetcher for ML training only.
    This class has NO connection to any live trading component.
    """
    BASE_URL = "https://data.alpaca.markets/v2"

    async def fetch_batch(
        self,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, list[Candle]]:
        """Fetch OHLCV for up to 200 symbols in one request."""
        params = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "all",   # corporate action adjusted
            "feed": "sip",         # consolidated tape
            "limit": 10000,
        }
        resp = await self.client.get(f"{self.BASE_URL}/stocks/bars", params=params)
        return self._parse_multi_bars(resp.json())

    async def sync_universe(self, symbols: list[str], timeframes: list[str]):
        """Weekly incremental sync for all watchlist candidates."""
        for tf in timeframes:
            # Batch symbols in groups of 200 (Alpaca limit)
            for batch in chunked(symbols, 200):
                last_stored = await self.repo.get_last_candle_time(batch, tf, source="alpaca_training")
                data = await self.fetch_batch(batch, tf, start=last_stored, end=datetime.utcnow())
                await self.repo.bulk_upsert(data, source="alpaca_training")
```

---

## Phase 4 — Market Data Pipeline & Candle Workers

**Timeline:** Week 4–5  
**Goal:** Tradier candle workers for active stock watchlist. Kraken candle workers for top 15 crypto pairs. Single worker per (symbol, timeframe) enforced via Redis lock.

### Stock Candle Workers (Tradier)

- [ ] `TradierCandleWorker`: subscribes to Tradier streaming quotes, tracks candle boundary by timeframe
- [ ] On candle close: wait 17s, fetch confirmed OHLCV from Tradier REST `/markets/history`
- [ ] Workers spawned only for symbols on the active watchlist — dynamically start/stop as watchlist changes
- [ ] Subscribe to Redis `watchlist_updated` event → start new worker for added symbol, stop for removed
- [ ] Validate OHLCV before persisting; publish `candle_closed:stock:{symbol}:{tf}` to Redis

### Crypto Candle Workers (Kraken)

- [ ] `KrakenCandleWorker`: subscribes to Kraken WS `ohlc` channel, one subscription per pair
- [ ] Fixed universe: always run workers for all 15 `KRAKEN_UNIVERSE` pairs — never dynamic
- [ ] On candle close: wait 17s, fetch OHLCV via Kraken REST `/0/public/OHLC`
- [ ] Validate and persist; publish `candle_closed:crypto:{symbol}:{tf}` to Redis

### Shared Candle Worker Rules

- [ ] Single-worker enforcement: Redis `SETNX` lock per `(asset_class, symbol, tf)` — TTL 2h, heartbeat refresh
- [ ] Back-fill on startup: pull historical candles from Tradier/Kraken to seed indicator windows
- [ ] Worker health monitor: alert via Telegram if any worker has not published in > 3× timeframe duration
- [ ] Price API (separate): Kraken + Tradier WebSocket for live bid/ask → Redis cache with 5s TTL

```python
class CandleWorker:
    def __init__(self, symbol: str, asset_class: str, timeframe: str,
                 source: str, delay_s: int = 17):
        self.symbol = symbol
        self.asset_class = asset_class
        self.tf = timeframe
        self.source = source          # 'tradier' | 'kraken'
        self.delay_s = delay_s
        self.lock_key = f"candle_worker:{asset_class}:{symbol}:{timeframe}"
        self.heartbeat_key = f"candle_heartbeat:{asset_class}:{symbol}:{timeframe}"

    async def run(self):
        acquired = await redis.set(self.lock_key, "1", nx=True, ex=7200)
        if not acquired:
            raise RuntimeError(f"Worker already running: {self.asset_class}/{self.symbol}/{self.tf}")

        async for candle_close_ts in self._stream_candle_closes():
            await asyncio.sleep(self.delay_s)
            await redis.expire(self.lock_key, 7200)           # refresh lock
            await redis.set(self.heartbeat_key, datetime.utcnow().isoformat(), ex=3600)
            candle = await self._fetch_confirmed_candle(candle_close_ts)
            if self._is_valid(candle):
                await self._persist(candle)
                channel = f"candle_closed:{self.asset_class}:{self.symbol}:{self.tf}"
                await redis.publish(channel, candle.json())

    def _is_valid(self, candle) -> bool:
        return (candle.volume > 0 and candle.high >= candle.low
                and candle.open > 0 and candle.close > 0)
```

---

## Phase 5 — Strategy Engine & Signal Generation

**Timeline:** Week 5–7  
**Goal:** Modular strategy framework with quant signals, ML overlay trained on Alpaca data, and trade direction enforcement.

### Strategy Framework

- [ ] `BaseStrategy` ABC: `on_candle(candle, balance) → Optional[Signal]` — balance passed for short eligibility
- [ ] `IndicatorLib`: vectorized pandas/numpy — EMA, VWAP, RSI, ATR, Bollinger Bands, ADX, MACD, OBV
- [ ] `Signal` dataclass: `symbol`, `asset_class`, `direction` (long/short/flat), `strength` (0–1), `entry_price`, `sl_price`, `tp_price`, `strategy_id`, `research_score`
- [ ] `StrategyRegistry`: YAML config — enable/disable strategies, set per-strategy risk multipliers
- [ ] **Direction gate:** every signal passes through `DirectionGate` before submission

```python
class DirectionGate:
    """Enforces long-only rules before any signal reaches the order engine."""

    def passes(self, signal: Signal, stock_balance: float) -> bool:
        if signal.asset_class == "crypto":
            if signal.direction == "short":
                logger.warning(f"Blocked short crypto signal for {signal.symbol} — crypto long only")
                return False
        elif signal.asset_class == "stock":
            if signal.direction == "short" and stock_balance <= 2500.0:
                logger.info(f"Blocked short stock signal for {signal.symbol} — balance ${stock_balance:.0f} ≤ $2,500")
                return False
        return True
```

### Quant Alpha Signals

- [ ] **Momentum:** Dual EMA crossover (8/21) with ADX > 25 filter — trend confirmation required
- [ ] **Mean reversion:** RSI extremes (< 30 / > 70) at Bollinger Band touch — long only below lower band
- [ ] **VWAP deviation:** Enter long when price > 1.5 std-devs below VWAP with volume confirmation
- [ ] **Breakout:** N-candle range high/low breakout with volume > 1.5× 20-candle average
- [ ] **Regime filter:** 200-EMA slope → only long above (stock + crypto), short only if balance allows and below
- [ ] **Volatility filter:** Skip signals when ATR % is in bottom 20th percentile
- [ ] **Order flow proxy:** Candle close location (close vs. wick ratio) as buying/selling pressure
- [ ] **Correlation filter:** Block new position if correlation > 0.7 with any open position
- [ ] **Research score boost:** Signals on symbols with research_score > 70 get 15% size bonus
- [ ] **Earnings blackout:** No new stock entries within 48h before or 24h after earnings

### ML Signal Layer

- [ ] Feature engineering pipeline: 80–120 features — technical indicators + research signal features
- [ ] **Research features added to ML input:**

```python
RESEARCH_FEATURES = [
    # News sentiment
    "news_sentiment_1d",        # 1-day rolling FinBERT score (-1 to +1)
    "news_sentiment_7d",        # 7-day rolling FinBERT score
    "news_article_count_7d",    # Volume of coverage
    "earnings_proximity_days",  # Days until/since last earnings

    # Congressional signal
    "congress_buy_score",       # Composite congress buy signal (0-1)
    "congress_cluster_30d",     # Number of politicians buying in last 30 days
    "days_since_last_congress", # Recency of most recent congress trade

    # Insider signal
    "insider_buy_score",        # Weighted insider purchase score (0-1)
    "insider_cluster_60d",      # Number of insiders buying in 60 days
    "insider_value_60d",        # Total dollar value of insider buys (log-scaled)
    "ceo_bought_90d",           # Binary: CEO purchased in last 90 days

    # Analyst
    "analyst_upgrade_score",    # Recent upgrade signal strength (0-1)
    "consensus_rating",         # 1=strong sell → 5=strong buy

    # Composite
    "watchlist_research_score", # Overall composite score (0-100, normalized to 0-1)
]
```

- [ ] **Training data source:** Alpaca batch OHLCV only — joined with research signals from DB
- [ ] LightGBM classifier: predict next-candle direction (up/flat/down) — train on 2-year Alpaca history
- [ ] **Separate models per asset class:** `model_stock.lgbm` and `model_crypto.lgbm`
- [ ] ML confidence threshold: 0.60 minimum to generate a signal; below threshold → no trade
- [ ] Walk-forward validation: 6-month train, 1-month test, roll forward — no lookahead bias
- [ ] Feature importance tracking — auto-prune zero-importance features each retrain
- [ ] Weekly retrain cron: auto-deploy if validation Sharpe improves; otherwise keep current model
- [ ] SHAP values logged per trade for explainability and model debugging
- [ ] **Research signal drift monitor:** alert if congressional/insider feature importance drops > 20% vs. prior run

### Feature Engineering Reference (Full)

```python
FEATURES = [
    # Price & returns
    "returns_1", "returns_3", "returns_5", "returns_10",
    "log_return_1", "log_return_5", "log_return_10",

    # Trend
    "ema_8", "ema_21", "ema_55", "ema_200",
    "ema_cross_8_21", "ema_cross_21_55", "price_vs_ema200",
    "adx_14", "di_plus_14", "di_minus_14",

    # Momentum
    "rsi_14", "rsi_7", "rsi_21",
    "macd", "macd_signal", "macd_hist", "macd_hist_slope",
    "stoch_k", "stoch_d", "cci_20", "williams_r_14",

    # Volatility
    "atr_14", "atr_pct_14", "bb_width", "bb_pct",
    "hist_vol_10", "hist_vol_20", "atr_percentile_252d",

    # Volume
    "volume_ratio_20", "volume_ratio_5", "obv", "obv_slope",
    "vwap_deviation", "vwap_deviation_pct",

    # Candle structure
    "candle_body_pct",    # body / total range
    "upper_wick_pct",     # upper wick / total range
    "lower_wick_pct",     # lower wick / total range
    "close_location",     # (close - low) / (high - low)

    # Calendar
    "hour_of_day", "day_of_week", "week_of_month",
    "is_monday", "is_friday", "days_to_month_end",

    # Research signals (stocks only — zero-filled for crypto)
    *RESEARCH_FEATURES,
]
```

---

## Phase 6 — Risk Engine & Position Sizing

**Timeline:** Week 7–8  
**Goal:** Portfolio-level risk controls, Kelly/ATR sizing with research score bonus, direction enforcement, drawdown circuit breakers.

### Position Sizing

- [ ] **ATR-based sizing (primary):** `size = (equity × risk_pct) / abs(entry_price − sl_price)`
- [ ] **Quarter-Kelly cross-check:** `kelly_size = equity × (edge / odds) × 0.25`
- [ ] **ML confidence scalar:** maps [0.6, 1.0] → [0.6×, 1.0×] multiplier on base size
- [ ] **Research score bonus (stocks):** score ≥ 70 → +15% size; score ≥ 85 → +25% size (cap at max)
- [ ] **Max single position:** 20% of portfolio — absolute hard cap
- [ ] **Liquidity check:** size < 1% of 20-day avg daily volume

### Portfolio Risk Controls

- [ ] `MAX_POSITIONS = 5` — checked before any signal reaches order engine
- [ ] **Position slots by asset class:** configurable split, e.g. max 3 crypto + max 3 stocks (can overlap at ≤ 5 total)
- [ ] Max total capital at risk: sum of (entry − SL) × size across all positions ≤ 6% of NAV
- [ ] **Short eligibility gate:** `stock_balance > $2,500` checked at signal time AND at order submission
- [ ] Correlation block: reject if new position would create portfolio correlation > 0.7
- [ ] **Daily loss limit:** halt all trading if daily P&L < −2% of NAV (auto circuit breaker)
- [ ] **Weekly drawdown limit:** halt + Telegram alert if weekly DD > 5% — manual re-enable required
- [ ] **Peak drawdown limit:** halt if 30-day rolling drawdown > 15%
- [ ] Trailing stop engine: move SL to breakeven at 1:1 R, trail with 1.5× ATR thereafter
- [ ] Time-based exit: close position after max N candles (configurable per strategy)

```python
def calculate_position_size(
    equity: float,
    entry_price: float,
    sl_price: float,
    ml_confidence: float,
    research_score: float = 0.0,    # 0-100, 0 for crypto
    asset_class: str = "stock",
    risk_pct: float = 0.01,
    max_position_pct: float = 0.20,
) -> float:
    sl_distance = abs(entry_price - sl_price)
    if sl_distance == 0:
        return 0.0

    base_size = (equity * risk_pct) / sl_distance

    # ML confidence scalar: [0.6, 1.0] → [0.6, 1.0]
    conf_scalar = max(0.6, min(1.0, ml_confidence))

    # Research score bonus (stocks only)
    research_bonus = 1.0
    if asset_class == "stock":
        if research_score >= 85:
            research_bonus = 1.25
        elif research_score >= 70:
            research_bonus = 1.15

    sized = base_size * conf_scalar * research_bonus

    # Hard cap
    max_size = (equity * max_position_pct) / entry_price
    return min(sized, max_size)
```

---

## Phase 7 — Internal Paper Trading Engine

**Timeline:** Week 8–9  
**Goal:** Full internal paper trading — realistic fills, slippage, commissions. Validates all new constraints before any live capital.

### Paper Broker Core

- [ ] `PaperBroker` implementing `BaseBroker` — identical interface to `KrakenBroker` / `TradierBroker`
- [ ] Virtual portfolios: `paper_stock_balance` and `paper_crypto_balance` tracked separately
- [ ] Short eligibility uses `paper_stock_balance` — tests the > $2,500 gate under simulated conditions
- [ ] Market orders: fill at last price + slippage model
- [ ] Limit orders: fill when `last_price` crosses `limit_price` on next matching candle
- [ ] Slippage: `N(0, σ)` where σ = 0.05% liquid, 0.15% illiquid stocks, 0.10% crypto mid-caps
- [ ] Commission: configurable flat + % (default: Tradier $0 flat + 0% for stocks, Kraken 0.16% taker)
- [ ] Partial fills: order size > 0.5% of candle volume → fill in 2–3 candles

### Paper Trading Validation Checklist

- [ ] Run paper trading for **minimum 30 calendar days** before live capital
- [ ] Verify: NAV = realized P&L + unrealized P&L + starting capital (to the cent)
- [ ] Verify: short signals are blocked when simulated stock balance ≤ $2,500
- [ ] Verify: zero short crypto signals appear in logs regardless of balance
- [ ] Stress test: replay 2020 crash, 2022 bear, 2024 vol spikes — max DD and recovery measured
- [ ] Confirm: research-boosted signals result in correct size multipliers vs. non-research signals
- [ ] Confirm: circuit breakers trigger correctly under simulated loss sequences
- [ ] Confirm: Alpaca training data does not bleed into candle worker path (source field isolation)
- [ ] **Paper Sharpe ≥ 1.0** and **Calmar ≥ 0.5** required — measured separately for stocks and crypto

### Go/No-Go Criteria (Paper → Live)

| Metric | Stock | Crypto |
|---|---|---|
| Sharpe ratio (annualized) | ≥ 1.0 | ≥ 1.0 |
| Calmar ratio | ≥ 0.5 | ≥ 0.5 |
| Win rate | ≥ 45% | ≥ 45% |
| Profit factor | ≥ 1.3 | ≥ 1.3 |
| Max drawdown | ≤ 15% | ≤ 18% |
| Paper run duration | ≥ 30 days | ≥ 30 days |
| Completed trades | ≥ 50 | ≥ 30 |
| Short gate verified | ✓ | n/a |
| Zero crypto shorts | n/a | ✓ |
| Research signal correlation | ≥ 0.15 with returns | n/a |

---

## Phase 8 — Live Brokers, React UI & Monitoring

**Timeline:** Week 9–11  
**Goal:** Kraken and Tradier live execution, full React dashboard with universe research panel, and alerting stack.

### Live Broker Integration

- [ ] `KrakenBroker`: REST + WS — `add_order`, `cancel_order`, `get_balance`, `get_open_positions`
- [ ] `TradierBroker`: REST — orders, account balance (stock), open positions, streaming quotes
- [ ] `BrokerRouter`: crypto symbols → `KrakenBroker`; stock symbols → `TradierBroker`
- [ ] Separate balance tracking: `kraken_balance` and `tradier_balance` — short gate reads `tradier_balance`
- [ ] Order state machine: `PENDING → SUBMITTED → PARTIAL → FILLED / CANCELLED / REJECTED`
- [ ] Reconciliation job: every 5 min compare internal state vs. broker account state
- [ ] **Emergency kill switch:** `POST /api/admin/halt` — cancel all orders, close all positions at market

```python
from abc import ABC, abstractmethod

class BaseBroker(ABC):
    @abstractmethod
    async def submit_order(self, symbol: str, side: str, size: float,
                           order_type: str, limit_price: float | None = None) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Position | None: ...

    @abstractmethod
    async def get_account_balance(self) -> dict[str, float]: ...
    # Returns: {"usd": float, "crypto_usd_equiv": float} for Kraken
    #          {"cash": float, "equity": float} for Tradier

    @abstractmethod
    async def get_open_orders(self) -> list[Order]: ...
```

### React Dashboard

- [ ] **Portfolio overview:** NAV, daily P&L, stock balance (with short-eligibility indicator), crypto balance
- [ ] **Live chart:** `lightweight-charts` OHLCV with signal markers, SL/TP lines, research score badge
- [ ] **Position cards:** symbol, entry, current price, unrealized P&L, SL/TP, ML confidence, research score
- [ ] **Watchlist manager:** table of active symbols with composite score, signal breakdown bars, add/remove
- [ ] **Universe research panel:**
  - News sentiment feed per symbol (FinBERT scores, article list)
  - Congressional trades timeline (politician, date, size, committee)
  - Insider trades table (name, title, shares, value, date)
  - Analyst upgrade log
  - Composite score history chart (30-day trend)
- [ ] **Strategy control panel:** enable/disable strategies, set risk multipliers, view per-strategy P&L
- [ ] **Paper ↔ Live mode toggle:** hard confirmation modal + password gate + 5-second delay
- [ ] **Performance analytics:** equity curve, rolling Sharpe, drawdown chart, win rate by strategy and asset class

### Monitoring & Alerting

- [ ] Prometheus metrics: candle lag, signal rate, order latency, fill rate, daily P&L, watchlist size
- [ ] Grafana dashboard: system health + trading KPIs + research pipeline health in one view
- [ ] Celery Flower: monitor all async tasks — retrain jobs, news polls, congress sync, screener runs
- [ ] **Telegram alerts:**
  - Candle worker silent > 3× timeframe → "⚠️ Worker dead: BTC/USD 1h"
  - Circuit breaker triggered → "🛑 Daily loss limit hit — trading halted"
  - New watchlist addition (auto) → "📋 NVDA added to watchlist — score: 84/100"
  - New congress buy detected → "🏛️ 3 senators bought PLTR this week"
  - New insider cluster → "👔 CEO + CFO of AAPL bought $2.1M in last 30 days"
- [ ] Nightly Celery report: P&L, positions, top research signals, ML model drift metrics

---

## Quant Research — Additional Methods

### Statistical & Econometric

| Method | Use Case | Complexity |
|---|---|---|
| Kalman filter | Dynamic hedge ratio, spread estimation for pairs | Medium |
| Cointegration (Johansen) | Pairs trading — stock + ETF basket arb | Medium |
| GARCH(1,1) | Volatility forecasting for position sizing | Medium |
| Hidden Markov Model | Market regime (bull/bear/sideways) classification | High |
| Ornstein-Uhlenbeck | Mean-reversion speed estimation for stat arb | Medium |

### ML Extensions

| Method | Use Case | Complexity |
|---|---|---|
| XGBoost ensemble | Vote with LightGBM on direction | Low |
| LSTM / Temporal Transformer | Sequence modeling on OHLCV time series | High |
| FinBERT fine-tune | Domain-adapt on your own trade history + news | High |
| Isolation Forest | Anomaly detection on price/volume/research signals | Low |
| Topic modeling (LDA/BERTopic) | Cluster news themes — detect emerging sector rotations | Medium |
| Named entity recognition (NER) | Extract tickers from news headlines automatically | Medium |

### Alternative Data Extensions

| Data Source | Signal | Complexity |
|---|---|---|
| **Reddit WallStreetBets** | Social sentiment momentum (retail crowd) | Low |
| **Twitter/X Fintwit** | Real-time hype detection via keyword tracking | Low |
| **Google Trends** | Search interest as leading indicator of retail attention | Low |
| **SEC 13F filings** | Track what top hedge funds bought last quarter | Medium |
| **Put/Call ratio** | Options market sentiment as contrarian indicator | Low |
| **Short interest data** | High short interest + positive catalyst = squeeze setup | Medium |
| **Satellite / alt data** | Parking lot occupancy, shipping data (institutional feeds) | Very High |

### Execution & Microstructure

| Method | Use Case | Complexity |
|---|---|---|
| TWAP / VWAP execution | Reduce market impact on larger orders | Low |
| Bid-ask spread modeling | Estimate realistic fill cost pre-trade | Medium |
| Order book imbalance (L2) | Directional signal from Kraken L2 data | Medium |
| Smart order routing | Route paper vs. live based on mode flag | Low |

### Portfolio Construction

| Method | Use Case | Complexity |
|---|---|---|
| Mean-variance optimization | Efficient frontier position weights across 5 slots | Medium |
| Risk parity | Weight by inverse volatility across positions | Low |
| Black-Litterman | Blend ML model views with market equilibrium | High |
| Sector exposure limits | Cap total position value in any one sector | Low |

---

## Directory Structure

```
trading-bot/
├── backend/
│   ├── app/
│   │   ├── api/                  # FastAPI routers (positions, watchlist, signals, admin)
│   │   ├── brokers/
│   │   │   ├── base.py           # BaseBroker ABC
│   │   │   ├── kraken.py         # KrakenBroker (live crypto)
│   │   │   ├── tradier.py        # TradierBroker (live stocks + watchlist candles)
│   │   │   ├── alpaca.py         # AlpacaTrainingFetcher (ML training only — NO live orders)
│   │   │   ├── paper.py          # PaperBroker
│   │   │   └── router.py         # BrokerRouter (symbol → broker mapping)
│   │   ├── candle/
│   │   │   ├── worker.py         # CandleWorker (base)
│   │   │   ├── kraken_worker.py  # KrakenCandleWorker (15 fixed pairs)
│   │   │   ├── tradier_worker.py # TradierCandleWorker (dynamic watchlist)
│   │   │   └── backfill.py       # BackfillService
│   │   ├── config/               # Pydantic settings, YAML strategy + signal weight config
│   │   ├── db/                   # SQLAlchemy models, Alembic migrations, repositories
│   │   ├── indicators/           # IndicatorLib (EMA, RSI, ATR, VWAP, ADX, OBV, etc.)
│   │   ├── ml/
│   │   │   ├── features.py       # Feature engineering pipeline (technical + research)
│   │   │   ├── trainer.py        # LightGBM walk-forward trainer
│   │   │   ├── predictor.py      # Inference — loads model_stock.lgbm / model_crypto.lgbm
│   │   │   ├── shap_logger.py    # SHAP per-trade explainability
│   │   │   └── drift_monitor.py  # Feature importance drift detection
│   │   ├── portfolio/
│   │   │   ├── manager.py        # PortfolioManager (MAX_POSITIONS=5, balance tracking)
│   │   │   ├── risk.py           # RiskEngine (circuit breakers, drawdown, correlation)
│   │   │   ├── sizer.py          # PositionSizer (ATR + Kelly + ML + research bonus)
│   │   │   └── direction_gate.py # DirectionGate (long-only rules enforcement)
│   │   ├── prices/               # PriceService (real-time bid/ask WebSocket cache)
│   │   ├── research/
│   │   │   ├── news_sentiment.py # FinBERT news scoring pipeline
│   │   │   ├── congress.py       # House + Senate STOCK Act disclosure scraper
│   │   │   ├── insider.py        # SEC EDGAR Form 4 parser
│   │   │   ├── screener.py       # FinViz/Alpaca quantitative screener
│   │   │   ├── analyst.py        # Benzinga analyst upgrade ingestion
│   │   │   └── scorer.py         # WatchlistScorer (composite 0-100 score)
│   │   ├── signals/
│   │   │   ├── base.py           # BaseStrategy ABC + Signal dataclass
│   │   │   └── registry.py       # StrategyRegistry (YAML-driven)
│   │   ├── strategies/
│   │   │   ├── momentum.py       # EMA crossover + ADX
│   │   │   ├── mean_reversion.py # RSI + Bollinger
│   │   │   ├── vwap.py           # VWAP deviation
│   │   │   └── breakout.py       # Range breakout + volume
│   │   └── watchlist/
│   │       └── manager.py        # WatchlistManager (promotion, demotion, Telegram alerts)
│   ├── tests/
│   ├── alembic/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chart.tsx          # lightweight-charts OHLCV + signal markers
│   │   │   ├── PositionCard.tsx   # Position with ML confidence + research score
│   │   │   ├── WatchlistTable.tsx # Active watchlist with composite scores
│   │   │   ├── ResearchPanel.tsx  # News / Congress / Insider / Analyst panels
│   │   │   ├── StrategyPanel.tsx  # Enable/disable + risk multiplier controls
│   │   │   └── KillSwitch.tsx     # Emergency halt with confirmation gate
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx      # Main trading view
│   │   │   ├── Research.tsx       # Full universe research view
│   │   │   ├── Analytics.tsx      # Equity curve, Sharpe, drawdown, win rates
│   │   │   └── Settings.tsx       # Mode toggle (paper/live), risk params
│   │   ├── hooks/
│   │   │   ├── usePositions.ts
│   │   │   ├── useWatchlist.ts
│   │   │   ├── useResearch.ts     # News, congress, insider feeds
│   │   │   └── usePortfolio.ts
│   │   └── api/
│   ├── Dockerfile
│   └── package.json
│
├── research/                      # Jupyter notebooks for signal research, backtesting
│   ├── congress_signal_analysis.ipynb
│   ├── insider_signal_backtest.ipynb
│   ├── finbert_calibration.ipynb
│   └── feature_importance_review.ipynb
│
├── scripts/
│   ├── seed_alpaca_training.py    # One-time: pull 2yr Alpaca history for universe
│   ├── retrain_models.py          # Weekly: walk-forward retrain both models
│   └── nightly_report.py          # Daily: P&L + signals + model drift report
│
├── docker-compose.yml
├── docker-compose.prod.yml
└── .github/workflows/ci.yml
```

---

## Development Sequence

```
Phase 1  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░  Infrastructure & schema
Phase 2  ░░░░░░░░████████████████░░░░░░░░░░░░░░░░░░░░  Universe research engine
Phase 3  ░░░░░░░░░░░░████████░░░░░░░░░░░░░░░░░░░░░░░░  Alpaca training pipeline
Phase 4  ░░░░░░░░░░░░░░░░████████████░░░░░░░░░░░░░░░░  Candle workers (Tradier + Kraken)
Phase 5  ░░░░░░░░░░░░░░░░░░░░████████████████░░░░░░░░  Strategy + ML engine
Phase 6  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████░░░░░░░░  Risk engine + direction gate
Phase 7  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████░░░░  Paper trading engine
Phase 8  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░████████  Live brokers + React UI
```

---

## Non-Negotiable Rules

1. **Crypto = long only, always** — `DirectionGate` blocks shorts unconditionally, logged as warning
2. **Stock shorts gated at $2,500** — balance checked at signal time AND at order submission
3. **Alpaca is training-only** — zero live order code in `alpaca.py`; file is read-only from `BaseBroker` perspective
4. **Tradier supplies watchlist candles** — Kraken supplies crypto candles; no cross-contamination
5. **One candle worker per (asset_class, symbol, timeframe)** — Redis lock, no exceptions
6. **Never skip paper trading** — 30-day gate, quantitative thresholds, direction gate verified
7. **Circuit breakers are automatic** — daily −2% NAV, weekly −5%, monthly −15%
8. **Research signals are ML inputs, not trade triggers** — they inform sizing and ML features, never bypass strategy rules
9. **All strategy parameters in YAML** — zero hardcoded values in business logic
10. **Every live order reconciled** — internal state vs. broker state every 5 minutes

---

*Generated by Claude · Last updated: April 2026 · v2 — universe research, direction gates, Alpaca training pipeline*

---

## Phase 8 Crypto News Sentiment Lane Update

Crypto news sentiment is implemented as a separate research lane from ML candle sync and ML prediction generation.

Execution order:

1. RSS sources
2. GDELT coverage
3. Structured news API, such as GNews or NewsData
4. Fallback API only when coverage is weak
5. Deduplication
6. Pre-scoring quality filter
7. FinBERT scoring
8. Daily sentiment storage

Storage contract:

- Missing sentiment remains `NULL`, not `0.0`.
- Missing coverage uses `coverage_score = 0`.
- Daily sentiment joins ML feature rows by canonical `symbol + sentiment_date`.
- Crypto stock-only research fields remain not applicable until replaced by source-backed crypto equivalents.

Worker policy:

- News ingestion should run on a dedicated Celery research queue.
- It should not share the ML candle/prediction queue.
- It should not block live trading candle workers.

Slice 11/12 RSS policy:

- Coinbase and CoinDesk RSS are the first source layer.
- RSS articles are normalized before any scoring.
- Articles are filtered by canonical crypto symbol aliases.
- Duplicate URLs and common tracking parameters are collapsed before scoring.
- Very short, stale, future-dated, or URL-less articles are rejected before FinBERT.
- RSS ingestion stops before DB sentiment writes until scoring is implemented.

Planned in-house crypto research score components:

- `technical_score`
- `news_sentiment_score`
- `liquidity_score`
- `on_chain_score` later

Slice 13 RSS scoring policy:

- Prepared RSS articles now aggregate into daily symbol-level sentiment summaries.
- Empty article coverage keeps sentiment fields `NULL` with `coverage_score = 0`.
- The current scorer is a deterministic fallback contract so tests stay lightweight.
- FinBERT remains the planned production scorer and should replace the fallback through the same scorer interface.
- Daily sentiment rows use deterministic `symbol:YYYY-MM-DD` ids for safe upserts.

Slice 14 FinBERT adapter policy:

- FinBERT is now represented by `FinbertCryptoSentimentScorer` behind the same article scorer protocol used by aggregation.
- The adapter loads HuggingFace `transformers.pipeline` lazily so normal tests and lightweight workers do not import transformer dependencies unless the scorer is used.
- The deterministic lexicon scorer remains as the fallback/testing scorer.
- ML retraining still waits for historical sentiment backfill; adding FinBERT now only stabilizes the scoring interface.


Slice 15 persistence policy:

- The live `tasks.news_sentiment.daily_crypto_sync` Celery entry point now writes through the persistence flow instead of returning a snapshot-only result.
- The persisted flow is:

```text
RSS → symbol filter → dedupe → pre-scoring filter → FinBERT → daily aggregate → crypto_daily_sentiment upsert
```

- The task persists exactly one row per requested canonical crypto ML symbol and sentiment date.
- Symbols with no prepared articles still get a row with `positive_score`, `neutral_score`, `negative_score`, and `compound_score` set to `NULL`; `article_count = 0`, `source_count = 0`, and `coverage_score = 0`.
- This does not join sentiment into ML features and does not retrain the model.

Slice 16 historical sentiment backfill design policy:

- Historical sentiment backfill is a separate research lane from daily RSS and from ML candle sync.
- Slice 16 is design-only and does not implement GDELT, historical APIs, article tables, ML feature joins, or retraining.
- Historical source order should be GDELT first, then GNews or NewsData if account limits support the needed date range, then practical archive sources such as CoinDesk or Coinbase only if terms-safe.
- Historical pulls must be chunked by canonical symbol and date range, resumable, idempotent, and safe to rerun.
- Historical backfill should remain on the dedicated research queue and must not block ML candles, predictions, trading candles, or runtime trading paths.
- All daily aggregate writes still use canonical `symbol + sentiment_date` and deterministic `SYMBOL:YYYY-MM-DD` ids.
- Missing historical coverage must remain `NULL` sentiment with zero article/source/coverage counts when a date has been explicitly evaluated and no valid articles were found.
- Failed provider calls must not overwrite previously good rows with empty rows.
- Before large historical ingestion, consider adding a normalized article table for source-quality debugging; daily aggregates alone are enough for ML features but weak for auditability.
- Do not join sentiment into ML features and do not retrain until historical coverage has been backfilled and reviewed.

Slice 17 historical source ingestion policy:

- GDELT is now represented by a lightweight historical article ingestion client scaffold.
- The Slice 17 client builds one canonical-symbol/date-window query at a time and normalizes article results into the existing `RssArticle` scoring contract so RSS and historical articles can share the same downstream sentiment scoring pipeline.
- Slice 17 does not create article storage, does not backfill `crypto_daily_sentiment`, does not join sentiment into ML features, and does not retrain models.
- GDELT responses are normalized before scoring: unusable rows without title, URL, or parseable seen date are rejected.
- GDELT query windows are explicit and inclusive at the day level so later backfill orchestration can chunk and resume safely.
- Daily sentiment missing-data semantics remain unchanged: no valid articles for an evaluated date must become NULL sentiment with zero coverage only when the aggregate backfill slice intentionally writes that day.

Slice 18 historical sentiment table backfill policy:

- Historical sentiment backfill now writes daily aggregates into `crypto_daily_sentiment` after a historical provider returns a successful symbol/date window.
- The backfill flow is:

```text
historical article search → symbol/date chunk → dedupe → pre-scoring filter → FinBERT → daily aggregate → crypto_daily_sentiment upsert
```

- The backfill task persists one row per requested canonical crypto symbol and evaluated sentiment date.
- Successful windows with no prepared articles intentionally write NULL sentiment with `article_count = 0`, `source_count = 0`, and `coverage_score = 0`.
- Failed provider windows are reported as `failed_windows` and must not overwrite previously good rows with empty sentiment.
- Slice 18 still does not join sentiment into ML features and does not retrain models.

Slice 19 sentiment-to-ML feature join policy:

- Persisted crypto daily sentiment now maps into ML research inputs by canonical `symbol + sentiment_date`.
- Crypto feature rows may use only the source-backed sentiment fields: `news_sentiment_1d`, `news_sentiment_7d`, and `news_article_count_7d`.
- Stock-only fields remain unavailable for crypto and must stay at their non-signal defaults: Congress, insider, CEO buy, earnings, analyst score, and consensus rating.
- Missing or zero-coverage sentiment rows are not treated as observed neutral articles. They produce zero article count and default numeric values only to preserve the current finite LightGBM feature-vector contract.
- Walk-forward training can now prefer date-specific research lookup entries before falling back to older symbol-level research inputs.
- Slice 19 does not retrain models. Retraining and SHAP review remain Slice 20 work after historical sentiment coverage has been reviewed.


Slice 20 sentiment refresh retraining policy:

- Old crypto model artifacts should be retired before running a sentiment refresh so the active model registry cannot serve a pre-sentiment model.
- The operator refresh flow is now:

```text
historical GDELT backfill → crypto_daily_sentiment upsert → crypto retrain → persisted prediction regeneration → sentiment SHAP summary
```

- The endpoint `POST /ml/train/crypto/sentiment-refresh` is the forced old-news fetch and retrain trigger. It accepts `start_date`, `end_date`, optional comma-separated `symbols`, `prediction_limit`, and `skip_backfill`.
- `skip_backfill=true` is only for rerunning retrain and SHAP review after sentiment rows are already populated.
- Prediction generation now loads the latest date-specific crypto sentiment row for each symbol so local SHAP uses the same sentiment feature lane as training.
- SHAP review remains daily-context only. Sentiment SHAP must explain the 1D ML model context and must not directly veto 15m, 1h, or 4h strategy entries.
