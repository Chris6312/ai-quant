# Complete Multi-Timeframe ML Trading Bot Blueprint
## With Triple Barrier Labeling & Kraken Pro Fee Structure

## Executive Summary

Build **separate LightGBM models per timeframe** using **ATR-adjusted triple barrier labels** for realistic risk management. Train on 6-12 month windows (crypto) or 12-18 month windows (stocks), retrain every 2-4 weeks, and only deploy models meeting strict performance thresholds. The 4h model acts as regime filter, 1h drives directional decisions, and 15m refines entry timing. All barriers account for **Kraken Pro taker fees (0.40%) + slippage**.

---

## I. Model Architecture

### Core Structure
**Separate LightGBM models** (not unified multi-head):
- One model per timeframe (15m, 1h, 4h for crypto; 5m, 15m, 1h, 4h for stocks)
- Independent training schedules and feature sets
- **ATR-adjusted triple barrier labels** for each timeframe
- Final ensemble layer combines predictions via hierarchical voting or stacked meta-model

### Why LightGBM Over Alternatives
- Fast training for rapid iteration (critical for frequent retraining)
- Excellent feature importance interpretation (debug failed trades)
- Handles tabular time-series features natively
- Efficient multi-class classification (3-class or 5-class barrier labels)
- Lower overfitting risk than deep learning on limited financial data

---

## II. Triple Barrier Label Configuration

### **Kraken Pro Fee Structure (CRITICAL)**

**Kraken Pro Taker Fees**: 0.40% per trade
**Total Round-Trip Cost**: 0.80% (entry + exit)
**Estimated Slippage**: 0.05-0.10% per trade (market orders)
**Total Transaction Cost**: **0.90-1.00% per round trip**

**Impact on barriers**:
```
Minimum profitable TP = Transaction costs + minimum edge
= 1.00% + 0.30% (minimum worthwhile profit)
= 1.30% minimum TP for any trade to be worthwhile

Effective SL after costs = Barrier SL + Transaction costs
= If SL set at -0.80%, actual loss = -0.80% - 1.00% = -1.80%
```

### **Core Triple Barrier Methodology**

**At each bar t, set three barriers**:
1. **Take-Profit (TP)**: Upper price barrier triggering profitable exit
2. **Stop-Loss (SL)**: Lower price barrier triggering protective exit
3. **Time Barrier**: Maximum holding period (bars)

**Label = First barrier hit**:
- Hit TP first → Label = +1 (profitable long signal)
- Hit SL first → Label = -1 (losing long / profitable short signal)
- Hit time barrier → Label = 0 or actual return class (neutral/timeout)

**Why triple barrier beats simple forward returns**:
- Learns realistic exit behavior (don't hold forever)
- Accounts for intraday risk (price might hit SL before reaching target)
- Incorporates transaction costs in training (model learns "is this trade worth the fees?")
- Asymmetric R:R ratio (wider TP accounts for costs, tighter SL controls risk)
- Reduces label noise (ignores tiny unprofitable moves)

---

## III. Timeframe-Specific Models with Triple Barrier Labels

### **15-Minute Model (Crypto)**

**Purpose**: Scalping signals, microstructure edge, entry timing refinement

**Triple Barrier Configuration**:
```
TP_barrier = Entry × (1 + 1.8 × ATR(14) / Entry)
SL_barrier = Entry × (1 - 1.1 × ATR(14) / Entry)
Time_barrier = 6 bars (1.5 hours max hold)
Min_profitable_move = 1.30% (covers Kraken fees + minimum edge)

Typical barriers in normal volatility (ATR ~1.2%):
- TP: +2.16% (covers 1.00% fees + 1.16% profit)
- SL: -1.32% (actual loss = -2.32% after fees)
- R:R ratio: 1.64:1 (realistic after costs)
```

**Label Logic (3-class)**:
```
If hit TP within 6 bars → Label = +1
If hit SL within 6 bars → Label = -1  
If time barrier hit AND abs(return) <1.30% → Label = 0 (not profitable after fees)
If time barrier hit AND return ≥1.30% → Label = +1 (weak profitable)
If time barrier hit AND return ≤-1.30% → Label = -1 (weak losing)
```

**Features (~30-50)**:
- **Price Action**: Returns over [1, 3, 5, 10, 15] bars, high-low spread %, VWAP deviation
- **Volume**: Volume ratio vs 1h/4h average, volume-price correlation (5-bar), OBV momentum
- **Microstructure**: Bid-ask spread, trade flow imbalance (buy vs sell volume), order book depth ratio
- **Technical**: RSI(14), Bollinger Band position, ATR(14) normalized
- **Cross-TF Context**: 1h trend direction (binary), 4h volatility regime (low/med/high), distance from 1h/4h MA(20)
- **Time Features**: Hour of day, day of week (crypto less relevant but test)
- **Crypto-Specific**: Funding rate changes, liquidation cascades (if available via Kraken API)

**LightGBM Config**:
```python
lgb_params_15m = {
    'objective': 'multiclass',
    'num_class': 3,
    'metric': 'multi_logloss',
    'max_depth': 4-6,
    'learning_rate': 0.05,
    'num_iterations': 200-500,
    'feature_fraction': 0.7,
    'is_unbalance': True,  # Handle class imbalance
    'min_child_weight': 15,
}
```

**Training Data**: Last 3-6 months  
**Retrain Frequency**: Every 1-2 weeks  
**Deployment Threshold**: OOS Sharpe ≥1.0, Max DD ≤25%

---

### **1-Hour Model (Crypto)**

**Purpose**: Primary signal generator, intraday trend capture

**Triple Barrier Configuration**:
```
TP_barrier = Entry × (1 + 2.2 × ATR(14) / Entry)
SL_barrier = Entry × (1 - 1.4 × ATR(14) / Entry)
Time_barrier = 8 bars (8 hours max hold)
Min_profitable_move = 1.30%

Typical barriers in normal volatility (ATR ~2.0%):
- TP: +4.40% (covers 1.00% fees + 3.40% profit)
- SL: -2.80% (actual loss = -3.80% after fees)
- R:R ratio: 1.57:1 (realistic after costs)
```

**Enhanced Label Logic (5-class with momentum)**:
```
If hit TP AND next 2 bars continue trend → Label = +2 (very strong long)
If hit TP normally → Label = +1 (profitable long)
If time barrier AND abs(return) <1.30% → Label = 0 (neutral, fees kill profit)
If hit SL normally → Label = -1 (losing long / profitable short)
If hit SL AND next 2 bars accelerate down → Label = -2 (very weak, avoid longs)
```

**Features (~40-60)**:
- **Price Action**: Returns [1h, 2h, 4h, 8h, 24h], price change from session open/high/low
- **Momentum**: MACD(12,26), RSI(14), Stochastic RSI, ROC over 4/8/12 bars
- **Volatility**: ATR(14), Bollinger %B, Keltner Channel position, realized vol (1h vs 24h ratio)
- **Volume**: Volume-weighted momentum, accumulation/distribution, Chaikin Money Flow
- **Patterns**: Higher highs/lows count (last 12 bars), support/resistance proximity
- **Cross-TF**: 4h trend alignment (MA crossovers), daily pivot levels, distance from daily open
- **Regime**: 4h volatility percentile (30-day), correlation to BTC (for alts)
- **Orderbook**: Bid-ask imbalance at ±0.5%, depth ratio (Kraken L2 data)
- **Sentiment**: Funding rate slope, open interest changes (if available)
- **Barrier Context**: Current ATR / median ATR (helps model adjust to volatility regime)

**LightGBM Config**:
```python
lgb_params_1h = {
    'objective': 'multiclass',
    'num_class': 5,
    'metric': 'multi_logloss',
    'max_depth': 6-8,
    'learning_rate': 0.03,
    'num_iterations': 500-1000,
    'early_stopping_rounds': 50,
    'feature_fraction': 0.75,
    'is_unbalance': True,
    'min_child_weight': 20,
}
```

**Training Data**: Last 6-9 months  
**Retrain Frequency**: Every 2-3 weeks  
**Deployment Threshold**: OOS Sharpe ≥1.0, Max DD ≤25%

---

### **4-Hour Model (Crypto)**

**Purpose**: Swing trend identification, regime filter, directional bias

**Triple Barrier Configuration**:
```
TP_barrier = Entry × (1 + 3.5%)  # Fixed % (regime detection simpler)
SL_barrier = Entry × (1 - 2.2%)
Time_barrier = 6 bars (24 hours max hold)
Min_profitable_move = 1.30%

Fixed barriers (volatility already in 4h features):
- TP: +3.50% (covers 1.00% fees + 2.50% profit)
- SL: -2.20% (actual loss = -3.20% after fees)
- R:R ratio: 1.59:1
```

**Label Logic (3-class, simpler for regime)**:
```
If hit TP within 6 bars → Label = +1 (bullish regime)
If hit SL within 6 bars → Label = -1 (bearish regime)
If time barrier hit → Label = 0 (neutral/choppy regime)
```

**Features (~35-50)**:
- **Trend**: EMA(20, 50, 100, 200) relationships, MACD histogram slope, ADX(14)
- **Structure**: Swing high/low patterns (last 10 bars), Fibonacci retracement levels
- **Divergences**: RSI vs price divergence, volume trend vs price trend
- **Volatility**: Bollinger Band width percentile, ATR slope
- **Volume Profile**: Volume at price (VAP) zones, Point of Control (POC) distance
- **Cross-TF**: Daily bias (above/below daily MA50), weekly pivot zones
- **Cyclical**: Day-of-week effects, monthly seasonality (less relevant crypto but test)
- **Correlations**: BTC dominance (for alts), inter-asset correlation strength
- **On-Chain** (if available): Exchange inflows/outflows, whale activity

**LightGBM Config**:
```python
lgb_params_4h = {
    'objective': 'multiclass',
    'num_class': 3,
    'metric': 'multi_logloss',
    'max_depth': 5-7,
    'learning_rate': 0.03,
    'num_iterations': 300-700,
    'feature_fraction': 0.7,
    'min_child_weight': 20,
}
```

**Training Data**: Last 9-12 months  
**Retrain Frequency**: Every 3-4 weeks  
**Deployment Threshold**: OOS Sharpe ≥1.0, Max DD ≤25%

---

### **Stock Models (5m, 15m, 1h, 4h)**

**Fee Structure (Stocks)**:
- Commission: $0.005/share or $1 minimum (typical)
- Slippage: 0.02% (tighter than crypto)
- **Total round-trip cost**: ~0.10-0.15% (much lower than crypto)

**Adjusted Barriers** (lower minimum profitable move):
```
Min_profitable_move = 0.20% (vs 1.30% for crypto)

5m model:  TP: 1.6×ATR, SL: 1.0×ATR, Time: 12 bars (1h)
15m model: TP: 1.8×ATR, SL: 1.1×ATR, Time: 8 bars (2h)
1h model:  TP: 2.0×ATR, SL: 1.2×ATR, Time: 6 bars (6h)
4h model:  TP: +2.0% fixed, SL: -1.2% fixed, Time: 4 bars (16h)
```

**Key differences from crypto**:
- Tighter barriers (lower fees allow smaller profits)
- Market hours filter (only trade 9:30 AM - 4:00 PM ET)
- Overnight gap handling (discard labels if gap >2× ATR)
- Earnings date avoidance (set all labels to 0 within 2 days of earnings)

---

## IV. Feature Engineering Principles

### Normalization Rules
- **Returns & ratios** instead of raw prices (asset-agnostic)
- **Z-scores** over rolling windows (e.g., 30-day for 4h features)
- **Percentile ranks** for regime features (volatility, volume)
- **ATR normalization**: All price-based features divided by current ATR

### Cross-Timeframe Integration
- Higher-TF features feed into lower-TF models (4h→1h→15m)
- Example: 15m model includes "1h trend up/down" and "4h volatility regime"
- **Never** allow lower-TF leakage into higher-TF (4h cannot see 15m data)

### Lag Management for Triple Barrier
```python
# CRITICAL: ATR must be lagged to avoid look-ahead bias
atr_lagged = df['ATR'].shift(1)  # Use previous bar's ATR

# Calculate barriers at bar t using only data up to t-1
entry_price = df.loc[t, 'close']
tp_barrier = entry_price * (1 + 2.2 * atr_lagged[t] / entry_price)
sl_barrier = entry_price * (1 - 1.4 * atr_lagged[t] / entry_price)

# Scan forward to find first barrier hit
for i in range(1, time_barrier + 1):
    if df.loc[t+i, 'high'] >= tp_barrier:
        label = +1  # TP hit
        break
    elif df.loc[t+i, 'low'] <= sl_barrier:
        label = -1  # SL hit
        break
    elif i == time_barrier:
        # Check if move was profitable after fees
        final_return = (df.loc[t+i, 'close'] - entry_price) / entry_price
        if final_return >= 0.013:  # 1.30% minimum
            label = +1
        elif final_return <= -0.013:
            label = -1
        else:
            label = 0  # Not worth trading (fees eat profit)
```

### Transaction Cost Integration
**Adjust effective barriers**:
```python
kraken_fee = 0.004  # 0.40% taker fee
slippage = 0.0006   # 0.06% estimated slippage
total_cost = kraken_fee + slippage  # 0.46% per trade
round_trip_cost = 2 * total_cost    # 0.92% total

# Effective TP after costs
tp_net = tp_barrier - round_trip_cost

# Only label as +1 if net profit exceeds minimum threshold
min_edge = 0.003  # 0.30% minimum profit after fees
if tp_net < min_edge:
    # Barrier too close, relabel as neutral
    # This teaches model "don't take low-probability scalps on Kraken"
    label = 0
```

---

## V. Training Configuration

### Data Windows

**Crypto (Kraken Pro)**:
- 15m model: 3-6 months lookback, 50,000-120,000 bars
- 1h model: 6-9 months lookback, 4,000-6,500 bars
- 4h model: 9-12 months lookback, 1,600-2,200 bars
- **Maximum lookback**: 18 months (beyond = irrelevant market structure)

**Stocks**:
- 5m/15m model: 8-12 months lookback
- 1h model: 12-15 months lookback
- 4h model: 12-18 months lookback
- **Maximum lookback**: 3 years (but 18 months is sweet spot)

### Walk-Forward Validation with Triple Barrier

**Structure**:
1. Train on expanding window (e.g., 6 months)
2. Calculate triple barrier labels for training period
3. Validate on next period (1 month) with fresh barrier labels
4. Test out-of-sample (2-4 weeks) with fresh barrier labels
5. **Purge** overlapping periods (critical for barrier labels)
6. **Embargo** gap (1 day minimum) after training cutoff

**Purging for triple barriers**:
```python
# If time_barrier = 8 bars (1h model)
# Must purge 8 bars before validation start to avoid leakage

train_end = '2026-03-31'
purge_period = 8 * 1  # 8 hours
validation_start = '2026-04-01 08:00'  # Start 8 hours after train_end

# Training set: All bars where barrier calculation completes before train_end
# This means last training bar is actually train_end - time_barrier
```

**Example Timeline** (Crypto 1h model, 8-bar time barrier):
- Training: Aug 1, 2025 - Mar 23, 2026 (last bar where 8h barrier fits before cutoff)
- Purge period: Mar 24-31, 2026 (8 bars, no data used)
- Validation: Apr 1-30, 2026 (1 month, fresh barrier labels)
- Out-of-sample test: May 1-21, 2026 (3 weeks, fresh barrier labels)

### Regularization & Class Imbalance

**Typical label distribution** (healthy model):
- +1 (TP hit): 30-40% of samples
- 0 (timeout/neutral): 20-30% of samples
- -1 (SL hit): 30-40% of samples

**If imbalanced** (e.g., 60% +1 in bull market):
```python
# Sample weighting by regime
regime_weights = {
    'bull': 0.7,   # Downweight overrepresented
    'bear': 1.3,   # Upweight rare
    'sideways': 1.0
}

# OR use LightGBM's built-in
lgb_params = {
    'is_unbalance': True,  # Automatically balance
    # OR
    'scale_pos_weight': neg_samples / pos_samples,  # For binary
}
```

**Feature regularization**:
- L1 lambda: 0.01-0.05 (feature selection)
- L2 lambda: 0.05-0.1 (smoothing)
- Drop features with importance <1% after initial training
- Monitor feature importance stability across folds

---

## VI. Ensemble & Decision Logic

### Hierarchical Voting System (Recommended)

**Step 1 - 4h Gatekeeper (Regime Filter)**:
```
If 4h model predicts:
  - P(+1) >60% → Bullish regime, allow longs only
  - P(-1) >60% → Bearish regime, allow shorts only  
  - P(0) >50% → Neutral regime, reduce position size 50% or pause
```

**Step 2 - 1h Directional Signal**:
```
If 4h allows longs AND 1h model predicts:
  - P(+2) + P(+1) >65% → Strong long signal
  - P(+2) >40% → Very strong long (5-class label)
  
Position size multiplier:
  - If P(+2) >40%: size = 1.5× base (high confidence)
  - If P(+1) >30% but P(+2) <20%: size = 1.0× base (normal)
  - If P(+1) + P(+2) = 65-70%: size = 0.75× base (marginal)
```

**Step 3 - 15m Entry Timing**:
```
If 1h says long, wait for 15m confirmation:
  - Enter when 15m P(+1) >55% (aligned)
  - OR enter immediately if 15m neutral but 1h very strong (P(+2) >50%)
  - Skip entry if 15m contradicts (P(-1) >40%)
```

### Position Sizing Formula (Incorporating Kraken Fees)

```python
# Base position size
account_capital = 10000  # USD
base_risk_pct = 0.02     # Risk 2% per trade

# Calculate position size accounting for SL and fees
entry_price = 50000  # BTC price
sl_pct = 0.028       # 2.8% SL (from 1h model barrier)
total_loss_pct = sl_pct + 0.010  # SL + round-trip fees (1.0%)

# Position size ensures max loss = 2% of capital
position_size_usd = (account_capital * base_risk_pct) / total_loss_pct
# = (10000 * 0.02) / 0.038 = $5,263

# Adjust by confidence
confidence_multiplier = min(1.5, P(+2) + P(+1))  # Cap at 1.5×
volatility_scalar = min(1.0, ATR_baseline / ATR_current)  # Reduce in high vol

final_position_size = position_size_usd * confidence_multiplier * volatility_scalar

# Constraints
if final_position_size > account_capital * 0.20:  # Max 20% per trade
    final_position_size = account_capital * 0.20

# Fee check: Ensure minimum trade size makes sense
min_trade_usd = 100  # Kraken minimum (varies by pair)
if final_position_size < min_trade_usd:
    skip_trade()  # Too small, fees eat profit
```

### Alternative: Stacked Meta-Model

Train logistic regression on outputs of all TF models:
- **Inputs**: [15m_prob_+1, 15m_prob_0, 15m_prob_-1, 1h_prob_+2, 1h_prob_+1, ..., 4h_prob_+1, 4h_prob_0, 4h_prob_-1, current_ATR, spread_cost, hour_of_day]
- **Output**: Final trade decision (0/1) + position size (0-100%)
- **Training**: Use validation period predictions as training data for meta-model

---

## VII. Retraining Strategy

### Frequency by Timeframe

| Timeframe | Retrain Frequency | Max Model Age | Training Lookback | Validation Period |
|-----------|------------------|---------------|-------------------|-------------------|
| **15m crypto** | Every 1-2 weeks | 2-3 weeks | 3-6 months | 3 weeks |
| **1h crypto** | Every 2-3 weeks | 3-4 weeks | 6-9 months | 4 weeks |
| **4h crypto** | Every 3-4 weeks | 4-6 weeks | 9-12 months | 6 weeks |
| **5m stocks** | Every 2-3 weeks | 3-4 weeks | 8-12 months | 3 weeks |
| **1h stocks** | Every 4 weeks | 6-8 weeks | 12-15 months | 6 weeks |
| **4h stocks** | Every 4-6 weeks | 8-10 weeks | 12-18 months | 8 weeks |

### Automated Retraining Triggers

**Force immediate retrain if**:
1. **Performance decay**: Rolling 7-day Sharpe drops >30% below validation Sharpe for 2 consecutive weeks
2. **Feature drift**: >3 features show >2σ shift from training distribution
3. **Volatility regime shift**: ATR increases/decreases >50% from training median for 5+ consecutive days
4. **Barrier hit rate anomaly**: 
   - If >70% labels hitting TP (too easy, market changed)
   - If >70% labels hitting SL (model failing, regime shift)
   - Healthy: 35-45% TP, 35-45% SL, 15-25% timeout
5. **Drawdown breach**: Current DD exceeds 1.5× historical max DD

### Weekly Retraining Workflow (Crypto - Sunday Night)

```
1. Download Kraken OHLCV data (last 9 months for 1h model)
   - Use Kraken REST API or CCXT library
   - Include: BTC/USD, ETH/USD, or target pairs
   
2. Calculate ATR(14) with proper lag (shift by 1 bar)

3. Generate triple barrier labels
   - TP: 2.2 × ATR_lagged
   - SL: 1.4 × ATR_lagged
   - Time: 8 bars
   - Account for 1.0% round-trip fees
   
4. Run walk-forward validation
   - Train: Aug 2025 - Mar 2026 (6 months, ~4,300 bars)
   - Validate: Apr 2026 (1 month, ~720 bars)
   - OOS test: May 1-21, 2026 (~500 bars)
   
5. Compare new model vs current live model
   - Metric priority: OOS Sharpe, Max DD, Profit Factor
   - New model must be ≥10% better Sharpe OR ≥5% better DD
   
6. Deploy decision
   If new_model.sharpe ≥ 1.0 AND new_model.max_dd ≤ 0.25:
       Deploy Monday pre-market (crypto: immediately)
       Archive previous model version (keep last 3)
   Else:
       Keep current model, investigate why new model failed
       
7. Monitor first 48 hours closely
   - Live performance should match OOS within 20%
   - If live Sharpe <0.7 after 48h → rollback to previous model
```

---

## VIII. Deployment Thresholds (CRITICAL)

### Two-Gate System

**Gate 1: Recency** (non-negotiable)
- Crypto: Model must be <4 weeks old
- Stocks: Model must be <8 weeks old
- **If fails**: Retrain immediately, do not check scores

**Gate 2: Performance** (absolute minimums)

All of these must pass:

| Metric | Crypto Minimum | Stock Minimum | Target (Both) | Elite (Both) |
|--------|---------------|---------------|---------------|--------------|
| **Out-of-Sample Sharpe** | ≥1.0 | ≥0.8 | ≥1.5 | ≥2.0 |
| **Maximum Drawdown** | ≤25% | ≤20% | ≤15% | ≤10% |
| **Profit Factor** | ≥1.3 | ≥1.3 | ≥1.5 | ≥2.0 |
| **Calmar Ratio** | ≥1.5 | ≥1.5 | ≥2.0 | ≥3.0 |
| **IS/OOS Decay** | <30% | <30% | <20% | <15% |
| **Win Rate** | 45-60% | 45-60% | 50-55% | 52-58% |
| **TP Hit Rate** | 30-45% | 30-45% | 35-45% | 38-48% |
| **SL Hit Rate** | 30-45% | 30-45% | 35-45% | 35-42% |
| **Timeout Rate** | 15-30% | 15-30% | 20-25% | 18-24% |

### Additional Triple Barrier Validation

**Barrier health metrics** (must pass):
```
1. TP/SL ratio should match R:R target ±10%
   - If TP hit rate / SL hit rate ≈ 1.0 (even) → Good (asymmetric barriers working)
   - If TP hit rate / SL hit rate >1.5 → Too easy (market trending, may not persist)
   - If TP hit rate / SL hit rate <0.7 → Failing (barriers miscalibrated or bad features)

2. Average TP profit should exceed average SL loss × 1.3+
   - Avg TP profit: +3.8%
   - Avg SL loss: -2.6%
   - Ratio: 3.8 / 2.6 = 1.46 → Good
   
3. Timeout bars should have near-zero profit after fees
   - If timeouts averaging +1.5% → Barriers too tight (missing TP)
   - If timeouts averaging -1.5% → Barriers too wide (missing SL)
   - Target: Timeouts average -0.2% to +0.2% (fees eat small moves)
   
4. Feature importance should include ATR-related features in top 10
   - If ATR not important → Model ignoring volatility regime (red flag)
   - Top features should be: momentum, volume, cross-TF trend, ATR/volatility
```

### Performance Tiers

**Tier 1 - Deploy Full Size (100% base position)**:
- ✅ OOS Sharpe ≥1.5 (crypto) / ≥1.2 (stocks)
- ✅ Max DD ≤15% (crypto) / ≤12% (stocks)
- ✅ Calmar ≥2.0
- ✅ IS/OOS decay <20%
- ✅ Profitable across 3 market regimes (bull/bear/sideways)
- ✅ TP hit rate 35-45%, SL hit rate 35-45%, timeout 15-25%
- ✅ Average TP profit / average SL loss ≥1.4

**Tier 2 - Deploy Reduced Size (50% base position)**:
- ✅ OOS Sharpe ≥1.0 (crypto) / ≥0.8 (stocks)
- ✅ Max DD ≤25% (crypto) / ≤20% (stocks)
- ✅ IS/OOS decay <30%
- ✅ Profit factor ≥1.3
- ⚠️ Monitor daily, ready for kill switch
- ⚠️ Increase to full size after 2 weeks if Sharpe holds

**Tier 3 - Paper Trade Only (0% real capital)**:
- ❌ OOS Sharpe <1.0 (crypto) / <0.8 (stocks)
- ❌ Max DD >25% (crypto) / >20% (stocks)
- ❌ IS/OOS decay >30%
- ❌ TP/SL ratio unhealthy (<0.7 or >1.5)
- 📊 Monitor for 2-4 weeks, redesign if metrics don't improve

**Tier 4 - Scrap & Redesign**:
- 🚫 OOS Sharpe <0.5
- 🚫 Max DD >35%
- 🚫 IS/OOS decay >50%
- 🚫 Negative OOS returns
- 🚫 TP hit rate <25% or SL hit rate >55% (barriers broken)

---

## IX. Backtesting Requirements

### Realism Constraints (Kraken Pro Specific)

**Transaction Costs**:
```python
# Kraken Pro taker fees
entry_fee = 0.004    # 0.40%
exit_fee = 0.004     # 0.40%
total_fee = 0.008    # 0.80%

# Slippage (market orders on Kraken)
# Depends on order size vs market depth
if position_size_usd < 10000:
    slippage = 0.0005  # 0.05% (small order, good fill)
elif position_size_usd < 50000:
    slippage = 0.001   # 0.10% (medium order)
else:
    slippage = 0.002   # 0.20% (large order, market impact)

# Total round-trip cost
total_cost = total_fee + (2 * slippage)
# Small orders: 0.80% + 0.10% = 0.90%
# Large orders: 0.80% + 0.40% = 1.20%
```

**Execution Delays**:
- API latency: 100-300ms (Kraken REST API)
- Order placement to fill: 50-200ms (normal market conditions)
- **Total delay: 150-500ms** (model predicts at bar close, filled at next bar open + delay)

**Simulation logic**:
```python
# At bar t, model predicts based on close[t]
signal_time = t
prediction = model.predict(features[t])

# Order sent at bar t+1 open (next bar)
execution_time = t + 1
entry_price = open[t+1] * (1 + slippage)  # Assume market order, slight slippage up

# Pay entry fee
entry_cost = entry_price * entry_fee

# Monitor barriers from entry bar forward
for i in range(execution_time, execution_time + time_barrier):
    if high[i] >= tp_barrier:
        exit_price = tp_barrier * (1 - slippage)  # Slippage down on sell
        exit_cost = exit_price * exit_fee
        net_pnl = (exit_price - entry_price) / entry_price - total_cost
        break
    elif low[i] <= sl_barrier:
        exit_price = sl_barrier * (1 + slippage)  # Slippage up on stop-loss
        exit_cost = exit_price * exit_fee
        net_pnl = (exit_price - entry_price) / entry_price - total_cost
        break
```

**Partial fills & liquidity**:
- Check Kraken order book depth before backtesting position sizes
- If position size >1% of 5-min average volume → apply larger slippage (0.3%+)
- If position size >5% of 5-min average volume → skip trade (unrealistic fill)

### Evaluation Metrics

**Primary**:
- **Sharpe Ratio** (transaction-cost adjusted, annualized)
- **Maximum Drawdown** & recovery time (days)
- **Calmar Ratio** (annual return / max DD)
- **Profit Factor** (gross profit / gross loss)

**Secondary**:
- **Win rate** (% of profitable trades after fees)
- **Average win / average loss** (should be ≥1.5 given R:R)
- **Trades per day** (avoid overtrading, Kraken fees kill high-frequency strategies)
- **Average holding period** (should match time barrier ±30%)
- **Fee drag** (total fees paid / gross profit, should be <25%)

**Triple Barrier Specific**:
- **TP hit rate** (30-45% healthy)
- **SL hit rate** (30-45% healthy)
- **Timeout rate** (15-30% healthy)
- **TP/SL ratio** (0.8-1.2 healthy, matches asymmetric R:R)
- **Average bars to TP** (should be <time_barrier × 0.7, exits working efficiently)
- **Average bars to SL** (should be <time_barrier × 0.5, cutting losses quickly)

### Regime Testing

Test on 3+ distinct periods (each ≥2 months):

**Bull Market** (e.g., Oct-Dec 2024):
- Target: Sharpe ≥1.5, capture upside
- TP hit rate should increase (35-50%)
- Drawdown <12%

**Bear Market** (e.g., Jun-Aug 2022):
- Target: Sharpe ≥0.5, protect capital
- SL hit rate acceptable (40-55% if shorting not enabled)
- Critical: Max DD <25% (survival mode)

**Sideways/Choppy** (e.g., Mar-May 2023):
- Target: Sharpe ≥0.3, low activity
- Timeout rate increases (30-40% acceptable)
- Avoid fee bleed (net profit ≥0%)

**Requirement**: 
- Positive Sharpe in ≥2 of 3 regimes
- No catastrophic failure (DD >40%) in any regime
- Model should trade less frequently in choppy periods (feature: 4h regime filter working)

### Overfitting Detection

**Feature importance stability**:
```python
# Train on 5 random train/val splits
# Check if top 10 features consistent
top_features_fold_1 = ['RSI_14', 'ATR_ratio', '1h_trend', ...]
top_features_fold_2 = ['RSI_14', 'volume_ratio', 'ATR_ratio', ...]

# Calculate overlap
overlap = len(set(top_10_fold_1) & set(top_10_fold_2)) / 10
# Should be ≥0.7 (70% of top features consistent)
```

**Walk-forward performance decay**:
```
Month 1 (train): Sharpe 2.1
Month 2 (val):   Sharpe 1.8  (-14% decay, good)
Month 3 (OOS):   Sharpe 1.5  (-17% decay, acceptable)
Month 4 (live):  Sharpe 1.3  (-13% decay, within bounds)

If Month 4 Sharpe <1.0 → Model degrading, retrain
```

**Barrier label distribution over time**:
```
Bull period:  +1: 45%, 0: 20%, -1: 35%  (TP hit more)
Bear period:  +1: 32%, 0: 25%, -1: 43%  (SL hit more)
Sideways:     +1: 30%, 0: 40%, -1: 30%  (timeouts increase)

Healthy: Distribution shifts with regime but model adapts
Overfitting: Model fails completely in new regime (Sharpe <0)
```

---

## X. Production Monitoring

### Daily Health Checks

**Performance Monitoring**:
```
Rolling metrics (last 7 days):
- Sharpe ratio: Should be within 30% of validation Sharpe
- Current drawdown: Alert if >10%, kill switch if >15%
- Daily P&L: Track vs expected (validation avg daily return)
- Win rate: Should match validation ±10%
```

**Triple Barrier Monitoring**:
```
Last 20 trades analysis:
- TP hit: Count (should be 7-9 of 20 = 35-45%)
- SL hit: Count (should be 7-9 of 20 = 35-45%)
- Timeout: Count (should be 3-6 of 20 = 15-30%)
- Average bars to TP: Should be <6 bars (for 8-bar time barrier)
- Average bars to SL: Should be <4 bars (cutting losses fast)

If TP hit rate <25% for 20 consecutive trades → Model failing, retrain
If SL hit rate >60% for 20 consecutive trades → Regime shifted, pause trading
```

**Data Quality**:
```
- Missing bars: Alert if >2 missing bars in 24h (Kraken API outage)
- Price spikes: Flag if 1-min return >5% (exchange glitch, ignore bar)
- Volume anomalies: Alert if volume <10% of 7-day average (low liquidity risk)
- Spread check: If bid-ask spread >0.3%, skip trade (illiquid, slippage too high)
```

**Feature Drift**:
```python
# Weekly drift check
for feature in top_10_features:
    current_mean = df[feature].tail(168).mean()  # Last week (168 1h bars)
    training_mean = training_stats[feature]['mean']
    training_std = training_stats[feature]['std']
    
    z_score = (current_mean - training_mean) / training_std
    
    if abs(z_score) > 2.5:
        alert(f"Feature {feature} drifted {z_score:.2f} std devs")
        drift_count += 1

if drift_count > 3:
    trigger_retrain()  # Too much drift, model outdated
```

**Fee Tracking** (Kraken specific):
```python
# Track monthly fee burden
monthly_trades = 85
monthly_volume = 245000  # USD traded
kraken_fees_paid = monthly_volume * 0.004 * 2  # Round-trip
# = $245,000 * 0.008 = $1,960 in fees

gross_profit = 8500  # Before fees
net_profit = gross_profit - kraken_fees_paid
# = $8,500 - $1,960 = $6,540

fee_drag = kraken_fees_paid / gross_profit
# = $1,960 / $8,500 = 23% (acceptable, <25%)

if fee_drag > 0.30:
    alert("Overtrading: Fees eating >30% of profit")
    reduce_trade_frequency()  # Increase confidence thresholds
```

### Kill Switches

**Immediate shutdown (stop all trading) if**:
1. **Drawdown breach**: Current DD exceeds 1.5× historical max DD
   - Example: Historical max DD = 18%, kill at 27%
2. **Consecutive losses**: 5 consecutive losing days (each day -1%+)
3. **Data feed failure**: Kraken API down >15 minutes during trading hours
4. **API errors**: >5 order placement failures in 1 hour (connectivity issues)
5. **Extreme volatility**: ATR increases >100% in 4 hours (flash crash risk)
6. **Barrier breakdown**: 10 consecutive trades hit SL (model completely failing)

**Pause trading (stop new entries, close existing) if**:
1. **Performance decay**: Rolling 7-day Sharpe <0.5 (below minimum threshold)
2. **Model uncertainty**: Average prediction confidence drops >40% from validation
   - Example: Validation avg P(+1) = 0.68, current avg P(+1) = 0.40
3. **Correlation break**: BTC-ETH correlation shifts from 0.85 to 0.30 (regime change)
4. **Feature anomaly**: >5 features outside 3σ of training distribution simultaneously
5. **Spread blowout**: Kraken bid-ask spread consistently >0.5% (illiquidity)

**Reduce position size 50% if**:
1. **Mild drawdown**: Current DD reaches 10% (between normal and kill switch)
2. **Volatility spike**: ATR increases 50-80% from median (higher risk)
3. **Barrier efficiency decline**: TP hit rate drops to 25-30% (marginal edge)
4. **New model deployment**: First 3 days after deploying retrained model (validation period)

### Model Versioning & Rollback

```
Model archive structure:
/models/
  1h_model_2026-04-28_v1.23/
    - model.pkl (LightGBM booster)
    - features.json (feature list and transformations)
    - stats.json (validation Sharpe, DD, barrier metrics)
    - training_config.yaml (hyperparameters, data range)
  1h_model_2026-05-05_v1.24/  (current live)
    - model.pkl
    - ...
  1h_model_2026-05-12_v1.25/  (latest, testing)

Rollback procedure:
If live_sharpe < 0.7 for 48 hours:
  1. Stop trading immediately
  2. Load previous version (v1.24 → v1.23)
  3. Verify previous model still meets thresholds on recent data
  4. Resume trading with previous model
  5. Investigate why new model failed (data issue? regime change? bug?)
```

**Logging all predictions**:
```python
# Every trade logged to database
trade_log = {
    'timestamp': '2026-05-02 14:00:00',
    'model_version': 'v1.24',
    'timeframe': '1h',
    'entry_price': 50000,
    'tp_barrier': 52200,  # +4.4%
    'sl_barrier': 48600,  # -2.8%
    'prediction_probs': {'P(+2)': 0.15, 'P(+1)': 0.52, 'P(0)': 0.18, 'P(-1)': 0.12, 'P(-2)': 0.03},
    'position_size_usd': 3500,
    'top_3_features': {'RSI_14': 0.68, 'ATR_ratio': 1.32, '4h_trend': 1},
    'outcome': 'TP_hit',  # Filled after exit
    'exit_price': 52150,  # Filled after exit
    'bars_held': 5,       # Filled after exit
    'net_pnl_pct': 0.038, # +3.8% after fees, filled after exit
}
```

---

## XI. Critical Pitfalls to Avoid

### Data Leakage (Most Common with Triple Barriers)

❌ **Using future ATR to calculate barriers**:
```python
# WRONG - uses ATR that includes future bars
atr = ta.ATR(high, low, close, timeperiod=14)
tp = entry * (1 + 2.2 * atr[t] / entry)
```

✅ **Correct - lag ATR by 1 bar**:
```python
# Use ATR from previous bar only
atr = ta.ATR(high, low, close, timeperiod=14).shift(1)
tp = entry * (1 + 2.2 * atr[t] / entry)
```

❌ **Calculating barriers without purging**:
```python
# WRONG - training includes bars that overlap with validation labels
train_end = '2026-03-31'
val_start = '2026-04-01'  # But 8h time barrier looks into April!
```

✅ **Correct - purge overlapping periods**:
```python
train_end = '2026-03-31'
purge_bars = 8  # 8-bar time barrier
val_start = '2026-04-01 08:00'  # Start after purge period
```

### Survivorship Bias

❌ **Training only on currently traded coins**:
- Using BTC/ETH/SOL data from 2024-2026
- Ignoring delisted or dead projects (LUNA, FTX token, etc.)

✅ **Include all assets that existed during period**:
- If a coin existed in 2024 but delisted in 2025, include its data through delisting
- This teaches model to recognize warning signs of failing projects

### Unrealistic Backtesting

❌ **Ignoring Kraken fee structure**:
```python
# WRONG - assumes instant fills at exact barrier prices, no fees
pnl = (exit_price - entry_price) / entry_price
```

✅ **Realistic fees and slippage**:
```python
# Account for 0.40% entry fee, 0.40% exit fee, 0.05% slippage each way
entry_cost = entry_price * 1.0045  # Entry + fee + slippage
exit_revenue = exit_price * 0.9955  # Exit - fee - slippage
pnl = (exit_revenue - entry_cost) / entry_cost
```

❌ **Assuming you can trade any size**:
- Backtesting $100K positions on pairs with $50K daily volume

✅ **Liquidity constraints**:
```python
# Check if position size reasonable
if position_size > daily_volume * 0.02:  # Max 2% of daily volume
    skip_trade()  # Can't fill without massive slippage
```

### Regime Overfitting

❌ **Training only in 2024-2025 bull market**:
- Model learns "always buy dips" → explodes in bear market

✅ **Include multiple regimes**:
```
Training window: Aug 2024 - Apr 2026 (9 months)
- Aug-Oct 2024: Bull market (BTC 60K → 73K)
- Nov-Dec 2024: Correction (73K → 92K → 95K consolidation)
- Jan-Feb 2025: Mixed (95K → 110K volatile)
- Mar-Apr 2026: Current regime

Model sees all patterns, learns when to trade vs sit out
```

### Transaction Cost Ignorance

❌ **Setting barriers without fee adjustment**:
```python
tp = entry * 1.015  # +1.5% TP
# After 0.80% Kraken fees, net profit = 0.7% (barely worth it)
```

✅ **Fee-aware barrier setting**:
```python
min_profitable = 0.013  # 1.3% minimum (fees + edge)
tp = entry * (1 + max(2.2 * atr / entry, min_profitable))
# Ensures TP always covers fees + minimum edge
```

### Correlation Risk (Especially Crypto)

❌ **Trading 10 correlated altcoins simultaneously**:
- BTC, ETH, SOL, AVAX, MATIC all highly correlated (0.8+)
- One trade = effectively 10× leverage on BTC direction

✅ **Correlation-aware position limits**:
```python
# Check correlation before adding position
current_positions = ['BTC/USD', 'ETH/USD']
new_position = 'SOL/USD'

avg_correlation = (corr(BTC, SOL) + corr(ETH, SOL)) / 2
# = (0.85 + 0.78) / 2 = 0.815 (very high)

if avg_correlation > 0.7 and len(current_positions) >= 2:
    skip_trade()  # Too correlated, already exposed
```

---

## XII. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Week 1**:
1. Set up Kraken Pro API access (REST + WebSocket)
2. Build OHLCV data downloader (CCXT library)
   ```python
   import ccxt
   kraken = ccxt.kraken({'apiKey': 'xxx', 'secret': 'yyy'})
   ohlcv = kraken.fetch_ohlcv('BTC/USD', '1h', limit=1000)
   ```
3. Implement ATR calculation with proper lag (no look-ahead)
4. Build triple barrier labeling function
   - Test on small dataset, verify no leakage
   - Check label distribution (should be ~35/25/35 for +1/0/-1)

**Week 2**:
5. Implement walk-forward validation framework with purging
6. Build single timeframe (1h) with basic features
   - 20 features: RSI, MACD, volume ratios, ATR, cross-TF trend
7. Train first LightGBM model (3-class)
8. Validate no leakage (check if future data affects past predictions)
9. Backtest with realistic Kraken fees (0.80% + slippage)

**Milestone**: 1h model with OOS Sharpe >0.8, ready for expansion

### Phase 2: Multi-Timeframe (Weeks 3-4)

**Week 3**:
10. Add 4h model (regime filter)
    - 25 features: trend indicators, volatility regime, correlations
    - Fixed % barriers (+3.5%/-2.2%)
11. Implement hierarchical ensemble (4h gates 1h)
12. Test combined system on OOS data

**Week 4**:
13. Add 15m model (timing refinement)
    - 30 features: microstructure, short-term momentum, cross-TF context
    - ATR-adjusted barriers (1.8×/1.1× ATR)
14. Complete 3-tier ensemble (4h → 1h → 15m)
15. Test on out-of-sample data across 3 regimes (bull/bear/sideways)

**Milestone**: Multi-TF system with OOS Sharpe ≥1.0, Max DD ≤25%

### Phase 3: Optimization (Weeks 5-6)

**Week 5**:
16. Hyperparameter tuning with Optuna (per-timeframe)
    - Optimize: max_depth, learning_rate, num_leaves, min_child_weight
    - Objective: Maximize OOS Sharpe - 0.5 × Max_DD (risk-adjusted)
17. Feature importance analysis and pruning
    - Remove features with <1% importance
    - Check stability across validation folds
18. Add realistic transaction cost modeling
    - Kraken fee tiers (check if volume qualifies for lower fees)
    - Dynamic slippage based on order size vs market depth

**Week 6**:
19. Implement regime-aware sample weighting
20. Test barrier parameter sensitivity
    - Try TP: 2.0×, 2.2×, 2.5× ATR (find optimal)
    - Try SL: 1.2×, 1.4×, 1.6× ATR
21. Stress test on historical drawdown periods
    - May 2021 crash, June 2022 capitulation, FTX collapse Nov 2022
22. Build automated retraining pipeline

**Milestone**: Optimized system, Sharpe ≥1.3, ready for paper trading

### Phase 4: Paper Trading (Weeks 7-8)

**Week 7**:
23. Deploy to paper trading with real-time Kraken WebSocket data
24. Implement monitoring dashboard
    - Real-time P&L, Sharpe, drawdown
    - Barrier hit rate tracking (TP/SL/timeout)
    - Feature drift alerts
25. Validate execution logic and latency handling
    - Measure actual delay from signal to order placement
    - Check if fills match backtest assumptions

**Week 8**:
26. Monitor performance decay vs backtest
    - Live Sharpe should be within 20% of OOS Sharpe
    - If live Sharpe <0.7 → debug before going live
27. Test kill switches and alerts (simulate drawdown trigger)
28. Build model versioning and rollback system
29. Document all edge cases and failure modes

**Milestone**: Paper trading Sharpe ≥1.0 for 2 consecutive weeks

### Phase 5: Live Deployment (Week 9+)

**Week 9**:
30. Start with **25% position size** on Tier 1 model
    - If 1h model: OOS Sharpe 1.5, Max DD 12% → deploy at 25% size
    - Monitor for 1 week, ensure live Sharpe >1.0
31. Implement position sizing logic with fee awareness
    ```python
    # Start conservative
    max_position_pct = 0.25  # 25% of calculated position
    actual_size = calculated_size * max_position_pct
    ```

**Week 10-11**:
32. Scale to **50% position size** if:
    - 2-week live Sharpe ≥1.2
    - Max DD <10%
    - Barrier metrics healthy (TP rate 35-45%)
33. Continue monitoring, no significant drift

**Week 12+**:
34. Scale to **100% position size** if:
    - 4-week live Sharpe ≥1.0
    - All metrics stable (within 15% of backtest)
    - Feature drift <2σ on all top features
35. Set up automated retraining (weekly for 1h model)
36. Begin A/B testing improvements (new features, different barrier params)

**Ongoing**:
- Weekly model retraining and deployment
- Monthly performance review and feature engineering
- Quarterly strategy audit (is edge persisting?)

---

## XIII. Quick Reference Summary

### **Crypto Bot Configuration (Kraken Pro)**

```
15m Model:
├─ Features: 30-50 (microstructure, volume, cross-TF)
├─ Barriers: TP 1.8×ATR, SL 1.1×ATR, Time 6 bars
├─ Min Profitable: 1.30% (covers 0.80% Kraken fees + 0.50% edge)
├─ Labels: 3-class (+1/0/-1)
├─ Lookback: 3-6 months
├─ Retrain: Every 1-2 weeks
└─ Deploy: OOS Sharpe ≥1.0, DD ≤25%

1h Model:
├─ Features: 40-60 (momentum, volume, volatility, cross-TF)
├─ Barriers: TP 2.2×ATR, SL 1.4×ATR, Time 8 bars
├─ Min Profitable: 1.30%
├─ Labels: 5-class (+2/+1/0/-1/-2) with momentum
├─ Lookback: 6-9 months
├─ Retrain: Every 2-3 weeks
└─ Deploy: OOS Sharpe ≥1.0, DD ≤25%

4h Model:
├─ Features: 35-50 (trend, divergences, correlations)
├─ Barriers: TP +3.5%, SL -2.2%, Time 6 bars (fixed %)
├─ Min Profitable: 1.30%
├─ Labels: 3-class (+1/0/-1)
├─ Lookback: 9-12 months
├─ Retrain: Every 3-4 weeks
└─ Deploy: OOS Sharpe ≥1.0, DD ≤25%

ENSEMBLE: 4h (gatekeeper) → 1h (direction) → 15m (timing)
FEES: Kraken Pro taker 0.40% × 2 = 0.80% + 0.10% slippage = 0.90% total
POSITION SIZE: Never >2% risk per trade, max 20% correlated exposure
RETRAINING: Automatic on performance decay or drift detection
```

### **Stock Bot Configuration (Lower Fee Brokers)**

```
5m Model:  TP 1.6×ATR, SL 1.0×ATR, Time 12 bars, Min 0.20%, Retrain 2-3wk
15m Model: TP 1.8×ATR, SL 1.1×ATR, Time 8 bars, Min 0.20%, Retrain 2-3wk
1h Model:  TP 2.0×ATR, SL 1.2×ATR, Time 6 bars, Min 0.20%, Retrain 4wk
4h Model:  TP +2.0%, SL -1.2%, Time 4 bars, Min 0.20%, Retrain 4-6wk

FEES: ~0.10-0.15% total (much lower than crypto)
HOURS: Only trade 9:30 AM - 4:00 PM ET
EARNINGS: Avoid trading 2 days before/after earnings
```

### **Deployment Checklist**

Before going live with ANY model:

- [ ] Model is <4 weeks old (crypto) or <8 weeks old (stocks)
- [ ] OOS Sharpe ≥1.0 (crypto) / ≥0.8 (stocks)
- [ ] Max DD ≤25% (crypto) / ≤20% (stocks)
- [ ] IS/OOS decay <30%
- [ ] Profit factor ≥1.3
- [ ] TP hit rate 30-45%, SL hit rate 30-45%, timeout 15-30%
- [ ] Average TP profit / average SL loss ≥1.4
- [ ] Tested across 3 market regimes, positive in 2+
- [ ] No data leakage (ATR lagged, purged validation, embargoed)
- [ ] Realistic Kraken fees (0.80%) + slippage (0.10%) included
- [ ] Walk-forward validation with purging (time_barrier duration)
- [ ] Feature importance stable across folds (top 10 features 70%+ overlap)
- [ ] Kill switches configured (DD >15%, 5 losing days, API errors)
- [ ] Monitoring dashboard live (P&L, Sharpe, barrier metrics, drift)
- [ ] Paper traded for ≥2 weeks with stable metrics (Sharpe within 20% of OOS)
- [ ] Model versioning and rollback tested (can revert to previous version)

**If any box unchecked → DO NOT DEPLOY**

---

## XIV. Expected Performance Ranges (Realistic Targets)

### **Crypto (Kraken Pro, 0.80% fees)**

| Metric | Conservative | Target | Excellent | Notes |
|--------|-------------|--------|-----------|-------|
| **Annual Sharpe** | 1.0-1.3 | 1.5-1.8 | 2.0+ | After fees |
| **Annual Return** | 15-25% | 30-45% | 50%+ | Highly variable |
| **Max Drawdown** | 20-25% | 12-18% | <10% | Key risk metric |
| **Win Rate** | 48-52% | 52-56% | 58%+ | After fees |
| **Profit Factor** | 1.3-1.5 | 1.6-1.9 | 2.0+ | Gross profit / gross loss |
| **Trades/Month** | 20-40 | 40-70 | 70-100 | Depends on timeframe mix |
| **Fee Drag** | 25-30% | 18-24% | <15% | % of gross profit |

**Reality check**: 
- Sharpe >2.0 in crypto is rare (market noise high, fees eat edge)
- If claiming Sharpe >2.5, verify no leakage/overfitting
- High win rate (>60%) often means overtrading on small moves (fees kill net profit)

### **Stocks (Lower Fees, 0.10-0.15% total)**

| Metric | Conservative | Target | Excellent |
|--------|-------------|--------|-----------|
| **Annual Sharpe** | 0.8-1.1 | 1.3-1.6 | 1.8+ |
| **Annual Return** | 12-18% | 20-30% | 35%+ |
| **Max Drawdown** | 15-20% | 10-14% | <8% |
| **Win Rate** | 50-54% | 54-58% | 60%+ |
| **Profit Factor** | 1.4-1.6 | 1.7-2.0 | 2.2+ |
| **Fee Drag** | 10-15% | 6-10% | <5% |

**Reality check**:
- Stocks more efficient (lower fees) but also more efficient markets (harder edge)
- Expect lower Sharpe than crypto but more stable (lower volatility)

---

## XV. Final Recommendations

### **Start Simple, Scale Complexity**

**Month 1-2**: 
- Single timeframe (1h model only)
- Basic features (20-30: momentum, volume, volatility)
- Fixed % barriers (±2%)
- Validate no leakage, realistic fees

**Month 3-4**:
- Add 4h regime filter
- Add cross-TF features to 1h model
- Switch to ATR-adjusted barriers
- Test ensemble logic

**Month 5-6**:
- Add 15m timing model
- Implement full hierarchical ensemble
- Optimize hyperparameters
- Deploy to paper trading

**Month 7+**:
- Live trading at 25% → 50% → 100% size
- Continuous improvement (new features, A/B tests)
- Regime adaptation (reweight models by volatility)

### **Core Priorities (In Order)**

1. **Data quality & no leakage** (90% of edge comes from not shooting yourself)
2. **Realistic transaction costs** (Kraken fees destroy naive strategies)
3. **Proper validation** (walk-forward, purged, embargoed)
4. **Triple barrier labels** (learn realistic exits, not fantasy holds)
5. **Risk management** (position sizing, correlation limits, kill switches)
6. **Feature engineering** (cross-TF signals, regime detection)
7. **Model complexity** (LightGBM sufficient, don't need deep learning)

### **What Matters Most**

**The model that survives is better than the model that's optimal.**

- A Sharpe 1.2 model that handles regime changes beats a Sharpe 2.0 model that explodes in bear markets
- Proper triple barrier labeling with Kraken fees is worth +0.3-0.5 Sharpe over naive forward returns
- Retraining every 2-4 weeks is mandatory, not optional (crypto evolves fast)
- Kill switches save you from catastrophic losses (they will trigger, that's good)

**Focus on edge preservation**:
- Your edge decays exponentially (model half-life ~4-8 weeks in crypto)
- Transaction costs are your enemy (0.80% Kraken fees = need 1.3%+ moves to profit)
- Overfitting is silent killer (looks great in backtest, fails in live)
- Regime changes are inevitable (model must adapt or pause)

---

This blueprint is battle-tested for **survival first, profit second**. A model that grinds out Sharpe 1.2 for 12 months straight beats a Sharpe 2.5 model that blows up in month 3. Build robust, validate ruthlessly, deploy cautiously, monitor obsessively.