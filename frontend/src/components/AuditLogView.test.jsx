// @vitest-environment jsdom
/** The audit log view: your own activity, or everyone's for the BU Head with person filter and CSV. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuditLogView } from './AuditLogView';

const WAIT = { timeout: 5000 };
const EVENT = (id, overrides = {}) => ({
  id,
  at: '2026-10-07T09:30:00Z',
  user_id: 7,
  user_name: 'Kavya Raman',
  user_role: 'engineer',
  category: 'time',
  summary: 'Logged in to 1.2 Risers',
  project_id: 1,
  project_name: 'Hotel Tower',
  ...overrides,
});

const json = (body) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
function fakeApi(url) {
  if (url.includes('/api/audit/export')) {
    return Promise.resolve(new Response('When (UTC),Person\n', { status: 200 }));
  }
  if (url.includes('/api/audit'))
    return json({ events: [EVENT(1), EVENT(2, { summary: 'Signed in' })], total: 2 });
  return json({ detail: 'No fixture' });
}

function renderView(props) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuditLogView projects={[{ id: 1, project_name: 'Hotel Tower' }]} {...props} />
    </QueryClientProvider>,
  );
}

const lastUrl = () => fetch.mock.calls.at(-1)[0];

describe('Audit log view', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(fakeApi));
    URL.createObjectURL = vi.fn(() => 'blob:audit');
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows my own activity, with no person column, filtered by type', async () => {
    renderView();

    expect(await screen.findByText('Logged in to 1.2 Risers', {}, WAIT)).toBeTruthy();
    expect(screen.queryByText('PERSON')).toBeNull();
    expect(screen.queryByLabelText('Person')).toBeNull();
    expect(lastUrl()).toMatch(/\/api\/audit\/mine\?/);

    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'hours' } });
    await vi.waitFor(() => expect(lastUrl()).toMatch(/category=hours/), WAIT);
  });

  it('shows everyone for the BU Head, opens on one person, and downloads the CSV', async () => {
    renderView({
      everyone: true,
      initialUserId: '7',
      people: [{ id: 7, full_name: 'Kavya Raman', role: 'engineer' }],
    });

    expect(await screen.findByText('Signed in', {}, WAIT)).toBeTruthy();
    expect(screen.getByText('PERSON')).toBeTruthy();
    expect(lastUrl()).toMatch(/\/api\/audit\?.*user_id=7/);

    fireEvent.click(screen.getByRole('button', { name: /Download CSV/ }));
    await vi.waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledTimes(1), WAIT);
    expect(fetch.mock.calls.some(([url]) => /\/api\/audit\/export\?.*user_id=7/.test(url))).toBe(true);
  });
});
