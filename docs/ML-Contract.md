Reviewed the uploaded ML blueprint and current zip. Your concern is correct: the current ML lane is still fundamentally **daily-candle centered**, while the trading logic is intraday and multi-timeframe. That creates a training/trading mismatch, aka the model is studying the weather map while the bot is driving through traffic. The blueprint calls for separate LightGBM models per timeframe with ATR-adjusted triple-barrier labels, 4h regime, 1h direction, and 15m/5m timing. 

## What the zip shows

Current ML training is anchored to `1Day` in several places:

`backend/app/tasks/ml_candles.py`

* `CRYPTO_ML_TIMEFRAMES = (ALPACA_DEFAULT_TIMEFRAME,)`
* `ALPACA_DEFAULT_TIMEFRAME = "1Day"`
* worker ID and event text are `ml:crypto:1D`

`backend/app/ml/training_inputs.py`

* stock and crypto assemblers default to `timeframe="1Day"`
* training loaders filter one timeframe at a time, but everything currently assumes daily

`backend/app/api/routers/ml.py`

* multiple constants/endpoints hardcode stock/crypto daily training and catch-up behavior

`backend/app/ml/trainer.py`

* trainer supports triple-barrier labels already
* but it uses one global label config, one global lookahead, and one model contract per asset class
* it does **not** yet have timeframe-specific configs, purged folds, fee-aware barriers, or multi-model ensemble scoring

## Keep

Keep these pieces. They are useful bones:

* `candles.usage = "ml" | "trading"` lane separation
* existing `CandleRow` schema, because `timeframe` is already part of the candle primary key
* existing LightGBM trainer foundation
* existing triple-barrier label module, but expand it
* existing prediction persistence, but migrate it for timeframe/model-role awareness
* existing Research page/ML page concepts, but change how predictions are grouped
* existing crypto long-only rule
* existing stock short rule: shorts only when stock cash > $2,500

## Delete or retire

Do **not** delete immediately, but retire these as the production ML path:

* daily-only crypto ML training as the active decision model
* `ml:crypto:1D` as the primary ML worker identity
* “latest prediction per symbol” as the final ML truth
* single active model per asset class
* single global label config for all crypto/stock timeframes
* prediction records that cannot identify timeframe, model role, or ensemble contribution
* daily candle freshness as the only ML freshness gate

Daily can stay as **context/regime/research**, but it should no longer be the trading model’s engine.

# New ML Contract: Multi-Timeframe Training System

## 1. Model contract

Create separate models by:

```text
asset_class + timeframe + model_role
```

Required model roles:

```text
crypto 4h = regime_filter
crypto 1h = direction
crypto 15m = entry_timing

stock 4h = regime_filter
stock 1h = direction
stock 15m = setup_timing
stock 5m = execution_timing
```

Daily candles become optional context only:

```text
1Day = macro/context, not primary trade model
```

## 2. Candle contract

Training candles:

```text
usage="ml"
source="alpaca_training" or provider-specific historical source
timeframes:
  crypto: 15m, 1h, 4h
  stocks: 5m, 15m, 1h, 4h
```

Trading candles:

```text
usage="trading"
source="kraken" for crypto
source="tradier" for stocks
only active runtime/watchlist symbols
closed candles only
delay after candle close
```

## 3. Label contract

Replace the single label config with timeframe-specific configs.

Crypto:

```text
15m:
  classes: 3
  TP: 1.8 x ATR
  SL: 1.1 x ATR
  hold: 6 bars
  min profitable move: fee + slippage + edge

1h:
  classes: 3 first, later 5
  TP: 2.2 x ATR
  SL: 1.4 x ATR
  hold: 8 bars

4h:
  classes: 3
  TP: fixed percent or ATR-backed config
  SL: fixed percent or ATR-backed config
  hold: 6 bars
```

Stocks:

```text
5m:
  TP: 1.6 x ATR
  SL: 1.0 x ATR
  hold: 12 bars

15m:
  TP: 1.8 x ATR
  SL: 1.1 x ATR
  hold: 8 bars

1h:
  TP: 2.0 x ATR
  SL: 1.2 x ATR
  hold: 6 bars

4h:
  TP: fixed percent
  SL: fixed percent
  hold: 4 bars
```

Critical fixes:

```text
ATR must be lagged by 1 bar.
Validation folds must purge at least max_holding_candles before test.
Timeout labels must account for fees/slippage.
Crypto bearish labels mean BLOCK/NO_TRADE only, never short.
```

## 4. Prediction contract

Add fields to prediction persistence:

```text
timeframe
model_role
model_version
prediction_group_id
barrier_config
probability_strong_up optional
probability_strong_down optional
expected_value
barrier_tp_pct
barrier_sl_pct
max_holding_bars
```

Current `PredictionRow` does not have enough metadata for multi-timeframe ML.

## 5. Ensemble contract

Final crypto decision:

```text
4h regime filter
→ 1h directional model
→ 15m timing model
→ sentiment/risk overlay
→ final action
```

Rules:

```text
4h bearish crypto = suppress longs, never short.
1h bullish without 4h permission = WATCH or NO_TRADE.
15m bullish without 1h confirmation = timing note only.
Sentiment can reduce/block, not magically create a trade.
```

Final stock decision:

```text
4h regime
→ 1h direction
→ 15m setup
→ 5m entry
→ stock research/catalyst/risk
```

Stock shorts:

```text
Allowed only when stock cash > $2,500.
Otherwise bearish stock ML suppresses long entries only.
```

# Implementation Contract

## Phase ML-TF1 — Config + Contract Foundation

Add:

```text
backend/app/ml/timeframe_config.py
backend/app/ml/model_contracts.py
backend/tests/unit/test_ml_timeframe_config.py
```

Purpose:

* define allowed timeframes
* define model roles
* define label configs per asset/timeframe
* define training lookback per asset/timeframe
* keep hardcoded `1Day` out of trainer/API logic

No DB migration yet.

## Phase ML-TF2 — Multi-Timeframe Candle ML Lane

Change:

```text
backend/app/tasks/ml_candles.py
backend/app/config/constants.py
```

Add:

```text
CRYPTO_ML_TIMEFRAMES = ("15m", "1h", "4h")
STOCK_ML_TIMEFRAMES = ("5m", "15m", "1h", "4h")
```

Keep `1Day` only as legacy/context.

Acceptance:

```text
ML candle summary shows rows by symbol + timeframe + usage.
No crypto trading candle worker duplication.
No stock runtime candle pollution.
```

## Phase ML-TF3 — Label Upgrade

Change:

```text
backend/app/ml/labels.py
backend/app/ml/trainer.py
```

Add:

* timeframe-aware label config
* lagged ATR
* fee/slippage aware minimum profitable move
* purged walk-forward folds
* barrier health report

Acceptance:

```text
ruff check app tests
python -m mypy app
pytest tests/unit/test_ml_labels*.py
```

## Phase ML-TF4 — Trainer Refactor

Change:

```text
backend/app/ml/trainer.py
backend/app/ml/training_inputs.py
backend/app/ml/model_registry.py
```

Trainer input becomes:

```text
asset_class
timeframe
model_role
```

Model registry stores:

```text
asset_class
timeframe
model_role
label_config
feature_contract
trained_at
eligibility
```

Acceptance:

```text
Can train crypto 15m, 1h, 4h separately.
Can train stock 5m, 15m, 1h, 4h separately later.
No single “active crypto model” assumption.
```

## Phase ML-TF5 — Prediction Persistence Migration

Add Alembic migration for prediction/model metadata.

Add fields:

```text
timeframe
model_role
prediction_group_id
expected_value
barrier_tp_pct
barrier_sl_pct
max_holding_bars
```

Acceptance:

```text
Latest predictions can be queried per symbol and timeframe.
Research page can show grouped ML stack instead of one flat row.
```

## Phase ML-TF6 — Ensemble Decision Engine

Add:

```text
backend/app/ml/ensemble.py
backend/app/decision/ml_stack.py
```

Rules:

```text
crypto: 4h → 1h → 15m
stocks: 4h → 1h → 15m → 5m
```

Acceptance:

```text
Final decision explains each timeframe:
4h regime
1h direction
15m timing
5m stock execution timing
risk/sentiment result
```

## Phase ML-TF7 — UI Contract

Update:

```text
frontend/src/pages/MachineLearning.tsx
frontend/src/pages/Research.tsx
```

Display:

```text
ML Stack:
  4h Regime
  1h Direction
  15m Timing
  5m Stock Entry, stock only
```

Do not show one daily prediction as the whole truth anymore.

# Bottom line

Yes, the current 1D-only ML training should be demoted. The bot needs **separate intraday models per timeframe**, with `4h` as the weather vane, `1h` as the steering wheel, and `15m/5m` as the trigger finger. Daily data can remain useful, but only as context, not as the trading brain.
