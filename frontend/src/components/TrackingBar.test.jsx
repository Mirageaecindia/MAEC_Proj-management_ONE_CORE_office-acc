// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { TrackingBar } from './TrackingBar';

let role = 'engineer';
vi.mock('../AuthContext', () => ({ useAuth: () => ({ role }) }));

let heartbeat;
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

function renderBar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TrackingBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('the tracking bar under the header', () => {
  beforeEach(() => {
    role = 'engineer';
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify(heartbeat), { status: 200 }))),
    );
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('says which subtask is tracked and since when, in the viewer\u2019s time', async () => {
    const loginAt = '2026-09-30T04:00:00+00:00';
    heartbeat = {
      active_session: {
        id: 7,
        project_id: 1,
        subtask_id: 5,
        subtask_name: '1.2 Load estimate',
        login_at: loginAt,
      },
      over_mark: false,
    };
    renderBar();

    const link = await screen.findByRole('link', { name: '1.2 Load estimate' });
    expect(link.getAttribute('href')).toBe('/task-details?nodeId=5&projectId=1');
    expect(screen.getByRole('status').textContent).toContain(`since ${clock(loginAt)}`);
    expect(screen.queryByText(/Over 8 hours today/)).toBeNull();
  });

  it('adds the visit rule once the day is past 8 hours', async () => {
    heartbeat = {
      active_session: {
        id: 7,
        project_id: 1,
        subtask_id: 5,
        subtask_name: '1.2 Load estimate',
        login_at: '2026-09-30T04:00:00Z',
      },
      over_mark: true,
    };
    renderBar();

    expect(await screen.findByText(/Over 8 hours today/)).toBeTruthy();
    expect(screen.getByRole('status').textContent).toContain('every 30 minutes');
  });

  it('tells an engineer the system logged them out, with the day so far in hours and minutes', async () => {
    heartbeat = {
      active_session: null,
      system_logout: { at: '2026-09-30T11:35:00Z', project_id: 1, subtask_id: 5, day_hours: 8.17 },
    };
    renderBar();

    expect(await screen.findByText(/You were logged out at/)).toBeTruthy();
    expect(screen.getByRole('status').textContent).toContain('8 h 10 min and it is saved');
    expect(screen.getByRole('link', { name: 'Log in again' }).getAttribute('href')).toBe(
      '/task-details?nodeId=5&projectId=1',
    );
  });

  it('shows nothing when nothing is tracked, and nothing at all for the BU Head', async () => {
    heartbeat = { active_session: null, system_logout: null };
    const engineer = renderBar();
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole('status')).toBeNull();
    // The line keeps its space for an engineer, so the page doesn't move on Login or Logout.
    expect(engineer.container.querySelector('.tracking-slot')).not.toBeNull();
    cleanup();

    role = 'bu_head';
    fetch.mockClear();
    const buHead = renderBar();
    expect(screen.queryByRole('status')).toBeNull();
    expect(buHead.container.querySelector('.tracking-slot')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
});
