import React from 'react';
import { getKrakenTicker, type KrakenTicker } from '../api';
import { usePortfolio } from '../hooks/usePortfolio';
import { KRAKEN_UNIVERSE } from '../constants';

type Props = { mode: 'paper' | 'live' };

const fmt$ = (n: number) =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function useKrakenTicker(symbols: readonly string[], intervalMs = 30000) {
  const [tickers, setTickers] = React.useState<KrakenTicker[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    const fetchTickers = async () => {
      try {
        const payload = await getKrakenTicker([...symbols]);
        if (cancelled) {
          return;
        }
        setTickers(payload);
        setError(null);
      } catch (err) {
        if (cancelled) {
          return;
        }
        const message = err instanceof Error ? err.message : 'Failed to load Kraken ticker.';
        setError(message);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchTickers();
    const timer = window.setInterval(() => {
      void fetchTickers();
    }, intervalMs);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [intervalMs, symbols]);

  return { tickers, loading, error };
}

function TickerRow({ ticker, loading }: { ticker?: KrakenTicker; loading: boolean }): React.ReactElement {
  const symbol = ticker?.symbol ?? '—';
  const lastPrice = ticker?.last_price ?? null;
  const changePct = ticker?.change_pct ?? null;
  const positive = changePct !== null && changePct >= 0;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '90px 1fr 80px',
        gap: 10,
        alignItems: 'center',
        padding: '8px 0',
        borderBottom: '0.5px solid var(--border)',
      }}
    >
      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)' }}>
        {symbol.replace('/USD', '')}
      </span>
      <span style={{ fontSize: 11, fontVariantNumeric: 'tabular-nums', color: 'var(--text)' }}>
        {loading ? '—' : lastPrice !== null ? `$${fmt$(lastPrice)}` : '—'}
      </span>
      <span
        style={{
          fontSize: 10,
          textAlign: 'right',
          color: changePct === null ? 'var(--text4)' : positive ? 'var(--green)' : 'var(--red)',
        }}
      >
        {loading ? '…' : changePct !== null ? `${positive ? '+' : ''}${changePct.toFixed(2)}%` : '—'}
      </span>
    </div>
  );
}

const Dashboard: React.FC<Props> = ({ mode }) => {
  const { snapshot, system, loading, error } = usePortfolio(mode, 8000);
  const { tickers, loading: tickerLoading, error: tickerError } = useKrakenTicker(KRAKEN_UNIVERSE, 30000);
  const tickerMap = React.useMemo(
    () => new Map(tickers.map((ticker) => [ticker.symbol, ticker])),
    [tickers],
  );
  const btcTicker = tickerMap.get('BTC/USD');

  return (
    <div className="page active">
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {(['api', 'db'] as const).map((key) => (
          <div
            key={key}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: 'var(--bg2)',
              border: '0.5px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '5px 12px',
            }}
          >
            <div
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background:
                  system[key] === 'ok'
                    ? 'var(--green)'
                    : system[key] === 'error'
                      ? 'var(--red)'
                      : 'var(--amber)',
              }}
            />
            <span
              style={{
                fontSize: 10,
                color: 'var(--text3)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
              }}
            >
              {key === 'api' ? `API ${system.version ? `v${system.version}` : ''}` : 'Database'}
            </span>
            <span style={{ fontSize: 10, color: system[key] === 'ok' ? 'var(--green)' : 'var(--red)' }}>
              {system[key]}
            </span>
          </div>
        ))}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: mode === 'paper' ? 'var(--amber-bg)' : 'var(--green-bg)',
            border: `0.5px solid ${mode === 'paper' ? 'var(--amber2)' : 'var(--green3)'}`,
            borderRadius: 'var(--radius-md)',
            padding: '5px 12px',
          }}
        >
          <span
            style={{
              fontSize: 10,
              color: mode === 'paper' ? 'var(--amber)' : 'var(--green)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}
          >
            {mode === 'paper' ? 'Paper trading' : 'Live trading'}
          </span>
        </div>
        {error && (
          <div
            style={{
              fontSize: 10,
              color: 'var(--amber)',
              padding: '5px 12px',
              background: 'var(--amber-bg)',
              borderRadius: 'var(--radius-md)',
              border: '0.5px solid var(--amber2)',
            }}
          >
            {error}
          </div>
        )}
      </div>

      <div className="metrics-row">
        <div className="metric-tile">
          <div className="metric-eyebrow">NAV</div>
          <div className="metric-value">{loading ? '—' : snapshot ? `$${fmt$(snapshot.nav)}` : 'N/A'}</div>
          <div className="metric-sub">Stock + Crypto</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">{mode === 'paper' ? 'Paper stock balance' : 'Tradier cash'}</div>
          <div className="metric-value">
            {loading ? '—' : snapshot ? `$${fmt$(snapshot.stockBalance)}` : 'N/A'}
          </div>
          <div
            className="metric-sub"
            style={{ color: snapshot?.shortEligible ? 'var(--green2)' : 'var(--red2)' }}
          >
            {snapshot ? (snapshot.shortEligible ? 'Shorts eligible' : 'Shorts blocked — need >$2,500') : ''}
          </div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">{mode === 'paper' ? 'Paper crypto balance' : 'Kraken USD equiv'}</div>
          <div className="metric-value">
            {loading ? '—' : snapshot ? `$${fmt$(snapshot.cryptoBalance)}` : 'N/A'}
          </div>
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
              : snapshot
                ? `${snapshot.openOrderCount} pending orders`
                : ''}
          </div>
        </div>
      </div>

      {mode === 'paper' && snapshot && (
        <div
          style={{
            padding: '10px 16px',
            background: 'var(--bg2)',
            border: '0.5px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            display: 'flex',
            gap: 24,
            alignItems: 'center',
          }}
        >
          <div>
            <div
              style={{
                fontSize: 9,
                color: 'var(--text3)',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                marginBottom: 4,
              }}
            >
              Realized P&L (paper)
            </div>
            <div
              style={{
                fontSize: 18,
                fontWeight: 500,
                color: snapshot.realizedPnl >= 0 ? 'var(--green)' : 'var(--red)',
              }}
            >
              {snapshot.realizedPnl >= 0 ? '+' : ''}${fmt$(snapshot.realizedPnl)}
            </div>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.7 }}>
            Resets when backend restarts. Persistent P&L requires migration 0002 (trades table).
          </div>
        </div>
      )}

      <div className="grid-3-1">
        <div className="card">
          <div className="card-header">
            <span className="card-title">BTC/USD · Kraken ticker</span>
            <span
              style={{
                fontSize: 9,
                color: btcTicker
                  ? btcTicker.change_pct >= 0
                    ? 'var(--green)'
                    : 'var(--red)'
                  : 'var(--text3)',
              }}
            >
              {tickerLoading
                ? 'loading…'
                : btcTicker
                  ? `${btcTicker.change_pct >= 0 ? '+' : ''}${btcTicker.change_pct.toFixed(2)}% vs open`
                  : 'ticker unavailable'}
            </span>
          </div>
          <div className="card-body">
            <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 6 }}>Current price</div>
            <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--text)' }}>
              {tickerLoading ? '—' : btcTicker ? `$${fmt$(btcTicker.last_price)}` : '—'}
            </div>
            <div
              style={{
                marginTop: 8,
                fontSize: 11,
                color: btcTicker
                  ? btcTicker.change_pct >= 0
                    ? 'var(--green)'
                    : 'var(--red)'
                  : 'var(--text4)',
              }}
            >
              {tickerLoading
                ? 'Refreshing Kraken ticker…'
                : btcTicker
                  ? `${btcTicker.change_pct >= 0 ? '+' : ''}${btcTicker.change_pct.toFixed(2)}% from daily open`
                  : tickerError ?? 'Ticker unavailable'}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Direction gate</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 11,
                padding: '4px 0',
                borderBottom: '0.5px solid var(--border)',
              }}
            >
              <span style={{ color: 'var(--text3)' }}>Crypto shorts</span>
              <span style={{ color: 'var(--red)' }}>Always blocked</span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 11,
                padding: '4px 0',
                borderBottom: '0.5px solid var(--border)',
              }}
            >
              <span style={{ color: 'var(--text3)' }}>Stock shorts</span>
              <span style={{ color: snapshot?.shortEligible ? 'var(--green)' : 'var(--red)' }}>
                {loading ? '…' : snapshot?.shortEligible ? 'Eligible' : 'Blocked'}
              </span>
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 11,
                padding: '4px 0',
              }}
            >
              <span style={{ color: 'var(--text3)' }}>Max positions</span>
              <span style={{ color: 'var(--text)' }}>5</span>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Kraken market snapshot</span>
          <span className="card-badge cb-blue">Ticker price + % from daily open</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 24px', padding: '0 16px' }}>
          {KRAKEN_UNIVERSE.map((symbol) => (
            <TickerRow
              key={symbol}
              ticker={tickerMap.get(symbol)}
              loading={tickerLoading}
            />
          ))}
        </div>
        {tickerError && (
          <div style={{ padding: '0 16px 12px', fontSize: 10, color: 'var(--amber)' }}>{tickerError}</div>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
