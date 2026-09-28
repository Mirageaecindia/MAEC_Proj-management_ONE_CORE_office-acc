import { describe, expect, it } from 'vitest';
import { canAccess } from './access';

describe('canAccess', () => {
  it('opens lead pages only to engineers who lead a project', () => {
    expect(canAccess(['lead', 'bu_head'], { role: 'engineer', leadsProjects: true })).toBe(true);
    expect(canAccess(['lead', 'bu_head'], { role: 'engineer', leadsProjects: false })).toBe(false);
    expect(canAccess(['lead', 'bu_head'], { role: 'bu_head' })).toBe(true);
    expect(canAccess(['engineer'], { role: 'bu_head', leadsProjects: true })).toBe(false);
  });
});
