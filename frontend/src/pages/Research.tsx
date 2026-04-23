import React, { useEffect, useMemo, useState } from 'react';

import { getResearchScope, type ResearchScopeResponse } from '../api';
import { useResearch } from '../hooks/useResearch';
import { useWatchlist, type WatchlistFilter, type WatchlistItem } from '../hooks/useWatchlist';
import type { CongressTrade, InsiderTrade, ResearchSignal } from '../hooks/useResearch';

function ScorePill({ score }: { score: number | null }): React.ReactElement {
  if (score === null) {
    return <span className="wl-source">—</span>;
  }
  const rounded = Math.round(score);
  const cls = rounded >= 70 ? 'score-hi' : rounded >= 50 ? 'score-mid' : 'score-lo';
  return <span className={`score-pill ${cls}`}>{rounded}</span>;
}

const SIG_ICON_CLASS: Record<string, string> = {
  congress_buy: 'sig-congress',
  insider_buy: 'sig-insider',
  news_sentiment: 'sig-news',
  screener: 'sig-screener',
  analyst_upgrade: 'sig-news',
};

const SIG_ICON_LABEL: Record<string, string> = {
  congress_buy: 'HO',
  insider_buy: 'IN',
  news_sentiment: 'NW',
  screener: 'SC',
  analyst_upgrade: 'AN',
};

type ResearchScopeItem = WatchlistItem & {
  scope_origin: 'stock_watchlist' | 'crypto_scope';
};

function buildCryptoScopeItems(scope: ResearchScopeResponse | null): ResearchScopeItem[] {
  if (!scope) {
    return [];
  }

  return scope.crypto_watchlist_symbols.map((symbol) => ({
    symbol,
    asset_class: 'crypto',
    added_at: '',
    added_by: 'crypto_scope',
    research_score: null,
    is_active: true,
    notes: 'Derived from backend crypto scope',
    scope_origin: 'crypto_scope',
  }));
}

function buildStockScopeItems(stockWatchlist: WatchlistItem[]): ResearchScopeItem[] {
  return stockWatchlist
    .filter((item) => item.asset_class === 'stock')
    .map((item) => ({ ...item, scope_origin: 'stock_watchlist' as const }));
}

function SignalFeed({ signals }: { signals: ResearchSignal[] }): React.ReactElement {
  if (signals.length === 0) {
    return (
      <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
        No signals stored yet — run congress/insider/news sync tasks
      </div>
    );
  }
  return (
    <div className="signal-feed">
      {signals.slice(0, 20).map((sig) => (
        <div className="signal-item" key={sig.id}>
          <div className={`sig-icon ${SIG_ICON_CLASS[sig.signal_type] ?? 'sig-news'}`}>
            {SIG_ICON_LABEL[sig.signal_type] ?? '??'}
          </div>
          <div className="sig-body">
            <div className="sig-title">{sig.signal_type.replace(/_/g, ' ')}</div>
            <div className="sig-detail">
              {sig.source ?? '—'} · {sig.direction ?? 'neutral'} · {sig.created_at.slice(0, 10)}
            </div>
          </div>
          <div className={`sig-score-col ${(sig.score ?? 0) >= 0 ? 'pos' : 'neg'}`}>
            {sig.score !== null ? `${sig.score >= 0 ? '+' : ''}${sig.score.toFixed(2)}` : '—'}
          </div>
        </div>
      ))}
    </div>
  );
}

function CongressFeed({ trades }: { trades: CongressTrade[] }): React.ReactElement {
  if (trades.length === 0) {
    return (
      <div style={{ fontSize: 11, color: 'var(--text3)', padding: '12px 0' }}>
        No congressional disclosures stored
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {trades.slice(0, 8).map((t) => (
        <div
          key={t.id}
          style={{
            background: 'var(--bg2)',
            border: '0.5px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '8px 12px',
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            gap: 8,
          }}
        >
          <div>
            <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{t.politician}</div>
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>
              {t.chamber.toUpperCase()} · {t.trade_type} · {t.trade_date}
            </div>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text3)', textAlign: 'right' }}>
            {t.committee ?? '—'}
          </div>
        </div>
      ))}
    </div>
  );
}

function InsiderFeed({ trades }: { trades: InsiderTrade[] }): React.ReactElement {
  if (trades.length === 0) {
    return (
      <div style={{ fontSize: 11, color: 'var(--text3)', padding: '12px 0' }}>
        No insider disclosures stored
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {trades.slice(0, 8).map((t) => (
        <div
          key={t.id}
          style={{
            background: 'var(--bg2)',
            border: '0.5px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '8px 12px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{t.insider_name}</span>
            <span style={{ fontSize: 11, color: t.transaction_type === 'P' ? 'var(--green)' : 'var(--red)' }}>
              {t.transaction_type === 'P' ? 'Buy' : 'Sell'}
            </span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>
            {t.title ?? '—'} · {t.total_value != null ? `$${t.total_value.toLocaleString()}` : '—'}
          </div>
        </div>
      ))}
    </div>
  );
}

const FILTERS: { key: WatchlistFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'stock', label: 'Stocks' },
  { key: 'crypto', label: 'Crypto' },
];

const Research: React.FC = () => {
  const { watchlist, loading: wlLoading, error: wlError, refresh } = useWatchlist(30000);
  const [filter, setFilter] = useState<WatchlistFilter>('all');
  const [selected, setSelected] = useState<string>('');
  const [tab, setTab] = useState<'signals' | 'congress' | 'insider'>('signals');
  const [scope, setScope] = useState<ResearchScopeResponse | null>(null);
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [scopeLoading, setScopeLoading] = useState(true);

  useEffect(() => {
    let active = true;

    const loadScope = async (): Promise<void> => {
      try {
        const payload = await getResearchScope();
        if (active) {
          setScope(payload);
          setScopeError(null);
        }
      } catch {
        if (active) {
          setScopeError('Crypto scope unavailable');
        }
      } finally {
        if (active) {
          setScopeLoading(false);
        }
      }
    };

    void loadScope();
    const intervalId = window.setInterval(() => {
      void loadScope();
    }, 30000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const stockItems = useMemo(() => buildStockScopeItems(watchlist), [watchlist]);
  const cryptoItems = useMemo(() => buildCryptoScopeItems(scope), [scope]);
  const allItems = useMemo(() => [...stockItems, ...cryptoItems], [cryptoItems, stockItems]);

  const displayList = useMemo(() => {
    switch (filter) {
      case 'stock':
        return stockItems;
      case 'crypto':
        return cryptoItems;
      default:
        return allItems;
    }
  }, [allItems, cryptoItems, filter, stockItems]);

  const { signals, congress, insider, loading: rLoading, hasData, error: rError } = useResearch(selected, 60000);

  const stockCount = scope?.stock_watchlist_count ?? stockItems.length;
  const cryptoCount = scope?.crypto_watchlist_count ?? cryptoItems.length;
  const scopeUnavailable = !scope && scopeError;

  return (
    <div className="page active">
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Research scope · {stockCount} stock · {cryptoCount} crypto</span>
            <button
              onClick={() => {
                refresh();
              }}
              style={{ fontSize: 9, color: 'var(--text3)', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              ↻ refresh
            </button>
          </div>

          <div style={{ padding: '10px 14px', borderBottom: '0.5px solid var(--border)', fontSize: 11, color: 'var(--text3)', lineHeight: 1.7 }}>
            Stocks come from the research watchlist. Crypto comes from backend crypto scope truth, which currently mirrors the canonical universe.
          </div>

          <div style={{ display: 'flex', borderBottom: '0.5px solid var(--border)' }}>
            {FILTERS.map((item) => {
              const count = item.key === 'stock' ? stockCount : item.key === 'crypto' ? cryptoCount : stockCount + cryptoCount;
              return (
                <button
                  key={item.key}
                  onClick={() => setFilter(item.key)}
                  style={{
                    flex: 1,
                    padding: '7px 0',
                    fontSize: 10,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-mono)',
                    color: filter === item.key ? 'var(--green)' : 'var(--text3)',
                    borderBottom: filter === item.key ? '2px solid var(--green)' : '2px solid transparent',
                  }}
                >
                  {item.label}
                  <span style={{ marginLeft: 4, opacity: 0.6 }}>({count})</span>
                </button>
              );
            })}
          </div>

          {wlLoading || scopeLoading ? (
            <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading…</div>
          ) : wlError ? (
            <div style={{ padding: '16px', fontSize: 11, color: 'var(--red)' }}>{wlError}</div>
          ) : scopeUnavailable ? (
            <div style={{ padding: '16px', fontSize: 11, color: 'var(--amber)' }}>{scopeError}</div>
          ) : displayList.length === 0 ? (
            <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
              No {filter === 'all' ? '' : filter} symbols available right now.
              <div style={{ marginTop: 6, color: 'var(--text4)' }}>
                Stock research promotion and crypto scope are intentionally separate so this page does not pretend one is the other.
              </div>
            </div>
          ) : (
            <div className="card-flush">
              <table className="wl-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Class</th>
                    <th>Score</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {displayList.map((item) => (
                    <tr
                      key={`${item.scope_origin}:${item.symbol}`}
                      className={selected === item.symbol ? 'selected' : ''}
                      onClick={() => setSelected(item.symbol)}
                    >
                      <td style={{ fontWeight: 500 }}>{item.symbol}</td>
                      <td>
                        <span className={`badge badge-${item.asset_class}`}>{item.asset_class}</span>
                      </td>
                      <td>{item.scope_origin === 'crypto_scope' ? <span className="wl-source">scope</span> : <ScorePill score={item.research_score} />}</td>
                      <td>
                        <span className="wl-source">{item.scope_origin === 'crypto_scope' ? 'crypto scope' : item.added_by ?? 'manual'}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">{selected ? `Research · ${selected}` : 'Select a symbol'}</span>
            {selected && !hasData && !rLoading && <span className="card-badge cb-amber">No data yet</span>}
            {selected && hasData && <span className="card-badge cb-green">Live data</span>}
          </div>

          {!selected ? (
            <div style={{ padding: '24px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
              Click a symbol in the scope panel to view its research signals
            </div>
          ) : rLoading ? (
            <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading…</div>
          ) : (
            <>
              <div style={{ display: 'flex', borderBottom: '0.5px solid var(--border)' }}>
                {(['signals', 'congress', 'insider'] as const).map((item) => (
                  <button
                    key={item}
                    onClick={() => setTab(item)}
                    style={{
                      flex: 1,
                      padding: '7px 0',
                      fontSize: 10,
                      letterSpacing: '0.08em',
                      textTransform: 'uppercase',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      fontFamily: 'var(--font-mono)',
                      color: tab === item ? 'var(--green)' : 'var(--text3)',
                      borderBottom: tab === item ? '2px solid var(--green)' : '2px solid transparent',
                    }}
                  >
                    {item}
                    <span style={{ marginLeft: 4, opacity: 0.6 }}>
                      ({item === 'signals' ? signals.length : item === 'congress' ? congress.length : insider.length})
                    </span>
                  </button>
                ))}
              </div>

              {rError && (
                <div style={{ padding: '16px', fontSize: 11, color: 'var(--red)' }}>{rError}</div>
              )}

              {!rError && (
                <div style={{ padding: '12px 16px' }}>
                  {tab === 'signals' ? <SignalFeed signals={signals} /> : null}
                  {tab === 'congress' ? <CongressFeed trades={congress} /> : null}
                  {tab === 'insider' ? <InsiderFeed trades={insider} /> : null}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Research;
