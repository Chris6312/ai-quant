type Strategy = {
  name: string;
  enabled: boolean;
  riskMultiplier: number;
};

type StrategyPanelProps = {
  strategies: Strategy[];
};

export default function StrategyPanel({ strategies }: StrategyPanelProps): JSX.Element {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Strategy control</p>
          <h2>Enable / disable</h2>
        </div>
        <span className="status-pill">YAML-driven</span>
      </div>
      <div className="strategy-list">
        {strategies.map((strategy) => (
          <label key={strategy.name} className="strategy-row">
            <input type="checkbox" checked={strategy.enabled} readOnly />
            <span>{strategy.name}</span>
            <span className="muted">×{strategy.riskMultiplier.toFixed(2)}</span>
          </label>
        ))}
      </div>
    </section>
  );
}
