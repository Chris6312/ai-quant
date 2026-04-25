# ✅ AI-Quant — Crypto-First Master Phase Checklist (Updated)

Source: 

---

# Phase 1 — Crypto Scope Model

## Goal

Define crypto as the first fully supported production lane.

### Backend

* [x] Treat `KRAKEN_UNIVERSE` as the initial crypto universe source of truth

* [x] Decide crypto watchlist behavior → **same as universe for Phase 1**

* [x] Define operator-facing terms clearly:

  * [x] Crypto Universe
  * [x] Crypto Watchlist (same as universe for now)
  * [x] Active Runtime Set (defined, not yet wired)
  * [x] Prediction Set (defined conceptually via ML system)

### Frontend

* [~] Update labels so crypto does not depend on stock-style watchlist semantics
  → partially true (UI still leans stock-first in places)

* [~] Ensure Research / Runtime / ML pages can represent crypto symbols
  → crypto exists, but:

  * Research page depends on stock watchlist ❌
  * Runtime page underrepresents crypto ❌
  * ML page shows crypto but not from runtime truth ❌

---

# Phase 2 — Crypto Universe / Watchlist Wiring

## Goal

Make crypto symbol scope visible and usable across the app.

### Backend

* [x] Add endpoint(s) exposing crypto universe / active set
* [ ] Add crypto watchlist/promoted layer (optional, likely skip for Phase 1)
* [x] Ensure runtime target derivation uses crypto scope

### Frontend

* [x] Research page shows crypto symbols from backend
* [x] Avoid empty page when stock watchlist is empty
* [x] Runtime page shows crypto scope counts
* [x] Runtime page shows active crypto targets
* [ ] ML page clarifies crypto-first behavior

---

# Phase 3 — Crypto Frontend Truth & Persistence

## Goal

Make operator pages truthful before runtime is live.

### Frontend state

* [x] Trading mode persistence exists (partial foundation)
* [ ] Persist selected crypto symbol
* [ ] Persist tab/filter state (Research / ML / Runtime)
* [ ] Rehydrate state on reload

### Empty-state truth

* [ ] Distinguish:

  * [ ] no crypto symbols configured
  * [ ] workers not running
  * [ ] no predictions yet
  * [ ] no paper positions yet

---

# Phase 4 — Crypto Worker Target Derivation

## Goal

Derive worker launch specs from crypto scope.

### Backend

* [x] Build active crypto runtime target list from `KRAKEN_UNIVERSE`
* [x] Make derivation explicit
* [x] Derive one target per `(symbol, timeframe)` while Phase 5 runs one shared scheduler worker

### Frontend

* [x] Show universe vs active runtime count
* [x] Show universe vs target runtime vs active runtime count

---

# Phase 5 — Crypto Candle Worker Activation

## Goal

Start crypto market-data heartbeat.

### Backend

* [x] Replace `_noop_sync_operation`
* [x] Enable `WorkerSupervisor`
* [x] Replace per-symbol crypto heartbeat workers with one crypto candle scheduler
* [x] Queue initial Kraken strategy backfill through Celery
* [x] Queue incremental Kraken trading candle sync through Celery
* [x] Schedule incremental sync only 20 seconds after each candle close
* [x] Keep 1D candles separated for ML-lane backfill
* [x] Start candle workers
  → one crypto scheduler worker is active and Celery executes queued Kraken tasks
* [x] Confirm scheduler dispatches only due timeframes
  → live runtime showed 5m + 15m during missed-window recovery and 5m-only at the next 5m close
* [x] Align Celery task contract with scheduler metadata
  → `requested_at` and `candle_close_at` are accepted by the sync task

### Frontend

* [x] Show crypto scheduler worker without symbol/table overflow noise
* [x] Show last candle close as a first-class runtime column
* [x] Move recent lifecycle events below managed workers at full page width
* [x] Keep ML daily worker visibility out of Phase 5 because that worker moved into Phase 6

### Validation

* [x] Candles persist
  → validated through running Celery + Kraken runtime sync path
* [ ] Redis `candle_closed` fires
  → still requires explicit pub/sub validation after persistence
* [x] Worker heartbeat visible
* [x] Static and unit test gates passed
  → `ruff check app tests`, `python -m mypy app`, and `pytest -q tests` passed with 96 tests

---

# Phase 6 — ML / Candle Convergence

## Goal

Make ML candle data a first-class, correctly sourced, consistently fresh lane without interfering with trading candles.

### Backend

* [x] Add dedicated ML Celery task module
* [x] Route ML tasks to separate `ml` Celery queue
* [x] Schedule daily ML candle sync at 08:40 ET
* [x] Keep trading candle tasks on the default queue
* [x] Sync crypto 1D ML candles through Alpaca training fetcher
* [x] Persist ML sync rows with `usage="ml"`
* [x] Align crypto universe with Kraken/Alpaca-supported overlap for Phase 6 ML freshness
* [x] Verify current candle schema usage separation: trading vs ml
* [x] Confirm existing candles are migrated or tagged correctly
* [x] Ensure ML reads the intended candle lane
* [x] Confirm crypto ML data is fresh enough for scoring

### Frontend

* [x] Add ML worker visibility to Runtime page
* [x] Keep heartbeat noise out of visible lifecycle events

### Execution mode

* [x] Daily ML sync only; no intraday ML polling

---

# Phase 7 — Crypto Prediction Persistence

## Goal

Store truth instead of rebuilding it.

### Database

* [x] Create `predictions` table
* [x] Create `prediction_shap` table

### Backend

* [x] Persist prediction records
* [x] Persist probabilities
* [x] Persist gate outcome
* [x] Persist model identity
* [x] Persist SHAP
* [x] Publish signal event

---

# Phase 8 — Crypto ML API Replacement

## Goal

ML page uses real persisted prediction data after the ML candle lane is stable.

### Backend

* [ ] Replace `/ml/predictions`
* [ ] Add `/ml/predictions/{id}/shap`
* [ ] Use persisted data
* [ ] Remove reconstruction path
* [x] Audit crypto zero-filled SHAP feature truth metadata
* [x] Mark unimplemented crypto sentiment fields as missing in metadata
* [x] Mark stock-only research fields as not applicable for crypto in metadata
* [x] Document planned in-house `crypto_research_score` components
* [x] Add crypto daily sentiment persistence contract
* [x] Route news sentiment scaffold to isolated research queue
* [x] Add RSS ingestion client for Coinbase and CoinDesk feeds
* [x] Add symbol filtering for crypto RSS articles
* [x] Add RSS deduplication and pre-scoring quality filter
* [x] Add daily RSS sentiment aggregation contract
* [x] Preserve missing sentiment as NULL when no prepared articles exist
* [x] Add FinBERT scoring adapter behind the crypto article sentiment scorer contract
* [x] Keep deterministic fallback scorer available for lightweight tests
* [x] Persist daily RSS + FinBERT sentiment aggregates into `crypto_daily_sentiment`
* [x] Upsert one sentiment row per canonical crypto symbol and sentiment date
* [x] Preserve no-article days as NULL sentiment with zero article/source/coverage counts
* [x] Document historical sentiment backfill design before implementing GDELT or other heavy ingestion
* [x] Document backfill source order, rate-limit/resume behavior, and coverage semantics
* [x] Preserve rule that historical missing sentiment remains NULL, not neutral zero
* [x] Add GDELT historical article ingestion client scaffold
* [x] Normalize GDELT articles into the shared crypto sentiment article contract
* [x] Build symbol/date-window GDELT query helpers without DB writes or ML joins
* [x] Add historical sentiment backfill task scaffold
* [x] Backfill `crypto_daily_sentiment` by canonical symbol/date from historical articles
* [x] Preserve provider failures without overwriting existing sentiment rows
* [x] Join persisted crypto daily sentiment into date-specific ML research inputs
* [x] Keep stock-only research features unavailable for crypto feature rows
* [x] Preserve missing sentiment as no-coverage defaults instead of source-backed neutral signal

### Frontend

* [ ] Show real predictions
* [ ] SHAP panel live
* [ ] Correct empty states

---

# Phase 9 — Crypto Paper Ledger Durability

## Goal

Paper trading survives restart.

### Backend

* [~] Paper trading exists (in-memory or partial)
* [ ] Persist balances
* [ ] Persist positions
* [ ] Persist fills
* [ ] Restore on startup
* [ ] Consolidate broker logic

### Frontend

* [ ] Show durable paper state
* [ ] Distinguish empty vs reset

---

# Phase 10 — Crypto End-to-End Validation

## Goal

System fully works.

### Validation

* [ ] Worker → candle → inference → prediction → UI → trade → persistence

### Stability

* [ ] No duplicates
* [ ] No stale timestamps
* [ ] No drift in worker scope

---

# Phase 11 — Crypto Drift & Runtime Insight

* [ ] Add `/ml/drift/crypto`
* [ ] Replace drift UI placeholders
* [ ] Add runtime metrics

---

# Phase 12 — Crypto Training Policy Improvements

* [ ] Constrain training horizon
* [ ] Cap folds
* [ ] Improve champion selection
* [ ] Reduce calendar dominance

---

# Phase 13 — Crypto Retraining Automation

* [ ] Replace retrain stub
* [ ] Schedule retraining
* [ ] Promote only valid models

---

# Phase 14 — Broker Reliability

* [ ] Add retry logic
* [ ] Validate config at startup

---

# Phase 15 — Production Hardening

* [ ] Observability improvements
* [ ] Deployment cleanup

---

# Phase 16 — Stock Expansion Planning

* [ ] Define stock candidate pool
* [ ] Wire research pipeline
* [ ] Populate research tables
* [ ] Build stock universe logic
* [ ] Train real stock model
* [ ] Attach stock workers

---

# 🔍 What changed (important)

### Completed (from prior work)

* ML pipeline (FeatureEngineer, ModelPredictor) ✅
* Crypto universe (`KRAKEN_UNIVERSE`) ✅
* Basic UI scaffolding ✅
* Paper trading skeleton ✅
* Model registry + training pipeline ✅

### Partially complete

* Frontend persistence ⚠️
* Paper ledger ⚠️
* ML page ⚠️ (still reconstruction-based)

### Not started (true blockers)

* Workers ❌
* Orchestrator ❌
* Prediction persistence ❌

---

# 🧠 Reality Check

You are **not starting from scratch**.

You are here:

```
Infrastructure:     ██████████
ML Pipeline:        ██████████
Frontend UI:        ███████░░░
Runtime Loop:       ░░░░░░░░░░
```

