import React from 'react';

// Analytics page — performance and paper-trading readiness.
// Worker/runtime visibility belongs on the Runtime page.

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
        ].map((m) => (
          <div className="card" key={m.label}>
            <div className="card-header">
              <span className="card-title">{m.label}</span>
              <span className="card-badge cb-muted">Not available</span>
            </div>
            <div className="card-body">
              <div className="stat-eyebrow">{m.note}</div>
              <div className="stat-big neutral" style={{ fontSize: 28, color: 'var(--text3)' }}>
                —
              </div>
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
              { label: 'Sharpe ≥ 1.0', value: 'No data', status: 'fail' as const },
              { label: 'Calmar ≥ 0.5', value: 'No data', status: 'fail' as const },
              { label: 'Win rate ≥ 45%', value: 'No trades', status: 'fail' as const },
              { label: 'Profit factor ≥ 1.3', value: 'No trades', status: 'fail' as const },
              { label: 'Max DD ≤ 15%', value: 'No data', status: 'fail' as const },
              { label: 'Trades ≥ 50', value: '0 / 50', status: 'fail' as const },
              { label: '30-day paper run', value: '0 / 30 days', status: 'fail' as const },
              { label: 'Direction gate verified', value: 'Unit tested', status: 'pass' as const },
              { label: 'Crypto shorts blocked', value: 'Enforced', status: 'pass' as const },
            ].map((g) => (
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

      {/* Alpaca training data status */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Alpaca training data · ML pipeline</span>
          <span className="card-badge cb-amber">ML module not built yet</span>
        </div>
        <div className="card-body">
          <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.8 }}>
            <div>
              <span style={{ color: 'var(--amber)' }}>·</span>{' '}
              Session 9 (app/ml/) has not been implemented — see audit report.
            </div>
            <div>
              <span style={{ color: 'var(--green)' }}>·</span>{' '}
              Alpaca batch fetcher is ready in{' '}
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
                app/brokers/alpaca.py
              </code>
            </div>
            <div>
              <span style={{ color: 'var(--green)' }}>·</span>{' '}
              Run{' '}
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
                python scripts/seed_alpaca_training.py
              </code>{' '}
              to seed 2yr OHLCV history.
            </div>
            <div>
              <span style={{ color: 'var(--amber)' }}>·</span>{' '}
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
                app/ml/features.py
              </code>
              ,{' '}
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
                trainer.py
              </code>
              ,{' '}
              <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
                predictor.py
              </code>{' '}
              needed to generate signals.
            </div>
            <div>
              <span style={{ color: 'var(--text4)' }}>·</span>{' '}
              Runtime worker visibility now belongs on the Runtime page instead of this analytics screen.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Analytics;