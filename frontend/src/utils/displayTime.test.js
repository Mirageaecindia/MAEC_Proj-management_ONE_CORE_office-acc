import { describe, expect, it } from 'vitest';
import { formatDayIST } from './displayTime';

describe('formatDayIST', () => {
  it("gives a UTC timestamp's day in India, in the WBS's date format", () => {
    expect(formatDayIST('2026-09-02T04:30:00Z')).toBe('2026-09-02');
    expect(formatDayIST('2026-09-02T20:00:00+00:00')).toBe('2026-09-03'); // 01:30 the next day in IST
    expect(formatDayIST('2026-09-02T20:00:00')).toBe('2026-09-03'); // a naive server time is UTC
  });

  it('leaves the cell empty when there is no time', () => {
    expect(formatDayIST(null)).toBe('');
    expect(formatDayIST('')).toBe('');
    expect(formatDayIST('not a date')).toBe('');
  });
});
