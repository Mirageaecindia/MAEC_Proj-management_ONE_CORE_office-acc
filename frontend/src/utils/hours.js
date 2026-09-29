/**
 * Daily hours: one row per subtask, engineer and day, approved per day by the task's lead
 * (or the BU Head). The week is only the sum of its days.
 */

export const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

/** Hours in a day past which the time is overtime: banked in full, flagged for the reviewer. */
export const DAILY_MARK_HOURS = 8;

export const isOverMark = (hours) => Number(hours) > DAILY_MARK_HOURS;

export const HOURS_STATUS_LABELS = {
  pending_review: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
};

export const HOURS_STATUS_PILL = {
  pending_review: 'status-pending',
  approved: 'status-approved',
  rejected: 'status-rejected',
  mixed: 'status-pending',
  none: 'status-none',
};

/** 'YYYY-MM-DD' -> 0 (Monday) … 6 (Sunday). */
export function weekdayIndex(isoDate) {
  const day = new Date(`${isoDate}T00:00:00`).getDay();
  return (day + 6) % 7;
}

const round2 = (value) => Math.round((Number(value) || 0) * 100) / 100;

/** The status of a set of rows (a day, or a week): all one status, or 'mixed'; 'none' when empty. */
export function rowsStatus(rows) {
  if (rows.length === 0) return 'none';
  const statuses = new Set(rows.map((row) => row.approval_status));
  if (statuses.size === 1) return rows[0].approval_status;
  return statuses.has('pending_review') ? 'pending_review' : 'mixed';
}

/** One engineer's week: hours per day with each day's status, totals, and what's waiting on the viewer. */
export function summarizeWeek(rows) {
  const days = DAY_KEYS.map(() => ({ hours: 0, rows: [] }));
  for (const row of rows) {
    const day = days[weekdayIndex(row.work_date)];
    day.hours = round2(day.hours + row.hours);
    day.rows.push(row);
  }
  const byStatus = (status) =>
    round2(rows.filter((row) => row.approval_status === status).reduce((sum, row) => sum + row.hours, 0));
  const loggedDays = days.filter((day) => day.rows.length > 0);
  return {
    days: days.map((day) => ({ hours: day.hours, status: rowsStatus(day.rows) })),
    total: round2(rows.reduce((sum, row) => sum + row.hours, 0)),
    approved: byStatus('approved'),
    pending: byStatus('pending_review'),
    rejected: byStatus('rejected'),
    status: rowsStatus(rows),
    daysLogged: loggedDays.length,
    daysApproved: loggedDays.filter((day) => rowsStatus(day.rows) === 'approved').length,
    // Pending, finished days that the viewer is the reviewer of: what "Approve week" would decide.
    reviewable: rows.filter((row) => row.can_review && row.approval_status === 'pending_review').length,
  };
}

/** Group daily rows by engineer, sorted by name. */
export function groupByEngineer(rows) {
  const groups = new Map();
  for (const row of rows) {
    const key = String(row.employee_id);
    if (!groups.has(key))
      groups.set(key, { employee_id: row.employee_id, employee_name: row.employee_name, rows: [] });
    groups.get(key).rows.push(row);
  }
  return Array.from(groups.values()).sort((a, b) =>
    (a.employee_name || '').localeCompare(b.employee_name || ''),
  );
}
