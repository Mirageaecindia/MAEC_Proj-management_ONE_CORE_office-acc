import { formatHours, formatPercent } from '../../utils/format';

/**
 * Each discipline's consumption of its baseline, as horizontal bars on one scale with
 * the project's alert threshold marked. One hue; a discipline past the threshold is
 * called out in words next to its bar, not by colour alone.
 */
export function DisciplineBars({ disciplines = [], thresholdPct }) {
  if (!disciplines.length) {
    return <div className="timesheet-empty-cell share-bar-empty">No discipline has booked hours yet.</div>;
  }
  const scale = Math.max(100, thresholdPct || 0, ...disciplines.map((d) => Number(d.consumption_pct) || 0));
  const at = (pct) => `${(Math.min(Number(pct) || 0, scale) / scale) * 100}%`;
  return (
    <div className="discipline-bars">
      {disciplines.map((discipline) => (
        <div className="discipline-bar-row" key={discipline.name}>
          <span className="discipline-bar-name">{discipline.name}</span>
          <div
            className="discipline-bar-track"
            title={`${discipline.name}: ${formatHours(discipline.consumed_hours)} of ${formatHours(discipline.baseline_hours)} (${formatPercent(discipline.consumption_pct)})`}
          >
            <span className="discipline-bar-fill" style={{ width: at(discipline.consumption_pct) }} />
            {thresholdPct != null && (
              <span className="discipline-bar-threshold" style={{ left: at(thresholdPct) }} />
            )}
          </div>
          <span className="discipline-bar-value">
            {formatPercent(discipline.consumption_pct)}
            {discipline.exceeded && <em className="discipline-bar-flag"> over threshold</em>}
          </span>
        </div>
      ))}
      {thresholdPct != null && (
        <p className="discipline-bars-note">
          <i className="discipline-bar-threshold-key" aria-hidden="true" /> Alert threshold{' '}
          {formatPercent(thresholdPct)} · consumed = approved + pending hours of the discipline&apos;s booked
          baseline
        </p>
      )}
    </div>
  );
}
