import { useState, useEffect, useCallback } from 'react';
import { requestJson } from '../api';

export type ResearchSignal = {
  id: string;
  symbol: string;
  signal_type: string;
  score: number | null;
  direction: string | null;
  source: string | null;
  raw_data: Record<string, unknown> | null;
  created_at: string;
};

export type CongressTrade = {
  id: string;
  politician: string;
  chamber: string | null;
  symbol: string;
  trade_type: string | null;
  amount_range: string | null;
  trade_date: string | null;
  disclosure_date: string | null;
  days_to_disclose: number | null;
  created_at: string;
};

export type InsiderTrade = {
  id: string;
  symbol: string;
  insider_name: string;
  title: string | null;
  transaction_type: string | null;
  total_value: number | null;
  filing_date: string | null;
  transaction_date: string | null;
};

export type ResearchData = {
  signals: ResearchSignal[];
  congress: CongressTrade[];
  insider: InsiderTrade[];
  loading: boolean;
  hasData: boolean;
  error: string | null;
};

export function useResearch(symbol: string, intervalMs = 60000): ResearchData {
  const [signals,  setSignals]  = useState<ResearchSignal[]>([]);
  const [congress, setCongress] = useState<CongressTrade[]>([]);
  const [insider,  setInsider]  = useState<InsiderTrade[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [hasData,  setHasData]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!symbol) { setLoading(false); return; }

    const enc = encodeURIComponent(symbol);
    const [sigR, conR, insR] = await Promise.allSettled([
      requestJson<ResearchSignal[]>(`/research/signals?symbol=${enc}`),
      requestJson<CongressTrade[]>(`/research/congress?symbol=${enc}`),
      requestJson<InsiderTrade[]>(`/research/insider?symbol=${enc}`),
    ]);

    const sig = sigR.status === 'fulfilled' ? sigR.value : [];
    const con = conR.status === 'fulfilled' ? conR.value : [];
    const ins = insR.status === 'fulfilled' ? insR.value : [];

    setSignals(sig);
    setCongress(con);
    setInsider(ins);

    const anyData = sig.length > 0 || con.length > 0 || ins.length > 0;
    setHasData(anyData);
    setError(anyData ? null : 'No research data yet — sync tasks have not run');
    setLoading(false);
  }, [symbol]);

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs]);

  return { signals, congress, insider, loading, hasData, error };
}
