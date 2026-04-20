import React from 'react';
import { usePortfolio } from '../hooks/usePortfolio';
import { useCandles, type Candle } from '../hooks/useCandles';
import { KRAKEN_UNIVERSE } from '../constants';

type Props = { mode: 'paper' | 'live' };

const fmt$ = (n: number) =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function MiniSparkline({ candles }: { candles: Candle[] }): React.ReactElement {
  const closes = candles.map(c => c.close ?? 0).filter(v => v > 0);
  if (closes.length < 2) return <span style={{ fontSize: 10, color: 'var(--text4)' }}>no data</span>;
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const W = 80; const H = 24;
  const pts = closes.map((v, i) => {
    const x = (i / (closes.length - 1)) * W;
    const y = max === min ? H / 2 : H - ((v - min) / (max - min)) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const isUp = closes[closes.length - 1] >= closes[0];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: W, height: H, display: 'block' }}>
      <polyline points={pts} fill="none" stroke={isUp ? 'var(--green)' : 'var(--red)'} strokeWidth="1.5" />
    </svg>
  );
}

function CryptoRow({ symbol }: { symbol: string }): React.ReactElement {
  const { candles, loading } = useCandles(symbol, '1h', 30, 30000);
  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];
  const close = last?.close ?? null;
  const pct   = (close && prev?.close) ? ((close - prev.close) / prev.close) * 100 : null;
  const isUp  = pct !== null && pct >= 0;

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '90px 90px 1fr 50px 44px',
      gap: 10, alignItems: 'center', padding: '6px 0',
      borderBottom: '0.5px solid var(--border)',
    }}>
      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)' }}>{symbol.replace('/USD', '')}</span>
      <span style={{ fontSize: 11, fontVariantNumeric: 'tabular-nums', color: 'var(--text)' }}>
        {loading ? '—' : close ? `$${close.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—'}
      </span>
      <MiniSparkline candles={candles} />
      <span style={{ fontSize: 10, color: isUp ? 'var(--green)' : 'var(--red)', textAlign: 'right' }}>
        {pct !== null ? `${isUp ? '+' : ''}${pct.toFixed(2)}%` : '—'}
      </span>
      <span style={{ fontSize: 9, letterSpacing: '0.08em', textAlign: 'right',
        color: candles.length > 0 ? 'var(--green)' : 'var(--text4)' }}>
        {loading ? '…' : candles.length > 0 ? 'DATA' : 'EMPTY'}
      </span>
    </div>
  );
}

function BtcChart({ candles }: { candles: Candle[] }): React.ReactElement {
  const closes = candles.map(c => c.close ?? 0).filter(v => v > 0);
  if (closes.length < 2) {
    return (
      <div style={{ height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontSize: 11, color: 'var(--text3)' }}>Awaiting backfill…</span>
      </div>
    );
  }
  const min = Math.min(...closes); const max = Math.max(...closes);
  const W = 400; const H = 100;
  const pts = closes.map((v, i) => {
    const x = (i / (closes.length - 1)) * W;
    const y = max === min ? H / 2 : H - ((v - min) / (max - min)) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const isUp = closes[closes.length - 1] >= closes[0];
  const color = isUp ? 'var(--green)' : 'var(--red)';
  return (
    <div style={{ height: 120 }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: '100%', height: '100%' }}>
        <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
      </svg>
    </div>
  );
}

const Dashboard: React.FC<Props> = ({ mode }) => {
  const { snapshot, system, loading, error } = usePortfolio(mode, 8000);
  const btc = useCandles('BTC/USD', '1h', 100, 30000);

  return (
    <div className="page active">

      {/* System status */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {(['api', 'db'] as const).map(key => (
          <div key={key} style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: 'var(--bg2)', border: '0.5px solid var(--border)',
            borderRadius: 'var(--radius-md)', padding: '5px 12px',
          }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: system[key] === 'ok' ? 'var(--green)' : system[key] === 'error' ? 'var(--red)' : 'var(--amber)',
            }} />
            <span style={{ fontSize: 10, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              {key === 'api' ? `API ${system.version ? `v${system.version}` : ''}` : 'Database'}
            </span>
            <span style={{ fontSize: 10, color: system[key] === 'ok' ? 'var(--green)' : 'var(--red)' }}>
              {system[key]}
            </span>
          </div>
        ))}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: mode === 'paper' ? 'var(--amber-bg)' : 'var(--green-bg)',
          border: `0.5px solid ${mode === 'paper' ? 'var(--amber2)' : 'var(--green3)'}`,
          borderRadius: 'var(--radius-md)', padding: '5px 12px',
        }}>
          <span style={{ fontSize: 10, color: mode === 'paper' ? 'var(--amber)' : 'var(--green)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            {mode === 'paper' ? 'Paper trading' : 'Live trading'}
          </span>
        </div>
        {error && (
          <div style={{ fontSize: 10, color: 'var(--amber)', padding: '5px 12px', background: 'var(--amber-bg)', borderRadius: 'var(--radius-md)', border: '0.5px solid var(--amber2)' }}>
            {error}
          </div>
        )}
      </div>

      {/* Portfolio metrics — source-aware */}
      <div className="metrics-row">
        <div className="metric-tile">
          <div className="metric-eyebrow">NAV</div>
          <div className="metric-value">{loading ? '—' : snapshot ? `$${fmt$(snapshot.nav)}` : 'N/A'}</div>
          <div className="metric-sub">Stock + Crypto</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">
            {mode === 'paper' ? 'Paper stock balance' : 'Tradier cash'}
          </div>
          <div className="metric-value">{loading ? '—' : snapshot ? `$${fmt$(snapshot.stockBalance)}` : 'N/A'}</div>
          <div className="metric-sub" style={{ color: snapshot?.shortEligible ? 'var(--green2)' : 'var(--red2)' }}>
            {snapshot ? (snapshot.shortEligible ? 'Shorts eligible' : 'Shorts blocked — need >$2,500') : ''}
          </div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">
            {mode === 'paper' ? 'Paper crypto balance' : 'Kraken USD equiv'}
          </div>
          <div className="metric-value">{loading ? '—' : snapshot ? `$${fmt$(snapshot.cryptoBalance)}` : 'N/A'}</div>
          <div className="metric-sub">Long only</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">Open positions</div>
          <div className="metric-value">
            {loading ? '—' : snapshot ? `${snapshot.openPositionCount} / 5` : 'N/A'}
          </div>
          <div className="metric-sub" style={{ color: 'var(--text3)' }}>
            {mode === 'paper'
              ? 'GET /positions not yet built'
              : snapshot ? `${snapshot.openOrderCount} pending orders` : ''}
          </div>
        </div>
      </div>

      {/* Realized P&L (paper only) */}
      {mode === 'paper' && snapshot && (
        <div style={{
          padding: '10px 16px', background: 'var(--bg2)',
          border: '0.5px solid var(--border)', borderRadius: 'var(--radius-md)',
          display: 'flex', gap: 24, alignItems: 'center',
        }}>
          <div>
            <div style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 4 }}>
              Realized P&L (paper)
            </div>
            <div style={{ fontSize: 18, fontWeight: 500, color: snapshot.realizedPnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
              {snapshot.realizedPnl >= 0 ? '+' : ''}${fmt$(snapshot.realizedPnl)}
            </div>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.7 }}>
            Resets when backend restarts. Persistent P&L requires migration 0002 (trades table).
          </div>
        </div>
      )}

      <div className="grid-3-1">
        {/* BTC chart */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">BTC/USD · 1h · Kraken candles</span>
            <span style={{ fontSize: 9, color: btc.candles.length > 0 ? 'var(--green)' : 'var(--text3)' }}>
              {btc.candles.length > 0 ? `${btc.candles.length} candles` : 'awaiting backfill'}
            </span>
          </div>
          <div className="card-body-sm">
            <BtcChart candles={btc.candles} />
          </div>
        </div>

        <div className="card">
          <div className="card-header"><span className="card-title">Direction gate</span></div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '4px 0', borderBottom: '0.5px solid var(--border)' }}>
              <span style={{ color: 'var(--text3)' }}>Crypto shorts</span>
              <span style={{ color: 'var(--red)' }}>Always blocked</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '4px 0', borderBottom: '0.5px solid var(--border)' }}>
              <span style={{ color: 'var(--text3)' }}>Stock shorts</span>
              <span style={{ color: snapshot?.shortEligible ? 'var(--green)' : 'var(--red)' }}>
                {loading ? '…' : snapshot?.shortEligible ? 'Eligible' : 'Blocked'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, padding: '4px 0' }}>
              <span style={{ color: 'var(--text3)' }}>Max positions</span>
              <span style={{ color: 'var(--text)' }}>5</span>
            </div>
          </div>
        </div>
      </div>

      {/* Crypto universe table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Kraken universe · 15 pairs · live candle status</span>
          <span className="card-badge cb-blue">Polls every 30s · 0 candles = run ML backfill</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px', padding: '0 16px' }}>
          {KRAKEN_UNIVERSE.map(sym => <CryptoRow key={sym} symbol={sym} />)}
        </div>
      </div>

    </div>
  );
};

export default Dashboard;
