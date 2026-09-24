import test from 'node:test';
import assert from 'node:assert/strict';

import { parseApiTimestamp, formatDateTimeIST, formatDateIST } from '../src/utils/displayTime.js';

test('naive backend timestamps are parsed as UTC', () => {
  assert.equal(parseApiTimestamp('2026-09-24T06:58:00').toISOString(), '2026-09-24T06:58:00.000Z');
});

test('tz-aware UTC timestamps parse identically', () => {
  assert.equal(parseApiTimestamp('2026-09-24T06:58:00Z').toISOString(), '2026-09-24T06:58:00.000Z');
  assert.equal(parseApiTimestamp('2026-09-24T06:58:00+00:00').toISOString(), '2026-09-24T06:58:00.000Z');
});

test('known UTC timestamp shifts to the expected IST wall-clock value', () => {
  assert.match(formatDateTimeIST('2026-09-24T06:58:00'), /12:28 PM/);
});

test('IST is 5.5 hours ahead: UTC 06:58 shows 12:28 local', () => {
  assert.match(formatDateTimeIST('2026-09-24T06:58:00'), /Sep 24, 2026, 12:28 PM/);
});

test('UTC day boundary rolls into the next IST day after 18:30 UTC', () => {
  assert.match(formatDateTimeIST('2026-09-24T18:30:00'), /Sep 25, 2026, 12:00 AM/);
});

test('date-only rendering evaluates the IST date, not the UTC date', () => {
  assert.equal(formatDateIST('2026-09-24T23:00:00'), 'Sep 25, 2026');
});

test('empty and invalid inputs return the fallback', () => {
  assert.equal(formatDateTimeIST(null, { fallback: '\u2014' }), '\u2014');
  assert.equal(formatDateTimeIST('', { fallback: '\u2014' }), '\u2014');
  assert.equal(formatDateTimeIST(undefined, { fallback: '\u2014' }), '\u2014');
  assert.equal(formatDateTimeIST('not-a-date', { fallback: '\u2014' }), '\u2014');
});