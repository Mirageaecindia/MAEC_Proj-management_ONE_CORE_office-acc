import { describe, expect, it } from 'vitest';
import {
  NOT_AVAILABLE,
  formatAmount,
  formatBytes,
  formatDecimal,
  formatHours,
  formatInteger,
  formatMoney,
  formatPercent,
  parseAmount,
} from './format';

describe('number formatting', () => {
  it('formats hours and percentages to one decimal', () => {
    expect(formatHours(12.345)).toBe('12.3 Hrs');
    expect(formatHours(10, { unit: 'hrs' })).toBe('10.0 hrs');
    expect(formatPercent(42.25)).toBe('42.3%');
    expect(formatDecimal(0.3, 2)).toBe('0.30');
  });

  it('falls back when there is no number', () => {
    expect(formatHours(null)).toBe(NOT_AVAILABLE);
    expect(formatPercent(undefined)).toBe(NOT_AVAILABLE);
    expect(formatDecimal('abc', 2, { fallback: 'N/A' })).toBe('N/A');
    expect(formatInteger('')).toBe('—');
  });

  it('formats integers with thousands separators', () => {
    expect(formatInteger(3840)).toBe('3,840');
  });
});

describe('money', () => {
  it('formats a currency amount', () => {
    expect(formatMoney(50000, 'USD')).toBe('$50,000.00');
    expect(formatMoney(null, 'USD')).toBe(NOT_AVAILABLE);
  });

  it('formats and parses raw amounts', () => {
    expect(formatAmount('480000')).toBe('480,000.00');
    expect(formatAmount('', { fallback: '' })).toBe('');
    expect(parseAmount('480,000.50')).toBe(480000.5);
  });
});

describe('formatBytes', () => {
  it('uses binary units', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5 MB');
  });
});
