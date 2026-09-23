/**
 * KPI card: label, headline value, sub-line, optional progress bar and footer.
 * `children` are rendered under the sub-line for card-specific extras.
 */
export function StatCard({
  label,
  value,
  sub,
  foot,
  progress,
  className = '',
  valueClassName = '',
  subClassName = '',
  children,
}) {
  return (
    <div className={`ed-card ${className}`.trim()}>
      <span className="ed-card-label">{label}</span>
      <strong className={`ed-card-value ${valueClassName}`.trim()}>{value}</strong>
      {sub && <span className={`ed-card-sub ${subClassName}`.trim()}>{sub}</span>}
      {children}
      {progress && <ProgressBar tone={progress.tone} percent={progress.percent} />}
      {foot && <span className="ed-card-foot">{foot}</span>}
    </div>
  );
}

/** Horizontal bar; `percent` is clamped to 0–100. tone: blue | orange | green. */
export function ProgressBar({ tone = 'blue', percent = 0 }) {
  const width = Math.max(0, Math.min(100, Number(percent) || 0));
  return (
    <div className={`ed-progress ed-progress-${tone}`}>
      <span style={{ width: `${width}%` }} />
    </div>
  );
}
