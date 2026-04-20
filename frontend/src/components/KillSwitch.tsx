type KillSwitchProps = {
  onHalt: () => void;
  halted: boolean;
};

export default function KillSwitch({ onHalt, halted }: KillSwitchProps): JSX.Element {
  return (
    <section className="panel">
      <div className="panel-header compact">
        <div>
          <p className="eyebrow">Emergency controls</p>
          <h2>Kill switch</h2>
        </div>
        <button type="button" className="halt-button" onClick={onHalt}>
          {halted ? 'Halted' : 'Halt all'}
        </button>
      </div>
      <p className="muted">Cancels live routing and blocks new submissions.</p>
    </section>
  );
}
