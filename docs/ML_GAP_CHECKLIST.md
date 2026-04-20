Below is the **checkbox-style Phase Gap Checklist** aligned to `docs/ml_trading_bot_plan_v2.md` and your current repo state.

This focuses on **wiring gaps**, not feature expansion.
ML logic remains untouched.
Crypto ML training will use **CSV OHLCV source** instead of Alpaca historical crypto bars.

You can paste this directly into:

```
docs/ML_GAP_CHECKLIST.md
```

---

# ML Trading Bot – Phase Gap Checklist

Status legend:

* [x] Wired
* [~] Partial
* [ ] Gap

---

# Phase 1 – Core Platform Foundation

## Infrastructure

* [x] FastAPI backend scaffold operational
* [x] React frontend scaffold operational
* [x] Docker Compose stack runs (db, redis, backend, frontend)
* [x] Postgres connection configured
* [x] Redis connection configured
* [x] Alembic migrations operational
* [x] Base schema initialized
* [x] Structured logging configured
* [x] Environment configuration loader implemented

## Observability

* [x] Prometheus metrics endpoint available
* [x] Grafana container configured
* [~] Metrics coverage partial
* [ ] Alert thresholds defined
* [ ] Alert routing configured

## Operational durability

* [~] Basic service startup orchestration exists
* [ ] Full supervisor lifecycle management
* [ ] Environment parity validation
* [ ] healthcheck coverage across services

---

# Phase 2 – Research & Universe Construction

## Research data sources

* [x] News sentiment service module exists
* [x] Congress trade ingestion module exists
* [x] Insider trade ingestion module exists
* [x] Screener service module exists
* [x] Analyst rating ingestion module exists

## Research persistence

* [x] DB models for research signals exist
* [x] repository layer for research persistence exists

## Watchlist construction

* [~] watchlist scoring logic modules exist
* [~] watchlist promotion/demotion modules exist
* [ ] automated research pipeline orchestration
* [ ] scheduled research runs
* [ ] research → watchlist pipeline integration
* [ ] research results visible in UI

---

# Phase 3 – Historical Data Pipeline for ML

## Stock OHLCV ingestion

* [x] Alpaca stock OHLCV ingestion service exists
* [x] stock backfill endpoints implemented
* [x] stock data coverage status endpoint implemented
* [x] ML page controls wired for stock backfill

### corrections required

* [ ] switch stock screener endpoint to most-actives
* [ ] enforce max 100 symbols for most-actives
* [ ] confirm correct symbol normalization for Alpaca bars endpoint

## Crypto OHLCV ingestion (CSV-based)

* [ ] define canonical crypto CSV schema
* [ ] create CSV ingestion service (CSVs are located in the project root folder/crypto-history)
* [ ] validate timestamp format consistency
* [ ] validate duplicate bar handling
* [ ] validate missing candle detection
* [ ] validate symbol normalization
* [ ] persist crypto candles for ML training
* [ ] integrate crypto CSV coverage into training readiness endpoint
* [ ] update ML page to treat crypto ML as CSV-backed source
* [ ] prevent Alpaca crypto historical ingestion from interfering with CSV source

## ML dataset readiness

* [x] dataset readiness endpoints exist
* [~] readiness logic partially implemented
* [ ] unified readiness contract across asset classes
* [ ] readiness thresholds defined

---

# Phase 4 – Live Market Data Pipeline

## Broker integrations

* [x] Kraken adapter exists
* [x] Tradier adapter exists
* [x] Alpaca adapter exists

## Candle workers

* [x] shared candle worker base exists
* [x] Redis locking implemented
* [x] publish mechanism implemented

## Worker orchestration

* [~] worker framework exists
* [ ] dynamic worker lifecycle management
* [ ] attach/detach symbols from watchlist automatically
* [ ] worker runtime supervision
* [ ] worker health visibility in UI

---

# Phase 5 – Feature Engineering Layer

## Feature generation

* [x] feature engineering modules exist
* [x] technical feature calculations implemented
* [x] feature persistence structure exists

## feature coverage

* [~] feature set partially aligned with ML contract
* [ ] verify feature parity between stock and crypto datasets
* [ ] validate feature completeness for ML scoring
* [ ] ensure feature reproducibility across runs

---

# Phase 6 – ML Model Training Layer

## training infrastructure

* [x] training service module exists
* [x] walk-forward validation logic exists
* [x] model artifact generation implemented
* [x] feature importance logging implemented
* [x] drift monitoring module exists

## lifecycle wiring

* [~] manual training flow exists
* [ ] automated retraining scheduling
* [ ] champion/challenger model tracking
* [ ] model promotion workflow
* [ ] artifact registry persistence
* [ ] model metadata persistence

---

# Phase 7 – Strategy Layer

## strategies

* [x] breakout strategy module exists
* [x] mean reversion strategy module exists
* [x] momentum strategy module exists
* [x] vwap strategy module exists

## orchestration

* [~] strategies callable individually
* [ ] unified strategy orchestration pipeline
* [ ] ML scoring integration into strategy decision path
* [ ] strategy audit logging
* [ ] strategy decision reproducibility

---

# Phase 8 – Risk Engine

## components

* [x] direction gating module exists
* [x] position sizing module exists
* [x] portfolio risk logic module exists

## integration

* [~] risk modules implemented
* [ ] enforce risk gate across all execution paths
* [ ] risk visibility in UI
* [ ] portfolio exposure tracking
* [ ] risk override logging

---

# Phase 9 – Paper Trading Engine

## endpoints

* [x] paper balance endpoint exists
* [x] paper order submission endpoint exists
* [x] paper order listing endpoint exists

## durability

* [~] paper ledger logic exists
* [ ] persistent paper ledger storage
* [ ] restart-safe paper positions
* [ ] fill simulation logic
* [ ] order lifecycle simulation
* [ ] trade history persistence
* [ ] reconciliation workflow

---

# Phase 10 – Live Execution Layer

## execution routing

* [x] broker routing layer exists
* [x] order submission abstraction exists

## live safety

* [~] basic execution pathways exist
* [ ] full execution audit trail
* [ ] reconciliation service integration
* [ ] exception handling workflow
* [ ] operator halt controls fully wired
* [ ] alert routing for execution failures

---

# Phase 11 – Background Jobs & Task Orchestration

## job handling

* [x] async job pattern exists
* [x] ML backfill job execution implemented
* [x] job polling implemented

## durability

* [ ] persistent job storage
* [ ] restart-safe job state
* [ ] retry logic
* [ ] resumable job execution
* [ ] job audit history
* [ ] celery integration fully wired

---

# Phase 12 – Operator UI

## pages

* [x] dashboard page exists
* [x] research page exists
* [x] analytics page exists
* [x] paper page exists
* [x] ML page exists
* [x] orders page exists
* [x] settings page exists

## MachineLearning.tsx wiring

* [x] stock backfill controls implemented
* [x] crypto backfill controls implemented
* [x] job progress display implemented
* [x] stock symbol input implemented
* [x] gainers fetch control implemented

## persistence gaps

* [ ] active tab persistence across reload
* [ ] page state persistence across navigation
* [ ] ML job state persistence across reload
* [ ] restore previously entered symbols
* [ ] restore gainers list after navigation
* [ ] restore active job banner

---

# Phase 13 – Observability & Auditability

## visibility

* [x] basic runtime status endpoints exist
* [~] ML readiness visibility partial

## audit completeness

* [ ] end-to-end lineage tracking
* [ ] dataset provenance visibility
* [ ] model provenance visibility
* [ ] job audit visibility
* [ ] research audit visibility
* [ ] unified operator audit panel

---

# Cross-phase priorities

## Highest priority gaps

* [ ] frontend persistence for ML page
* [ ] durable ML job storage
* [ ] switch stock screener endpoint to most-actives
* [ ] implement crypto CSV ingestion path
* [ ] complete research → watchlist orchestration wiring
* [ ] persistent paper ledger

---

If helpful, next I can provide:

• minimal persistence plan for MachineLearning.tsx
• schema proposal for crypto CSV ingestion
• minimal job table design for ML tasks
• dependency diagram showing how Phase 3 → 6 connect
