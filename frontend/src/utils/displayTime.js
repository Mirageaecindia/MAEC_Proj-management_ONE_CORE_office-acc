const IST_TIME_ZONE = 'Asia/Kolkata';

function isTimezoneAware(value) {
  return /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim());
}

/**
 * Parse a backend timestamp into a Date. Every timestamp this app stores is
 * UTC: timezone-aware strings ("...Z" / "+00:00") parse natively, and naive
 * strings (serialized by Pydantic from SQLite data without an offset) are
 * assumed to be UTC and given an explicit "Z" so the browser never mistakes
 * them for local time.
 */
export function parseApiTimestamp(value) {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return new Date(value);
  if (typeof value === 'string') {
    const raw = value.trim();
    if (!raw) return null;
    return isTimezoneAware(raw) ? new Date(raw) : new Date(`${raw}Z`);
  }
  return null;
}

export function formatDateTimeIST(value, options = {}) {
  const { fallback = '', includeSeconds = false } = options;
  const date = parseApiTimestamp(value);
  if (!date || Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat('en-US', {
    timeZone: IST_TIME_ZONE,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
  }).format(date);
}

export function formatDateIST(value, options = {}) {
  const { fallback = '' } = options;
  const date = parseApiTimestamp(value);
  if (!date || Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat('en-US', {
    timeZone: IST_TIME_ZONE,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}