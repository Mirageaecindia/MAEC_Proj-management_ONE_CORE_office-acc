import { AlertCircle, Check, X } from 'lucide-react';

/** Inline error line. Accepts an Error (e.g. ApiError) or a string; renders nothing when empty. */
export function ErrorBanner({ error }) {
  const message = typeof error === 'string' ? error : error?.message;
  if (!message) return null;
  return (
    <div className="resource-error" role="alert">
      {message}
    </div>
  );
}

/** Dismissible success/error notice, optionally with a link (e.g. the SharePoint folder). */
export function Notice({ type = 'success', message, url, onDismiss }) {
  if (!message) return null;
  return (
    <div className={`notice ${type}`} role="status">
      {type === 'success' ? <Check size={18} /> : <AlertCircle size={18} />}
      <div>
        <strong>{message}</strong>
        {url && (
          <a href={url} target="_blank" rel="noreferrer">
            {url}
          </a>
        )}
      </div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Dismiss notification">
          <X size={17} />
        </button>
      )}
    </div>
  );
}

/** Centered message used for loading and empty states. */
export function EmptyState({ children }) {
  return <div className="empty-state">{children}</div>;
}
