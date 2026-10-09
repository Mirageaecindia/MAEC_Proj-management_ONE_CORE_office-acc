// @vitest-environment jsdom
/** A notification with a page (a finished subtask, ready for review) opens it and counts as read. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { NotificationBell } from './NotificationBell';

const LINK = '/weekly-logs?projectId=3&employeeId=2&weekStart=2026-10-05';
const NOTES = [
  {
    id: 9,
    notification_type: 'subtask_done',
    title: 'Subtask done: 1.2 Risers',
    message: 'Arjun Mehta finished 1.2 Risers on Hotel Tower: 3 h waiting for your review.',
    link: LINK,
    is_read: false,
    created_at: '2026-10-09T09:00:00Z',
  },
  { id: 8, title: 'Old notice', message: 'Seen already', link: null, is_read: true, created_at: null },
];

function Where() {
  const location = useLocation();
  return <p>at {location.pathname + location.search}</p>;
}

describe('NotificationBell', () => {
  beforeEach(() =>
    vi.stubGlobal(
      'fetch',
      vi.fn((url) =>
        Promise.resolve(
          new Response(JSON.stringify(url.endsWith('/read') ? { ok: true } : NOTES), { status: 200 }),
        ),
      ),
    ),
  );
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('Open goes to the linked page and marks the notification read', async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/wbs-structure']}>
          <NotificationBell />
          <Routes>
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Notifications (1 unread)' }));
    expect(screen.getAllByRole('button', { name: 'Open' })).toHaveLength(1); // only the one with a page
    fireEvent.click(screen.getByRole('button', { name: 'Open' }));

    expect(await screen.findByText(`at ${LINK}`)).toBeTruthy();
    await vi.waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/notifications\/9\/read$/), expect.anything()),
    );
  });
});
