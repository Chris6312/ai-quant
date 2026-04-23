import React, { useState } from 'react';
import { useWatchlist, type WatchlistItem, type WatchlistFilter } from '../hooks/useWatchlist';
import { useResearch } from '../hooks/useResearch';
import type { ResearchSignal, CongressTrade, InsiderTrade } from '../hooks/useResearch';

function ScorePill({ score }: { score: number | null }): React.ReactElement {
  if (score === null) return <span className="wl-source">—</span>;
  const rounded = Math.round(score);
  const cls = rounded >= 70 ? 'score-hi' : rounded >= 50 ? 'score-mid' : 'score-lo';
  return <span className={`score-pill ${cls}`}>{rounded}</span>;
}

const SIG_ICON_CLASS: Record<string, string> = {
  congress_buy:    'sig-congress',
  insider_buy:     'sig-insider',
  news_sentiment:  'sig-news',
  screener:        'sig-screener',
  analyst_upgrade: 'sig-news',
};

const SIG_ICON_LABEL: Record<string, string> = {
  congress_buy: 'HO', insider_buy: 'IN',
  news_sentiment: 'NW', screener: 'SC', analyst_upgrade: 'AN',
};

function SignalFeed({ signals }: { signals: ResearchSignal[] }): React.ReactElement {
  if (signals.length === 0) return (
    <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
      No signals stored yet — run congress/insider/news sync tasks
    </div>
  );
  return (
    <div className="signal-feed">
      {signals.slice(0, 20).map(sig => (
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
  if (trades.length === 0) return (
    <div style={{ fontSize: 11, color: 'var(--text3)', padding: '12px 0' }}>
      No congressional disclosures stored
    </div>
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {trades.slice(0, 8).map(t => (
        <div key={t.id} style={{
          background: 'var(--bg2)', border: '0.5px solid var(--border)',
          borderRadius: 'var(--radius-md)', padding: '8px 12px',
          display: 'grid', gridTemplateColumns: '1fr auto', gap: 8,
        }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{t.politician}</div>
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>
              {t.chamber} · {t.amount_range ?? '—'} · {t.days_to_disclose ?? '?'}d to disclose
            </div>
          </div>
          <span style={{
            fontSize: 9, padding: '2px 6px', borderRadius: 'var(--radius-sm)', alignSelf: 'flex-start',
            background: t.trade_type === 'purchase' ? 'var(--green-bg)' : 'var(--red-bg)',
            color: t.trade_type === 'purchase' ? 'var(--green)' : 'var(--red)',
            border: `0.5px solid ${t.trade_type === 'purchase' ? 'var(--green3)' : 'var(--red3)'}`,
            textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>
            {t.trade_type ?? '—'}
          </span>
        </div>
      ))}
    </div>
  );
}

function InsiderFeed({ trades }: { trades: InsiderTrade[] }): React.ReactElement {
  if (trades.length === 0) return (
    <div style={{ fontSize: 11, color: 'var(--text3)', padding: '12px 0' }}>
      No Form 4 filings stored
    </div>
  );
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {trades.slice(0, 6).map(t => (
        <div key={t.id} style={{
          background: 'var(--bg2)', border: '0.5px solid var(--border)',
          borderRadius: 'var(--radius-md)', padding: '8px 12px',
        }}>
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
  { key: 'all',    label: 'All'    },
  { key: 'stock',  label: 'Stocks' },
  { key: 'crypto', label: 'Crypto' },
];

const Research: React.FC = () => {
  const { watchlist, filtered, loading: wlLoading, error: wlError, refresh } = useWatchlist(30000);
  const [filter, setFilter]   = useState<WatchlistFilter>('all');
  const [selected, setSelected] = useState<string>('');
  const [tab, setTab]           = useState<'signals' | 'congress' | 'insider'>('signals');

  const displayList = filtered(filter);
  const { signals, congress, insider, loading: rLoading, hasData, error: rError } = useResearch(selected, 60000);

  return (
    <div className="page active">
      <div className="grid-2">
        {/* Watchlist panel */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              Watchlist · {watchlist.length} / 20
            </span>
            <button
              onClick={refresh}
              style={{ fontSize: 9, color: 'var(--text3)', background: 'none', border: 'none', cursor: 'pointer' }}
            >
              ↻ refresh
            </button>
          </div>

          {/* Filter tabs */}
          <div style={{ display: 'flex', borderBottom: '0.5px solid var(--border)' }}>
            {FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                style={{
                  flex: 1, padding: '7px 0', fontSize: 10, letterSpacing: '0.08em',
                  textTransform: 'uppercase', background: 'none', border: 'none',
                  cursor: 'pointer', fontFamily: 'var(--font-mono)',
                  color: filter === f.key ? 'var(--green)' : 'var(--text3)',
                  borderBottom: filter === f.key ? '2px solid var(--green)' : '2px solid transparent',
                }}
              >
                {f.label}
                {f.key !== 'all' && (
                  <span style={{ marginLeft: 4, opacity: 0.6 }}>
                    ({watchlist.filter(w => w.asset_class === f.key).length})
                  </span>
                )}
              </button>
            ))}
          </div>

          {wlLoading ? (
            <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading…</div>
          ) : wlError ? (
            <div style={{ padding: '16px', fontSize: 11, color: 'var(--red)' }}>{wlError}</div>
          ) : displayList.length === 0 ? (
            <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
              No {filter === 'all' ? '' : filter} symbols on watchlist yet.
              <div style={{ marginTop: 6, color: 'var(--text4)' }}>
                Crypto scope is defined separately from stock research promotion. In Phase 1, the crypto universe exists even when this research watchlist panel is empty.
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
                    <th>Added by</th>
                  </tr>
                </thead>
                <tbody>
                  {displayList.map(item => (
                    <tr
                      key={item.symbol}
                      className={selected === item.symbol ? 'selected' : ''}
                      onClick={() => setSelected(item.symbol)}
                    >
                      <td style={{ fontWeight: 500 }}>{item.symbol}</td>
                      <td>
                        <span className={`badge badge-${item.asset_class}`}>{item.asset_class}</span>
                      </td>
                      <td><ScorePill score={item.research_score} /></td>
                      <td><span className="wl-source">{item.added_by ?? 'manual'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Research detail panel */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">
              {selected ? `Research · ${selected}` : 'Select a symbol'}
            </span>
            {selected && !hasData && !rLoading && (
              <span className="card-badge cb-amber">No data yet</span>
            )}
            {selected && hasData && (
              <span className="card-badge cb-green">Live data</span>
            )}
          </div>

          {!selected ? (
            <div style={{ padding: '24px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
              Click a symbol in the watchlist to view its research signals
            </div>
          ) : rLoading ? (
            <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading…</div>
          ) : (
            <>
              {/* Sub-tabs */}
              <div style={{ display: 'flex', borderBottom: '0.5px solid var(--border)' }}>
                {(['signals', 'congress', 'insider'] as const).map(t => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    style={{
                      flex: 1, padding: '7px 0', fontSize: 10, letterSpacing: '0.08em',
                      textTransform: 'uppercase', background: 'none', border: 'none',
                      cursor: 'pointer', fontFamily: 'var(--font-mono)',
                      color: tab === t ? 'var(--green)' : 'var(--text3)',
                      borderBottom: tab === t ? '2px solid var(--green)' : '2px solid transparent',
                    }}
                  >
                    {t}
                    <span style={{ marginLeft: 4, opacity: 0.6 }}>
                      ({t === 'signals' ? signals.length : t === 'congress' ? congress.length : insider.length})
                    </span>
                  </button>
                ))}
              </div>

              {rError && (
                <div style={{ margin: '10px 16px', padding: '8px 10px', fontSize: 11, color: 'var(--amber)', background: 'var(--amber-bg)', borderRadius: 'var(--radius-md)', border: '0.5px solid var(--amber2)' }}>
                  {rError}
                </div>
              )}

              <div style={{ padding: tab === 'signals' ? 0 : '12px 16px' }}>
                {tab === 'signals'  && <SignalFeed  signals={signals}   />}
                {tab === 'congress' && <CongressFeed trades={congress}  />}
                {tab === 'insider'  && <InsiderFeed  trades={insider}   />}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Research;
