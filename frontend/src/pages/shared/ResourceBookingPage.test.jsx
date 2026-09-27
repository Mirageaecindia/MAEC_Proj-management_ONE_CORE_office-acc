// @vitest-environment jsdom
/** BU Head rejects a pending booking submission with a reason (TODO C4). */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ResourceBookingPage } from './ResourceBookingPage';

// The page loads several endpoints on mount; allow for a busy machine running the whole suite.
const WAIT = { timeout: 5000 };

vi.mock('../../AuthContext', () => ({
  useAuth: () => ({ role: 'bu_head', authHeaders: () => ({}), logout: vi.fn() }),
}));

let bookingStatus = 'pending_approval';

const booking = () => ({
  id: 9,
  employee_id: 1,
  employee_name: 'Arjun Mehta',
  employee_code: 'E0001',
  discipline: 'Mechanical Engineer',
  role_title: 'Mechanical Engineer',
  planned_hours: 40,
  utilization_rate: 50,
  bench_status: 'Partially Allocated',
  approval_status: bookingStatus,
  start_date: '2026-09-01',
  end_date: '2026-09-30',
});

const ROUTES = [
  [/\/api\/server-date$/, { date: '2026-09-26', datetime: '2026-09-26T10:00:00+00:00', timezone: 'UTC' }],
  [/\/api\/notifications$/, []],
  [/\/api\/projects$/, [{ id: 1, project_name: 'Hotel Tower', project_code: 'MAEC-001' }]],
  [
    /\/api\/employees$/,
    [{ id: 1, name: 'Arjun Mehta', employee_code: 'E0001', discipline: 'Mechanical Engineer' }],
  ],
  [/\/api\/projects\/1\/resource-bookings$/, () => [booking()]],
  [
    /\/api\/projects\/1\/resource-summary$/,
    () => ({ project_name: 'Hotel Tower', approval_status: bookingStatus }),
  ],
  [
    /\/api\/resource-bookings\/gantt\?project_id=1$/,
    { engineers: [], date_range: { start: null, end: null }, count: 0 },
  ],
  [/\/api\/projects\/1\/resource-bookings\/reject$/, () => ({ status: 'draft', status_label: 'Draft' })],
];

function fakeApi(url, options = {}) {
  if (/\/reject$/.test(url) && options.method === 'POST') bookingStatus = 'draft';
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const body = match
    ? typeof match[1] === 'function'
      ? match[1]()
      : match[1]
    : { detail: `No fixture for ${url}` };
  return Promise.resolve(new Response(JSON.stringify(body), { status: match ? 200 : 404 }));
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

describe('Resource Booking: BU Head reject', () => {
  beforeEach(() => {
    bookingStatus = 'pending_approval';
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('asks for a reason, then sends it and refreshes the bookings', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }, WAIT));
    const dialog = screen.getByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: 'Reject' });
    expect(confirm.disabled).toBe(true); // a reason is required

    fireEvent.change(within(dialog).getByRole('textbox'), { target: { value: 'Arjun is needed elsewhere' } });
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);

    await vi.waitFor(() => {
      const reject = fetch.mock.calls.find(
        ([url, options]) => /\/reject$/.test(url) && options?.method === 'POST',
      );
      expect(JSON.parse(reject[1].body)).toEqual({ reason: 'Arjun is needed elsewhere' });
    }, WAIT);
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), WAIT);
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull(); // back to draft: nothing to reject
  });

  it('shows each resource on one line: name (employee code), and discipline once', async () => {
    renderPage();

    const name = await screen.findByText('Arjun Mehta', {}, WAIT);
    expect(name.closest('td').textContent).toBe('Arjun Mehta (E0001)');
    expect(screen.queryByText('AM')).toBeNull(); // no initials badge
    // The assignment timeline is loaded for the selected project only.
    expect(fetch).toHaveBeenCalledWith(expect.stringMatching(/gantt\?project_id=1$/), expect.anything());
    expect(screen.getAllByText('Mechanical Engineer').filter((el) => el.tagName === 'TD')).toHaveLength(1); // discipline = role: shown once
  });

  it('offers Reject only while a submission is pending', async () => {
    bookingStatus = 'approved';
    renderPage();

    expect(await screen.findByRole('button', { name: 'Approved' }, WAIT)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });
});
