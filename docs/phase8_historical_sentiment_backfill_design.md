# Phase 8 Slice 16 — Historical Crypto Sentiment Backfill Design

## Goal

Design the historical sentiment lane before adding heavy ingestion code. This slice intentionally does not call GDELT, GNews, NewsData, CoinDesk archives, Coinbase archives, or FinBERT at runtime. It documents the durable contract that later ingestion slices must follow.

## Why this lane exists

Daily RSS is useful for forward/live sentiment, but it does not create enough history for training. The model should not be retrained with sentiment until the historical backfill has produced enough source-backed rows in `crypto_daily_sentiment`.

Target coverage before retraining:

- Minimum: 6 to 12 months of sentiment coverage.
- Better: 2 or more years.
- Best: match the ML candle training window.

## Source order

Historical ingestion should layer sources from broad/free coverage to structured/fallback coverage:

1. GDELT historical article search.
2. GNews historical search, only if account limits and licensing allow the needed date range.
3. NewsData historical search, only if account limits and licensing allow the needed date range.
4. CoinDesk and Coinbase archives, only if practical and terms-safe.
5. Optional public crypto news datasets later, only if source quality and redistribution constraints are acceptable.

## Target flow

```text
symbol + date range
  → historical article search
  → normalized article candidates
  → symbol alias matching
  → URL/source dedupe
  → pre-scoring quality filter
  → FinBERT scoring
  → daily aggregate
  → crypto_daily_sentiment upsert
```

## Canonical symbol contract

All writes must use the canonical crypto ML symbols already used by the ML candle lane.

Provider aliases may be used for searching and matching, but they must not leak into the persisted aggregate key. The persisted row id remains:

```text
SYMBOL:YYYY-MM-DD
```

## Date contract

Historical sentiment should aggregate by Eastern Time market date for consistency with the rest of AI-Quant.

Rules:

- Use `published_at` as the article timestamp.
- Convert to `America/New_York` before deriving `sentiment_date`.
- Keep the raw published timestamp in source metadata if article-level persistence is added later.
- Never assign future-dated articles to a backfill day.

## Idempotency and resume behavior

Historical backfill must be safe to stop and rerun.

Required behavior:

- Input windows are chunked by symbol and date range.
- Re-running a completed window produces the same daily aggregate row keys.
- Daily writes use upsert semantics.
- Missing days are represented by a daily aggregate row with `NULL` sentiment scores and zero coverage counts only when the job explicitly evaluated that date.
- Failed source calls do not overwrite previously good rows with empty rows.
- Partial failures are reported with symbol/date/source context.

## Rate-limit strategy

Backfill workers should be conservative by default.

Rules:

- Limit source calls by provider and by symbol/date chunk.
- Prefer daily or weekly chunks rather than a single huge historical request.
- Store enough metadata in job logs/results to resume from the failed chunk.
- Use provider-specific throttling in the historical puller layer.
- Keep historical backfill on the dedicated research queue so it cannot starve ML candles, predictions, trading candles, or runtime trading paths.

## Article normalization contract

Every historical source should normalize into the same article shape used by RSS sentiment.

Required fields:

- `source`
- `url`
- `title`
- `summary` or snippet text
- `published_at`
- matched canonical symbol
- match context, such as matched alias or keyword

Recommended metadata for later debugging:

- provider query string
- provider article id, when available
- language
- source domain
- source confidence or ranking, when available

## Article-level storage decision

Daily aggregates are enough for ML features, but they are weak for debugging source quality. Before Slice 17 or 18 writes large historical data, consider adding a raw/normalized article table.

Recommended table if added later:

```text
crypto_news_articles
```

This is a design recommendation only. Slice 16 does not add the table or migration.

## Coverage semantics

Preserve the existing missing-data rule:

```text
Missing sentiment = NULL
coverage_score = 0
```

Do not store `0.0` as neutral unless an article was actually scored and the scorer produced a neutral result.

No evaluated articles for a symbol/date:

```text
positive_score = NULL
neutral_score = NULL
negative_score = NULL
compound_score = NULL
article_count = 0
source_count = 0
coverage_score = 0
```

## ML integration guardrails

Do not join historical sentiment into ML features until the backfill has enough coverage.

Do not retrain until:

- historical backfill has completed for the target symbols and date range,
- coverage statistics have been reviewed,
- missing days are understood,
- feature contracts include explicit missing indicators or safe imputation,
- SHAP is regenerated after retraining.

SHAP sentiment values must remain untrusted until after historical backfill and retraining.

## Slice boundaries

Slice 16 includes design only. It does not include GDELT client implementation, API keys, article table migration, historical job runner, FinBERT execution over historical articles, ML feature joins, or model retraining.
