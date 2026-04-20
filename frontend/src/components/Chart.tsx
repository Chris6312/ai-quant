type CandlePoint = {
  time: string;
  close: number;
};

type ChartProps = {
  symbol: string;
  candles: CandlePoint[];
};

export default function Chart({ symbol, candles }: ChartProps): JSX.Element {
  const values = candles.map((candle) => candle.close);
  const min = Math.min(...values);
  const max = Math.max(...values);

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Live chart</p>
          <h2>{symbol}</h2>
        </div>
        <span className="status-pill">lightweight-charts placeholder</span>
      </div>
      <div className="sparkline">
        {candles.map((candle, index) => {
          const normalized = max === min ? 50 : ((candle.close - min) / (max - min)) * 100;
          return (
            <div
              key={`${candle.time}-${index}`}
              className="spark-bar"
              title={`${candle.time}: ${candle.close.toFixed(2)}`}
              style={{ height: `${Math.max(8, normalized)}%` }}
            />
          );
        })}
      </div>
    </section>
  );
}
