import { Check, X } from 'lucide-react';
import { useState } from 'react';

/**
 * A table cell edited where it stands (decided 2026-10-08): click it, choose or type, then
 * ✓ (or Enter) saves and ✕ (or Esc) puts the old value back. A locked cell is plain greyed
 * text; `locked` is the reason, shown on hover. A refused save keeps the editor open with
 * the server's reason under it.
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
    setDraft(value ?? '');
  };
  const cancel = () => {
    setDraft(null);
    setError('');
  };
  const save = async () => {
    if (kind === 'number' && draft !== '') {
      const number = Number(draft);
      if (!Number.isInteger(number) || (min != null && number < min) || (max != null && number > max)) {
        setError(`A whole number from ${min} to ${max}.`);
        return;
      }
    }
    if (String(draft) === String(value ?? '')) {
      cancel(); // nothing changed
      return;
    }
    setSaving(true);
    setError('');
    try {
      await onSave(draft);
      setDraft(null);
    } catch (err) {
      setError(err.message || 'Could not save.');
    } finally {
      setSaving(false);
    }
  };
  const keys = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      save();
    } else if (event.key === 'Escape') {
      cancel();
    }
  };

  if (draft === null) {
    return (
      <button type="button" className="inline-cell" aria-label={`Change ${label}`} onClick={start}>
        {display || <span className="inline-cell-placeholder">{placeholder}</span>}
      </button>
    );
  }

  const common = {
    'aria-label': label,
    autoFocus: true,
    disabled: saving,
    value: draft,
    onChange: (event) => setDraft(event.target.value),
    onKeyDown: keys,
    onClick: stop,
  };
  return (
    <div className="inline-cell-editor" onClick={stop}>
      <div className="inline-cell-row">
        {kind === 'select' ? (
          <select {...common}>
            <option value="">—</option>
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input {...common} type={kind} min={min} max={max} step={kind === 'number' ? 1 : undefined} />
        )}
        <button
          type="button"
          className="inline-cell-ok"
          aria-label={`Save ${label}`}
          title="Save (Enter)"
          disabled={saving}
          onClick={save}
        >
          <Check size={14} />
        </button>
        <button
          type="button"
          className="inline-cell-cancel"
          aria-label={`Cancel ${label}`}
          title="Cancel (Esc)"
          disabled={saving}
          onClick={cancel}
        >
          <X size={14} />
        </button>
      </div>
      {error && (
        <small className="inline-cell-error" role="alert">
          {error}
        </small>
      )}
    </div>
  );
}
