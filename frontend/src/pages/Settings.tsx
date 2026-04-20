import React, { useState, useEffect, useCallback } from 'react';
import { getConfigKeys, postHalt, triggerWatchlistResearch, type ConfigKeys } from '../api';

type Mode = 'paper' | 'live';
type WeightKey = 'congress' | 'insider' | 'news' | 'screener' | 'analyst';

const WEIGHT_LABELS: Record<WeightKey, string> = {
  congress: 'Congress buy (30%)',
  insider:  'Insider buy (25%)',
  news:     'News sentiment (20%)',
  screener: 'Screener pass (15%)',
  analyst:  'Analyst upgrade (10%)',
};
const DEFAULT_WEIGHTS: Record<WeightKey, number> = {
  congress: 30, insider: 25, news: 20, screener: 15, analyst: 10,
};

type Props = { mode: Mode; onModeChange: (m: Mode) => void };

function KeyRow({ label, val }: { label: string; val: { configured: boolean; preview?: string; hint?: string } | undefined }): React.ReactElement {
  if (!val) return <></>;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '0.5px solid var(--border)' }}>
      <span style={{ fontSize: 11, color: 'var(--text3)' }}>{label}</span>
      {val.configured ? (
        <span style={{ fontSize: 11, color: 'var(--green)', fontFamily: 'var(--font-mono)' }}>
          {val.preview} ✓
        </span>
      ) : (
        <span style={{ fontSize: 11, color: 'var(--red)' }}>
          Not set — {val.hint}
        </span>
      )}
    </div>
  );
}

const Settings: React.FC<Props> = ({ mode, onModeChange }) => {
  const [keys,    setKeys]    = useState<ConfigKeys | null>(null);
  const [keyErr,  setKeyErr]  = useState<string | null>(null);
  const [weights, setWeights] = useState<Record<WeightKey, number>>(DEFAULT_WEIGHTS);
  const [confirm, setConfirm] = useState(false);
  const [halted,  setHalted]  = useState(false);
  const [halting, setHalting] = useState(false);
  const [haltMsg, setHaltMsg] = useState<string | null>(null);
  const [resMsg,  setResMsg]  = useState<string | null>(null);

  const loadKeys = useCallback(async () => {
    try {
      const k = await getConfigKeys();
      setKeys(k);
    } catch {
      setKeyErr('Could not reach /config/keys — is the backend running?');
    }
  }, []);

  useEffect(() => { loadKeys(); }, [loadKeys]);

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0);

  async function handleHalt() {
    setHalting(true);
    try {
      const r = await postHalt();
      setHalted(true);
      setHaltMsg(`Halted. ${Object.entries(r.brokers).map(([k, v]) => `${k}=${v}`).join(', ')}`);
    } catch { setHaltMsg('Halt call failed — check backend logs'); }
    finally { setHalting(false); setConfirm(false); }
  }

  async function handleResearch() {
    try {
      const job = await triggerWatchlistResearch();
      setResMsg(`Job queued: ${job.job_id}`);
    } catch { setResMsg('Research trigger failed'); }
    setTimeout(() => setResMsg(null), 5000);
  }

  const allConfigured = keys
    ? keys.kraken.api_key.configured && keys.tradier.api_key.configured && keys.alpaca.api_key.configured
    : false;

  return (
    <div className="page active">
      <div className="settings-grid">
        <div className="settings-col">

          {/* API key status */}
          <div>
            <div className="settings-group-title">
              API keys — configured in <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)', textTransform: 'none', letterSpacing: 0 }}>backend/.env</code>
            </div>
            {keyErr ? (
              <div style={{ padding: '10px', background: 'var(--red-bg)', border: '0.5px solid var(--red3)', borderRadius: 'var(--radius-md)', fontSize: 11, color: 'var(--red)' }}>
                {keyErr}
              </div>
            ) : (
              <div className="card">
                {/* Kraken */}
                <div style={{ padding: '10px 16px', borderBottom: '0.5px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)' }}>Kraken</span>
                    <span style={{ fontSize: 9, color: 'var(--text3)' }}>{keys?.kraken.base_url}</span>
                  </div>
                  <KeyRow label="KRAKEN_API_KEY"    val={keys?.kraken.api_key} />
                  <KeyRow label="KRAKEN_API_SECRET" val={keys?.kraken.api_secret} />
                </div>
                {/* Tradier */}
                <div style={{ padding: '10px 16px', borderBottom: '0.5px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)' }}>Tradier</span>
                    <span style={{ fontSize: 9, color: 'var(--text3)' }}>{keys?.tradier.base_url}</span>
                  </div>
                  <KeyRow label="TRADIER_API_KEY"    val={keys?.tradier.api_key} />
                  <KeyRow label="TRADIER_ACCOUNT_ID" val={keys?.tradier.account_id} />
                </div>
                {/* Alpaca */}
                <div style={{ padding: '10px 16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)' }}>Alpaca</span>
                    <span style={{ fontSize: 9, color: 'var(--text3)' }}>{keys?.alpaca.base_url}</span>
                  </div>
                  <KeyRow label="ALPACA_API_KEY"    val={keys?.alpaca.api_key} />
                  <KeyRow label="ALPACA_API_SECRET" val={keys?.alpaca.api_secret} />
                </div>
                <div style={{ padding: '8px 16px', background: 'var(--bg2)', borderTop: '0.5px solid var(--border)', fontSize: 10, color: 'var(--text3)' }}>
                  Edit <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>backend/.env</code> then restart the backend for changes to take effect.
                  {keys?.note && ` ${keys.note}`}
                </div>
              </div>
            )}
          </div>

          {/* Trading mode */}
          <div>
            <div className="settings-group-title">Trading mode</div>
            <div className="setting-row">
              <div>
                <div className="setting-label">Active mode</div>
                <div className="setting-desc">
                  Paper: fills simulated internally, no broker calls.
                  Live: routes buy/sell to Kraken + Tradier.
                </div>
              </div>
              <select className="select-ctrl" value={mode} onChange={e => onModeChange(e.target.value as Mode)}>
                <option value="paper">Paper trading</option>
                <option value="live" disabled={!allConfigured}>
                  {allConfigured ? 'Live trading' : 'Live (keys missing)'}
                </option>
              </select>
            </div>
          </div>

          {/* Circuit breakers */}
          <div>
            <div className="settings-group-title">Circuit breakers</div>
            <div className="cb-grid">
              {[
                { label: 'Daily loss',  val: '-2.0%',  note: 'Halts all trading' },
                { label: 'Weekly DD',   val: '-5.0%',  note: 'Manual re-enable'  },
                { label: 'Peak DD',     val: '-15.0%', note: 'From equity peak'  },
              ].map(cb => (
                <div className="cb-tile" key={cb.label}>
                  <div className="cb-tile-label">{cb.label}</div>
                  <div className="cb-tile-value">{cb.val}</div>
                  <div className="cb-tile-status">{cb.note}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Watchlist research trigger */}
          <div>
            <div className="settings-group-title">Watchlist research</div>
            <div className="setting-row">
              <div>
                <div className="setting-label">Run research on active watchlist</div>
                <div className="setting-desc">
                  Triggers congress, insider, news, and screener scoring for all watchlist symbols.
                </div>
              </div>
              <button
                onClick={handleResearch}
                style={{
                  padding: '7px 14px', background: 'var(--purple-bg)', border: '0.5px solid var(--purple)',
                  color: 'var(--purple)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)',
                  fontSize: 10, letterSpacing: '0.1em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap',
                }}
              >
                Run research
              </button>
            </div>
            {resMsg && (
              <div style={{ marginTop: 6, fontSize: 11, color: 'var(--green)', padding: '6px 10px', background: 'var(--green-bg)', borderRadius: 'var(--radius-md)', border: '0.5px solid var(--green3)' }}>
                {resMsg}
              </div>
            )}
          </div>
        </div>

        <div className="settings-col">

          {/* Emergency halt */}
          <div>
            <div className="settings-group-title">Emergency halt</div>
            <div className="card">
              <div className="halt-zone">
                {halted ? (
                  <div>
                    <div className="halted-banner">{haltMsg ?? 'Trading halted'}</div>
                    <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 10 }}>
                      Restart the backend or call <code style={{ fontFamily: 'var(--font-mono)' }}>resume()</code> on each broker to re-enable.
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="halt-desc">
                      Calls <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>POST /admin/halt</code> — cancels all
                      open orders and closes all positions at market. Cannot be reversed without
                      restarting the backend.
                    </div>
                    <button className="halt-btn" onClick={() => setConfirm(true)}>Halt all trading</button>
                    {confirm && (
                      <div className="confirm-overlay">
                        <div className="confirm-text">
                          This calls POST /admin/halt. All orders cancelled, all positions
                          flattened at market. Cannot be undone automatically.
                        </div>
                        <div className="confirm-row">
                          <button className="btn-cancel" onClick={() => setConfirm(false)}>Cancel</button>
                          <button className="btn-confirm-halt" onClick={handleHalt} disabled={halting}>
                            {halting ? 'Halting…' : 'Confirm halt'}
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Research signal weights */}
          <div>
            <div className="settings-group-title">
              Research signal weights
              <span style={{ marginLeft: 8, fontSize: 9, color: totalWeight === 100 ? 'var(--green)' : 'var(--amber)' }}>
                {totalWeight}% {totalWeight !== 100 ? '⚠' : '✓'}
              </span>
            </div>
            <div className="card">
              <div className="weight-rows">
                {(Object.keys(DEFAULT_WEIGHTS) as WeightKey[]).map(key => (
                  <div className="weight-row" key={key}>
                    <span className="weight-label">{WEIGHT_LABELS[key].split(' (')[0]}</span>
                    <input
                      type="range" className="weight-slider"
                      min={0} max={50} step={1} value={weights[key]}
                      onChange={e => setWeights(prev => ({ ...prev, [key]: Number(e.target.value) }))}
                    />
                    <span className="weight-val">{weights[key]}%</span>
                  </div>
                ))}
                <div style={{ fontSize: 9, color: 'var(--text3)', paddingTop: 4, lineHeight: 1.7 }}>
                  UI-only. Apply permanently in <code style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>app/config/constants.py → DEFAULT_SIGNAL_WEIGHTS</code>
                </div>
              </div>
            </div>
          </div>

          {/* Data sources */}
          <div>
            <div className="settings-group-title">Data sources</div>
            <div className="card">
              <div className="card-body-sm" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {[
                  { label: 'Kraken',  role: 'Live crypto execution + candle workers',    badge: 'cb-green',  tag: 'LIVE'     },
                  { label: 'Tradier', role: 'Live stock execution + watchlist candles',   badge: 'cb-green',  tag: 'LIVE'     },
                  { label: 'Alpaca',  role: 'ML training OHLCV only — no live orders',   badge: 'cb-blue',   tag: 'TRAINING' },
                ].map(src => (
                  <div key={src.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{src.label}</div>
                      <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>{src.role}</div>
                    </div>
                    <span className={`card-badge ${src.badge}`}>{src.tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
