type ResearchPanelProps = {
  signals: {
    symbol: string;
    news: number;
    congress: number;
    insider: number;
    analyst: number;
  }[];
};

export default function ResearchPanel({ signals }: ResearchPanelProps): JSX.Element {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Universe research</p>
          <h2>Signal breakdown</h2>
        </div>
        <span className="status-pill">research signals</span>
      </div>
      <div className="research-list">
        {signals.map((signal) => (
          <article key={signal.symbol} className="research-row">
            <div className="research-title">
              <strong>{signal.symbol}</strong>
              <span className="muted">news / congress / insider / analyst</span>
            </div>
            <Bar label="News" value={signal.news} />
            <Bar label="Congress" value={signal.congress} />
            <Bar label="Insider" value={signal.insider} />
            <Bar label="Analyst" value={signal.analyst} />
          </article>
        ))}
      </div>
    </section>
  );
}

function Bar({ label, value }: { label: string; value: number }): JSX.Element {
  return (
    <div className="bar-row">
      <span>{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${Math.max(4, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}
