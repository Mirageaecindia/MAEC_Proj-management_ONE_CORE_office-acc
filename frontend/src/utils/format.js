import { parseApiTimestamp } from './displayTime';

/** Display formatting shared by every page (numbers, money, dates, sizes). */

export const NOT_AVAILABLE = 'Not available';

export function isFiniteNumber(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
}

/** 12.345 -> "12.3 Hrs" */
export function formatHours(value, { fallback = NOT_AVAILABLE, unit = 'Hrs' } = {}) {
  return isFiniteNumber(value) ? `${Number(value).toFixed(1)} ${unit}` : fallback;
}

/** 42.25 -> "42.3%" */
export function formatPercent(value, { fallback = NOT_AVAILABLE } = {}) {
  return isFiniteNumber(value) ? `${Number(value).toFixed(1)}%` : fallback;
}

/** 0.3 -> "0.30" (digits = 2) */
export function formatDecimal(value, digits = 1, { fallback = NOT_AVAILABLE } = {}) {
  return isFiniteNumber(value) ? Number(value).toFixed(digits) : fallback;
}

/** 4 -> "4", 3840 -> "3,840" */
export function formatInteger(value, { fallback = '—' } = {}) {
  return isFiniteNumber(value)
    ? Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })
    : fallback;
}

/** ISO date/time -> locale date and time. */
export function formatDateTime(value, { fallback = NOT_AVAILABLE } = {}) {
  if (!value) return fallback;
  const parsed = parseApiTimestamp(value); // server times are UTC, shown in the viewer's time zone
  return !parsed || Number.isNaN(parsed.getTime()) ? fallback : parsed.toLocaleString();
}

/** 50000, "USD" -> "$50,000.00" */
export function formatMoney(value, currency = 'USD', { fallback = NOT_AVAILABLE } = {}) {
  if (!isFiniteNumber(value)) return fallback;
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(value));
  } catch {
    return `${currency} ${formatAmount(value)}`;
  }
}

/** 480000 -> "480,000.00" (no currency symbol). */
export function formatAmount(value, { fallback = '—' } = {}) {
  const amount = parseAmount(value);
  return Number.isFinite(amount) && String(value ?? '').trim() !== ''
    ? amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : fallback;
}

/** "480,000.50" -> 480000.5 (strips everything except digits and the decimal point). */
export function parseAmount(raw) {
  return Number(String(raw ?? '').replace(/[^0-9.]/g, ''));
}

/** 1536 -> "1.5 KB" */
export function formatBytes(bytes) {
  if (!isFiniteNumber(bytes) || Number(bytes) <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${parseFloat((bytes / 1024 ** exponent).toFixed(2))} ${units[exponent]}`;
}
