import { useRef, useState } from 'react';

/**
 * A table cell edited where it stands (decided 2026-10-08, simplified 2026-10-09): click it,
 * then picking an engineer or a date saves at once; hours save on Enter or when the field is
 * left. Esc puts the old value back. A locked cell is plain greyed text; `locked` is the
 * reason, shown on hover. A refused save keeps the editor open with the server's reason.
 *
 * kind: 'select' (options: [{ value, label }]), 'date', or 'number' (whole numbers, min/max).
 * onSave(value) returns a promise; `value` is '' when cleared.
 */
export function InlineEditCell({
  kind,
  value,
  display,
  placeholder,
  label,
  options = [],
  min,
  max,
  locked,
  onSave,
}) {
  const [draft, setDraft] = useState(null); // null: not editing
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const savingRef = useRef(false); // a pick saves, then the field loses focus: save once
  const cancelledRef = useRef(false);

  if (locked) {
    return (
      <div className="wbs-readonly inline-cell-locked" title={locked}>
        {display || '—'}
      </div>
    );
  }

  const stop = (event) => event.stopPropagation(); // the row itself opens Task Details
  const start = (event) => {
    stop(event);
    setError('');
    cancelledRef.current = false;
    setDraft(value ?? '');
  };
  const cancel = () => {
    cancelledRef.current = true; // Esc closes the field; leaving it then must not save
    setDraft(null);
    setError('');
  };
  const save = async (next) => {
    if (savingRef.current) return;
    if (kind === 'number' && next !== '') {
      const number = Number(next);
      if (!Number.isInteger(number) || (min != null && number < min) || (max != null && number > max)) {
        setError(`A whole number from ${min} to ${max}.`);
        return;
      }
    }
    if (String(next) === String(value ?? '')) {
      cancel(); // nothing changed
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setError('');
    try {
      await onSave(next);
      setDraft(null);
    } catch (err) {
      setError(err.message || 'Could not save.');
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  if (draft === null) {
    return (
      <button type="button" className="inline-cell" aria-label={`Change ${label}`} onClick={start}>
        {display || <span className="inline-cell-placeholder">{placeholder}</span>}
      </button>
    );
  }

  const keys = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      save(draft);
    } else if (event.key === 'Escape') {
      cancel();
    }
  };
  const common = {
    'aria-label': label,
    autoFocus: true,
    disabled: saving,
    value: draft,
    onKeyDown: keys,
    onClick: stop,
  };
  return (
    <div className="inline-cell-editor" onClick={stop}>
      {kind === 'select' ? (
        <select
          {...common}
          onChange={(event) => {
            setDraft(event.target.value);
            save(event.target.value); // picking a name saves it
          }}
          onBlur={() => !savingRef.current && !error && cancel()}
        >
          <option value="">—</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : kind === 'date' ? (
        <input
          {...common}
          type="date"
          onChange={(event) => {
            setDraft(event.target.value);
            save(event.target.value); // picking a day saves it
          }}
          onBlur={() => !savingRef.current && !error && cancel()}
        />
      ) : (
        <input
          {...common}
          type="number"
          min={min}
          max={max}
          step={1}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={() => !cancelledRef.current && save(draft)} // typed hours save when the field is left (or on Enter)
        />
      )}
      {error && (
        <small className="inline-cell-error" role="alert">
          {error}
        </small>
      )}
    </div>
  );
}
