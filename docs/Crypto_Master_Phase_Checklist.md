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

* [ ] Add endpoint(s) exposing crypto universe / active set
* [ ] Add crypto watchlist/promoted layer (optional, likely skip for Phase 1)
* [ ] Ensure runtime target derivation uses crypto scope

### Frontend

* [ ] Research page shows crypto symbols from backend
* [ ] Avoid empty page when stock watchlist is empty
* [ ] Runtime page shows crypto scope counts
* [ ] Runtime page shows active crypto targets
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

* [ ] Build active crypto runtime target list from `KRAKEN_UNIVERSE`
* [ ] Make derivation explicit
* [ ] Ensure one `(symbol, timeframe)` per worker

### Frontend

* [ ] Show universe vs active runtime count

---

# Phase 5 — Crypto Candle Worker Activation

## Goal

Start crypto market-data heartbeat.

### Backend

* [ ] Replace `_noop_sync_operation`
* [ ] Enable `WorkerSupervisor`
* [ ] Attach real crypto workers
* [ ] Start candle workers

### Validation

* [ ] Candles persist
* [ ] Redis `candle_closed` fires
* [ ] Worker heartbeat visible

---

# Phase 6 — Crypto Signal Orchestrator

## Goal

Turn candle-close into inference.

### Backend

* [ ] Create `SignalOrchestrator`
* [ ] Subscribe to `candle_closed:*`
* [ ] Load trading-lane candles
* [ ] Convert → `Candle`
* [x] FeatureEngineer already exists
* [x] ModelPredictor already exists
* [ ] Wire them into orchestrator
* [ ] Apply gates
* [ ] Call risk/sizer/portfolio

### Execution mode

* [ ] Paper-only execution first

---

# Phase 7 — Crypto Prediction Persistence

## Goal

Store truth instead of rebuilding it.

### Database

* [ ] Create `predictions` table
* [ ] Create `prediction_shap` table

### Backend

* [ ] Persist prediction records
* [ ] Persist probabilities
* [ ] Persist gate outcome
* [ ] Persist model identity
* [ ] Persist SHAP
* [ ] Publish signal event

---

# Phase 8 — Crypto ML API Replacement

## Goal

ML page uses real data.

### Backend

* [ ] Replace `/ml/predictions`
* [ ] Add `/ml/predictions/{id}/shap`
* [ ] Use persisted data
* [ ] Remove reconstruction path

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

