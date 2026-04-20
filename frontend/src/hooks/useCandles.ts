import { useState, useEffect, useCallback } from 'react';
import { getCandles, type Candle } from '../api';

export type { Candle };

export function useCandles(symbol: string, timeframe: string, limit = 100, intervalMs = 20000): {
  candles: Candle[];
  loading: boolean;
  error: string | null;
} {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    if (!symbol) return;
    try {
      const data = await getCandles(symbol, timeframe, limit);
      // API returns desc order — reverse for chart (oldest first)
      setCandles([...data].reverse());
      setError(null);
    } catch {
      setError(`No candles for ${symbol}`);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, limit]);

  useEffect(() => {
    setCandles([]);
    setLoading(true);
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => clearInterval(id);
  }, [fetch, intervalMs]);

  return { candles, loading, error };
}
