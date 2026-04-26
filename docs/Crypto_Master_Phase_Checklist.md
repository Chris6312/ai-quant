# ✅ AI-Quant — Crypto-First Master Phase Checklist

Source: `docs/Crypto_Master_Phase_Checklist.md`
Last reviewed against backup zip: `tracked-files-20260426-161505.zip`

---

# Phase Status Audit

| Phase | Name | Status | Review result |
|---|---|---:|---|
| Phase 1 | Crypto Scope Model | ✅ Complete | Crypto universe/scope foundation exists. Some older UI wording remains, but it is not a blocker for post-Phase 9 work. |
| Phase 2 | Crypto Universe / Watchlist Wiring | ✅ Complete | Backend crypto scope and runtime targets are wired. Research-only promoted crypto list is implemented as a soft operator-focus layer. |
| Phase 3 | Crypto Frontend Truth & Persistence | ✅ Complete | Research now surfaces persisted ML predictions, latest-per-symbol truth, no-trade explanations, sentiment values, and localStorage state rehydration for current Research scope. |
| Phase 4 | Crypto Worker Target Derivation | ✅ Complete | Runtime target derivation is explicit and scheduler-oriented. |
| Phase 5 | Crypto Candle System | ✅ Complete | Crypto candle scheduler/worker path is implemented and validated. Redis `candle_closed` explicit pub/sub validation should remain tracked as a later integration check. |
| Phase 6 | ML Candle / Freshness | ✅ Complete | Dedicated ML lane, usage separation, Alpaca 1D ML sync, and freshness gating are in place. |
| Phase 7 | Prediction Pipeline | ✅ Complete | Prediction persistence tables and backend persistence path are present. UI polish can continue later. |
| Phase 8 | Model Selection Hardening | ✅ Complete | Recency-aware/quality-aware model selection hardening is implemented. |
| Phase 9 | Sentiment Risk Layer | ✅ Complete | Implemented before ledger durability and now renumbered as the completed Phase 9. |
| Phase 10 | Crypto Paper Ledger Durability | ✅ Complete | Durable paper ledger schema/service/API/UI path was implemented and validated in the current project state. |

---

# Phase 1 — Crypto Scope Model

## Goal

Define crypto as the first fully supported production lane.

### Backend

* [x] Treat `KRAKEN_UNIVERSE` as the initial crypto universe source of truth
* [x] Decide crypto watchlist behavior → same as universe for early crypto phases
* [x] Define operator-facing terms clearly:
  * [x] Crypto Universe
  * [x] Crypto Watchlist / scope display
  * [x] Active Runtime Set
  * [x] Prediction Set

### Frontend

* [x] Update labels so crypto does not depend on stock-style watchlist semantics
* [x] Ensure Research / Runtime / ML pages can represent crypto symbols

### Carry-forward notes

* [ ] True promoted crypto watchlist is still not a runtime driver. Keep this deferred unless explicitly prioritized.

---

# Phase 2 — Crypto Universe / Watchlist Wiring

## Goal

Make crypto symbol scope visible and usable across the app.

### Backend

* [x] Add endpoint(s) exposing crypto universe / active set
* [x] Ensure runtime target derivation uses crypto scope
* [x] Add crypto watchlist/promoted layer
  → implemented as a Research-only promoted list. It influences operator focus only and does not change workers, ML, paper trading, or live execution.

### Frontend

* [x] Research page shows crypto symbols from backend scope
* [x] Avoid empty page when stock watchlist is empty
* [x] Runtime page shows crypto scope counts
* [x] Runtime page shows active crypto targets
* [x] ML page clarifies crypto-first behavior enough for current phases

---

# Phase 3 — Crypto Frontend Truth & Persistence

## Goal

Make operator pages truthful before runtime is live.

### Frontend state

* [x] Trading mode persistence exists
* [x] Persist selected crypto symbol for Research
* [x] Persist Research tab/filter state
* [x] Rehydrate Research state on reload
* [ ] Extend equivalent tab/filter persistence across ML / Runtime if needed later

### Empty-state truth

* [x] Distinguish no crypto symbols configured for Research scope
* [x] Distinguish no predictions yet / no high-confidence predictions
* [x] Distinguish prediction exists vs tradable signal
* [x] Distinguish sentiment unavailable vs scored sentiment
* [x] Distinguish no paper positions / empty paper state through Phase 10 durable paper UI

### Carry-forward notes

* [x] Research page now shows persisted ML predictions as observation/signals, latest prediction per symbol, no-trade explanations, sentiment values, and promoted-symbol focus.

---

# Phase 4 — Crypto Worker Target Derivation

## Goal

Derive worker launch specs from crypto scope.

### Backend

* [x] Build active crypto runtime target list from `KRAKEN_UNIVERSE`
* [x] Make derivation explicit
* [x] Derive one target per `(symbol, timeframe)` while the shared crypto scheduler dispatches the actual work

### Frontend

* [x] Show universe vs active runtime count
* [x] Show universe vs target runtime vs active runtime count

---

# Phase 5 — Crypto Candle System

## Goal

Start crypto market-data heartbeat.

### Backend

* [x] Replace `_noop_sync_operation`
* [x] Enable `WorkerSupervisor`
* [x] Replace per-symbol crypto heartbeat workers with one crypto candle scheduler
* [x] Queue initial Kraken strategy backfill through Celery
* [x] Queue incremental Kraken trading candle sync through Celery
* [x] Schedule incremental sync only about 20 seconds after each candle close
* [x] Keep 1D candles separated for ML-lane backfill
* [x] Start candle workers
* [x] Confirm scheduler dispatches only due timeframes
* [x] Align Celery task contract with scheduler metadata

### Frontend

* [x] Show crypto scheduler worker without symbol/table overflow noise
* [x] Show last candle close as a first-class runtime column
* [x] Move recent lifecycle events below managed workers at full page width
* [x] Keep ML daily worker visibility in Phase 6, not Phase 5

### Validation

* [x] Candles persist through running Celery + Kraken runtime sync path
* [x] Worker heartbeat visible
* [x] Static and unit test gates passed during the phase
* [ ] Explicit Redis `candle_closed` pub/sub validation remains a later integration check

---

# Phase 6 — ML Candle / Freshness

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

# Phase 7 — Prediction Pipeline

## Goal

Store prediction truth instead of rebuilding it from transient state.

### Database

* [x] Create `predictions` table
* [x] Create `prediction_shap` table

### Backend

* [x] Persist prediction records
* [x] Persist probabilities
* [x] Persist gate outcome
* [x] Persist model identity
* [x] Persist SHAP rows / summaries
* [x] Publish signal event
* [x] Regenerate persisted crypto predictions after sentiment-aware retraining

### Frontend

* [x] ML page can consume persisted prediction/state paths for current phase needs
* [ ] Continue UI cleanup for prediction detail and SHAP inspection after ledger durability

---

# Phase 8 — Model Selection Hardening

## Goal

Prevent stale or misleading model folds from becoming production champions.

### Backend

* [x] Replace naive/global Sharpe-only model selection behavior
* [x] Add production fold eligibility tied to recency and quality
* [x] Reject or demote stale folds such as very old 2014–2015 windows for today’s crypto market
* [x] Add sample/quality gates for model promotion
* [x] Keep active model registry state explicit
* [x] Ignore missing or invalid artifacts when selecting/displaying active models
* [x] Distinguish active, eligible, and research-only model states conceptually

### Frontend

* [x] Surface model-selection state clearly enough to prevent old-fold confusion
* [ ] Continue polish for advanced model cards and local SHAP inspection later

---

# Phase 9 — Sentiment Risk Layer

## Goal

Use BTC + ETH macro sentiment as a crypto risk-pressure layer for gating, sizing, and confidence weighting.

### Backend

* [x] Add crypto daily sentiment persistence contract
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
* [x] Document historical sentiment backfill design before heavy ingestion
* [x] Add GDELT historical article ingestion client scaffold
* [x] Normalize GDELT articles into the shared crypto sentiment article contract
* [x] Build symbol/date-window GDELT query helpers without DB writes or ML joins
* [x] Add historical sentiment backfill task scaffold
* [x] Backfill `crypto_daily_sentiment` by canonical symbol/date from historical articles
* [x] Preserve provider failures without overwriting existing sentiment rows
* [x] Join persisted crypto daily sentiment into date-specific ML research inputs
* [x] Keep stock-only research features unavailable for crypto feature rows
* [x] Preserve missing sentiment as no-coverage defaults instead of source-backed neutral signal
* [x] Add operator trigger to force historical sentiment backfill before crypto retraining
* [x] Block retraining when historical sentiment coverage is below the requested threshold
* [x] Move sentiment refresh orchestration out of oversized `ml.py` router
* [x] Add BTC/ETH macro sentiment blending for crypto feature rows
* [x] Apply macro sentiment as pressure, not as a universal gate
* [x] Add sentiment gate logic
* [x] Add sentiment sizing multiplier logic
* [x] Add confidence weighting / weak-signal blocking behavior
* [x] Add pre-trade sentiment enforcement path
* [x] Add deterministic verification endpoint for sentiment-risk scenarios

### Frontend

* [x] Surface sentiment-aware ML/risk outputs sufficiently for current phase validation
* [ ] Continue richer operator UI polish after durable paper state exists

### Status

* [x] Phase 9 is complete and committed/pushed/backed up in the provided project state

---

# Phase 10 — Crypto Paper Ledger Durability

## Goal

Paper trading survives restart.

### Backend

* [x] Paper trading exists with durable ledger backing
* [x] Persist paper account balances
* [x] Persist paper positions
* [x] Persist paper fills
* [x] Persist paper orders
* [x] Restore paper state on startup
* [x] Make database state the source of truth
* [x] Consolidate broker + paper execution logic sufficiently for current durable-paper phase
* [x] Keep paper and live broker behavior clearly separated

### Required data model preview

* [x] `paper_account`
* [x] `paper_positions`
* [x] `paper_fills`
* [x] `paper_orders`

### Restart behavior

* [x] Load balances from DB
* [x] Load open positions from DB
* [x] Rebuild portfolio state from persisted paper records
* [x] Resume as if the app never restarted

### Frontend

* [x] Show durable paper account state
* [x] Distinguish empty account
* [x] Distinguish reset account
* [x] Distinguish active positions

### Hard rules

* [x] Do not rebuild positions from candles
* [x] Do not rely on runtime memory as source of truth
* [x] Do not mix paper and live broker logic blindly
* [x] Do not skip fill persistence

---

# Phase 9.1 — Decision Layer Visibility

## Goal

Make Phase 9 sentiment-risk decisions visible in the same operator-facing decision object as ML predictions.

### Why this exists

Phase 9 sentiment-risk logic was implemented and manually verified, but Research currently surfaces mostly the ML prediction, confidence gate, and no-trade action. The operator needs to see the distinction between:

* ML prediction direction
* macro sentiment bias from BTC/ETH market weather
* symbol sentiment bias / local forecast
* final sentiment decision
* risk-reduced vs blocked vs boosted outcome

### Backend

* [ ] Add visible `macro_sentiment_bias` to prediction/decision payloads
* [ ] Add visible `symbol_sentiment_bias` to prediction/decision payloads
* [ ] Add visible `final_sentiment_decision` to prediction/decision payloads
* [ ] Add visible confidence adjustment / size multiplier where available
* [ ] Preserve Phase 9 rule: BTC/ETH macro sentiment is a headwind/tailwind, not a universal iron gate
* [ ] Preserve allowed-but-risk-reduced behavior when macro is bearish but symbol setup is strong
* [ ] Do not change execution behavior until the visible decision object is validated

### Frontend

* [ ] Show ML prediction separately from final decision context
* [ ] Show macro weather vs symbol forecast clearly
* [ ] Show blocked / risk-reduced / boosted reason labels
* [ ] Keep Research as signal visibility, not auto-execution

### Validation scenarios

* [ ] BTC/ETH bearish + SOL strongly bullish = allowed but risk-reduced
* [ ] BTC/ETH bearish + SOL neutral/weak = blocked or downgraded
* [ ] BTC/ETH bullish + SOL bullish = allowed normal or boosted
* [ ] Stocks remain unscoped by crypto macro sentiment

---

# Phase 11 — Crypto End-to-End Validation

## Goal

System fully works from market data through durable paper state.

### Validation

* [ ] Worker → candle → inference → prediction → UI → paper trade → durable persistence
* [ ] Restart app and confirm paper state survives

### Stability

* [ ] No duplicate candles/predictions/fills
* [ ] No stale timestamps
* [ ] No drift in worker scope
* [ ] Redis `candle_closed` signal path explicitly validated

---

# Phase 12 — Crypto Drift & Runtime Insight

* [ ] Add `/ml/drift/crypto`
* [ ] Replace drift UI placeholders
* [ ] Add runtime metrics
* [ ] Add operator-facing freshness and drift explanation states

---

# Phase 13 — Crypto Training Policy Improvements

* [ ] Constrain training horizon
* [ ] Cap folds
* [ ] Improve champion selection
* [ ] Reduce calendar dominance
* [ ] Continue improving regime-aware model promotion rules

---

# Phase 14 — Crypto Retraining Automation

* [ ] Replace retrain stub
* [ ] Schedule retraining
* [ ] Promote only valid models
* [ ] Keep sentiment coverage gates in retraining flow

---

# Phase 15 — Broker Reliability

* [ ] Add retry logic
* [ ] Validate config at startup
* [ ] Improve broker error visibility
* [ ] Keep paper and live broker execution paths isolated

---

# Phase 16 — Production Hardening

* [ ] Observability improvements
* [ ] Deployment cleanup
* [ ] Runtime failure recovery checks
* [ ] Operator-safe controls

---

# Phase 17 — Stock Expansion Planning

* [ ] Define stock candidate pool
* [ ] Wire research pipeline
* [ ] Populate research tables
* [ ] Build stock universe logic
* [ ] Train real stock model
* [ ] Attach stock workers

---

# Carry-Forward Items Before Phase 11

These are real incomplete items, but they should remain scoped instead of being allowed to blur into unrelated feature work.

* [ ] Phase 5: explicit Redis `candle_closed` pub/sub validation remains a later end-to-end integration check.
* [ ] Phase 9.1: expose sentiment-risk decision context so Research can show macro weather, symbol forecast, and final decision separately from raw ML prediction.
* [ ] ML prediction/SHAP UI can still be improved, but should not block Phase 9.1 unless directly needed for decision visibility.
* [ ] Auto-promoted Research candidates are approved as a future Phase 2B concept, but should not be mixed into Phase 2A manual promoted-list validation.

---

# Next Actual Phase

```text
Phase 9.1 — Decision Layer Visibility

Proceed with a visibility-only patch:
- expose macro_sentiment_bias
- expose symbol_sentiment_bias
- expose final_sentiment_decision
- expose risk-reduced / blocked / boosted reason
- do not change execution behavior yet
```

