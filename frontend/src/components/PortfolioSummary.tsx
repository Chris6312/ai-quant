type SummaryProps = {
  appName: string;
  version: string;
  healthStatus: string;
  readyStatus: string;
  portfolio: {
    nav: number;
    dailyPnl: number;
    stockBalance: number;
    cryptoBalance: number;
    shortEligible: boolean;
  };
};

export default function PortfolioSummary({
  appName,
  version,
  healthStatus,
  readyStatus,
  portfolio,
}: SummaryProps): JSX.Element {
  return (
    <section className="panel panel-hero">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Phase 8 live stack</p>
          <h1>{appName}</h1>
          <p className="muted">Version {version}</p>
        </div>
        <div className="status-stack">
          <span className="status-pill">API: {healthStatus}</span>
          <span className="status-pill">DB: {readyStatus}</span>
        </div>
      </div>
      <div className="metrics-grid">
        <Metric label="NAV" value={`$${portfolio.nav.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
        <Metric label="Daily P&L" value={`$${portfolio.dailyPnl.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
        <Metric label="Stock balance" value={`$${portfolio.stockBalance.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
        <Metric label="Crypto balance" value={`$${portfolio.cryptoBalance.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
      </div>
      <div className={`gate-badge ${portfolio.shortEligible ? 'gate-on' : 'gate-off'}`}>
        Short gate: {portfolio.shortEligible ? 'eligible' : 'blocked'}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="metric-card">
      <span className="metric-label">{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
