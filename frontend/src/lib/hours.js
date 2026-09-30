const HOURS_PER_WORKING_DAY = 8;

function toCalendarDate(value) {
  if (value instanceof Date) return value;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value));
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function countWorkingDays(startDate, endDate) {
  if (!startDate || !endDate) return 0;
  const start = toCalendarDate(startDate);
  const end = toCalendarDate(endDate);
  if (!start || !end) return 0;
  if (end < start) return 0;
  let weekdays = 0;
  for (let cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    const day = cursor.getDay();
    if (day !== 0 && day !== 6) weekdays += 1;
  }
  return weekdays;
}

export function plannedHoursForRange(startDate, endDate) {
  return countWorkingDays(startDate, endDate) * HOURS_PER_WORKING_DAY;
}

/** A booking's planned hours: working days x 8 h x the booking percentage (the server's rule). */
export function bookingPlannedHours(startDate, endDate, percent) {
  return Math.round((plannedHoursForRange(startDate, endDate) * (Number(percent) || 0)) / 100);
}
