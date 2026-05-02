# ML Trading Bot — Phase Implementation Contract
**Source audit:** `tracked-files-20260502-104747.zip`
**Date:** 2026-05-02
**Scope:** Unimplemented phases only. Completed phases (1–10, S2–S5) are omitted.

---

## What Is Already Done (Reference Only)

| Layer | Status |
|---|---|
| `timeframe_config.py` + `model_contracts.py` | ✅ Contracts defined, enums exist |
| `labels.py` triple-barrier engine | ✅ ATR barriers present, 3-class labeling works |
| `trainer.py` LightGBM walk-forward core | ✅ Folds, calibration, model registry wired |
| `predictions` table + `prediction_shap` table | ✅ Persisted, but missing timeframe/model_role fields |
| Crypto candle workers (trading lane) | ✅ Kraken live candles flowing |
| ML candle worker | ✅ Exists — but hardcoded to `1Day` only |
| Paper ledger durability | ✅ Phase 10 complete |
| Sentiment/risk layer | ✅ Phase 9 complete |
| Stock DB schema | ✅ Phase S2 complete |
| Stock screener worker stub | ✅ Phase S5 complete |

---

## Phase ML-TF2 — Multi-Timeframe ML Candle Lane

**Unblocks:** All subsequent ML-TF phases and stock ML phases.

### Problem
`ml_candles.py` is hardcoded to `ALPACA_DEFAULT_TIMEFRAME = "1Day"`.
The worker ID is `ml:crypto:1D`. No 15m, 1h, or 4h ML candles are being fetched.

### Backend
- [ ] Add `CRYPTO_ML_TIMEFRAMES = ("15m", "1h", "4h")` to `constants.py`
- [ ] Add `STOCK_ML_TIMEFRAMES = ("5m", "15m", "1h", "4h")` to `constants.py`
- [ ] Refactor `ml_candles.py` to iterate over all timeframes from the contract
- [ ] Replace hardcoded `"1Day"` lookback with per-timeframe lookback values from `timeframe_config.py`
- [ ] Rename Celery task worker ID from `ml:crypto:1D` to `ml:crypto:intraday`
- [ ] Keep `1Day` only as a context/research sync (separate task, separate worker ID)
- [ ] Add stock ML candle sync task (Alpaca historical, `usage="ml"`)
- [ ] Validate no trading candle pollution in the ML lane (`usage` column guard)

### Frontend
- [ ] Update ML page worker status row to reflect new `ml:crypto:intraday` worker ID
- [ ] Show per-timeframe candle counts in ML candle summary (symbol × timeframe × usage)

### Worker
- [ ] Add `ml:crypto:intraday` Celery beat schedule (daily, off-hours)
- [ ] Add `ml:stock:intraday` Celery beat schedule (weekly, post-market Saturday)
- [ ] Retire `ml:crypto:1D` as a primary beat schedule entry

### Database
- [ ] Migration required — ML and trading intraday candle lanes can overlap on the same symbol/timeframe/time, so `usage` must be part of candle uniqueness
- [ ] Update `CandleRow` identity from `(time, symbol, timeframe)` to `(time, symbol, timeframe, usage)`
- [ ] Add/update query indexing for `(symbol, timeframe, usage, time)`

---

## Phase ML-TF3 — Label Upgrade (Fee-Aware, Purged, Per-Timeframe)

**Unblocks:** ML-TF4 trainer refactor.

### Problem
`labels.py` has ATR barrier support but:
- ATR is **not lagged** (potential look-ahead bias)
- No fee/slippage minimum profitable move check
- `TradeLabelConfig` is a single global config, not per-timeframe
- Walk-forward folds in `trainer.py` do not purge overlapping barrier windows

### Backend
- [ ] Fix ATR calculation in `labels.py` — shift by 1 bar before use (`atr_values[index - 1]`)
- [ ] Add `min_profitable_move_pct` field to `TradeLabelConfig`
- [ ] Default crypto `min_profitable_move_pct = 0.013` (covers 0.80% Kraken fees + 0.10% slippage + 0.30% edge)
- [ ] Default stock `min_profitable_move_pct = 0.002` (covers lower broker costs)
- [ ] Relabel timeout bars as `NO_EDGE_LABEL` when `abs(return) < min_profitable_move_pct`
- [ ] Add per-timeframe label config factory in `timeframe_config.py`:

  | Asset | Timeframe | TP Mult | SL Mult | Hold Bars |
  |---|---|---|---|---|
  | Crypto | 15m | 1.8× ATR | 1.1× ATR | 6 |
  | Crypto | 1h | 2.2× ATR | 1.4× ATR | 8 |
  | Crypto | 4h | fixed +3.5% | fixed −2.2% | 6 |
  | Stock | 5m | 1.6× ATR | 1.0× ATR | 12 |
  | Stock | 15m | 1.8× ATR | 1.1× ATR | 8 |
  | Stock | 1h | 2.0× ATR | 1.2× ATR | 6 |
  | Stock | 4h | fixed +2.0% | fixed −1.2% | 4 |

- [ ] Add `barrier_health_report()` to `labels.py`:
  - TP hit rate should be 30–45%
  - SL hit rate should be 30–45%
  - Timeout rate should be 15–30%
  - Alert if any band is violated
- [ ] Add purge logic to walk-forward folds in `trainer.py`:
  - Purge `max_holding_candles` bars before validation start
  - Add minimum 1-bar embargo after training cutoff
- [ ] Add unit tests for lagged ATR, fee-aware timeout labels, and purge logic

### Frontend
- [ ] No changes required in this phase

### Worker
- [ ] No changes required in this phase

### Database
- [ ] No migration required in this phase

---

## Phase ML-TF4 — Trainer Refactor (Per-Timeframe Models)

**Unblocks:** ML-TF5 prediction persistence, ML-TF6 ensemble.

### Problem
`trainer.py` uses one global `TrainerConfig` with no concept of `timeframe` or `model_role`.
`training_inputs.py` defaults `timeframe="1Day"` in both crypto and stock assemblers.
`model_registry.py` stores one active model per asset class.

### Backend
- [ ] Add `timeframe: str` and `model_role: ModelRole` to `TrainerConfig`
- [ ] Add `lookback_months` to `TrainerConfig`, driven by per-timeframe values:
  - Crypto 15m: 3–6 months
  - Crypto 1h: 6–9 months
  - Crypto 4h: 9–12 months
  - Stock 5m/15m: 8–12 months
  - Stock 1h: 12–15 months
  - Stock 4h: 12–18 months
- [ ] Update `training_inputs.py` crypto assembler: accept `timeframe` arg, remove `"1Day"` default
- [ ] Update `training_inputs.py` stock assembler: accept `timeframe` arg, remove `"1Day"` default
- [ ] Update `trainer.py` to resolve label config from `timeframe_config.py` by `(asset_class, timeframe)`
- [ ] Update `trainer.py` to apply purged walk-forward folds from ML-TF3
- [ ] Update `model_registry.py` to key stored models by `(asset_class, timeframe, model_role)`
- [ ] Remove assumption of a single `active_model` per asset class
- [ ] Add `TrainResult.timeframe` and `TrainResult.model_role` fields
- [ ] Update ML API router (`ml.py`) to accept `timeframe` and `model_role` as training params
- [ ] Ensure crypto training never creates short labels (bearish = block only)
- [ ] Add unit tests: train crypto 15m, 1h, 4h separately without cross-contamination

### Frontend
- [ ] ML page training trigger: expose timeframe selector dropdown (15m / 1h / 4h for crypto; 5m / 15m / 1h / 4h for stocks)
- [ ] Show per-timeframe training status independently (not one combined "crypto training" row)

### Worker
- [ ] Add per-timeframe retrain Celery tasks:
  - `ml:train:crypto:15m` — retrain every 1–2 weeks
  - `ml:train:crypto:1h` — retrain every 2–3 weeks
  - `ml:train:crypto:4h` — retrain every 3–4 weeks
- [ ] Keep all per-timeframe tasks independent (different schedules, different model outputs)

### Database
- [ ] No migration required — model registry is file-based; schema changes come in ML-TF5

---

## Phase ML-TF5 — Prediction Persistence Migration

**Unblocks:** ML-TF6 ensemble, Research page multi-TF stack display.

### Problem
`PredictionRow` has no `timeframe`, `model_role`, `prediction_group_id`, or barrier metadata fields.
Research page shows one flat prediction per symbol, not a 4h → 1h → 15m stack.

### Backend
- [ ] Add Alembic migration — add columns to `predictions` table:
  ```
  timeframe            VARCHAR(16)   nullable, default NULL (backfill-safe)
  model_role           VARCHAR(32)   nullable, default NULL
  prediction_group_id  VARCHAR(128)  nullable (groups same bar's 3-TF predictions)
  barrier_tp_pct       FLOAT         nullable
  barrier_sl_pct       FLOAT         nullable
  max_holding_bars     INT           nullable
  expected_value       FLOAT         nullable
  probability_strong_up   FLOAT      nullable
  probability_strong_down FLOAT      nullable
  ```
- [ ] Add index `(symbol, timeframe, candle_time)` to replace flat `(symbol, candle_time)`
- [ ] Update `predictor.py` to populate new fields when persisting predictions
- [ ] Add query helper: `get_latest_prediction_stack(symbol, asset_class)` — returns latest prediction per timeframe for a symbol
- [ ] Update ML router `GET /ml/predictions` to group by `prediction_group_id` when present

### Frontend
- [ ] No UI changes yet — that is ML-TF7

### Worker
- [ ] No changes required in this phase

### Database
- [ ] **Migration:** `20260502_0010_add_prediction_timeframe_fields.py`
  - All new columns nullable (zero downtime, safe backfill)
  - Add composite index `(symbol, timeframe, candle_time)`

---

## Phase ML-TF6 — Ensemble Decision Engine

**Unblocks:** Runtime trade decisions using multi-timeframe ML signal.

### Problem
`decision/composer.py` merges a single ML bias with sentiment/intraday signals.
There is no `ensemble.py` or `decision/ml_stack.py`. The 4h → 1h → 15m hierarchy does not exist in code.

### Backend
- [ ] Create `backend/app/ml/ensemble.py`:
  - Input: `(symbol, asset_class)` → fetch latest prediction per timeframe from DB
  - Apply gating rules:
    - 4h `P(bearish) > 0.60` → suppress all longs for this symbol (crypto: never short)
    - 1h directional signal requires 4h permission to become actionable
    - 15m timing signal requires 1h confirmation to trigger entry
  - Output: `EnsembleDecision` dataclass with fields: `final_action`, `regime_signal`, `direction_signal`, `timing_signal`, `confidence`, `reason`
- [ ] Create `backend/app/decision/ml_stack.py`:
  - Wraps `ensemble.py` output for use by `composer.py`
  - Exposes `ml_stack_bias(symbol, asset_class)` replacing the existing single-model `ml_bias`
- [ ] Update `composer.py` to consume `ml_stack_bias` instead of single-model prediction
- [ ] Enforce stock short rule: shorts only when `stock_cash > 2500`
- [ ] Crypto bearish: suppress longs, never generate short signal
- [ ] Add unit tests covering:
  - 4h bearish blocks 1h bullish (no trade)
  - 1h bullish without 4h permission → WATCH only
  - 15m bullish without 1h → note only, no entry
  - Full stack aligned → BUY signal

### Frontend
- [ ] No UI changes yet — that is ML-TF7

### Worker
- [ ] No changes required in this phase

### Database
- [ ] No migration required in this phase

---

## Phase ML-TF7 — Multi-Timeframe UI

**Unblocks:** Operator visibility into the multi-TF ML stack.

### Problem
`MachineLearning.tsx` and `Research.tsx` show one flat daily prediction per symbol.
After ML-TF4/TF5/TF6, the backend can return a 3-layer (or 4-layer for stocks) stack per symbol.

### Backend
- [ ] Add `GET /ml/stack/{symbol}` endpoint: returns latest `EnsembleDecision` + per-timeframe predictions
- [ ] Add `GET /ml/stack/batch` endpoint: returns stacks for all watchlist symbols

### Frontend
- [ ] Update `MachineLearning.tsx`:
  - Replace single prediction row per symbol with expandable ML stack card
  - Show per-timeframe rows: **4h Regime** / **1h Direction** / **15m Timing** / **5m Execution** (stocks)
  - Each row: timeframe label, direction, confidence bar, barrier config (TP%/SL%), bars held
  - Show `EnsembleDecision.final_action` as the top-level badge
  - Remove daily prediction as primary signal display
- [ ] Update `Research.tsx`:
  - Symbol detail panel: replace single ML prediction with stacked TF view
  - Show ensemble final action with reason string
  - Show which timeframe gated or enabled the trade
- [ ] Add `useMLStack(symbol)` hook in `frontend/src/hooks/`
- [ ] Update `api.ts` with `fetchMLStack(symbol)` and `fetchMLStackBatch()` typed calls

### Worker
- [ ] No changes required in this phase

### Database
- [ ] No migration required in this phase

---

## Phase 11 — Crypto End-to-End Integration Validation

**Unblocks:** Production confidence, Phase 12 drift tooling.

### Problem
Phase 10 completed ledger durability. Phase 11 in the checklist validates the full vertical slice but all items remain unchecked.

### Backend
- [ ] Validate full pipeline under a simulated session:
  - Worker → candle closed → inference trigger → prediction persisted → decision composed → paper order placed → ledger fill persisted
- [ ] Confirm no duplicate candles, predictions, or fills across a restart cycle
- [ ] Confirm no stale timestamps in any worker event log

### Frontend
- [ ] Validate paper state survives a full app restart without data loss
- [ ] Confirm no stale worker counts or dead status indicators after reconnect

### Worker
- [ ] Explicitly validate Redis `candle_closed` pub/sub path end-to-end (not just unit tested)
- [ ] Confirm no worker scope drift (symbols added mid-session stay stable)

### Database
- [ ] Run duplicate-detection queries on `candles`, `predictions`, `paper_fills`
- [ ] Confirm all timestamps are timezone-aware UTC throughout the pipeline

---

## Phase 12 — Crypto Drift & Runtime Insight

**Unblocks:** Operator trust in live model health.

### Backend
- [ ] Add `GET /ml/drift/crypto` endpoint:
  - Returns per-timeframe drift report from `DriftMonitor`
  - Includes feature z-scores, top-10 feature overlap across recent folds
  - Returns `drift_detected: bool` per timeframe
- [ ] Update `drift_monitor.py` to accept `timeframe` and `model_role` context
- [ ] Add freshness age check per timeframe (age since last retrain vs max age policy)
- [ ] Add barrier health summary endpoint `GET /ml/barrier-health/{asset_class}`

### Frontend
- [ ] Replace drift UI placeholders in `MachineLearning.tsx` with live data from `/ml/drift/crypto`
- [ ] Show per-timeframe drift status badge (OK / Drifting / Stale)
- [ ] Show freshness countdown: days since last retrain vs threshold
- [ ] Show barrier health: TP hit rate, SL hit rate, timeout rate per timeframe

### Worker
- [ ] Add weekly drift check Celery task `ml:drift:check` (runs Sunday post-retrain)
- [ ] Log drift alert to `runtime_events` table if `drift_detected = true`

### Database
- [ ] No migration required — drift is computed on demand from existing model registry and prediction tables

---

## Phase 13 — Crypto Training Policy Improvements

**Unblocks:** Cleaner model selection and more reliable champion promotion.

### Backend
- [ ] Constrain training horizon per timeframe (use lookback months from ML-TF4, reject candles older than max lookback)
- [ ] Cap walk-forward fold count (max 8 folds for 1h, max 6 for 4h, max 12 for 15m)
- [ ] Improve champion fold selection: use `validation_sharpe × (1 - IS/OOS_decay)` as composite score
- [ ] Reject any fold with IS/OOS decay > 30%
- [ ] Reject any fold with max drawdown > 25% (crypto) or > 20% (stocks)
- [ ] Add `eligibility_reason` values for all new rejection conditions
- [ ] Reduce calendar effect dominance: add month-of-year as a feature but not as a label stratification key

### Frontend
- [ ] ML page fold table: show IS/OOS decay column alongside existing validation Sharpe
- [ ] Highlight folds with decay > 30% in red

### Worker
- [ ] No changes required in this phase

### Database
- [ ] No migration required in this phase

---

## Phase 14 — Crypto Retraining Automation

**Unblocks:** Hands-off weekly retraining cycle.

### Problem
`scripts/retrain_models.py` is a stub. There is no automated trigger or deployment gate.

### Backend
- [ ] Implement `retrain_models.py` as a fully automated retrain pipeline:
  - For each active timeframe contract: fetch latest candles → build features → label → train → evaluate
  - Only promote new model if: OOS Sharpe ≥ threshold AND max DD ≤ threshold AND IS/OOS decay < 30%
  - Keep last 3 model versions per `(asset_class, timeframe, model_role)`
  - Emit `runtime_events` record with outcome (promoted / rejected / error)
- [ ] Add `POST /ml/retrain/trigger` endpoint for manual operator-triggered retrain
- [ ] Add rollback endpoint `POST /ml/rollback/{asset_class}/{timeframe}` (reverts to previous champion)
- [ ] Add sentiment coverage gate: skip retrain if sentiment data < 70% coverage for training window

### Frontend
- [ ] ML page: add "Retrain" button per timeframe with confirmation modal
- [ ] Show retrain history: last 5 retrain attempts with outcome (promoted / rejected / failed)
- [ ] Show rollback button when previous model version is available

### Worker
- [ ] Add weekly Celery beat per timeframe retrain task:
  - `ml:retrain:crypto:15m` — Sunday 01:00 UTC
  - `ml:retrain:crypto:1h` — Sunday 02:00 UTC
  - `ml:retrain:crypto:4h` — Sunday 03:00 UTC
- [ ] Retrain tasks must be idempotent (safe to re-run on failure)

### Database
- [ ] Add `retrain_log` table:
  ```
  id              UUID PK
  asset_class     VARCHAR(16)
  timeframe       VARCHAR(16)
  model_role      VARCHAR(32)
  triggered_by    VARCHAR(32)   -- 'schedule' | 'manual'
  outcome         VARCHAR(16)   -- 'promoted' | 'rejected' | 'error'
  oos_sharpe      FLOAT
  max_drawdown    FLOAT
  oos_decay_pct   FLOAT
  model_version   VARCHAR(128)
  error_detail    TEXT nullable
  created_at      TIMESTAMPTZ
  ```
- [ ] **Migration:** `20260502_0011_add_retrain_log.py`

---

## Phase 15 — Broker Reliability

**Unblocks:** Production confidence in order execution.

### Backend
- [ ] Add retry logic with exponential backoff to Kraken broker (`kraken.py`): 3 retries, 2s/4s/8s delays
- [ ] Add retry logic to Alpaca fetcher (`alpaca.py`): 3 retries for candle sync failures
- [ ] Add retry logic to Tradier broker (`tradier.py`): 3 retries for order placement
- [ ] Validate broker config at startup (API keys present, connectivity check) — fail fast with clear error
- [ ] Add per-broker error rate counter to `runtime_events` (log each retry and final failure)
- [ ] Keep paper and live broker execution paths isolated — no shared retry budget

### Frontend
- [ ] Runtime page: show per-broker error count in last 24h
- [ ] Show broker connectivity status badge (OK / Degraded / Down)

### Worker
- [ ] No new tasks — broker retry is inline within existing tasks

### Database
- [ ] No migration required — broker errors logged to existing `runtime_events` table

---

## Phase S1 — Stock Scope & Guardrails (Enforcement)

**Note:** The S1 rules exist in docs but none are enforced in code yet.

### Backend
- [ ] Add `STOCK_LONG_ONLY_CASH_THRESHOLD = 2500.0` to `constants.py`
- [ ] Add guardrail in `composer.py`: block stock shorts when `stock_cash < 2500`
- [ ] Add guardrail in paper ledger service: reject short orders below threshold
- [ ] Add market session gate utility (`is_market_open(timestamp, tz="America/New_York")`)
- [ ] Apply session gate to all stock candle workers and order placement
- [ ] Add `max_hold_hours` field to stock position entry (freeze at open)
- [ ] Enforce crypto long-only at order placement level (no short order path for crypto)

### Frontend
- [ ] Settings page: show stock cash balance vs short threshold
- [ ] Paper ledger: show "Shorts disabled (insufficient cash)" when below threshold

### Worker
- [ ] All stock candle workers must check session gate before fetching

### Database
- [ ] No migration required — `max_hold_hours` placeholder already exists in stock schema (Phase S2)

---

## Phase S6 — Stock Candle Workers

**Unblocks:** All stock ML training phases.

### Backend
- [ ] Add `StockMLCandleTask` Celery task (`tasks/stock_ml_candles.py`):
  - Fetches Alpaca historical candles for `STOCK_ML_TIMEFRAMES = ("5m", "15m", "1h", "4h")`
  - Stores with `usage="ml"`, `source="alpaca_training"`
  - Respects per-timeframe lookback months from `timeframe_config.py`
- [ ] Add `StockIntradayCandelTask` Celery task:
  - Fetches Tradier live intraday candles for active watchlist symbols only
  - Stores with `usage="trading"`, `source="tradier"`
  - Runs only during market session hours (ET)
  - Closed candles only, 20-second delay after close
- [ ] Add stock post-close daily sync (Alpaca 1Day, `usage="ml"` context lane)
- [ ] No full-market intraday scanning — active watchlist only

### Frontend
- [ ] Runtime page: add stock candle worker row with last sync time and symbol count

### Worker
- [ ] Add `stock:candles:intraday` beat schedule (every 5 minutes, session hours only)
- [ ] Add `stock:candles:ml` beat schedule (nightly, post-market)

### Database
- [ ] No migration required — `stock_candles` table already created in Phase S2

---

## Phase S12 — Stock ML Training Inputs

**Unblocks:** Phase S13 stock labeling and training.

### Backend
- [ ] Add stock-specific feature columns to `features.py`:
  - Sector classification (from S4 screening data)
  - Earnings proximity flag (days to/from nearest earnings)
  - Congress signal score (from `stock_congress_events` table)
  - Insider buy score (from `stock_insider_events` table)
  - News sentiment score (from `stock_news_events` table)
  - Cross-TF context features (same pattern as crypto: 4h trend into 1h features)
- [ ] Add `StockDatasetAssembler` to `training_inputs.py`:
  - Supports all 4 stock timeframes
  - Joins candles with news, congress, insider tables by `(symbol, date)` window
  - Respects market session (no pre/post market candles in training data)
  - Excludes candles within 2 days of earnings (avoid label noise)
- [ ] Add unit tests for stock feature join and earnings exclusion

### Frontend
- [ ] No changes required in this phase

### Worker
- [ ] No changes required in this phase

### Database
- [ ] No migration required in this phase

---

## Phase S13 — Stock ML Labels & Training

**Unblocks:** Stock prediction persistence and decision engine.

### Backend
- [ ] Apply `timeframe_config.py` stock label configs to `build_long_trade_labels()`:
  - Use ATR-adjusted barriers for 5m, 15m, 1h
  - Use fixed % barriers for 4h
  - Apply stock `min_profitable_move_pct = 0.002`
- [ ] Add overnight gap handler in `labels.py`:
  - If `gap_open > TP_barrier` OR `gap_open < SL_barrier` → label as `NO_EDGE_LABEL` (unrealistic fill)
- [ ] Add stock short label support:
  - When `stock_cash > 2500` and model predicts `STOP_LOSS_LABEL`, this may signal a short entry (not just a block)
  - When `stock_cash < 2500`, bearish stock label = block long only (same as crypto)
- [ ] Extend `trainer.py` to support stock asset class with all 4 timeframes
- [ ] Add stock-specific eligibility thresholds to `TrainerConfig`:
  - `stock_min_validation_sharpe = 0.8`
  - `stock_max_drawdown = 0.20`
  - `stock_max_oos_decay = 0.30`

### Frontend
- [ ] No changes required in this phase

### Worker
- [ ] Add per-timeframe retrain Celery tasks for stocks:
  - `ml:retrain:stock:5m` — Saturday 04:00 ET
  - `ml:retrain:stock:15m` — Saturday 05:00 ET
  - `ml:retrain:stock:1h` — Saturday 06:00 ET
  - `ml:retrain:stock:4h` — Saturday 07:00 ET

### Database
- [ ] No migration required — prediction table updated in ML-TF5 already supports stocks

---

## Appendix: Phase Dependency Chain

```
ML-TF2 (candle lanes)
  └── ML-TF3 (labels)
        └── ML-TF4 (trainer refactor)
              └── ML-TF5 (prediction migration)
                    └── ML-TF6 (ensemble engine)
                          └── ML-TF7 (UI stack)

Phase 11 (E2E validation)
  └── Phase 12 (drift tooling)
        └── Phase 13 (training policy)
              └── Phase 14 (retrain automation)

Phase 15 (broker reliability) — parallel, no strict dependency

S1 (stock guardrails) — must precede all S6+
  └── S6 (stock candle workers)
        └── S12 (stock training inputs)
              └── S13 (stock labels + training)
```

---

## Appendix: Deployment Thresholds (Reference)

These thresholds gate every model before it goes live. Enforced in Phase 14 retrain automation.

| Metric | Crypto Minimum | Stock Minimum |
|---|---|---|
| OOS Sharpe | ≥ 1.0 | ≥ 0.8 |
| Max Drawdown | ≤ 25% | ≤ 20% |
| IS/OOS Decay | < 30% | < 30% |
| Profit Factor | ≥ 1.3 | ≥ 1.3 |
| TP Hit Rate | 30–45% | 30–45% |
| SL Hit Rate | 30–45% | 30–45% |
| Timeout Rate | 15–30% | 15–30% |
| Model Max Age (15m) | 2 weeks | 3 weeks |
| Model Max Age (1h) | 3 weeks | 4 weeks |
| Model Max Age (4h) | 4 weeks | 6 weeks |

**Kraken Pro fee assumption baked into all crypto barriers:** 0.40% taker × 2 + 0.10% slippage = **1.00% round-trip cost.** Minimum profitable move before any crypto trade label is counted as a win: **1.30%.**
