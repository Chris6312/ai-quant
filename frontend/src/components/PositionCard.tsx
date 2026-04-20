type PositionCardProps = {
  symbol: string;
  side: string;
  entryPrice: number;
  currentPrice: number;
  size: number;
  mlConfidence: number;
  researchScore: number;
};

export default function PositionCard({
  symbol,
  side,
  entryPrice,
  currentPrice,
  size,
  mlConfidence,
  researchScore,
}: PositionCardProps): JSX.Element {
  const unrealized = (currentPrice - entryPrice) * size;
  const pnlClass = unrealized >= 0 ? 'positive' : 'negative';

  return (
    <article className="position-card">
      <div className="panel-header compact">
        <strong>{symbol}</strong>
        <span className="status-pill">{side}</span>
      </div>
      <div className="card-grid">
        <span>Entry</span>
        <strong>${entryPrice.toFixed(2)}</strong>
        <span>Current</span>
        <strong>${currentPrice.toFixed(2)}</strong>
        <span>Size</span>
        <strong>{size.toFixed(2)}</strong>
        <span>ML confidence</span>
        <strong>{Math.round(mlConfidence * 100)}%</strong>
        <span>Research</span>
        <strong>{researchScore.toFixed(0)}/100</strong>
        <span>P&amp;L</span>
        <strong className={pnlClass}>${unrealized.toFixed(2)}</strong>
      </div>
    </article>
  );
}
