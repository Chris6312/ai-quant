import React, { useState } from 'react';
import Dashboard       from './pages/Dashboard';
import Research        from './pages/Research';
import Analytics       from './pages/Analytics';
import PaperLedger     from './pages/PaperLedger';
import MachineLearning from './pages/MachineLearning';
import OrderLog        from './pages/OrderLog';
import Runtime         from './pages/Runtime';
import Settings        from './pages/Settings';

type TabKey = 'dashboard' | 'research' | 'analytics' | 'paper' | 'ml' | 'orders' | 'runtime' | 'settings';
type Mode   = 'paper' | 'live';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'research',  label: 'Research'  },
  { key: 'analytics', label: 'Analytics' },
  { key: 'paper',     label: 'Paper'     },
  { key: 'ml',        label: 'ML'        },
  { key: 'orders',    label: 'Orders'    },
  { key: 'runtime',   label: 'Runtime'   },
  { key: 'settings',  label: 'Settings'  },
];

const App: React.FC = () => {
  const [active, setActive] = useState<TabKey>('dashboard');

  // Mode persists across page reloads
  const [mode, setMode] = useState<Mode>(() => {
    try { return (localStorage.getItem('trading_mode') as Mode) || 'paper'; } catch { return 'paper'; }
  });

  function handleModeChange(m: Mode): void {
    setMode(m);
    try { localStorage.setItem('trading_mode', m); } catch { /* ignore */ }
  }

  return (
    <div className="app-shell">
      <nav className="topbar">
        <div className="brand">
          <div className="brand-indicator">
            <div className={`brand-dot ${mode === 'live' ? 'live' : ''}`} />
            <div className="brand-pulse" />
          </div>
          <span className="brand-name">AlphaBot</span>
        </div>
        <div className="nav">
          {TABS.map(tab => (
            <button
              key={tab.key} type="button"
              className={`nav-btn${active === tab.key ? ' active' : ''}`}
              onClick={() => setActive(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="topbar-right">
          <div className="status-indicator">
            <div className="status-dot" />
            <span className="status-text">Connected</span>
          </div>
          <div className="mode-toggle">
            <button type="button" className={`mode-btn${mode === 'paper' ? ' active-paper' : ''}`} onClick={() => handleModeChange('paper')}>Paper</button>
            <button type="button" className={`mode-btn${mode === 'live'  ? ' active-live'  : ''}`} onClick={() => handleModeChange('live')}>Live</button>
          </div>
        </div>
      </nav>
      <main className="page-content">
        {active === 'dashboard' && <Dashboard    mode={mode} />}
        {active === 'research'  && <Research />}
        {active === 'analytics' && <Analytics />}
        {active === 'paper'     && <PaperLedger />}
        {active === 'ml'        && <MachineLearning />}
        {active === 'orders'    && <OrderLog />}
        {active === 'runtime'   && <Runtime />}
        {active === 'settings'  && <Settings mode={mode} onModeChange={handleModeChange} />}
      </main>
    </div>
  );
};

export default App;
