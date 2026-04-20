import React, { useState } from 'react';
import { useCandles } from '../hooks/useCandles';
import { KRAKEN_UNIVERSE } from '../constants';

// Analytics page — shows real candle counts as a proxy for worker health.
// Performance metrics (Sharpe, Calmar) require the /analytics endpoint
// which doesn't exist yet — shows honest "not available" state.

type WorkerStatus = { symbol: string; count: number; lastTime: string | null; loading: boolean };

function WorkerRow({ symbol }: { symbol: string }): React.ReactElement {
  const { candles, loading } = useCandles(symbol, '1h', 5, 0);
  const last = candles[candles.length - 1];
  const isLive = !loading && candles.length > 0;
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '100px 1fr auto auto',
      gap: 10, alignItems: 'center', padding: '7px 0',
      borderBottom: '0.5px solid var(--border)',
    }}>
      <span style={{ fontSize: 11, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>{symbol}</span>
      <div style={{ height: 3, background: 'var(--bg3)', borderRadius: 2 }}>
        <div style={{ height: '100%', borderRadius: 2, background: isLive ? 'var(--green)' : 'var(--text4)', width: isLive ? '100%' : '10%', transition: 'width 0.4s' }} />
      </div>
      <span style={{ fontSize: 10, color: 'var(--text3)', minWidth: 120 }}>
        {loading ? 'checking…' : last ? last.time.slice(0, 16).replace('T', ' ') : 'no data'}
      </span>
      <span style={{ fontSize: 9, letterSpacing: '0.08em', color: isLive ? 'var(--green)' : 'var(--text4)' }}>
        {loading ? '…' : isLive ? 'LIVE' : 'EMPTY'}
      </span>
    </div>
  );
}

const Analytics: React.FC = () => {
  return (
    <div className="page active">

      {/* Performance metrics — honest N/A until backend adds /analytics route */}
      <div className="analytics-grid">
        {[
          { label: 'Sharpe ratio', note: 'Requires 30+ days paper data' },
          { label: 'Calmar ratio', note: 'Requires /analytics endpoint' },
          { label: 'Win rate', note: 'No closed trades yet' },
          { label: 'Max drawdown', note: 'No trade history yet' },
        ].map(m => (
          <div className="card" key={m.label}>
            <div className="card-header">
              <span className="card-title">{m.label}</span>
              <span className="card-badge cb-muted">Not available</span>
            </div>
            <div className="card-body">
              <div className="stat-eyebrow">{m.note}</div>
              <div className="stat-big neutral" style={{ fontSize: 28, color: 'var(--text3)' }}>—</div>
              <div className="stat-delta neutral">
                Add GET /analytics/summary to the backend to populate this card
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Go/no-go checklist — paper trading gate */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Paper trading go / no-go gate</span>
          <span className="card-badge cb-amber">In progress</span>
        </div>
        <div className="card-body card-flush" style={{ padding: '0 16px' }}>
          <div className="gate-list">
            {[
              { label: 'Sharpe ≥ 1.0',        value: 'No data',   status: 'fail' as const },
              { label: 'Calmar ≥ 0.5',        value: 'No data',   status: 'fail' as const },
              { label: 'Win rate ≥ 45%',      value: 'No trades', status: 'fail' as const },
              { label: 'Profit factor ≥ 1.3', value: 'No trades', status: 'fail' as const },
              { label: 'Max DD ≤ 15%',        value: 'No data',   status: 'fail' as const },
              { label: 'Trades ≥ 50',         value: '0 / 50',    status: 'fail' as const },
              { label: '30-day paper run',     value: '0 / 30 days', status: 'fail' as const },
              { label: 'Direction gate verified', value: 'Unit tested', status: 'pass' as const },
              { label: 'Crypto shorts blocked',   value: 'Enforced',   status: 'pass' as const },
            ].map(g => (
              <div className="gate-row" key={g.label}>
                <span className="gate-label">{g.label}</span>
                <span className={`gate-${g.status}`}>
                  {g.status === 'pass' ? '✓' : g.status === 'warn' ? '~' : '✗'} {g.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Candle worker health — real data from /candles */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Kraken candle workers · live status</span>
          <span className="card-badge cb-blue">Polls /candles every 20s</span>
        </div>
        <div className="card-body-sm" style={{ columns: 2, columnGap: 24 }}>
          {KRAKEN_UNIVERSE.map(sym => (
            <div key={sym} style={{ breakInside: 'avoid' }}>
              <WorkerRow symbol={sym} />
            </div>
          ))}
        </div>
        <div style={{ padding: '10px 16px', borderTop: '0.5px solid var(--border)', fontSize: 10, color: 'var(--text3)' }}>
          EMPTY = no candles stored yet. Run <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>scripts/seed_alpaca_training.py</code> or
          start the candle workers to begin backfilling.
        </div>
      </div>

      {/* Alpaca training data status */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Alpaca training data · ML pipeline</span>
          <span className="card-badge cb-amber">ML module not built yet</span>
        </div>
        <div className="card-body">
          <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.8 }}>
            <div>
              <span style={{ color: 'var(--amber)' }}>·</span>
              {' '}Session 9 (app/ml/) has not been implemented — see audit report.
            </div>
            <div>
              <span style={{ color: 'var(--green)' }}>·</span>
              {' '}Alpaca batch fetcher is ready in <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>app/brokers/alpaca.py</code>
            </div>
            <div>
              <span style={{ color: 'var(--green)' }}>·</span>
              {' '}Run <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>python scripts/seed_alpaca_training.py</code> to seed 2yr OHLCV history.
            </div>
            <div>
              <span style={{ color: 'var(--amber)' }}>·</span>
              {' '}<code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>app/ml/features.py</code>, <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>trainer.py</code>, <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>predictor.py</code> needed to generate signals.
            </div>
            <div>
              <span style={{ color: 'var(--text4)' }}>·</span>
              {' '}Crypto pairs are hardcoded via KRAKEN_UNIVERSE — workers start automatically on launch.
            </div>
          </div>
        </div>
      </div>

    </div>
  );
};

export default Analytics;
