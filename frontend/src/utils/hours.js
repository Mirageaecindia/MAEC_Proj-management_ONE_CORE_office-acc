import { parseApiTimestamp } from './displayTime';

/**
 * Daily hours: one row per subtask, engineer and day, approved per day by the task's lead
 * (or the BU Head). The week is only the sum of its days.
 */

export const DAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

/** Hours in a day past which the time is overtime: banked in full, flagged for the reviewer. */
export const DAILY_MARK_HOURS = 8;

export const isOverMark = (hours) => Number(hours) > DAILY_MARK_HOURS;

/** What a bulk approval left for the reviewer to look at one by one, or '' when nothing. */
export function bulkNotice({
  reviewed = 0,
  skipped_over_mark: over = 0,
  skipped_unattended: unattended = 0,
}) {
  const left = [over && `${over} over 8 hours`, unattended && `${unattended} unattended`].filter(Boolean);
  if (!left.length) return '';
  const days = over + unattended;
  return `Approved ${reviewed} day${reviewed === 1 ? '' : 's'}. ${days} day${days === 1 ? '' : 's'} left for review: ${left.join(', ')} (open the weekly log).`;
}

/** What is left of the seven days in which rejected hours can be approved again. */
export function describeTimeLeft(hoursLeft) {
  if (hoursLeft >= 48) return `${Math.floor(hoursLeft / 24)} days left to approve.`;
  if (hoursLeft >= 24) return '1 day left to approve.';
  const hours = Math.max(1, Math.round(hoursLeft));
  return `${hours} hour${hours === 1 ? '' : 's'} left to approve.`;
}

const SESSION_END_LABELS = {
  engineer: 'logged out',
  laptop_off: 'laptop off',
  no_visit: 'logged out by the system (no visit)',
  subtask_deleted: 'subtask deleted',
  project_archived: 'project archived',
};

// Server times are UTC; the browser shows them in the viewer's own time zone.
const clock = (value) =>
  parseApiTimestamp(value)?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) ?? '';

/** Hours in words, to the minute: 8.17 -> "8 h 10 min", 6 -> "6 h", 0.5 -> "30 min". */
export function formatDuration(hours) {
  const minutes = Math.round((Number(hours) || 0) * 60);
  const whole = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (whole && rest) return `${whole} h ${rest} min`;
  return whole ? `${whole} h` : `${rest} min`;
}

/** One line per Login/Logout session behind a day's row: "09:00 – 17:00 · last visit 11:00 · laptop off". */
export function describeSession(session) {
  const parts = [`${clock(session.login_at)} – ${clock(session.logout_at)}`];
  if (session.unattended) parts.push(`last visit ${clock(session.last_visit_at)}`);
  parts.push(SESSION_END_LABELS[session.ended_by] || 'ended');
  return parts.join(' · ');
}

export const HOURS_STATUS_LABELS = {
  pending_review: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
};

/** What a day cell's colour means, in the order of the legend. */
export const DAY_LEGEND = [
  ['status-approved', 'Approved'],
  ['status-pending', 'Pending'],
  ['status-rejected', 'Rejected'],
  ['is-over-mark', 'Over 8 h'],
  ['is-unattended', 'Unattended'],
];

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

/** A day the reviewer must look at on its own: bulk approval leaves it alone. */
export const needsIndividualReview = (row) => isOverMark(row.hours) || Boolean(row.unattended);

/** "15.5 h approved \u00b7 6 h pending \u00b7 9 h rejected": only the parts that exist. */
export function describeTotals({ approved, pending, rejected }) {
  return [
    approved && `${approved} h approved`,
    pending && `${pending} h pending`,
    rejected && `${rejected} h rejected`,
  ]
    .filter(Boolean)
    .join(' \u00b7 ');
}

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
  const mine = rows.filter((row) => row.can_review && row.approval_status === 'pending_review');
  const approved = byStatus('approved');
  const pending = byStatus('pending_review');
  return {
    days: days.map((day) => ({
      hours: day.hours,
      status: rowsStatus(day.rows),
      unattended: day.rows.some((row) => row.unattended),
    })),
    total: round2(approved + pending), // rejected hours never count
    approved,
    pending,
    rejected: byStatus('rejected'),
    status: rowsStatus(rows),
    daysLogged: loggedDays.length,
    daysApproved: loggedDays.filter((day) => rowsStatus(day.rows) === 'approved').length,
    // Pending, finished days the viewer reviews: what a bulk approval decides, and what it
    // leaves for an individual look (over 8 hours, unattended).
    reviewable: mine.filter((row) => !needsIndividualReview(row)).length,
    held: mine.filter(needsIndividualReview).length,
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
