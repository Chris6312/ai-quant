import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  backfillCrypto,
  backfillGainers,
  backfillStocks,
  getActiveMlJob,
  getMlJobs,
  getMlPersistence,
  getTopGainers,
  getTrainingStatus,
  triggerWatchlistResearch,
  type GainersResponse,
  type MlJob,
  type TrainingStatus,
} from '../api';
import { KRAKEN_UNIVERSE } from '../constants';

const STORAGE_KEY = 'ml-page-state-v1';

type PersistedMlViewState = {
  stockSyms: string;
  activeJobId: string | null;
  gainers: GainersResponse | null;
};

const DEFAULT_VIEW_STATE: PersistedMlViewState = {
  stockSyms: '',
  activeJobId: null,
  gainers: null,
};

const loadPersistedViewState = (): PersistedMlViewState => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_VIEW_STATE;
    }
    return {
      ...DEFAULT_VIEW_STATE,
      ...(JSON.parse(raw) as Partial<PersistedMlViewState>),
    };
  } catch {
    return DEFAULT_VIEW_STATE;
  }
};

const fmtDuration = (start: string, end: string | null): string => {
  if (!end) return '…';
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms < 60000 ? `${(ms / 1000).toFixed(1)}s` : `${(ms / 60000).toFixed(1)}m`;
};

function ProgressBar({ job }: { job: MlJob }): React.ReactElement {
  if (job.status === 'done') {
    return <div style={{ fontSize: 10, color: 'var(--green)' }}>Done — {job.rows_fetched.toLocaleString()} rows written</div>;
  }
  if (job.status === 'error') {
    return <div style={{ fontSize: 10, color: 'var(--red)' }}>Error: {job.error}</div>;
  }

  const pct = job.progress_pct ?? 0;
  const statusLine = job.status_message
    ?? (job.current_symbol ? `Fetching ${job.current_symbol}` : 'Starting…');
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, gap: 12 }}>
        <span style={{ color: 'var(--amber)' }}>{statusLine}</span>
        <span style={{ color: 'var(--text3)', textAlign: 'right' }}>
          {job.done_symbols} / {job.total_symbols} symbols
          {job.current_timeframe ? ` · ${job.current_timeframe}` : ''}
          {' · '}
          {job.rows_fetched.toLocaleString()} rows
          {' · '}
          {pct}%
        </span>
      </div>
      <div style={{ height: 6, background: 'var(--bg3)', borderRadius: 3, overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            borderRadius: 3,
            background: 'var(--amber)',
            width: `${pct}%`,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
    </div>
  );
}

function JobCard({ job }: { job: MlJob }): React.ReactElement {
  const [open, setOpen] = useState(job.status === 'running');
  const isRunning = job.status === 'running';

  return (
    <div
      style={{
        background: 'var(--bg2)',
        border: `0.5px solid ${isRunning ? 'var(--amber)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        marginBottom: 8,
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr auto auto',
          gap: 12,
          alignItems: 'center',
          padding: '10px 14px',
          cursor: 'pointer',
        }}
        onClick={() => setOpen((value) => !value)}
      >
        <div>
          <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>
            {job.type.replace(/_/g, ' ')}
            <span
              style={{
                marginLeft: 8,
                fontSize: 9,
                padding: '1px 5px',
                borderRadius: 3,
                background:
                  job.asset_class === 'crypto'
                    ? 'var(--blue-bg)'
                    : job.asset_class === 'stock'
                      ? 'var(--amber-bg)'
                      : 'var(--bg3)',
                color:
                  job.asset_class === 'crypto'
                    ? 'var(--blue)'
                    : job.asset_class === 'stock'
                      ? 'var(--amber)'
                      : 'var(--text3)',
              }}
            >
              {job.asset_class}
            </span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>
            {job.symbols.length} symbols · started {job.started_at.slice(11, 16)}
            {job.finished_at ? ` · took ${fmtDuration(job.started_at, job.finished_at)}` : ''}
          </div>
        </div>
        <span style={{ fontSize: 11, color: 'var(--text3)' }}>
          {job.rows_fetched > 0 ? `${job.rows_fetched.toLocaleString()} rows` : ''}
        </span>
        <span
          className={`card-badge ${
            job.status === 'running' ? 'cb-amber' : job.status === 'done' ? 'cb-green' : 'cb-muted'
          }`}
        >
          {job.status}
        </span>
      </div>
      {open && (
        <div style={{ padding: '0 14px 12px', borderTop: '0.5px solid var(--border)' }}>
          <div style={{ marginTop: 10 }}>
            <ProgressBar job={job} />
          </div>
          {job.result && (
            <pre
              style={{
                marginTop: 10,
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                color: 'var(--text2)',
                whiteSpace: 'pre-wrap',
              }}
            >
              {JSON.stringify(job.result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

type ActionBtnProps = { label: string; onClick: () => void; color?: string; disabled?: boolean };
function ActionBtn({ label, onClick, color = 'green', disabled = false }: ActionBtnProps): React.ReactElement {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '9px 16px',
        background: `var(--${color}-bg)`,
        border: `0.5px solid var(--${color}3)`,
        color: `var(--${color})`,
        borderRadius: 'var(--radius-md)',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </button>
  );
}

function TrainingSection({ training }: { training: TrainingStatus | null }): React.ReactElement {
  if (!training) return <></>;

  const renderDetail = (rows: TrainingStatus['crypto_detail'], label: string) => {
    if (rows.length === 0) {
      return (
        <div style={{ padding: '10px 16px', fontSize: 11, color: 'var(--text3)' }}>
          No {label} training data yet — run backfill above.
        </div>
      );
    }

    const bySymbol: Record<string, { timeframes: string[]; total: number; earliest: string; latest: string }> = {};
    for (const row of rows) {
      if (!bySymbol[row.symbol]) {
        bySymbol[row.symbol] = {
          timeframes: [],
          total: 0,
          earliest: row.earliest ?? '',
          latest: row.latest ?? '',
        };
      }
      bySymbol[row.symbol].timeframes.push(`${row.timeframe}:${row.candle_count.toLocaleString()}`);
      bySymbol[row.symbol].total += row.candle_count;
    }

    return (
      <table className="wl-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Timeframes</th>
            <th>Total candles</th>
            <th>Earliest</th>
            <th>Latest</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(bySymbol).map(([symbol, info]) => (
            <tr key={symbol}>
              <td style={{ fontWeight: 500 }}>{symbol}</td>
              <td style={{ fontSize: 10, color: 'var(--text3)' }}>{info.timeframes.join(' · ')}</td>
              <td style={{ fontVariantNumeric: 'tabular-nums' }}>{info.total.toLocaleString()}</td>
              <td style={{ fontSize: 10, color: 'var(--text3)' }}>{info.earliest.slice(0, 10)}</td>
              <td style={{ fontSize: 10, color: 'var(--text3)' }}>{info.latest.slice(0, 10)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  return (
    <>
      {training.crypto_candles > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Crypto training data</span>
            <span className="card-badge cb-blue">
              {training.crypto_candles.toLocaleString()} candles · {training.crypto_symbols} symbols
            </span>
          </div>
          {training.generated_at && (
            <div style={{ padding: '0 16px 10px', fontSize: 10, color: 'var(--text3)' }}>
              Readiness cache: {training.cache_state ?? 'fresh'} · generated {new Date(training.generated_at).toLocaleString()}
            </div>
          )}
          <div className="card-flush">{renderDetail(training.crypto_detail, 'crypto')}</div>
        </div>
      )}
      {training.stock_candles > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Stock training data</span>
            <span className="card-badge cb-amber">
              {training.stock_candles.toLocaleString()} candles · {training.stock_symbols} symbols
            </span>
          </div>
          <div className="card-flush">{renderDetail(training.stock_detail, 'stock')}</div>
        </div>
      )}
    </>
  );
}

const MachineLearning: React.FC = () => {
  const initialState = useMemo(loadPersistedViewState, []);
  const [jobs, setJobs] = useState<MlJob[]>([]);
  const [training, setTraining] = useState<TrainingStatus | null>(null);
  const [gainers, setGainers] = useState<GainersResponse | null>(initialState.gainers);
  const [loading, setLoading] = useState(true);
  const [stockSyms, setStockSyms] = useState(initialState.stockSyms);
  const [activeJobId, setActiveJobId] = useState<string | null>(initialState.activeJobId);
  const [gainersLoading, setGainersLoading] = useState(false);

  const activeJob = useMemo(
    () => jobs.find((job) => job.job_id === activeJobId) ?? null,
    [activeJobId, jobs],
  );
  const hasRunningJobs = useMemo(
    () => jobs.some((job) => job.status === 'running'),
    [jobs],
  );
  const isRunning = activeJob !== null || hasRunningJobs;

  useEffect(() => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ stockSyms, activeJobId, gainers } satisfies PersistedMlViewState),
    );
  }, [activeJobId, gainers, stockSyms]);

  const refreshTraining = useCallback(async () => {
    const nextTraining = await getTrainingStatus().catch(() => null);
    if (nextTraining) {
      setTraining(nextTraining);
    }
  }, []);

  const loadAll = useCallback(async () => {
    try {
      const persisted = await getMlPersistence();
      setJobs(persisted.jobs);
      setTraining(persisted.training);
      setActiveJobId((current) => current ?? persisted.active_job_id);
      setLoading(false);
      return;
    } catch {
      const [jobsResult, trainingResult] = await Promise.allSettled([getMlJobs(), getTrainingStatus()]);
      if (jobsResult.status === 'fulfilled') {
        setJobs(jobsResult.value);
      }
      if (trainingResult.status === 'fulfilled') {
        setTraining(trainingResult.value);
      }
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!activeJobId && !hasRunningJobs) {
      return;
    }

    const mergeJob = (job: MlJob) => {
      setJobs((current) => [job, ...current.filter((item) => item.job_id !== job.job_id)]);
    };

    const intervalId = window.setInterval(async () => {
      const activeResponse = await getActiveMlJob().catch(() => null);
      const trackedJob = activeResponse?.job ?? null;

      if (trackedJob) {
        mergeJob(trackedJob);
        if (trackedJob.job_id !== activeJobId) {
          setActiveJobId(trackedJob.job_id);
        }
        return;
      }

      if (activeJobId) {
        const finishedJob = await getMlJob(activeJobId).catch(() => null);
        if (finishedJob) {
          mergeJob(finishedJob);
        }
        setActiveJobId(null);
        await refreshTraining();
        return;
      }

      if (hasRunningJobs) {
        const allJobs = await getMlJobs().catch(() => [] as MlJob[]);
        if (allJobs.length > 0) {
          setJobs(allJobs);
        }
      }
    }, 1500);

    return () => window.clearInterval(intervalId);
  }, [activeJobId, hasRunningJobs, refreshTraining]);

  const runJob = useCallback(async (fn: () => Promise<MlJob>, label: string) => {
    try {
      const job = await fn();
      if ('error' in job) {
        alert(`${label}: ${String((job as { error?: string }).error ?? 'unknown error')}`);
        return;
      }
      setJobs((current) => [job, ...current.filter((item) => item.job_id !== job.job_id)]);
      setActiveJobId(job.job_id);
    } catch (error) {
      alert(`${label} failed: ${String(error)}`);
    }
  }, []);

  const handleCryptoBackfill = useCallback(() => {
    void runJob(backfillCrypto, 'Crypto backfill');
  }, [runJob]);

  const handleStockBackfill = useCallback(() => {
    if (!stockSyms.trim()) {
      alert('Enter at least one symbol');
      return;
    }
    void runJob(() => backfillStocks(stockSyms), 'Stock backfill');
  }, [runJob, stockSyms]);

  const handleGainersBackfill = useCallback(() => {
    void runJob(() => backfillGainers(100, 365), 'Gainers backfill');
  }, [runJob]);

  const handleWatchlistResearch = useCallback(() => {
    void runJob(triggerWatchlistResearch, 'Watchlist research');
  }, [runJob]);

  const handleFetchGainers = useCallback(async () => {
    setGainersLoading(true);
    setGainers(null);
    const response = await getTopGainers(100).catch(
      (error) => ({
        error: String(error),
        gainers: [],
        count: 0,
        fetched_at: '',
      }) satisfies GainersResponse,
    );
    setGainers(response);
    setGainersLoading(false);
  }, []);

  return (
    <div className="page active">
      <div className="metrics-row">
        <div className="metric-tile">
          <div className="metric-eyebrow">Crypto training candles</div>
          <div className="metric-value" style={{ color: 'var(--blue)' }}>
            {loading ? '—' : (training?.crypto_candles ?? 0).toLocaleString()}
          </div>
          <div className="metric-sub">{training?.crypto_symbols ?? 0} symbols</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">Stock training candles</div>
          <div className="metric-value" style={{ color: 'var(--amber)' }}>
            {loading ? '—' : (training?.stock_candles ?? 0).toLocaleString()}
          </div>
          <div className="metric-sub">{training?.stock_symbols ?? 0} symbols</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">Jobs run</div>
          <div className="metric-value">{jobs.length}</div>
          <div className="metric-sub" style={{ color: isRunning ? 'var(--amber)' : 'var(--text3)' }}>
            {isRunning ? 'Recovered from persisted state' : 'None active'}
          </div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">ML module</div>
          <div className="metric-value" style={{ fontSize: 14, color: 'var(--amber)' }}>Not built</div>
          <div className="metric-sub">Session 9 pending</div>
        </div>
      </div>

      {activeJob && activeJob.status === 'running' && (
        <div
          style={{
            padding: '14px 16px',
            background: 'var(--amber-bg)',
            border: '0.5px solid var(--amber2)',
            borderRadius: 'var(--radius-lg)',
          }}
        >
          <div style={{ fontSize: 11, color: 'var(--amber)', marginBottom: 8, fontWeight: 500 }}>
            {activeJob.type.replace(/_/g, ' ')} in progress — state survives refresh and navigation
          </div>
          {activeJob.current_symbol && (
            <div style={{ fontSize: 10, color: 'var(--text2)', marginBottom: 8 }}>
              Live telemetry: {activeJob.current_symbol}
              {activeJob.current_timeframe ? ` · ${activeJob.current_timeframe}` : ''}
              {' · '}
              {activeJob.done_symbols}/{activeJob.total_symbols} symbols complete
            </div>
          )}
          <ProgressBar job={activeJob} />
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Crypto · Kraken universe · 15 pairs</span>
            <span className="card-badge cb-blue">Alpaca batch · 2yr</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
              Fetches daily + 1-hour OHLCV for all 15 Kraken pairs via Alpaca. Stored as{' '}
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>source=alpaca_training</code>{' '}
              — never mixed with live candles.
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {KRAKEN_UNIVERSE.map((symbol) => (
                <span
                  key={symbol}
                  style={{
                    fontSize: 9,
                    padding: '2px 6px',
                    background: 'var(--blue-bg)',
                    color: 'var(--blue)',
                    border: '0.5px solid var(--blue2)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  {symbol.replace('/USD', '')}
                </span>
              ))}
            </div>
            <ActionBtn label="Backfill all crypto (2yr)" onClick={handleCryptoBackfill} disabled={isRunning} />
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Stocks · custom symbols</span>
            <span className="card-badge cb-amber">Alpaca batch · 2yr</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
              Comma-separated tickers. Input persists in local storage and the backend keeps the job ledger alive.
            </div>
            <input
              type="text"
              className="num-input"
              placeholder="NVDA,MSFT,AAPL,JPM,META"
              value={stockSyms}
              onChange={(event) => setStockSyms(event.target.value)}
              style={{ width: '100%', textAlign: 'left', fontSize: 11 }}
            />
            <ActionBtn label="Backfill stocks (2yr)" onClick={handleStockBackfill} color="amber" disabled={isRunning} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Recommend — Alpaca top 100 gainers</span>
          <span className="card-badge cb-green">Live screener</span>
        </div>
        <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <ActionBtn
              label={gainersLoading ? 'Fetching…' : 'Fetch top 100 gainers'}
              onClick={() => void handleFetchGainers()}
              disabled={gainersLoading}
            />
            <ActionBtn label="Fetch gainers + backfill (1yr)" onClick={handleGainersBackfill} color="teal" disabled={isRunning} />
          </div>
          {gainers?.error && (
            <div
              style={{
                fontSize: 11,
                color: 'var(--red)',
                padding: '8px 10px',
                background: 'var(--red-bg)',
                borderRadius: 'var(--radius-md)',
                border: '0.5px solid var(--red3)',
              }}
            >
              {gainers.error}
            </div>
          )}
          {gainers && !gainers.error && gainers.gainers.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 8 }}>
                {gainers.count} gainers · {gainers.fetched_at.slice(0, 16).replace('T', ' ')} UTC
              </div>
              <table className="wl-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Price</th>
                    <th>Change %</th>
                    <th>Volume</th>
                  </tr>
                </thead>
                <tbody>
                  {gainers.gainers.slice(0, 30).map((row, index) => {
                    const symbol = String(row.symbol ?? row.S ?? '');
                    const pct = Number(row.percent_change ?? row.percent ?? 0);
                    const price = Number(row.price ?? row.c ?? 0);
                    const volume = Number(row.volume ?? row.v ?? 0);
                    return (
                      <tr key={index}>
                        <td style={{ fontWeight: 500 }}>{symbol}</td>
                        <td>{price > 0 ? `$${price.toFixed(2)}` : '—'}</td>
                        <td style={{ color: pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
                          {pct >= 0 ? '+' : ''}
                          {pct.toFixed(2)}%
                        </td>
                        <td style={{ color: 'var(--text3)' }}>{volume > 0 ? volume.toLocaleString() : '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {gainers.gainers.length > 30 && (
                <div style={{ fontSize: 10, color: 'var(--text3)', padding: '6px 14px' }}>
                  +{gainers.gainers.length - 30} more
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Watchlist research</span>
          <span className="card-badge cb-muted">Stub — Session 9 required</span>
        </div>
        <div className="card-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
            Congress, insider, news, screener scoring for all watchlist symbols. Requires{' '}
            <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>app/ml/</code> (Session 9).
          </div>
          <ActionBtn label="Run watchlist research" onClick={handleWatchlistResearch} color="purple" disabled={isRunning} />
        </div>
      </div>

      <TrainingSection training={training} />

      {jobs.length > 0 && (
        <div className="card">
          <div className="card-header">
            <span className="card-title">Job history</span>
            {isRunning && <span style={{ fontSize: 10, color: 'var(--amber)' }}>● polling every 1.5s</span>}
          </div>
          <div className="card-body">
            {jobs.map((job) => (
              <JobCard key={job.job_id} job={job} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default MachineLearning;
