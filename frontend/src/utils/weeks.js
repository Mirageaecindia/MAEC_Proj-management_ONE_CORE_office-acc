/** Week arithmetic shared by the timesheet pages (weeks start on Monday). */

export function getMonday(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(date.setDate(diff));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

/** Local date as 'YYYY-MM-DD'. */
export function formatDateStr(dateObj) {
  const y = dateObj.getFullYear();
  const m = String(dateObj.getMonth() + 1).padStart(2, '0');
  const d = String(dateObj.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** ISO week number and a "Sep 21 - 27, 2026" label for the week starting on `monday`. */
export function getWeekInfo(monday) {
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  const target = new Date(monday.valueOf());
  const dayNr = (monday.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  }
  const weekNum = 1 + Math.round((firstThursday - target.valueOf()) / 604800000);

  const startMonth = monday.toLocaleString('en-US', { month: 'short' });
  const endMonth = sunday.toLocaleString('en-US', { month: 'short' });
  const rangeStr =
    startMonth === endMonth
      ? `${startMonth} ${monday.getDate()} - ${sunday.getDate()}, ${monday.getFullYear()}`
      : `${startMonth} ${monday.getDate()} - ${endMonth} ${sunday.getDate()}, ${monday.getFullYear()}`;

  return { weekNum, rangeStr };
}
