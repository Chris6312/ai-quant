import { useEffect, useMemo, useState } from 'react';

import Chart from './components/Chart';
import KillSwitch from './components/KillSwitch';
import PortfolioSummary from './components/PortfolioSummary';
import PositionCard from './components/PositionCard';
import ResearchPanel from './components/ResearchPanel';
import StrategyPanel from './components/StrategyPanel';
import WatchlistTable from './components/WatchlistTable';
import { requestJson } from './api';

type HealthResponse = { status: string; app?: string; version?: string };
type ReadyResponse = { status: string };
type WatchlistEntry = { symbol: string; asset_class: string; research_score: number | null; added_by: string | null };
type ReconcileResponse = {
  internal_open_positions: number;
  open_orders: Record<string, number>;
  balances: {
    kraken?: Record<string, number>;
    tradier?: Record<string, number>;
  };
};

const samplePositions = [
  { symbol: 'AAPL', side: 'long', entryPrice: 182.14, currentPrice: 188.92, size: 12, mlConfidence: 0.84, researchScore: 76 },
  { symbol: 'BTC/USD', side: 'long', entryPrice: 62350.0, currentPrice: 64120.0, size: 0.21, mlConfidence: 0.77, researchScore: 0 },
];

const sampleResearch = [
  { symbol: 'AAPL', news: 72, congress: 40, insider: 55, analyst: 67 },
  { symbol: 'NVDA', news: 83, congress: 71, insider: 44, analyst: 79 },
  { symbol: 'MSFT', news: 61, congress: 35, insider: 40, analyst: 59 },
];

const sampleStrategies = [
  { name: 'momentum', enabled: true, riskMultiplier: 1.0 },
  { name: 'mean_reversion', enabled: true, riskMultiplier: 0.9 },
  { name: 'vwap', enabled: true, riskMultiplier: 0.8 },
  { name: 'breakout', enabled: true, riskMultiplier: 1.1 },
];

const sampleCandles = [
  { time: '09:30', close: 100 },
  { time: '10:00', close: 102 },
  { time: '10:30', close: 101 },
  { time: '11:00', close: 104 },
  { time: '11:30', close: 108 },
  { time: '12:00', close: 107 },
  { time: '12:30', close: 110 },
];

export default function App(): JSX.Element {
  const [health, setHealth] = useState<HealthResponse>({ status: 'loading' });
  const [ready, setReady] = useState<ReadyResponse>({ status: 'loading' });
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [reconcile, setReconcile] = useState<ReconcileResponse | null>(null);
  const [halted, setHalted] = useState(false);

  useEffect(() => {
    void requestJson<HealthResponse>('/health').then(setHealth).catch(() => setHealth({ status: 'offline' }));
    void requestJson<ReadyResponse>('/ready').then(setReady).catch(() => setReady({ status: 'offline' }));
    void requestJson<WatchlistEntry[]>('/watchlist').then(setWatchlist).catch(() => setWatchlist([]));
    void requestJson<ReconcileResponse>('/admin/reconcile').then(setReconcile).catch(() => setReconcile(null));
  }, []);

  const portfolio = useMemo(() => {
    const kraken = reconcile?.balances.kraken;
    const tradier = reconcile?.balances.tradier;
    const stockBalance = tradier?.cash ?? 12_500;
    const cryptoBalance = kraken?.usd ?? 18_000;
    return {
      nav: (tradier?.equity ?? 120_000) + (kraken?.crypto_usd_equiv ?? 0),
      dailyPnl: 2_342.88,
      stockBalance,
      cryptoBalance,
      shortEligible: stockBalance > 2_500,
    };
  }, [reconcile]);

  const appName = health.app ?? 'ML Trading Bot';
  const version = health.version ?? '0.1.0';

  const handleHalt = async (): Promise<void> => {
    try {
      await requestJson<{ status: string }>('/admin/halt', { method: 'POST' });
      setHalted(true);
    } catch {
      setHalted(true);
    }
  };

  return (
    <main className="dashboard">
      <PortfolioSummary
        appName={appName}
        version={version}
        healthStatus={health.status}
        readyStatus={ready.status}
        portfolio={portfolio}
      />

      <div className="grid two-up">
        <Chart symbol="AAPL" candles={sampleCandles} />
        <KillSwitch onHalt={handleHalt} halted={halted} />
      </div>

      <div className="grid two-up">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Position cards</p>
              <h2>Open positions</h2>
            </div>
            <span className="status-pill">{samplePositions.length} open</span>
          </div>
          <div className="positions-list">
            {samplePositions.map((position) => (
              <PositionCard key={position.symbol} {...position} />
            ))}
          </div>
        </section>

        <WatchlistTable
          items={
            watchlist.length > 0
              ? watchlist
              : [
                  { symbol: 'AAPL', asset_class: 'stock', research_score: 82, added_by: 'manual' },
                  { symbol: 'NVDA', asset_class: 'stock', research_score: 91, added_by: 'ml_screener' },
                ]
          }
        />
      </div>

      <div className="grid two-up">
        <ResearchPanel signals={sampleResearch} />
        <StrategyPanel strategies={sampleStrategies} />
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Monitoring & alerting</p>
            <h2>Reconciliation snapshot</h2>
          </div>
          <span className="status-pill">{reconcile ? 'live' : 'mock'}</span>
        </div>
        <div className="metrics-grid compact">
          <div className="metric-card"><span className="metric-label">Open positions</span><strong>{reconcile?.internal_open_positions ?? 2}</strong></div>
          <div className="metric-card"><span className="metric-label">Kraken orders</span><strong>{reconcile?.open_orders.kraken ?? 0}</strong></div>
          <div className="metric-card"><span className="metric-label">Tradier orders</span><strong>{reconcile?.open_orders.tradier ?? 0}</strong></div>
          <div className="metric-card"><span className="metric-label">Watchlist size</span><strong>{watchlist.length || 2}</strong></div>
        </div>
        <p className="muted">Telegram alerts: worker silence, circuit breakers, watchlist promotions, and research spikes.</p>
      </section>
    </main>
  );
}
