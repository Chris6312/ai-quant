import { useState, useEffect, useCallback } from 'react';
import { getHealth, getReady, getReconcile, getPaperBalance } from '../api';

export type SystemStatus = {
  api: 'ok' | 'error' | 'loading';
  db:  'ok' | 'error' | 'loading';
  version: string;
};

export type PortfolioSnapshot = {
  stockBalance:      number;
  cryptoBalance:     number;
  nav:               number;
  openPositionCount: number;
  openOrderCount:    number;
  shortEligible:     boolean;
  realizedPnl:       number;
  source:            'paper' | 'live';
};

const STOCK_SHORT_THRESHOLD = 2500;

export function usePortfolio(mode: 'paper' | 'live', intervalMs = 8000): {
  snapshot: PortfolioSnapshot | null;
  system:   SystemStatus;
  loading:  boolean;
  error:    string | null;
  refresh:  () => void;
} {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [system,   setSystem]   = useState<SystemStatus>({ api: 'loading', db: 'loading', version: '' });
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  const fetch = useCallback(async () => {
    // Always check API/DB health
    const [health, ready] = await Promise.allSettled([getHealth(), getReady()]);
    const apiOk   = health.status === 'fulfilled';
    const dbOk    = ready.status  === 'fulfilled';
    setSystem({
      api:     apiOk ? 'ok' : 'error',
      db:      dbOk  ? 'ok' : 'error',
      version: apiOk ? health.value.version : '',
    });

    if (mode === 'paper') {
      // Paper mode: read from /paper/balance which is always available
      try {
        const bal = await getPaperBalance();
        setSnapshot({
          stockBalance:      bal.stock_balance,
          cryptoBalance:     bal.crypto_balance,
          nav:               bal.nav,
          openPositionCount: 0,   // /positions endpoint not yet built
          openOrderCount:    0,
          shortEligible:     bal.stock_balance > STOCK_SHORT_THRESHOLD,
          realizedPnl:       bal.realized_pnl,
          source:            'paper',
        });
        setError(null);
      } catch {
        setError('Paper ledger unavailable — is the backend running?');
      }
    } else {
      // Live mode: read from /admin/reconcile which calls actual brokers
      try {
        const r = await getReconcile();
        const k = r.balances['kraken']  ?? {};
        const t = r.balances['tradier'] ?? {};
        const tradierCash = t['cash'] ?? 0;
        const cryptoTotal = (k['usd'] ?? 0) + (k['crypto_usd_equiv'] ?? 0);
        const totalOrders = Object.values(r.open_orders).reduce((a, b) => a + b, 0);
        setSnapshot({
          stockBalance:      tradierCash,
          cryptoBalance:     cryptoTotal,
          nav:               tradierCash + cryptoTotal,
          openPositionCount: r.internal_open_positions,
          openOrderCount:    totalOrders,
          shortEligible:     tradierCash > STOCK_SHORT_THRESHOLD,
          realizedPnl:       0,
          source:            'live',
        });
        setError(null);
      } catch {
        setError('Live broker reconcile unavailable — check API keys in .env');
      }
    }
    setLoading(false);
  }, [mode]);

  useEffect(() => {
    setLoading(true);
    setSnapshot(null);
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => clearInterval(id);
  }, [fetch, intervalMs, mode]);

  return { snapshot, system, loading, error, refresh: fetch };
}
