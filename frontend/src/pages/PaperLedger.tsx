import React, { useState, useEffect, useCallback } from 'react';
import { getPaperBalance, setPaperBalance, resetPaperBalance, type PaperBalance } from '../api';

const fmt$ = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });

const PaperLedger: React.FC = () => {
  const [balance, setBalance]   = useState<PaperBalance | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error,   setError]     = useState<string | null>(null);
  const [stockIn, setStockIn]   = useState('');
  const [cryptoIn,setCryptoIn]  = useState('');
  const [saving,  setSaving]    = useState(false);
  const [msg,     setMsg]       = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const b = await getPaperBalance();
      setBalance(b);
      setError(null);
    } catch {
      setError('Paper ledger endpoint unavailable — is the backend running?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleSet(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const stock  = stockIn  ? parseFloat(stockIn)  : undefined;
      const crypto = cryptoIn ? parseFloat(cryptoIn) : undefined;
      const b = await setPaperBalance(stock, crypto);
      setBalance(b);
      setMsg('Balances updated');
      setStockIn(''); setCryptoIn('');
    } catch { setMsg('Failed to update — check backend'); }
    finally { setSaving(false); setTimeout(() => setMsg(null), 3000); }
  }

  async function handleReset(ac: 'stock' | 'crypto' | 'all') {
    try {
      const b = await resetPaperBalance(ac);
      setBalance(b);
      setMsg(`${ac} reset to default`);
    } catch { setMsg('Reset failed'); }
    setTimeout(() => setMsg(null), 3000);
  }

  const tile = (label: string, val: string, sub?: string, color?: string) => (
    <div className="metric-tile">
      <div className="metric-eyebrow">{label}</div>
      <div className="metric-value" style={color ? { color } : {}}>{val}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );

  return (
    <div className="page active">
      <div className="metrics-row">
        {tile('NAV', loading ? '—' : balance ? fmt$(balance.nav) : 'N/A', 'Stock + Crypto')}
        {tile('Stock balance', loading ? '—' : balance ? fmt$(balance.stock_balance) : 'N/A',
          balance ? `Default: ${fmt$(balance.stock_default)}` : '')}
        {tile('Crypto balance', loading ? '—' : balance ? fmt$(balance.crypto_balance) : 'N/A',
          balance ? `Default: ${fmt$(balance.crypto_default)}` : '')}
        {tile('Realized P&L', loading ? '—' : balance ? fmt$(balance.realized_pnl) : 'N/A',
          'Closed trades only', balance && balance.realized_pnl >= 0 ? 'var(--green)' : 'var(--red)')}
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--red-bg)', border: '0.5px solid var(--red3)', borderRadius: 'var(--radius-md)', fontSize: 11, color: 'var(--red)' }}>
          {error}
        </div>
      )}

      {msg && (
        <div style={{ padding: '10px 14px', background: 'var(--green-bg)', border: '0.5px solid var(--green3)', borderRadius: 'var(--radius-md)', fontSize: 11, color: 'var(--green)' }}>
          {msg}
        </div>
      )}

      <div className="grid-2">
        {/* Set custom balances */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Set custom balance</span>
            <span className="card-badge cb-amber">Paper only</span>
          </div>
          <div className="card-body">
            <form onSubmit={handleSet} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 10, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                  Stock balance (Tradier)
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13, color: 'var(--text3)' }}>$</span>
                  <input
                    className="num-input" type="number" min="0" step="100"
                    placeholder={balance ? balance.stock_balance.toFixed(2) : '100000'}
                    value={stockIn} onChange={e => setStockIn(e.target.value)}
                    style={{ width: '100%', textAlign: 'left' }}
                  />
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 10, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                  Crypto balance (Kraken)
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13, color: 'var(--text3)' }}>$</span>
                  <input
                    className="num-input" type="number" min="0" step="100"
                    placeholder={balance ? balance.crypto_balance.toFixed(2) : '100000'}
                    value={cryptoIn} onChange={e => setCryptoIn(e.target.value)}
                    style={{ width: '100%', textAlign: 'left' }}
                  />
                </div>
              </div>
              <button
                type="submit" disabled={saving || (!stockIn && !cryptoIn)}
                style={{
                  padding: '9px 0', background: 'var(--green-bg)', border: '0.5px solid var(--green3)',
                  color: 'var(--green)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)',
                  fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', cursor: 'pointer',
                  opacity: (!stockIn && !cryptoIn) ? 0.4 : 1,
                }}
              >
                {saving ? 'Saving…' : 'Apply balances'}
              </button>
            </form>
          </div>
        </div>

        {/* Reset controls */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Reset to default</span>
            <span className="card-badge cb-muted">Resets to last set value</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {([
              { key: 'stock',  label: 'Reset stock balance',        val: balance?.stock_default  },
              { key: 'crypto', label: 'Reset crypto balance',       val: balance?.crypto_default },
              { key: 'all',    label: 'Reset all + clear order log', val: undefined },
            ] as const).map(({ key, label, val }) => (
              <div key={key} className="setting-row">
                <div>
                  <div className="setting-label">{label}</div>
                  {val !== undefined && (
                    <div className="setting-desc">Resets to {fmt$(val)}</div>
                  )}
                </div>
                <button
                  onClick={() => handleReset(key)}
                  style={{
                    padding: '6px 14px', background: key === 'all' ? 'var(--red-bg)' : 'var(--bg3)',
                    border: `0.5px solid ${key === 'all' ? 'var(--red3)' : 'var(--border2)'}`,
                    color: key === 'all' ? 'var(--red)' : 'var(--text3)',
                    borderRadius: 'var(--radius-sm)', fontFamily: 'var(--font-mono)',
                    fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', cursor: 'pointer',
                  }}
                >
                  Reset
                </button>
              </div>
            ))}
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4, lineHeight: 1.7 }}>
              Balances are stored in-process. They reset to default when the backend restarts.
              Persistent ledger requires the <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>trades</code> and <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>portfolio_snapshots</code> tables
              from audit gap GAP 3 (migration 0002).
            </div>
          </div>
        </div>
      </div>

      {/* Short gate status */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Direction gate status</span>
          <span className="card-badge cb-green">Live check</span>
        </div>
        <div className="card-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <div className="cb-tile">
              <div className="cb-tile-label">Stock shorts</div>
              <div className="cb-tile-value" style={{ fontSize: 14, color: balance && balance.stock_balance > 2500 ? 'var(--green)' : 'var(--red)' }}>
                {loading ? '—' : balance && balance.stock_balance > 2500 ? 'Eligible' : 'Blocked'}
              </div>
              <div className="cb-tile-status">
                {balance ? `Balance ${fmt$(balance.stock_balance)} vs $2,500 gate` : ''}
              </div>
            </div>
            <div className="cb-tile">
              <div className="cb-tile-label">Crypto shorts</div>
              <div className="cb-tile-value" style={{ fontSize: 14, color: 'var(--red)' }}>Always blocked</div>
              <div className="cb-tile-status">Long only — hardcoded in DirectionGate</div>
            </div>
            <div className="cb-tile">
              <div className="cb-tile-label">Max positions</div>
              <div className="cb-tile-value" style={{ fontSize: 14 }}>5</div>
              <div className="cb-tile-status">Enforced by PortfolioManager</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PaperLedger;
