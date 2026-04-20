type WatchlistEntry = {
  symbol: string;
  asset_class: string;
  research_score: number | null;
  added_by: string | null;
};

type WatchlistTableProps = {
  items: WatchlistEntry[];
};

export default function WatchlistTable({ items }: WatchlistTableProps): JSX.Element {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Watchlist manager</p>
          <h2>Active symbols</h2>
        </div>
        <span className="status-pill">{items.length} symbols</span>
      </div>
      <div className="table-shell">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Class</th>
              <th>Score</th>
              <th>Added by</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.symbol}>
                <td>{item.symbol}</td>
                <td>{item.asset_class}</td>
                <td>{item.research_score?.toFixed(0) ?? '—'}</td>
                <td>{item.added_by ?? 'manual'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
