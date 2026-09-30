import { X } from 'lucide-react';
import { ErrorBanner } from './Feedback';

/** Modal asking the user to confirm an action: destructive by default (`tone="danger"`), or `tone="primary"`. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel = 'Confirm',
  busyLabel = 'Working…',
  busy = false,
  confirmDisabled = false,
  tone = 'danger',
  error = null,
  onConfirm,
  onCancel,
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
        <div className="modal-heading">
          <h2 id="confirm-dialog-title">{title}</h2>
          <button type="button" aria-label="Close" disabled={busy} onClick={onCancel}>
            <X size={18} />
          </button>
        </div>
        <div className="confirm-modal-body">
          {children}
          <ErrorBanner error={error} />
        </div>
        <div className="modal-actions">
          <button className="button button-secondary" type="button" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          <button
            className={`button button-${tone}`}
            type="button"
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
          >
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
