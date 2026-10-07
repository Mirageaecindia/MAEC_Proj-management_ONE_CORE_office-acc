/**
 * Part-to-whole as one horizontal stacked bar (decided 2026-10-07, dataviz method):
 * each part is labelled with its name and value below the bar, so colour never
 * carries the meaning alone, and every segment has a hover title.
 * `parts`: [{ key, label, value, color }]; `format` renders a value.
 */
export function ShareBar({ parts, format = String, emptyMessage = 'Nothing to show yet.', label }) {
  const total = parts.reduce((sum, part) => sum + (Number(part.value) || 0), 0);
  if (total <= 0) return <div className="timesheet-empty-cell share-bar-empty">{emptyMessage}</div>;
  return (
    <figure className="share-bar" aria-label={label}>
      <div
        className="share-bar-track"
        role="img"
        aria-label={parts.map((p) => `${p.label} ${format(p.value)}`).join(', ')}
      >
        {parts
          .filter((part) => Number(part.value) > 0)
          .map((part) => (
            <span
              key={part.key}
              className="share-bar-segment"
              style={{ flexGrow: Number(part.value), background: part.color }}
              title={`${part.label}: ${format(part.value)} (${Math.round((Number(part.value) / total) * 100)}%)`}
            />
          ))}
      </div>
      <figcaption className="share-bar-legend">
        {parts.map((part) => (
          <span key={part.key}>
            <i style={{ background: part.color }} aria-hidden="true" />
            {part.label} <strong>{format(part.value)}</strong>
            <em>{Math.round(((Number(part.value) || 0) / total) * 100)}%</em>
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
