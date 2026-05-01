# Stock Master Phase Checklist

This document is the authoritative roadmap for adding stocks to AI-Quant. It is ordered by dependency and must remain append-only with checkmarks unless Christian explicitly approves a structural change.

Stocks and crypto must stay separated. Stocks are event-driven, screened-universe, multi-strategy, and support long plus conditional short logic. Crypto remains fixed-universe, spot-only, long-only, and macro-sentiment driven.

---

# Checklist Integrity Rules

GPT **IS allowed** to:

* Mark items as `[x]` when completed
* Add sub-bullets inside a slice for clarity
* Add implementation notes under a slice

GPT **IS NOT allowed** to:

* Delete any existing phases
* Delete any existing slices
* Rename phases without explicit instruction
* Collapse multiple phases into one
* Skip phases out of order
* Modify previous completed phase definitions retroactively

If something changes later:

* Add a note under the phase
* Do not rewrite history

This checklist is append-only with checkmarks.

---

# Phase Ordering

```text
S1 Guardrails
→ S2 Schema
→ S3 Providers
→ S4 Universe
→ S5 Candles
→ S6 News
→ S7 Congress
→ S8 Insiders
→ S9 Strategy Engine
→ S10 Watchlist
→ S11 ML Inputs
→ S12 ML Training
→ S13 Prediction Persistence
→ S14 Final Decision Engine
→ S15 Paper Ledger
→ S16 Risk
→ S17 Runtime
→ S18 Frontend
→ S19 Backtesting
→ S20 Live Execution
```

---

## Phase S1 — Stock Scope & Guardrails

### Goal

Define stock behavior, constraints, and separation from crypto before building schema, workers, UI, ML, runtime logic, or execution logic.

### Rules

* [x] Stocks are a separate asset lane from crypto
* [x] Crypto remains spot-only / long-only with no shorting under any condition
* [x] Stock shorts allowed only when stock cash > $2,500
* [x] Stocks use independent strategy weights, not crypto weights
* [x] Stocks use their own watchlist, not the crypto universe
* [x] Stocks use their own runtime workers
* [x] Stocks respect U.S. market hours in Eastern Time
* [x] Stock positions must have `max_hold_hours` frozen at entry
* [x] Congress signals are context only, not direct triggers
* [x] Insider signals are supporting signals, not triggers
* [x] ML is a confidence modifier, not a trade authority
* [x] ML cannot extend hold time
* [x] ML cannot override hard risk rules
* [x] Each stock trade must map to a specific strategy type
* [x] Strategy must define entry logic
* [x] Strategy must define invalidation
* [x] Strategy must define exit conditions
* [x] Strategy must define max hold time
* [x] No global-score-only decision making allowed

### Must happen before

* Stock schema
* Stock screening
* Stock strategies
* Stock ML
* Stock paper trading
* Stock runtime workers
* Stock frontend pages

### Exit Criteria

* [x] Existing `docs/Stock_Master_Phase_Checklist.md` updated
* [x] Phase S1 guardrails completed/checked off as appropriate
* [x] No future slices/phases deleted
* [x] No backend/frontend code changes made

### Implementation Notes

* Phase S1 is planning-only.
* Do not touch backend code, frontend code, DB models, migrations, workers, runtime logic, or providers in this phase.
* Validation still runs backend quality gates to prove the planning-only patch did not introduce code drift.

---

## Phase S2 — Stock Schema & Persistence

### Goal

Create the database foundation for stocks without contaminating crypto schema behavior.

### Backend

* [ ] Add stock universe table
* [ ] Add stock watchlist table
* [ ] Add stock research snapshot table
* [ ] Add stock news articles table
* [ ] Add stock congress trades table
* [ ] Add stock insider trades table
* [ ] Add stock strategy scores table
* [ ] Add stock ML prediction persistence
* [ ] Add stock paper ledger fields for long/short positions
* [ ] Add Alembic migration

### Must happen before

* Any worker persistence
* Watchlist promotion
* ML prediction display
* Paper trading durability

---

## Phase S3 — Stock Provider Boundaries

### Goal

Decide which data provider owns each stock job and isolate provider failures.

### Provider roles

* [ ] Alpaca = historical stock candles for ML/backtesting
* [ ] Tradier = live quotes
* [ ] Tradier = active stock watchlist intraday candles
* [ ] SEC = insider/Form 4 data
* [ ] Congress source/API = congressional filings
* [ ] News/RSS/API = article ingestion
* [ ] Optional later: earnings/analyst provider

### Backend

* [ ] Add stock provider config
* [ ] Add provider health checks
* [ ] Add symbol normalization rules
* [ ] Add failure logging per provider

### Must happen before

* Stock workers
* Stock screening
* ML training
* Runtime trading

---

## Phase S4 — Stock Universe & Screening Foundation

### Goal

Build the raw stock pool before deciding what deserves attention.

### Universe tiers

* [ ] S&P 500
* [ ] Nasdaq 100
* [ ] High-volume liquid stocks
* [ ] Manual/user-added symbols
* [ ] Event-driven candidates

### Screening filters

* [ ] Price filter
* [ ] Dollar-volume filter
* [ ] Liquidity filter
* [ ] Spread filter
* [ ] Halt/exclusion filter
* [ ] Tradier tradability check
* [ ] Earnings danger window placeholder
* [ ] Sector classification

### Must happen before

* Watchlist promotion
* Stock research page
* Strategy scoring

---

## Phase S5 — Stock Candle Workers

### Goal

Fetch stock candles cleanly without polluting crypto candle logic.

### Workers

* [ ] Stock daily ML candle worker
* [ ] Stock intraday active-watchlist candle scheduler
* [ ] Stock intraday candle sync task
* [ ] Stock quote snapshot worker
* [ ] Stock market-session gate
* [ ] Post-close daily sync

### Rules

* [ ] Historical ML candles use `usage="ml"`
* [ ] Trading candles use `usage="trading"`
* [ ] Intraday candles only fetch active watchlist symbols
* [ ] No full-market intraday scanning
* [ ] Closed candles only, delayed after candle close

### Must happen before

* Stock ML
* Live prediction freshness
* Runtime stock signals

---

## Phase S6 — Stock News Pipeline

### Goal

Add company-specific catalyst detection.

### Backend

* [ ] Add stock news fetch worker
* [ ] Deduplicate articles
* [ ] Map articles to stock symbols
* [ ] Score sentiment
* [ ] Classify catalyst type
* [ ] Store article count and source count
* [ ] Generate daily stock news sentiment features

### Catalyst types

* [ ] Earnings
* [ ] Guidance
* [ ] Analyst upgrade/downgrade
* [ ] FDA/regulatory
* [ ] Lawsuit
* [ ] M&A
* [ ] Executive change
* [ ] Product launch
* [ ] SEC investigation
* [ ] Sector macro news

### Must happen before

* News catalyst strategy
* Stock ML news features
* Watchlist catalyst badges

---

## Phase S7 — Congress Filing Pipeline

### Goal

Use congressional filings with filing-lag decay as context, not direct triggers.

### Backend

* [ ] Ingest congressional trades
* [ ] Store trade date
* [ ] Store disclosure date
* [ ] Calculate filing lag days
* [ ] Classify buy/sell
* [ ] Score amount range
* [ ] Add freshness decay
* [ ] Add committee relevance placeholder
* [ ] Add repeat-buyer detection

### Rules

* [ ] 0–7 days = fresh signal
* [ ] 8–30 days = reduced signal
* [ ] 31–45 days = weak context
* [ ] 46+ days = historical context only
* [ ] Never use stale filing as direct trade trigger

### Must happen before

* Congress accumulation strategy
* Congress watchlist badges
* Congress ML features

---

## Phase S8 — Insider Buy Pipeline

### Goal

Use SEC Form 4 data for slow accumulation signals.

### Backend

* [ ] Ingest Form 4 insider trades
* [ ] Identify open-market purchases
* [ ] Separate buys from sales
* [ ] Detect CEO/CFO/director role
* [ ] Detect cluster buying
* [ ] Score transaction size
* [ ] Downweight planned/scheduled sales
* [ ] Store insider accumulation score

### Rules

* [ ] Insider buys can support long setups
* [ ] Insider selling alone is not a short trigger
* [ ] Cluster buying > single buyer
* [ ] CEO/CFO buy > director buy

### Must happen before

* Insider accumulation strategy
* Insider ML features
* Watchlist insider badges

---

## Phase S9 — Stock Strategy Engine

### Goal

Score each stock by actual strategy fit, not one giant soup score.

### Strategy modules

* [ ] Trend continuation long
* [ ] Breakout + retest long
* [ ] News catalyst momentum
* [ ] Breakdown short
* [ ] Earnings drift long
* [ ] Insider accumulation long
* [ ] Congress accumulation long
* [ ] Mean reversion long

### Required strategy contract

* [ ] Entry logic
* [ ] Invalidation
* [ ] Exit conditions
* [ ] Max hold time
* [ ] Direction
* [ ] Risk flags

### Outputs

* [ ] Strategy fit score
* [ ] Selected strategy
* [ ] Direction
* [ ] Entry thesis
* [ ] Invalidation level
* [ ] Suggested max hold
* [ ] Risk flags

### Must happen before

* Watchlist promotion
* Stock trade decisions
* Stock paper trading

---

## Phase S10 — Stock Watchlist Promotion

### Goal

Turn screened candidates into active monitored symbols.

### Backend

* [ ] Add watchlist promotion engine
* [ ] Add demotion engine
* [ ] Add reason tracking
* [ ] Add catalyst badges
* [ ] Add strategy-fit summary
* [ ] Add max watchlist size
* [ ] Add sector concentration limits
* [ ] Add stale candidate cleanup

### Promotion gates

* [ ] Liquidity pass
* [ ] Strategy score pass
* [ ] Risk score acceptable
* [ ] Has catalyst, technical setup, or ML edge
* [ ] Not overexposed by sector

### Must happen before

* Active stock runtime
* Intraday stock candle fetching
* Stock prediction table

---

## Phase S11 — Stock ML Training Inputs

### Goal

Build stock-specific ML features.

### Features

* [ ] Price returns
* [ ] ATR / volatility
* [ ] Volume surge
* [ ] Relative volume
* [ ] RSI / MACD
* [ ] Moving-average structure
* [ ] SPY/QQQ regime
* [ ] Sector ETF trend
* [ ] Relative strength vs SPY
* [ ] News sentiment
* [ ] Congress score
* [ ] Insider score
* [ ] Earnings proximity
* [ ] Strategy fit scores

### Must happen before

* Stock ML training
* Stock prediction persistence

---

## Phase S12 — Stock ML Labels & Training

### Goal

Train stock models on trade-like outcomes.

### Labels

* [ ] Triple-barrier long labels
* [ ] Triple-barrier short labels
* [ ] Profit target hit first
* [ ] Stop hit first
* [ ] Timeout
* [ ] Max favorable excursion
* [ ] Max adverse excursion

### Models

* [ ] Stock long model
* [ ] Stock short model
* [ ] Stock gap-risk model
* [ ] Stock watchlist promotion model

### Rules

* [ ] ML modifies confidence
* [ ] ML does not override hard risk gates
* [ ] ML does not extend max hold time
* [ ] Short model only usable when stock cash > $2,500

### Must happen before

* ML-backed stock trade decisions
* Stock ML page

---

## Phase S13 — Stock Prediction Persistence

### Goal

Persist stock predictions so UI loads fast.

### Backend

* [ ] Persist latest stock predictions
* [ ] Add stock prediction API endpoint
* [ ] Add freshness gate
* [ ] Add model version tracking
* [ ] Add feature snapshot hash
* [ ] Add local explanation placeholder
* [ ] Add stale prediction handling

### Must happen before

* Stock ML frontend
* Runtime trade decisions
* Watchlist confidence display

---

## Phase S14 — Stock Final Decision Engine

### Goal

Convert strategy + ML + risk into final actions.

### Actions

* [ ] ALLOW_LONG
* [ ] ALLOW_SHORT
* [ ] WATCH
* [ ] BLOCK
* [ ] NO_TRADE

### Rules

* [ ] Longs require valid long strategy
* [ ] Shorts require valid short strategy
* [ ] Shorts require stock cash > $2,500
* [ ] Shorts require liquidity/squeeze filters
* [ ] Earnings danger window can block trades
* [ ] ML confidence can reduce/block, not force a trade
* [ ] Congress/insider can support, not command
* [ ] No global-score-only decisions

### Must happen before

* Stock paper trading
* Stock runtime execution

---

## Phase S15 — Stock Paper Ledger Durability

### Goal

Make stock paper trading survive restart.

### Backend

* [ ] Persist stock cash
* [ ] Persist long positions
* [ ] Persist short positions
* [ ] Persist fills
* [ ] Persist realized PnL
* [ ] Persist unrealized PnL
* [ ] Restore on startup
* [ ] Track strategy type
* [ ] Track max hold hours
* [ ] Track time decay
* [ ] Track exit reason

### Must happen before

* Runtime stock trading
* Frontend ledger page

---

## Phase S16 — Stock Risk Management

### Goal

Prevent the bot from turning into a confetti cannon.

### Risk rules

* [ ] Max stock positions
* [ ] Max sector exposure
* [ ] Max symbol exposure
* [ ] Max daily loss
* [ ] Max weekly loss
* [ ] ATR-based sizing
* [ ] Strategy-based sizing
* [ ] Time-decay exits
* [ ] Hard stop required
* [ ] Short squeeze filter
* [ ] Earnings risk filter

### Must happen before

* Runtime execution
* Live/paper automation

---

## Phase S17 — Stock Runtime Workers

### Goal

Run stock decisions safely during market hours.

### Runtime

* [ ] Stock runtime scheduler
* [ ] Market open/close awareness
* [ ] Active watchlist quote refresh
* [ ] Active watchlist candle refresh
* [ ] Prediction refresh
* [ ] Decision refresh
* [ ] Paper fill simulation
* [ ] Exit monitor
* [ ] Worker heartbeat events

### Must happen before

* Live Tradier execution
* Automated stock paper trading

---

## Phase S18 — Stock Frontend Pages

### Goal

Make stock behavior visible without cluttering crypto pages.

### Pages

* [ ] Stock Research
* [ ] Stock Watchlist
* [ ] Stock ML
* [ ] Stock Runtime
* [ ] Stock Paper Ledger
* [ ] Stock Signals

### UI elements

* [ ] Selected strategy
* [ ] Final action
* [ ] Why added to watchlist
* [ ] News catalyst badge
* [ ] Congress badge
* [ ] Insider badge
* [ ] ML confidence
* [ ] Risk flags
* [ ] Max hold timer
* [ ] Position exit reason

### Must happen before

* Operator confidence
* Live execution

---

## Phase S19 — Backtesting & Forward Testing

### Goal

Prove stock strategies before trusting them.

### Backend

* [ ] Strategy-level backtest
* [ ] Long-only stock backtest
* [ ] Short-only stock backtest
* [ ] Mixed stock strategy backtest
* [ ] Watchlist promotion backtest
* [ ] Congress/insider feature ablation
* [ ] News catalyst feature ablation
* [ ] Paper-vs-hypothetical comparison

### Must happen before

* Live stock trading

---

## Phase S20 — Tradier Live Execution

### Goal

Only after paper trading proves stable.

### Backend

* [ ] Tradier order adapter
* [ ] Account sync
* [ ] Position sync
* [ ] Buying power sync
* [ ] Order status reconciliation
* [ ] Partial fill handling
* [ ] Cancel/replace flow
* [ ] Emergency kill switch
* [ ] Manual confirmation mode
* [ ] Audit log

### Must happen before

* Any live stock automation
