import React, { useState, useEffect, useCallback } from 'react';
import { getOrders, exportOrdersCsv, type OrderEntry, type OrdersFilter } from '../api';

const fmtPrice = (v?: number | null) =>
  v != null ? `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}` : '—';
const fmtDate  = (v?: string | null) => v ? v.slice(0, 16).replace('T', ' ') : '—';

const OrderLog: React.FC = () => {
  const [orders,   setOrders]   = useState<OrderEntry[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  const [source,   setSource]   = useState('all');
  const [side,     setSide]     = useState('');
  const [acFilter, setAcFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo,   setDateTo]   = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    const f: OrdersFilter = { source, limit: 500 };
    if (side)     f.status    = undefined;  // side is in paper orders only, skip status filter
    if (acFilter) f.asset_class = acFilter;
    if (dateFrom) f.date_from = dateFrom;
    if (dateTo)   f.date_to   = dateTo;
    try {
      const data = await getOrders(f);
      // Apply side filter client-side since it comes from both sources
      const filtered = side ? data.filter(o => o.side === side) : data;
      setOrders(filtered);
      setError(null);
    } catch {
      setError('Order log unavailable — ensure the backend is running');
    } finally {
      setLoading(false);
    }
  }, [source, side, acFilter, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const totalBuys  = orders.filter(o => o.side === 'buy').length;
  const totalSells = orders.filter(o => o.side === 'sell').length;

  const sel = (val: string, onChange: (v: string) => void, opts: string[][]) => (
    <select className="select-ctrl" value={val} onChange={e => onChange(e.target.value)}>
      {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );

  return (
    <div className="page active">
      {/* Filters */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Filters</span>
          <button onClick={load} style={{ fontSize: 9, color: 'var(--text3)', background: 'none', border: 'none', cursor: 'pointer' }}>
            ↻ refresh
          </button>
        </div>
        <div className="card-body" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Source</span>
            {sel(source, setSource, [['all','All'],['live','Live'],['paper','Paper']])}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Side</span>
            {sel(side, setSide, [['','All'],['buy','Buy'],['sell','Sell']])}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Asset class</span>
            {sel(acFilter, setAcFilter, [['','All'],['stock','Stocks'],['crypto','Crypto']])}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>From</span>
            <input type="date" className="select-ctrl" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ width: 130 }} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <span style={{ fontSize: 9, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>To</span>
            <input type="date" className="select-ctrl" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ width: 130 }} />
          </div>
          <a
            href={exportOrdersCsv(source, dateFrom || undefined, dateTo || undefined)}
            download
            style={{
              padding: '6px 14px', background: 'var(--green-bg)', border: '0.5px solid var(--green3)',
              color: 'var(--green)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)',
              fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase',
              textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6,
            }}
          >
            Export CSV
          </a>
        </div>
      </div>

      {/* Summary counts */}
      <div className="metrics-row">
        <div className="metric-tile">
          <div className="metric-eyebrow">Total orders</div>
          <div className="metric-value">{loading ? '—' : orders.length}</div>
          <div className="metric-sub">{source} · filtered</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">Buys</div>
          <div className="metric-value pos">{loading ? '—' : totalBuys}</div>
          <div className="metric-sub">Long entries</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">Sells / exits</div>
          <div className="metric-value neg">{loading ? '—' : totalSells}</div>
          <div className="metric-sub">Closes + shorts</div>
        </div>
        <div className="metric-tile">
          <div className="metric-eyebrow">Showing</div>
          <div className="metric-value">{loading ? '—' : Math.min(orders.length, 500)}</div>
          <div className="metric-sub">Max 500 per query</div>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--red-bg)', border: '0.5px solid var(--red3)', borderRadius: 'var(--radius-md)', fontSize: 11, color: 'var(--red)' }}>
          {error}
        </div>
      )}

      {/* Order table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Order history</span>
          {!loading && orders.length === 0 && (
            <span className="card-badge cb-muted">No orders</span>
          )}
        </div>
        {loading ? (
          <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)' }}>Loading…</div>
        ) : orders.length === 0 ? (
          <div style={{ padding: '24px 16px', fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>
            No orders found for the selected filters.
            <div style={{ marginTop: 6, color: 'var(--text4)' }}>
              Paper orders are added via POST /paper/orders/add. Live orders come from PositionRow records.
            </div>
          </div>
        ) : (
          <div className="card-flush" style={{ overflowX: 'auto' }}>
            <table className="wl-table" style={{ minWidth: 800 }}>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Class</th>
                  <th>Price</th>
                  <th>Size</th>
                  <th>Value</th>
                  <th>Strategy</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {orders.map(o => {
                  const price = o.entry_price ?? o.price ?? null;
                  const value = o.entry_value ?? o.gross ?? null;
                  const date  = o.opened_at ?? o.created_at ?? null;
                  return (
                    <tr key={o.id}>
                      <td style={{ fontWeight: 500 }}>{o.symbol}</td>
                      <td>
                        <span className={`badge ${o.side === 'buy' ? 'badge-long' : 'badge-short'}`}>
                          {o.side}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-${o.asset_class}`}>{o.asset_class}</span>
                      </td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(price)}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{o.size?.toLocaleString() ?? '—'}</td>
                      <td style={{ fontVariantNumeric: 'tabular-nums' }}>{fmtPrice(value)}</td>
                      <td style={{ fontSize: 10, color: 'var(--text3)' }}>{o.strategy_id ?? '—'}</td>
                      <td>
                        <span className={`card-badge ${o.source === 'paper' ? 'cb-amber' : 'cb-green'}`}>
                          {o.source}
                        </span>
                      </td>
                      <td style={{ fontSize: 10, color: 'var(--text3)' }}>{o.status ?? '—'}</td>
                      <td style={{ fontSize: 10, color: 'var(--text3)', whiteSpace: 'nowrap' }}>{fmtDate(date)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default OrderLog;
