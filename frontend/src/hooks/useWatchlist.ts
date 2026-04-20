import { useState, useEffect, useCallback } from 'react';
import { getWatchlist, type WatchlistItem } from '../api';

export type { WatchlistItem };

export type WatchlistFilter = 'all' | 'stock' | 'crypto';

export function useWatchlist(intervalMs = 30000): {
  watchlist: WatchlistItem[];
  filtered: (f: WatchlistFilter) => WatchlistItem[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
} {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      const data = await getWatchlist();
      setWatchlist(data);
      setError(null);
    } catch {
      setError('Watchlist unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => clearInterval(id);
  }, [fetch, intervalMs]);

  const filtered = useCallback(
    (f: WatchlistFilter) =>
      f === 'all' ? watchlist : watchlist.filter(w => w.asset_class === f),
    [watchlist],
  );

  return { watchlist, filtered, loading, error, refresh: fetch };
}
