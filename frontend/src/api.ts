const BASE = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ── Health ────────────────────────────────────────────────────────────────
export type HealthResponse = { status: string; app: string; version: string };
export type ReadyResponse = { status: string };

export const getHealth = () => requestJson<HealthResponse>('/health');
export const getReady = () => requestJson<ReadyResponse>('/ready');

// ── Config ────────────────────────────────────────────────────────────────
export type KeyStatus = { configured: boolean; preview?: string; hint?: string };
export type ConfigKeys = {
  alpaca: { api_key: KeyStatus; api_secret: KeyStatus; base_url: string };
  tradier: { api_key: KeyStatus; account_id: KeyStatus; base_url: string };
  kraken: { api_key: KeyStatus; api_secret: KeyStatus; base_url: string };
  env_file: string;
  note: string;
};

export const getConfigKeys = () => requestJson<ConfigKeys>('/config/keys');


export type RuntimeWorkerSummary = {
  total_workers: number;
  healthy_workers: number;
  stale_workers: number;
  inactive_workers: number;
  error_workers: number;
};

export type RuntimeWorkerRecord = {
  worker_id: string;
  symbol: string;
  asset_class: string;
  timeframe: string;
  source: string;
  status: string;
  health: string;
  started_at: string;
  updated_at: string;
  last_heartbeat_at: string | null;
  last_candle_close_at: string | null;
  last_error: string | null;
  task_name: string | null;
  heartbeat_ttl_s: number;
  heartbeat_age_s: number | null;
  freshness?: string;
  latest_ml_candle_at?: string | null;
  latest_ml_candle_date?: string | null;
  tracked_symbol_count?: number;
  symbols_with_ml_candles?: number;
  missing_or_stale_symbols?: string[];
};

export type RuntimeWorkerEvent = {
  worker_id: string;
  status: string;
  recorded_at: string;
  detail: string | null;
};

export type RuntimeSupervisorResult = {
  started: number;
  stopped: number;
  unchanged: number;
};

export type RuntimeSupervisorSnapshot = {
  name: string;
  interval_seconds: number;
  enabled: boolean;
  running: boolean;
  iteration_count: number;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_result: RuntimeSupervisorResult | null;
};

export type RuntimeCoverageSummary = {
  watchlist_targets: number;
  attached_workers: number;
  unattached_workers: number;
  scope_note?: string;
};

export type RuntimeCryptoScope = {
  universe_symbols: string[];
  universe_count: number;
  universe_source: string;
  watchlist_symbols: string[];
  watchlist_count: number;
  watchlist_source: string;
  target_runtime_symbols: string[];
  target_runtime_count: number;
  target_runtime_source: string;
  active_runtime_symbols: string[];
  active_runtime_count: number;
  active_runtime_source: string;
};

export type RuntimeWatchlistTarget = {
  worker_id: string;
  symbol: string;
  asset_class: string;
  timeframe: string;
  worker_attached: boolean;
  worker_status: string | null;
  worker_health: string | null;
  last_heartbeat_at: string | null;
  last_error: string | null;
};

export type RuntimeWorkersResponse = {
  as_of: string;
  summary: RuntimeWorkerSummary;
  coverage: RuntimeCoverageSummary;
  crypto_scope: RuntimeCryptoScope;
  workers: RuntimeWorkerRecord[];
  ml_workers: RuntimeWorkerRecord[];
  watchlist_targets: RuntimeWatchlistTarget[];
  recent_events: RuntimeWorkerEvent[];
  supervisor: RuntimeSupervisorSnapshot;
};

export const getRuntimeWorkers = (eventLimit = 20) =>
  requestJson<RuntimeWorkersResponse>(`/runtime/workers?event_limit=${eventLimit}`);

export type ResearchScopeResponse = {
  stock_watchlist_symbols: string[];
  stock_watchlist_count: number;
  stock_watchlist_source: string;
  crypto_universe_symbols: string[];
  crypto_universe_count: number;
  crypto_universe_source: string;
  crypto_watchlist_symbols: string[];
  crypto_watchlist_count: number;
  crypto_watchlist_source: string;
};

export const getResearchScope = () => requestJson<ResearchScopeResponse>('/research/scope');

// ── Watchlist ─────────────────────────────────────────────────────────────
export type WatchlistItem = {
  symbol: string;
  asset_class: string;
  added_at: string;
  added_by: string | null;
  research_score: number | null;
  is_active: boolean;
  notes: string | null;
};

export const getWatchlist = () => requestJson<WatchlistItem[]>('/watchlist');

// ── Candles ───────────────────────────────────────────────────────────────
export type Candle = {
  time: string;
  symbol: string;
  asset_class: string;
  timeframe: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
  source: string;
};

export const getCandles = (symbol: string, timeframe = '1h', limit = 100) =>
  requestJson<Candle[]>(
    `/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&limit=${limit}`,
  );

// ── Admin ─────────────────────────────────────────────────────────────────
export type ReconcileResponse = {
  internal_open_positions: number;
  open_orders: Record<string, number>;
  balances: Record<string, Record<string, number>>;
};

export const getReconcile = () => requestJson<ReconcileResponse>('/admin/reconcile');

export const postHalt = () =>
  requestJson<{ status: string; brokers: Record<string, boolean> }>('/admin/halt', {
    method: 'POST',
  });

// ── Paper ledger ──────────────────────────────────────────────────────────
export type PaperBalance = {
  stock_balance: number;
  crypto_balance: number;
  stock_default: number;
  crypto_default: number;
  realized_pnl: number;
  nav: number;
};

export const getPaperBalance = () => requestJson<PaperBalance>('/paper/balance');

export const setPaperBalance = (stock?: number, crypto?: number) => {
  const q = new URLSearchParams();
  if (stock !== undefined) {
    q.set('stock', String(stock));
  }
  if (crypto !== undefined) {
    q.set('crypto', String(crypto));
  }
  return requestJson<PaperBalance>(`/paper/balance/set?${q.toString()}`, {
    method: 'POST',
  });
};

export const resetPaperBalance = (assetClass: 'stock' | 'crypto' | 'all') =>
  requestJson<PaperBalance>(`/paper/balance/reset?asset_class=${assetClass}`, {
    method: 'POST',
  });

// ── Orders ────────────────────────────────────────────────────────────────
export type OrderEntry = {
  id: string;
  symbol: string;
  asset_class: string;
  side: string;
  entry_price?: number | null;
  price?: number | null;
  size: number | null;
  entry_value?: number | null;
  gross?: number | null;
  strategy_id?: string | null;
  status?: string;
  source: string;
  opened_at?: string | null;
  created_at?: string | null;
  closed_at?: string | null;
  ml_confidence?: number | null;
  research_score?: number | null;
};

export type OrdersFilter = {
  source?: string;
  status?: string;
  symbol?: string;
  asset_class?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
};

export const getOrders = (filter: OrdersFilter = {}) => {
  const q = new URLSearchParams();
  Object.entries(filter).forEach(([key, value]) => {
    if (value !== undefined) {
      q.set(key, String(value));
    }
  });
  return requestJson<OrderEntry[]>(`/orders?${q.toString()}`);
};

export const exportOrdersCsv = (
  source: string,
  dateFrom?: string,
  dateTo?: string,
): string => {
  const q = new URLSearchParams({ source });
  if (dateFrom) {
    q.set('date_from', dateFrom);
  }
  if (dateTo) {
    q.set('date_to', dateTo);
  }
  return `${BASE}/orders/export?${q.toString()}`;
};

// ── ML / Research ─────────────────────────────────────────────────────────
export type MlJob = {
  job_id: string;
  type: string;
  asset_class: string;
  symbols: string[];
  status: 'running' | 'done' | 'error';
  started_at: string;
  finished_at: string | null;
  total_symbols: number;
  done_symbols: number;
  current_symbol: string | null;
  current_timeframe: string | null;
  status_message?: string | null;
  total_batches: number;
  done_batches: number;
  rows_fetched: number;
  progress_pct: number;
  error: string | null;
  result: Record<string, unknown> | null;
  gainers_snapshot?: Record<string, unknown>[];
};

export type TrainingDetail = {
  symbol: string;
  asset_class: string;
  timeframe: string;
  candle_count: number;
  earliest: string | null;
  latest: string | null;
};

export type TrainingStatus = {
  source: string;
  total_candles: number;
  crypto_candles: number;
  stock_candles: number;
  crypto_symbols: number;
  stock_symbols: number;
  symbols_with_data: number;
  crypto_detail: TrainingDetail[];
  stock_detail: TrainingDetail[];
  generated_at?: string;
  cache_state?: string;
};

export type MlPersistenceResponse = {
  jobs: MlJob[];
  active_job_id: string | null;
  has_running_job: boolean;
  training: TrainingStatus;
  persisted_at: string;
};

export type ActiveMlJobResponse = {
  job: MlJob | null;
};

export type FeatureContractResponse = {
  feature_count: number;
  technical_feature_count: number;
  research_feature_count: number;
  feature_names: string[];
};

export type GainerRow = {
  symbol: string;
  price: number | null;
  percent_change: number | null;
  volume: number | null;
};

export type CryptoUniverseResponse = {
  symbols: string[];
  count: number;
  source_dir: string;
  scope_source: string;
  watchlist_mode: string;
  runtime_mode: string;
  prediction_mode: string;
  scope_model: Record<string, string>;
  phase_1_mapping: Record<string, string>;
};

export type StockUniverseUnsupportedSymbol = {
  symbol: string;
  reason: string | null;
};

export type StockUniverseResponse = {
  index: string;
  as_of: string;
  source_file: string;
  constituent_stock_count: number;
  supported_symbol_count: number;
  unsupported_symbol_count: number;
  target_candles_per_symbol: number;
  minimum_candles_per_symbol: number;
  timeframe: string;
  lookback_days: number;
  sample_symbols: string[];
  unsupported_symbols: StockUniverseUnsupportedSymbol[];
  generated_at: string;
};

export type GainersResponse = {
  gainers: GainerRow[];
  count: number;
  fetched_at: string;
  error?: string;
};

export type ModelFold = {
  fold_index: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  validation_sharpe: number;
  validation_accuracy: number;
  n_train_samples: number;
  n_test_samples: number;
  model_path: string;
  eligibility_status?: string;
  eligibility_reason?: string;
};

export type MlModelRecord = {
  model_id: string;
  asset_class: 'crypto' | 'stock';
  status: 'active' | 'retired' | 'challenger' | 'failed';
  artifact_path: string;
  trained_at: string;
  fold_count: number;
  best_fold: number;
  validation_accuracy: number;
  validation_sharpe: number;
  train_samples: number;
  test_samples: number;
  feature_count: number;
  confidence_threshold: number;
  latest_job_id: string | null;
  feature_importances: Record<string, number>;
  folds: ModelFold[];
  selection_regime?: string;
  selection_policy?: Record<string, unknown>;
};

export type MlModelImportance = {
  feature: string;
  importance: number;
};

export type MlModelImportancesResponse = {
  model_id: string;
  asset_class: 'crypto' | 'stock';
  feature_count: number;
  importances: MlModelImportance[];
  generated_at: string;
};

export type MlPredictionRow = {
  prediction_id: string;
  model_id: string | null;
  symbol: string;
  asset_class: 'crypto' | 'stock';
  direction: 'short' | 'flat' | 'long';
  confidence: number;
  class_probabilities: {
    down: number;
    flat: number;
    up: number;
  };
  top_driver: string;
  candle_time: string;
  action: 'signal' | 'skip';
  confidence_threshold: number;
};

export type MlPredictionFreshness = {
  latest_candle_time: string | null;
  lag_days: number | null;
  is_stale: boolean;
  status: 'fresh' | 'stale' | 'no_data';
};

export type MlPredictionShapRow = {
  prediction_id: string;
  model_id: string | null;
  symbol: string;
  feature_name: string;
  feature_value: number;
  contribution: number;
  rank: number;
};

export type MlPredictionShapResponse = {
  prediction_id: string;
  model_id: string | null;
  symbol: string;
  asset_class: 'crypto' | 'stock';
  rows: MlPredictionShapRow[];
  count: number;
  returned_count?: number;
  limit?: number | null;
  source: 'persisted';
};

export type MlPredictionsResponse = {
  predictions: MlPredictionRow[];
  count: number;
  persisted_count?: number;
  source?: 'persisted' | 'generated';
  active_model_ids: {
    crypto: string | null;
    stock: string | null;
  };
  freshness_by_asset: Partial<Record<'crypto' | 'stock', MlPredictionFreshness>>;
  generated_at: string;
};

export type FeatureParityResponse = {
  generated_at: string;
  feature_count: number;
  parity_ok: boolean;
  same_feature_order: boolean;
  stock_contract_valid: boolean;
  crypto_contract_valid: boolean;
  stock_missing: string[];
  stock_extra: string[];
  stock_nonfinite: string[];
  crypto_missing: string[];
  crypto_extra: string[];
  crypto_nonfinite: string[];
  stock_research_features_with_signal: string[];
  crypto_research_features_with_signal: string[];
  stock_preview: Record<string, number>;
  crypto_preview: Record<string, number>;
};

export type MlModelsResponse = {
  models: MlModelRecord[];
  active_by_asset: {
    crypto: string | null;
    stock: string | null;
  };
  generated_at: string;
};

export type TrainModelResponse = {
  job?: MlJob;
  active_model_id?: string | null;
  model_id?: string;
  best_fold?: number;
  asset_class?: 'crypto' | 'stock';
};

export const getMlJobs = () => requestJson<MlJob[]>('/ml/jobs');
export const getMlPersistence = () =>
  requestJson<MlPersistenceResponse>('/ml/persistence');
export const getActiveMlJob = () =>
  requestJson<ActiveMlJobResponse>('/ml/jobs/active');
export const getMlJob = (id: string) => requestJson<MlJob>(`/ml/jobs/${id}`);
export const getTopGainers = (limit = 100) =>
  requestJson<GainersResponse>(`/ml/gainers?limit=${limit}`);
export const getTrainingStatus = () =>
  requestJson<TrainingStatus>('/ml/training/status');
export const getFeatureContract = () =>
  requestJson<FeatureContractResponse>('/ml/features/contract');
export const getCryptoUniverse = () =>
  requestJson<CryptoUniverseResponse>('/ml/crypto/universe');
export const getStockUniverse = () =>
  requestJson<StockUniverseResponse>('/ml/stock/universe');
export const getMlModels = (assetClass?: 'crypto' | 'stock') =>
  requestJson<MlModelsResponse>(assetClass ? `/ml/models?asset_class=${assetClass}` : '/ml/models');
export const getMlModel = (modelId: string) =>
  requestJson<MlModelRecord>(`/ml/models/${modelId}`);
export const getMlModelImportances = (modelId: string) =>
  requestJson<MlModelImportancesResponse>(`/ml/models/${modelId}/importances`);
export const getFeatureParity = () =>
  requestJson<FeatureParityResponse>('/ml/features/parity');
export const getMlPredictions = (limit = 50, assetClass?: 'crypto' | 'stock') => {
  const query = new URLSearchParams({ limit: String(limit) });
  if (assetClass) {
    query.set('asset_class', assetClass);
  }
  return requestJson<MlPredictionsResponse>(`/ml/predictions?${query.toString()}`);
};

export const runMlPredictions = (limit = 200, assetClass?: 'crypto' | 'stock') => {
  const query = new URLSearchParams({ limit: String(limit) });
  if (assetClass) {
    query.set('asset_class', assetClass);
  }
  return requestJson<MlPredictionsResponse>(`/ml/predictions/run?${query.toString()}`, {
    method: 'POST',
  });
};

export const getMlPredictionShap = (
  predictionId: string,
  options: { limit?: number; all?: boolean } = {},
) => {
  const query = new URLSearchParams({ prediction_id: predictionId });
  if (options.all) {
    query.set('all', 'true');
  } else if (options.limit) {
    query.set('limit', String(options.limit));
  }
  return requestJson<MlPredictionShapResponse>(`/ml/predictions/shap?${query.toString()}`);
};

export const trainMlModel = (assetClass: 'crypto' | 'stock'): Promise<TrainModelResponse> =>
  requestJson<TrainModelResponse>(`/ml/train/${assetClass}`, {
    method: 'POST',
  });

export const importCryptoCsv = (): Promise<MlJob> =>
  requestJson<MlJob>('/ml/import/crypto-csv', {
    method: 'POST',
  });

export const catchUpCryptoDaily = () =>
  requestJson<MlJob>('/ml/backfill/crypto/daily-catchup', {
    method: 'POST',
  });

export const backfillSp500Stocks = (targetCandles = 1000) =>
  requestJson<MlJob>(`/ml/backfill/stocks/sp500?target_candles=${targetCandles}`, {
    method: 'POST',
  });

export const backfillGainers = (limit = 100, days = 365): Promise<MlJob> =>
  requestJson<MlJob>(`/ml/backfill/gainers?limit=${limit}&lookback_days=${days}`, {
    method: 'POST',
  });

export const triggerWatchlistResearch = () =>
  requestJson<MlJob>('/ml/research/watchlist', { method: 'POST' });

export type KrakenTicker = {
  symbol: string;
  last_price: number;
  open_price: number;
  change_pct: number;
  source: string;
};

export const getKrakenTicker = (symbols?: string[]) => {
  const query = symbols && symbols.length > 0
    ? `?symbols=${encodeURIComponent(symbols.join(','))}`
    : '';
  return requestJson<KrakenTicker[]>(`/candles/kraken-ticker${query}`);
};
