import { describe, expect, it } from 'vitest';
import {
  MAX_COLUMNS,
  columnDates,
  columnLabel,
  columnTotals,
  hoursOutsideGrid,
  rowTotal,
  stagesOutsideGrid,
  toPayload,
} from './estimation';

const JAN = ['2027-01-01', '2027-01-08', '2027-01-15', '2027-01-22', '2027-01-29'];

describe('columnDates', () => {
  it('starts at the start date and steps by the days given, up to the end date', () => {
    expect(columnDates('2027-01-01', '2027-02-01', 7)).toEqual({ dates: JAN, error: '' });
    expect(columnDates('2027-01-01', '2027-01-29', 7).dates).toEqual(JAN); // the end date when it falls on one
    expect(columnDates('2027-01-01', '2027-01-01', 7).dates).toEqual(['2027-01-01']);
    expect(columnDates('2027-03-27', '2027-03-29', 1).dates).toEqual([
      '2027-03-27',
      '2027-03-28',
      '2027-03-29',
    ]);
  });

  it('says why there are no columns', () => {
    expect(columnDates('', '2027-02-01', 7).error).toMatch(/start and end/);
    expect(columnDates('2027-02-01', '2027-01-01', 7).error).toMatch(/on or after/);
    expect(columnDates('2027-01-01', '2027-02-01', 0).error).toMatch(/1 or more/);
    expect(columnDates('2027-01-01', '2040-01-01', 1).error).toMatch(`at most ${MAX_COLUMNS}`);
  });
});

describe('totals', () => {
  const rows = [
    { hours: { '2027-01-01': '9', '2027-01-15': '22.5' } },
    { hours: { '2027-01-08': 27, '2027-01-29': '', '2027-02-05': 40 } }, // the last is off the grid
  ];

  it('adds each row, each date column and leaves blank cells out', () => {
    expect(rows.map((row) => rowTotal(row.hours, JAN))).toEqual([31.5, 27]);
    expect(columnTotals(rows, JAN)).toEqual([9, 27, 22.5, 0, 0]);
    expect(hoursOutsideGrid(rows, JAN)).toBe(40);
  });

  it('sends only the hours on the grid, as numbers', () => {
    const payload = toPayload(
      {
        name: ' Tender ',
        startDate: '2027-01-01',
        endDate: '2027-02-01',
        intervalDays: '7',
        rows: [{ code: 'BE', role: 'BIM Modeller-E', ...rows[1] }],
        stages: { '2027-01-01': 'CD', '2027-01-08': '', '2027-02-05': 'SD' },
      },
      JAN,
    );
    expect(payload).toEqual({
      name: 'Tender',
      start_date: '2027-01-01',
      end_date: '2027-02-01',
      interval_days: 7,
      rows: [{ code: 'BE', role: 'BIM Modeller-E', hours: { '2027-01-08': 27 } }],
      stages: { '2027-01-01': 'CD' }, // empty and off-grid stages left out
    });
    expect(stagesOutsideGrid({ '2027-01-01': 'CD', '2027-02-05': 'SD' }, JAN)).toBe(1);
  });
});

it('labels a column like the resourcing sheet', () => {
  expect(columnLabel('2027-01-08')).toBe('08 Jan 27');
});
