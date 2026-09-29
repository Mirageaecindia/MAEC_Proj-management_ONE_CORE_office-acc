import { describe, expect, it } from 'vitest';
import { groupByEngineer, rowsStatus, summarizeWeek, weekdayIndex, isOverMark } from './hours';

const row = (overrides) => ({
  employee_id: 3,
  employee_name: 'Ritu',
  work_date: '2026-09-24',
  hours: 2,
  approval_status: 'pending_review',
  can_review: false,
  ...overrides,
});

describe('daily hours helpers', () => {
  it('maps a date to its weekday column, Monday first', () => {
    expect(weekdayIndex('2026-09-21')).toBe(0); // Monday
    expect(weekdayIndex('2026-09-27')).toBe(6); // Sunday
  });

  it('sums a week per day and reports each day’s status', () => {
    const summary = summarizeWeek([
      row({ hours: 2, approval_status: 'approved' }),
      row({ hours: 1.5, work_date: '2026-09-24', approval_status: 'pending_review', can_review: true }),
      row({ hours: 3, work_date: '2026-09-26', approval_status: 'approved' }),
    ]);

    expect(summary.days[3]).toEqual({ hours: 3.5, status: 'pending_review' }); // Thursday: one row still pending
    expect(summary.days[5]).toEqual({ hours: 3, status: 'approved' }); // Saturday counts like any day
    expect(summary.total).toBe(6.5);
    expect([summary.approved, summary.pending, summary.rejected]).toEqual([5, 1.5, 0]);
    expect([summary.daysLogged, summary.daysApproved, summary.reviewable]).toEqual([2, 1, 1]);
  });

  it('calls a set of rows mixed only when nothing is pending', () => {
    expect(rowsStatus([])).toBe('none');
    expect(rowsStatus([row({ approval_status: 'approved' }), row({ approval_status: 'rejected' })])).toBe(
      'mixed',
    );
    expect(rowsStatus([row({ approval_status: 'approved' }), row()])).toBe('pending_review');
  });

  it('groups rows by engineer in name order', () => {
    const groups = groupByEngineer([row({ employee_id: 5, employee_name: 'Vivek' }), row(), row()]);

    expect(groups.map((group) => [group.employee_name, group.rows.length])).toEqual([
      ['Ritu', 2],
      ['Vivek', 1],
    ]);
  });
});

describe('isOverMark', () => {
  it('flags only days beyond 8 hours', () => {
    expect([isOverMark(8), isOverMark(8.01), isOverMark('9'), isOverMark(0)]).toEqual([
      false,
      true,
      true,
      false,
    ]);
  });
});
