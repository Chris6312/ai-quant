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

export type RuntimeWorkersResponse = {
  as_of: string;
  summary: RuntimeWorkerSummary;
  workers: RuntimeWorkerRecord[];
  recent_events: RuntimeWorkerEvent[];
  supervisor: RuntimeSupervisorSnapshot;
};

export const getRuntimeWorkers = (eventLimit = 20) =>
  requestJson<RuntimeWorkersResponse>(`/runtime/workers?event_limit=${eventLimit}`);

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

export type GainersResponse = {
  gainers: Record<string, unknown>[];
  count: number;
  fetched_at: string;
  error?: string;
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

export const backfillCrypto = (): Promise<MlJob> =>
  requestJson<MlJob>('/ml/backfill/crypto', {
    method: 'POST',
    body: JSON.stringify({}),
  });

export const backfillStocks = (symbols: string, days = 730) =>
  requestJson<MlJob>(
    `/ml/backfill/stocks?symbols=${encodeURIComponent(symbols)}&lookback_days=${days}`,
    { method: 'POST' },
  );

export const backfillGainers = (limit = 100, days = 365): Promise<MlJob> =>
  requestJson<MlJob>(`/ml/backfill/gainers?limit=${limit}&lookback_days=${days}`, {
    method: 'POST',
  });

export const triggerWatchlistResearch = () =>
  requestJson<MlJob>('/ml/research/watchlist', { method: 'POST' });