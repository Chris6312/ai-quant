import React, { useCallback, useEffect, useState } from 'react';

import {
  getRuntimeWorkers,
  type RuntimeWatchlistTarget,
  type RuntimeWorkerEvent,
  type RuntimeWorkerRecord,
  type RuntimeWorkersResponse,
} from '../api';

const POLL_MS = 15000;
const EVENT_LIMIT = 20;

type Tone = 'green' | 'amber' | 'red' | 'blue' | 'muted';

const toneStyle: Record<Tone, React.CSSProperties> = {
  green: {
    background: 'var(--green-bg)',
    border: '0.5px solid var(--green3)',
    color: 'var(--green)',
  },
  amber: {
    background: 'var(--amber-bg)',
    border: '0.5px solid var(--amber2)',
    color: 'var(--amber)',
  },
  red: {
    background: 'var(--red-bg)',
    border: '0.5px solid var(--red3)',
    color: 'var(--red)',
  },
  blue: {
    background: 'var(--blue-bg)',
    border: '0.5px solid var(--blue2)',
    color: 'var(--blue)',
  },
  muted: {
    background: 'var(--bg3)',
    border: '0.5px solid var(--border2)',
    color: 'var(--text3)',
  },
};

function fmtDateTime(value: string | null): string {
  if (!value) {
    return '—';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('en-US', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function fmtAge(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return '—';
  }
  if (value < 1) {
    return '<1s';
  }
  if (value < 60) {
    return `${Math.round(value)}s`;
  }
  if (value < 3600) {
    return `${Math.round(value / 60)}m`;
  }
  return `${(value / 3600).toFixed(1)}h`;
}

function pillStyle(tone: Tone): React.CSSProperties {
  return {
    ...toneStyle[tone],
    display: 'inline-flex',
    alignItems: 'center',
    padding: '2px 8px',
    borderRadius: 'var(--radius-sm)',
    fontSize: 10,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  };
}

function toneForHealth(health: string): Tone {
  switch (health) {
    case 'healthy':
      return 'green';
    case 'stale':
      return 'amber';
    case 'error':
      return 'red';
    case 'inactive':
      return 'muted';
    default:
      return 'muted';
  }
}

function toneForStatus(status: string): Tone {
  switch (status) {
    case 'running':
      return 'green';
    case 'starting':
    case 'stopping':
      return 'amber';
    case 'error':
      return 'red';
    case 'stopped':
      return 'muted';
    default:
      return 'muted';
  }
}

function RuntimeWorkerTable({ workers }: { workers: RuntimeWorkerRecord[] }): React.ReactElement {
  if (workers.length === 0) {
    return (
      <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
        No managed workers are currently registered. This usually means the supervisor is disabled,
        watchlist-driven workers have not been attached yet, or the runtime has not launched any
        candle worker tasks in this process.
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="wl-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Asset</th>
            <th>Timeframe</th>
            <th>Source</th>
            <th>Status</th>
            <th>Health</th>
            <th>Heartbeat</th>
            <th>Age</th>
            <th>Candle close</th>
            <th>Task</th>
            <th>Last error</th>
          </tr>
        </thead>
        <tbody>
          {workers.map((worker) => (
            <tr key={worker.worker_id}>
              <td style={{ fontWeight: 500 }}>{worker.symbol}</td>
              <td>{worker.asset_class}</td>
              <td>{worker.timeframe}</td>
              <td>{worker.source}</td>
              <td>
                <span style={pillStyle(toneForStatus(worker.status))}>{worker.status}</span>
              </td>
              <td>
                <span style={pillStyle(toneForHealth(worker.health))}>{worker.health}</span>
              </td>
              <td>{fmtDateTime(worker.last_heartbeat_at)}</td>
              <td>{fmtAge(worker.heartbeat_age_s)}</td>
              <td>{fmtDateTime(worker.last_candle_close_at)}</td>
              <td style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                {worker.task_name ?? '—'}
              </td>
              <td style={{ color: worker.last_error ? 'var(--red)' : 'var(--text3)' }}>
                {worker.last_error ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RuntimeTargetTable({ targets }: { targets: RuntimeWatchlistTarget[] }): React.ReactElement {
  if (targets.length === 0) {
    return (
      <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
        No active stock watchlist symbols were found. Once symbols are active in the watchlist, this
        section will show whether each one has a real worker attached.
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="wl-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Asset</th>
            <th>Timeframe</th>
            <th>Attachment</th>
            <th>Worker status</th>
            <th>Worker health</th>
            <th>Last heartbeat</th>
            <th>Last error</th>
          </tr>
        </thead>
        <tbody>
          {targets.map((target) => (
            <tr key={target.worker_id}>
              <td style={{ fontWeight: 500 }}>{target.symbol}</td>
              <td>{target.asset_class}</td>
              <td>{target.timeframe}</td>
              <td>
                <span style={pillStyle(target.worker_attached ? 'green' : 'amber')}>
                  {target.worker_attached ? 'Attached' : 'Missing'}
                </span>
              </td>
              <td>
                {target.worker_status ? (
                  <span style={pillStyle(toneForStatus(target.worker_status))}>{target.worker_status}</span>
                ) : (
                  '—'
                )}
              </td>
              <td>
                {target.worker_health ? (
                  <span style={pillStyle(toneForHealth(target.worker_health))}>{target.worker_health}</span>
                ) : (
                  '—'
                )}
              </td>
              <td>{fmtDateTime(target.last_heartbeat_at)}</td>
              <td style={{ color: target.last_error ? 'var(--red)' : 'var(--text3)' }}>
                {target.last_error ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RuntimeEventTable({ events }: { events: RuntimeWorkerEvent[] }): React.ReactElement {
  if (events.length === 0) {
    return (
      <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text3)' }}>
        No lifecycle events recorded yet.
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="wl-table">
        <thead>
          <tr>
            <th>Worker</th>
            <th>Status</th>
            <th>Recorded</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event, index) => (
            <tr key={`${event.worker_id}:${event.recorded_at}:${index}`}>
              <td style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{event.worker_id}</td>
              <td>
                <span style={pillStyle(toneForStatus(event.status))}>{event.status}</span>
              </td>
              <td>{fmtDateTime(event.recorded_at)}</td>
              <td style={{ color: event.detail ? 'var(--text2)' : 'var(--text3)' }}>
                {event.detail ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const Runtime: React.FC = () => {
  const [runtime, setRuntime] = useState<RuntimeWorkersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRuntime = useCallback(async (background = false) => {
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const snapshot = await getRuntimeWorkers(EVENT_LIMIT);
      setRuntime(snapshot);
      setError(null);
    } catch {
      setError('Could not reach /runtime/workers. Check backend status and refresh again.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadRuntime(false);

    const interval = window.setInterval(() => {
      void loadRuntime(true);
    }, POLL_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, [loadRuntime]);

  const supervisor = runtime?.supervisor;
  const summary = runtime?.summary;
  const coverage = runtime?.coverage;
  const watchlistTargets = runtime?.watchlist_targets ?? [];

  return (
    <div className="page active">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div style={{ fontSize: 18, color: 'var(--text)', fontWeight: 500 }}>Worker runtime</div>
          <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>
            Live visibility into the Phase 4 worker registry, supervisor, and watchlist-to-worker coverage.
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={pillStyle(refreshing ? 'blue' : 'muted')}>
            {refreshing ? 'Refreshing' : 'Read only'}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text3)' }}>
            Last snapshot: {fmtDateTime(runtime?.as_of ?? null)}
          </span>
          <button
            type="button"
            onClick={() => {
              void loadRuntime(false);
            }}
            style={{
              padding: '8px 14px',
              background: 'var(--blue-bg)',
              border: '0.5px solid var(--blue2)',
              color: 'var(--blue)',
              borderRadius: 'var(--radius-md)',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              cursor: 'pointer',
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div
          style={{
            marginTop: 12,
            padding: '10px 14px',
            background: 'var(--red-bg)',
            border: '0.5px solid var(--red3)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--red)',
            fontSize: 11,
          }}
        >
          {error}
        </div>
      )}

      {!error && (
        <div
          style={{
            marginTop: 12,
            padding: '10px 14px',
            background: supervisor?.enabled ? 'var(--bg2)' : 'var(--amber-bg)',
            border: supervisor?.enabled ? '0.5px solid var(--border)' : '0.5px solid var(--amber2)',
            borderRadius: 'var(--radius-md)',
            color: supervisor?.enabled ? 'var(--text2)' : 'var(--amber)',
            fontSize: 11,
            lineHeight: 1.7,
          }}
        >
          {supervisor?.enabled
            ? 'Supervisor is enabled. The coverage table below is still stock-watchlist coverage only. Crypto scope is now treated as a separate first-class lane and will gain runtime-derived coverage in later phases.'
            : 'Supervisor is currently disabled. The coverage table below still shows which active stock watchlist symbols are missing worker attachments in this process. Crypto scope is defined separately from this stock table.'}
        </div>
      )}

      <div className="metrics-row" style={{ marginTop: 14 }}>
        {[
          { label: 'Total workers', value: summary?.total_workers ?? '—', tone: 'muted' as Tone, sub: 'Registry snapshot' },
          { label: 'Healthy', value: summary?.healthy_workers ?? '—', tone: 'green' as Tone, sub: 'Fresh heartbeats' },
          { label: 'Stale', value: summary?.stale_workers ?? '—', tone: 'amber' as Tone, sub: 'Needs attention' },
          { label: 'Stock targets', value: coverage?.watchlist_targets ?? '—', tone: 'blue' as Tone, sub: 'Active stock watchlist symbols' },
          { label: 'Attached', value: coverage?.attached_workers ?? '—', tone: 'green' as Tone, sub: 'Targets with workers' },
          { label: 'Missing', value: coverage?.unattached_workers ?? '—', tone: 'amber' as Tone, sub: 'Targets without workers' },
        ].map((item) => (
          <div className="metric-tile" key={item.label}>
            <div className="metric-eyebrow">{item.label}</div>
            <div
              className="metric-value"
              style={{
                color:
                  item.tone === 'green'
                    ? 'var(--green)'
                    : item.tone === 'amber'
                      ? 'var(--amber)'
                      : item.tone === 'red'
                        ? 'var(--red)'
                        : item.tone === 'blue'
                          ? 'var(--blue)'
                          : 'var(--text)',
              }}
            >
              {item.value}
            </div>
            <div className="metric-sub">{item.sub}</div>
          </div>
        ))}
      </div>

      <div className="settings-grid" style={{ marginTop: 16 }}>
        <div className="settings-col">
          <div className="card">
            <div className="card-header">
              <span className="card-title">Supervisor</span>
              <span style={pillStyle(supervisor?.running ? 'green' : supervisor?.enabled ? 'amber' : 'muted')}>
                {loading ? 'Loading' : supervisor?.running ? 'Running' : supervisor?.enabled ? 'Idle' : 'Disabled'}
              </span>
            </div>
            <div className="card-body" style={{ display: 'grid', gap: 10 }}>
              {[
                ['Name', supervisor?.name ?? '—'],
                ['Enabled', supervisor ? (supervisor.enabled ? 'Yes' : 'No') : '—'],
                ['Interval', supervisor ? `${supervisor.interval_seconds}s` : '—'],
                ['Iterations', supervisor?.iteration_count ?? '—'],
                ['Last started', fmtDateTime(supervisor?.last_started_at ?? null)],
                ['Last finished', fmtDateTime(supervisor?.last_finished_at ?? null)],
                ['Last success', fmtDateTime(supervisor?.last_success_at ?? null)],
                ['Last error', supervisor?.last_error ?? '—'],
                [
                  'Last result',
                  supervisor?.last_result
                    ? `start ${supervisor.last_result.started} · stop ${supervisor.last_result.stopped} · unchanged ${supervisor.last_result.unchanged}`
                    : '—',
                ],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    gap: 12,
                    paddingBottom: 8,
                    borderBottom: '0.5px solid var(--border)',
                    fontSize: 11,
                  }}
                >
                  <span style={{ color: 'var(--text3)' }}>{label}</span>
                  <span
                    style={{
                      color: label === 'Last error' && value !== '—' ? 'var(--red)' : 'var(--text)',
                      textAlign: 'right',
                      maxWidth: '65%',
                    }}
                  >
                    {value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="settings-col">
          <div className="card">
            <div className="card-header">
              <span className="card-title">Phase 4 visibility notes</span>
              <span style={pillStyle('blue')}>UI</span>
            </div>
            <div className="card-body" style={{ display: 'grid', gap: 8, fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
              <div>The worker table shows only real registry entries from this backend process.</div>
              <div>The watchlist coverage table answers a different question: which active stock watchlist symbols should have workers attached right now.</div>
              <div>This page is read-only on purpose. No start, stop, or restart controls are exposed in Phase 4.</div>
              <div>Health reflects registry timestamps: healthy, stale, inactive, and error.</div>
              <div>Recent events are capped to the latest {EVENT_LIMIT} entries from the backend API.</div>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <span className="card-title">Watchlist worker coverage</span>
          <span style={pillStyle((coverage?.unattached_workers ?? 0) > 0 ? 'amber' : 'green')}>
            {coverage?.attached_workers ?? 0} / {coverage?.watchlist_targets ?? 0} stock targets attached
          </span>
        </div>
        {loading && !runtime ? (
          <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading coverage snapshot…</div>
        ) : (
          <RuntimeTargetTable targets={watchlistTargets} />
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <span className="card-title">Managed workers</span>
          <span style={pillStyle(summary?.total_workers ? 'green' : 'muted')}>
            {summary?.total_workers ?? 0} tracked
          </span>
        </div>
        {loading && !runtime ? (
          <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading worker snapshot…</div>
        ) : (
          <RuntimeWorkerTable workers={runtime?.workers ?? []} />
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-header">
          <span className="card-title">Recent lifecycle events</span>
          <span style={pillStyle((runtime?.recent_events.length ?? 0) > 0 ? 'amber' : 'muted')}>
            {runtime?.recent_events.length ?? 0} events
          </span>
        </div>
        {loading && !runtime ? (
          <div style={{ padding: '12px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading event history…</div>
        ) : (
          <RuntimeEventTable events={runtime?.recent_events ?? []} />
        )}
      </div>
    </div>
  );
};

export default Runtime;
