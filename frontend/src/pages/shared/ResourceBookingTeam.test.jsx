// @vitest-environment jsdom
/** The lead's Team Members: Assign Engineer waits for a team and then offers only its people. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ResourceBookingPage } from './ResourceBookingPage';

const WAIT = { timeout: 5000 };

vi.mock('../../AuthContext', () => {
  const auth = { role: 'engineer', user: { id: 5 } };
  return { useAuth: () => auth };
});

let team = [];
const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

function fakeApi(url, options = {}) {
  if (/\/api\/projects\/1\/team-members$/.test(url)) {
    if (options.method === 'PUT') team = JSON.parse(options.body).employee_ids;
    return json({ employee_ids: team });
  }
  if (/\/api\/server-date$/.test(url))
    return json({ date: '2026-10-07', datetime: '2026-10-07T10:00:00+00:00' });
  if (/\/api\/notifications$/.test(url)) return json([]);
  if (/\/api\/projects$/.test(url)) return json([{ id: 1, project_name: 'Hotel Tower', my_role: 'lead' }]);
  if (/\/api\/employees$/.test(url))
    return json([
      { id: 1, name: 'Arjun Mehta', employee_code: 'E0001', role_title: 'Mechanical Engineer' },
      { id: 2, name: 'Ravi Kumar', employee_code: 'E0002', role_title: 'Electrical Engineer' },
    ]);
  if (/\/resource-bookings$/.test(url)) return json([]);
  if (/\/resource-summary$/.test(url)) return json({ project_name: 'Hotel Tower', approval_status: 'draft' });
  if (/\/gantt\?/.test(url)) return json({ engineers: [], date_range: { start: null, end: null }, count: 0 });
  return json({ detail: `No fixture for ${url}` }, 404);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/resource-booking?projectId=1']}>
        <ResourceBookingPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Resource Booking: Team Members (lead)', () => {
  beforeEach(() => {
    team = [];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('keeps Assign Engineer off until the team has people, then offers only them', async () => {
    renderPage();
    const assign = await screen.findByRole('button', { name: /Assign Engineer/ }, WAIT);
    expect(assign.disabled).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /Team Members/ }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Search people'), { target: { value: 'arjun' } });
    expect(within(dialog).queryByText('Ravi Kumar')).toBeNull(); // the search narrows the list
    fireEvent.click(within(dialog).getByRole('checkbox'));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save team' }));

    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), WAIT);
    expect(team).toEqual([1]);
    expect(screen.getByRole('button', { name: /Team Members \(1\)/ })).toBeTruthy();
    await vi.waitFor(() => expect(assign.disabled).toBe(false), WAIT);

    fireEvent.click(assign);
    const options = [...document.querySelectorAll('select option')].map((option) => option.textContent);
    expect(options.some((text) => text.startsWith('Arjun Mehta'))).toBe(true);
    expect(options.some((text) => text.startsWith('Ravi Kumar'))).toBe(false); // not in the team
  });
});
