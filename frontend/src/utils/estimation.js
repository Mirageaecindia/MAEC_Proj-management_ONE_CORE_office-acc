/**
 * Project estimation grid (backend: app/domain/estimation.py). The columns are dates: the start
 * date, then every `intervalDays` days, up to the end date. Each row is a staff code and role with
 * hours per column date; totals are per row, per date column and for the whole grid.
 */

export const MAX_COLUMNS = 400; // the server's limit too
const DAY_MS = 24 * 60 * 60 * 1000;

function utcDay(iso) {
  const [year, month, day] = String(iso).split('-').map(Number);
  return Date.UTC(year, month - 1, day);
}

function isoDay(ms) {
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * The column dates as 'YYYY-MM-DD', or an `error` saying why there are none.
 * 2027-01-01 to 2027-02-01 every 7 days: 1, 8, 15, 22 and 29 Jan.
 */
export function columnDates(start, end, intervalDays) {
  const step = Number(intervalDays);
  if (!start || !end) return { dates: [], error: 'Choose the start and end dates.' };
  if (!Number.isInteger(step) || step < 1)
    return { dates: [], error: 'The days between columns must be 1 or more.' };
  const first = utcDay(start);
  const last = utcDay(end);
  if (Number.isNaN(first) || Number.isNaN(last))
    return { dates: [], error: 'Choose the start and end dates.' };
  if (last < first) return { dates: [], error: 'The end date must be on or after the start date.' };
  const count = Math.floor((last - first) / DAY_MS / step) + 1;
  if (count > MAX_COLUMNS) {
    return {
      dates: [],
      error: `That makes ${count} date columns; at most ${MAX_COLUMNS}. Check the dates or space the columns further apart.`,
    };
  }
  return { dates: Array.from({ length: count }, (_, n) => isoDay(first + n * step * DAY_MS)), error: '' };
}

/** A cell's hours as a number; empty or not a number is 0. */
export function hoursOf(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

const round = (value) => Math.round(value * 100) / 100;

/** A row's total over the grid's dates. */
export function rowTotal(hours, dates) {
  return round(dates.reduce((sum, day) => sum + hoursOf(hours?.[day]), 0));
}

/** Each date column's total over all rows. */
export function columnTotals(rows, dates) {
  return dates.map((day) => round(rows.reduce((sum, row) => sum + hoursOf(row.hours?.[day]), 0)));
}

/** Hours entered on dates no longer in the grid (after the dates changed): left out when saved. */
export function hoursOutsideGrid(rows, dates) {
  const inGrid = new Set(dates);
  return round(
    rows.reduce(
      (sum, row) =>
        sum +
        Object.entries(row.hours || {})
          .filter(([day]) => !inGrid.has(day))
          .reduce((rowSum, [, value]) => rowSum + hoursOf(value), 0),
      0,
    ),
  );
}

/** What the server stores: hours only on the grid's dates and only where there are some. */
export function toPayload({ name, startDate, endDate, intervalDays, rows }, dates) {
  const inGrid = new Set(dates);
  return {
    name: name.trim(),
    start_date: startDate,
    end_date: endDate,
    interval_days: Number(intervalDays),
    rows: rows.map((row) => ({
      code: row.code,
      role: row.role,
      hours: Object.fromEntries(
        Object.entries(row.hours || {})
          .filter(([day, value]) => inGrid.has(day) && hoursOf(value) !== 0)
          .map(([day, value]) => [day, hoursOf(value)]),
      ),
    })),
  };
}

/** '2027-01-08' -> '08 Jan 27', the column heading (the sheet's date format). */
export function columnLabel(iso) {
  return new Date(utcDay(iso)).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
    timeZone: 'UTC',
  });
}
