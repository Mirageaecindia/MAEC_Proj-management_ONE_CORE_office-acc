/**
 * Project estimation grid (backend: app/domain/estimation.py). The columns are dates: the start
 * date, then every `intervalDays` days, up to the end date. Each row is a staff code and role with
 * hours per column date; totals are per row, per date column and for the whole grid.
 */

export const MAX_COLUMNS = 400; // the server's limit too
export const HOURS_PER_DAY = 9; // one person's working day (Monday to Friday); the server's rule too
/** The design stage a date column falls in (the sheet's stage row), chosen per column or left empty. */
export const STAGES = ['CD', 'SD', 'DD', 'TD', 'IFC'];
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

/**
 * The most hours one person can have in each date column: HOURS_PER_DAY for each working day
 * (Monday to Friday) the column covers, from its date to the day before the next column (the
 * last column: to the end date). Every 2 days from a Monday: 18; from a Friday: 9.
 */
export function columnLimits(dates, endDate, intervalDays) {
  const end = utcDay(endDate);
  const span = Number(intervalDays) - 1;
  return Object.fromEntries(
    dates.map((day) => {
      const first = utcDay(day);
      const last = Math.min(first + span * DAY_MS, end);
      let working = 0;
      for (let ms = first; ms <= last; ms += DAY_MS) {
        const weekday = new Date(ms).getUTCDay();
        if (weekday !== 0 && weekday !== 6) working += 1;
      }
      return [day, working * HOURS_PER_DAY];
    }),
  );
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

/** Stages chosen on dates no longer in the grid: left out when saved. */
export function stagesOutsideGrid(stages, dates) {
  const inGrid = new Set(dates);
  return Object.entries(stages || {}).filter(([day, stage]) => stage && !inGrid.has(day)).length;
}

/** What the server stores: hours and stages only on the grid's dates, and only where there are some. */
export function toPayload({ name, startDate, endDate, intervalDays, rows, stages = {} }, dates) {
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
    stages: Object.fromEntries(Object.entries(stages).filter(([day, stage]) => inGrid.has(day) && stage)),
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
