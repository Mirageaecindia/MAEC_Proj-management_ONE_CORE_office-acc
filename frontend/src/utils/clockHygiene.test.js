// The frontend never decides a day from the browser clock: "today" comes from the server
// (hooks/useServerToday.js), because the browser's local date and the server's UTC day differ
// between midnight and 05:30 India time. This test fails on any new `new Date()` in page or
// component code; the few allowed ones are instants (a timestamp), not days.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..');
const ALLOWED = new Set([
  'hooks/useServerToday.js', // the browser's UTC date until the server has answered
  'hooks/useTracking.js', // the instant of a click, sent to the server as a timestamp
  'pages/shared/WbsStructurePage.jsx', // "Last refreshed HH:MM", a timestamp
]);

function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(js|jsx)$/.test(name) && !/\.test\.(js|jsx)$/.test(name) ? [path] : [];
  });
}

describe('one clock', () => {
  it('no page or component builds a day on the browser clock', () => {
    const offenders = sourceFiles(SRC).flatMap((path) => {
      const file = relative(SRC, path).replace(/\\/g, '/');
      if (ALLOWED.has(file)) return [];
      return readFileSync(path, 'utf8')
        .split('\n')
        .map((line, index) => (line.includes('new Date()') ? `${file}:${index + 1}: ${line.trim()}` : null))
        .filter(Boolean);
    });
    expect(offenders, 'take "today" from useServerToday() instead').toEqual([]);
  });
});
