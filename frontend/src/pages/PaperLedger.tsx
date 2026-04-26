import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getPaperState,
  resetPaperBalance,
  setPaperBalance,
  type PaperAccount,
  type PaperFill,
  type PaperOrder,
  type PaperPosition,
  type PaperState,
} from '../api';

const fmt$ = (n: number) =>
  n.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  });

const fmtNum = (n: number) =>
  n.toLocaleString('en-US', {
    maximumFractionDigits: 8,
  });

const fmtDate = (value?: string | null) =>
  value ? value.slice(0, 16).replace('T', ' ') : '—';

const positionValue = (position: PaperPosition) =>
  position.size * position.average_entry_price;

const orderValue = (order: PaperOrder) =>
  order.average_fill_price == null ? null : order.filled_size * order.average_fill_price;

type PaperStateLabel = {
  label: string;
  detail: string;
  badgeClass: string;
};

function getStateLabel(state: PaperState | null): PaperStateLabel {
  if (state === null) {
    return {
      label: 'Loading',
      detail: 'Checking durable paper ledger state.',
      badgeClass: 'cb-muted',
    };
  }

  const hasAccounts = (state.balance.accounts?.length ?? 0) > 0;
  const hasOpenPositions = state.positions.length > 0;
  const hasActivity = state.orders.length > 0 || state.fills.length > 0;
  const wasReset = (state.balance.accounts ?? []).some(account => account.reset_count > 0);
  const hasCash = state.balance.nav > 0;

  if (!hasAccounts) {
    return {
      label: 'Empty account',
      detail: 'No durable paper account rows exist yet.',
      badgeClass: 'cb-amber',
    };
  }

  if (hasOpenPositions) {
    return {
      label: 'Active positions',
      detail: 'Open paper positions are loaded from the database.',
      badgeClass: 'cb-green',
    };
  }

  if (wasReset && !hasActivity) {
    return {
      label: 'Reset account',
      detail: 'Account was reset and has no current paper activity.',
      badgeClass: 'cb-amber',
    };
  }

  if (!hasCash && !hasActivity) {
    return {
      label: 'Empty account',
      detail: 'Durable ledger exists, but cash and activity are empty.',
      badgeClass: 'cb-amber',
    };
  }

  return {
    label: 'No paper positions',
    detail: hasActivity
      ? 'Paper account has historical orders or fills, but no open positions.'
      : 'Paper account exists and is ready for the first durable trade.',
    badgeClass: 'cb-muted',
  };
}

const Tile: React.FC<{
  label: string;
  value: string;
  sub?: string;
  color?: string;
}> = ({ label, value, sub, color }) => (
  <div className="metric-tile">
    <div className="metric-eyebrow">{label}</div>
    <div className="metric-value" style={color ? { color } : undefined}>
      {value}
    </div>
    {sub && <div className="metric-sub">{sub}</div>}
  </div>
);

const PaperLedger: React.FC = () => {
  const [state, setState] = useState<PaperState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stockIn, setStockIn] = useState('');
  const [cryptoIn, setCryptoIn] = useState('');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const nextState = await getPaperState();
      setState(nextState);
      setError(null);
    } catch {
      setError('Paper ledger endpoint unavailable — is the backend running?');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const status = useMemo(() => getStateLabel(state), [state]);
  const balance = state?.balance ?? null;
  const accounts = balance?.accounts ?? [];
  const recentOrders = state?.orders.slice(0, 6) ?? [];
  const recentFills = state?.fills.slice(0, 6) ?? [];

  async function handleSet(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const stock = stockIn ? parseFloat(stockIn) : undefined;
      const crypto = cryptoIn ? parseFloat(cryptoIn) : undefined;
      await setPaperBalance(stock, crypto);
      await load();
      setMsg('Durable balances updated');
      setStockIn('');
      setCryptoIn('');
    } catch {
      setMsg('Failed to update — check backend');
    } finally {
      setSaving(false);
      window.setTimeout(() => setMsg(null), 3000);
    }
  }

  async function handleReset(assetClass: 'stock' | 'crypto' | 'all') {
    try {
      await resetPaperBalance(assetClass);
      await load();
      setMsg(`${assetClass} ledger reset`);
    } catch {
      setMsg('Reset failed');
    }
    window.setTimeout(() => setMsg(null), 3000);
  }

  const pnlColor = balance && balance.realized_pnl >= 0 ? 'var(--green)' : 'var(--red)';

  return (
    <div className="page active">
      <div className="metrics-row">
        <Tile
          label="NAV"
          value={loading ? '—' : balance ? fmt$(balance.nav) : 'N/A'}
          sub={`Source: ${state?.source ?? 'database'}`}
        />
        <Tile
          label="Stock balance"
          value={loading ? '—' : balance ? fmt$(balance.stock_balance) : 'N/A'}
          sub={balance ? `Default: ${fmt$(balance.stock_default)}` : ''}
        />
        <Tile
          label="Crypto balance"
          value={loading ? '—' : balance ? fmt$(balance.crypto_balance) : 'N/A'}
          sub={balance ? `Default: ${fmt$(balance.crypto_default)}` : ''}
        />
        <Tile
          label="Realized P&L"
          value={loading ? '—' : balance ? fmt$(balance.realized_pnl) : 'N/A'}
          sub="Closed paper fills only"
          color={pnlColor}
        />
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Durable paper state</span>
          <span className={`card-badge ${status.badgeClass}`}>{status.label}</span>
        </div>
        <div className="card-body">
          <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.7 }}>
            {status.detail}
          </div>
          <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text3)', lineHeight: 1.7 }}>
            Paper state is loaded from database-backed accounts, positions, orders, and fills. A
            backend restart should not erase balances, open positions, or fill history.
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '10px 14px',
            background: 'var(--red-bg)',
            border: '0.5px solid var(--red3)',
            borderRadius: 'var(--radius-md)',
            fontSize: 11,
            color: 'var(--red)',
          }}
        >
          {error}
        </div>
      )}

      {msg && (
        <div
          style={{
            padding: '10px 14px',
            background: 'var(--green-bg)',
            border: '0.5px solid var(--green3)',
            borderRadius: 'var(--radius-md)',
            fontSize: 11,
            color: 'var(--green)',
          }}
        >
          {msg}
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Set custom balance</span>
            <span className="card-badge cb-amber">Paper only</span>
          </div>
          <div className="card-body">
            <form onSubmit={handleSet} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <BalanceInput
                label="Stock balance"
                value={stockIn}
                placeholder={balance ? balance.stock_balance.toFixed(2) : '100000'}
                onChange={setStockIn}
              />
              <BalanceInput
                label="Crypto balance"
                value={cryptoIn}
                placeholder={balance ? balance.crypto_balance.toFixed(2) : '100000'}
                onChange={setCryptoIn}
              />
              <button
                type="submit"
                disabled={saving || (!stockIn && !cryptoIn)}
                style={{
                  padding: '9px 0',
                  background: 'var(--green-bg)',
                  border: '0.5px solid var(--green3)',
                  color: 'var(--green)',
                  borderRadius: 'var(--radius-md)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                  opacity: !stockIn && !cryptoIn ? 0.4 : 1,
                }}
              >
                {saving ? 'Saving…' : 'Apply durable balances'}
              </button>
            </form>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Reset durable account</span>
            <span className="card-badge cb-muted">DB-backed</span>
          </div>
          <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <ResetRow
              label="Reset stock balance"
              detail={balance ? `Resets to ${fmt$(balance.stock_default)}` : 'Stock account'}
              onClick={() => handleReset('stock')}
            />
            <ResetRow
              label="Reset crypto balance"
              detail={balance ? `Resets to ${fmt$(balance.crypto_default)}` : 'Crypto account'}
              onClick={() => handleReset('crypto')}
            />
            <ResetRow
              danger
              label="Reset all paper accounts"
              detail="Clears open paper state back to configured defaults"
              onClick={() => handleReset('all')}
            />
            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4, lineHeight: 1.7 }}>
              Resets are persisted through <code>paper_account</code>. Open position and fill
              cleanup is handled by the backend ledger rules.
            </div>
          </div>
        </div>
      </div>

      <AccountTable accounts={accounts} loading={loading} />
      <PositionTable positions={state?.positions ?? []} loading={loading} />
      <RecentOrders orders={recentOrders} loading={loading} />
      <RecentFills fills={recentFills} loading={loading} />
    </div>
  );
};

const BalanceInput: React.FC<{
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}> = ({ label, placeholder, value, onChange }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    <label
      style={{
        fontSize: 10,
        color: 'var(--text3)',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
      }}
    >
      {label}
    </label>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 13, color: 'var(--text3)' }}>$</span>
      <input
        className="num-input"
        type="number"
        min="0"
        step="100"
        placeholder={placeholder}
        value={value}
        onChange={event => onChange(event.target.value)}
        style={{ width: '100%', textAlign: 'left' }}
      />
    </div>
  </div>
);

const ResetRow: React.FC<{
  label: string;
  detail: string;
  onClick: () => void;
  danger?: boolean;
}> = ({ label, detail, onClick, danger = false }) => (
  <div className="setting-row">
    <div>
      <div className="setting-label">{label}</div>
      <div className="setting-desc">{detail}</div>
    </div>
    <button
      onClick={onClick}
      style={{
        padding: '6px 14px',
        background: danger ? 'var(--red-bg)' : 'var(--bg3)',
        border: `0.5px solid ${danger ? 'var(--red3)' : 'var(--border2)'}`,
        color: danger ? 'var(--red)' : 'var(--text3)',
        borderRadius: 'var(--radius-sm)',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
        cursor: 'pointer',
      }}
    >
      Reset
    </button>
  </div>
);

const AccountTable: React.FC<{ accounts: PaperAccount[]; loading: boolean }> = ({
  accounts,
  loading,
}) => (
  <div className="card">
    <div className="card-header">
      <span className="card-title">Durable accounts</span>
      <span className="card-badge cb-green">paper_account</span>
    </div>
    {loading ? (
      <EmptyPanel text="Loading accounts…" />
    ) : accounts.length === 0 ? (
      <EmptyPanel text="No durable paper accounts found." />
    ) : (
      <div className="card-flush" style={{ overflowX: 'auto' }}>
        <table className="wl-table" style={{ minWidth: 760 }}>
          <thead>
            <tr>
              <th>Class</th>
              <th>Cash</th>
              <th>Default</th>
              <th>Realized P&L</th>
              <th>Resets</th>
              <th>Last reset</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map(account => (
              <tr key={account.id}>
                <td>{account.asset_class}</td>
                <td>{fmt$(account.cash_balance)}</td>
                <td>{fmt$(account.default_cash_balance)}</td>
                <td>{fmt$(account.realized_pnl)}</td>
                <td>{account.reset_count}</td>
                <td>{fmtDate(account.last_reset_at)}</td>
                <td>{fmtDate(account.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const PositionTable: React.FC<{ positions: PaperPosition[]; loading: boolean }> = ({
  positions,
  loading,
}) => (
  <div className="card">
    <div className="card-header">
      <span className="card-title">Open paper positions</span>
      <span className="card-badge cb-green">paper_positions</span>
    </div>
    {loading ? (
      <EmptyPanel text="Loading positions…" />
    ) : positions.length === 0 ? (
      <EmptyPanel text="No paper positions yet. This is distinct from a reset account." />
    ) : (
      <div className="card-flush" style={{ overflowX: 'auto' }}>
        <table className="wl-table" style={{ minWidth: 760 }}>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Class</th>
              <th>Side</th>
              <th>Size</th>
              <th>Avg entry</th>
              <th>Entry value</th>
              <th>Status</th>
              <th>Opened</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(position => (
              <tr key={position.id}>
                <td>{position.symbol}</td>
                <td>{position.asset_class}</td>
                <td>{position.side}</td>
                <td>{fmtNum(position.size)}</td>
                <td>{fmt$(position.average_entry_price)}</td>
                <td>{fmt$(positionValue(position))}</td>
                <td>{position.status}</td>
                <td>{fmtDate(position.opened_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const RecentOrders: React.FC<{ orders: PaperOrder[]; loading: boolean }> = ({
  orders,
  loading,
}) => (
  <div className="card">
    <div className="card-header">
      <span className="card-title">Recent durable orders</span>
      <span className="card-badge cb-muted">paper_orders</span>
    </div>
    {loading ? (
      <EmptyPanel text="Loading orders…" />
    ) : orders.length === 0 ? (
      <EmptyPanel text="No paper orders recorded yet." />
    ) : (
      <div className="card-flush" style={{ overflowX: 'auto' }}>
        <table className="wl-table" style={{ minWidth: 760 }}>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Size</th>
              <th>Avg fill</th>
              <th>Value</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {orders.map(order => {
              const value = orderValue(order);
              return (
                <tr key={order.id}>
                  <td>{order.symbol}</td>
                  <td>{order.side}</td>
                  <td>{fmtNum(order.filled_size)}</td>
                  <td>{order.average_fill_price == null ? '—' : fmt$(order.average_fill_price)}</td>
                  <td>{value == null ? '—' : fmt$(value)}</td>
                  <td>{order.status}</td>
                  <td>{fmtDate(order.created_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const RecentFills: React.FC<{ fills: PaperFill[]; loading: boolean }> = ({
  fills,
  loading,
}) => (
  <div className="card">
    <div className="card-header">
      <span className="card-title">Recent durable fills</span>
      <span className="card-badge cb-muted">paper_fills</span>
    </div>
    {loading ? (
      <EmptyPanel text="Loading fills…" />
    ) : fills.length === 0 ? (
      <EmptyPanel text="No paper fills recorded yet." />
    ) : (
      <div className="card-flush" style={{ overflowX: 'auto' }}>
        <table className="wl-table" style={{ minWidth: 820 }}>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Size</th>
              <th>Price</th>
              <th>Gross</th>
              <th>Fee</th>
              <th>Realized P&L</th>
              <th>Filled</th>
            </tr>
          </thead>
          <tbody>
            {fills.map(fill => (
              <tr key={fill.id}>
                <td>{fill.symbol}</td>
                <td>{fill.side}</td>
                <td>{fmtNum(fill.fill_size)}</td>
                <td>{fmt$(fill.fill_price)}</td>
                <td>{fmt$(fill.gross)}</td>
                <td>{fmt$(fill.commission)}</td>
                <td>{fmt$(fill.realized_pnl)}</td>
                <td>{fmtDate(fill.filled_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </div>
);

const EmptyPanel: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ padding: '20px 16px', fontSize: 11, color: 'var(--text3)' }}>{text}</div>
);

export default PaperLedger;
