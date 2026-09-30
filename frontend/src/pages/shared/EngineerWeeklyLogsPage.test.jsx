// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { EngineerWeeklyLogsPage } from './EngineerWeeklyLogsPage';

let currentRole = 'engineer';
const authHeaders = () => ({});
vi.mock('../../AuthContext', () => ({
  useAuth: () => ({ role: currentRole, authHeaders, logout: vi.fn() }),
}));

const PROJECTS = [{ id: 1, project_name: 'TEST 1' }];

const NODES = [
  {
    id: 1,
    project_id: 1,
    parent_id: null,
    wbs_code: '1',
    task_name: 'task 1',
    deliverable_status: 'Not Started',
    assigned_engineer_id: 3,
  },
  {
    id: 2,
    project_id: 1,
    parent_id: 1,
    wbs_code: '1.1',
    task_name: 'subtask 1',
    deliverable_status: 'Done',
    assigned_engineer_id: 3,
  },
  {
    id: 3,
    project_id: 1,
    parent_id: null,
    wbs_code: null,
    task_name: 'task 2',
    deliverable_status: 'Not Started',
    assigned_engineer_id: 3,
  },
  {
    id: 4,
    project_id: 1,
    parent_id: 3,
    wbs_code: null,
    task_name: 'subtask 2',
    deliverable_status: 'Done',
    assigned_engineer_id: 3,
  },
];

// One row per subtask, engineer and day (Thursday 24 Sep 2026), as GET /timesheet returns them.
const ENTRIES = [
  {
    id: 1,
    project_id: 1,
    task_id: 2,
    wbs_code: '1.1',
    task_name: 'subtask 1',
    employee_id: 3,
    employee_name: 'Ritu',
    work_date: '2026-09-24',
    hours: 0.02,
    approval_status: 'pending_review',
    reviewed_by: null,
    reviewed_at: null,
    review_reason: null,
    finished: true,
    can_review: false,
  },
  {
    id: 2,
    project_id: 1,
    task_id: 4,
    wbs_code: null,
    task_name: 'subtask 2',
    employee_id: 3,
    employee_name: 'Ritu',
    work_date: '2026-09-24',
    hours: 0.01,
    approval_status: 'pending_review',
    reviewed_by: null,
    reviewed_at: null,
    review_reason: null,
    finished: true,
    can_review: false,
  },
];

const TIMELINE = {
  scope: { role: 'engineer', engineer_id: 3, engineer_name: 'Ritu' },
  engineers: [{ id: 3, name: 'Ritu', employee_code: 'M0182' }],
  tasks: [],
  phases: [],
};

let entriesData = [];

const ROUTES = [
  [/\/api\/projects$/, () => PROJECTS.map((project) => ({ ...project, my_role: currentRole }))],
  [/\/api\/projects\/1\/wbs-structure$/, NODES],
  [/\/api\/projects\/1\/timesheet\?/, () => entriesData],
  [/\/api\/projects\/1\/timeline-logs$/, TIMELINE],
  [/\/api\/server-date$/, () => ({ date: new Date().toISOString().slice(0, 10) })], // today, as the server says
];

function fakeApi(url, options) {
  const method = (options && options.method) || 'GET';
  const decision = url.match(/\/time-log-entries\/(\d+)\/(approve-attended|approve|reject)$/);
  if (method === 'POST' && decision) {
    const [, id, action] = decision;
    const reason = JSON.parse(options.body).reason;
    const attendedOnly = action === 'approve-attended';
    entriesData = entriesData.map((entry) =>
      String(entry.id) === id
        ? {
            ...entry,
            approval_status: action === 'reject' ? 'rejected' : 'approved',
            reviewed_by: 'Anita Kumar',
            review_reason: attendedOnly ? 'Approved up to the last visit: 2 of 8 h' : reason,
            ...(attendedOnly ? { hours: entry.attended_hours, unattended: false, attended_hours: null } : {}),
          }
        : entry,
    );
    return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
  }
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const fixture = match && (typeof match[1] === 'function' ? match[1]() : match[1]);
  const [status, body] = match ? [200, fixture] : [404, { detail: `No fixture for ${url}` }];
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  );
}

function renderPage(route = '/weekly-logs?projectId=1&employeeId=3&weekStart=2026-09-21') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[route]}>
        <EngineerWeeklyLogsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Engineer Weekly Logs details page', () => {
  beforeEach(() => {
    currentRole = 'engineer';
    entriesData = ENTRIES;
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows the engineer, the week, and one row per subtask and day', async () => {
    const { container } = renderPage();

    expect(await screen.findByText('Ritu')).toBeTruthy();
    expect(screen.getAllByText(/Sep 21 - 27, 2026/).length).toBeGreaterThan(0);

    const details = container.querySelector('.details-table');
    expect(within(details).getByText('subtask 1')).toBeTruthy();
    expect(within(details).getByText('subtask 2')).toBeTruthy();
    expect(within(details).getByText('task 1')).toBeTruthy();
    expect(within(details).getByText('1.1')).toBeTruthy();
    expect(within(details).getAllByText('Thu, Sep 24')).toHaveLength(2);
    expect(within(details).getByText('0.02 hrs')).toBeTruthy();
    expect(within(details).getByText('0.01 hrs')).toBeTruthy();
    expect(within(details).getAllByText('Pending review')).toHaveLength(2);
  });

  it('an engineer only reads the status of each day', async () => {
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });
});

describe('Reviewing days on the Engineer Weekly Logs page', () => {
  beforeEach(() => {
    currentRole = 'lead';
    entriesData = ENTRIES.map((entry) => ({ ...entry, can_review: true }));
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('approves one day at a time and names the reviewer', async () => {
    renderPage();

    fireEvent.click((await screen.findAllByRole('button', { name: 'Approve' }))[0]);

    expect(await screen.findByText('Approved')).toBeTruthy();
    expect(screen.getByText('by Anita Kumar')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Approve' })).toHaveLength(1); // the other day is still pending
  });

  it('shows an unattended session and approves the day up to the last visit', async () => {
    entriesData = entriesData.map((entry, index) =>
      index === 0
        ? {
            ...entry,
            hours: 8,
            can_review: true,
            unattended: true,
            attended_hours: 2,
            sessions: [
              {
                login_at: '2026-09-24T09:00:00Z',
                logout_at: '2026-09-24T17:00:00Z',
                last_visit_at: '2026-09-24T11:00:00Z',
                ended_by: 'laptop_off',
                unattended: true,
              },
            ],
          }
        : entry,
    );
    renderPage();

    expect(await screen.findByText('unattended')).toBeTruthy();
    expect(screen.getByText(/last visit .* laptop off/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Approve up to last visit (2 h)' }));

    expect(await screen.findByText(/Approved up to the last visit: 2 of 8 h/)).toBeTruthy();
    expect(screen.queryByText('unattended')).toBeNull();
    expect(screen.getByText('2.00 hrs')).toBeTruthy();
  });

  it('rejecting a pending day asks for a reason too', async () => {
    renderPage();

    fireEvent.click((await screen.findAllByRole('button', { name: 'Reject' }))[0]);

    expect(screen.getByRole('button', { name: 'Confirm reject' }).disabled).toBe(true);
    expect(fetch.mock.calls.some(([url]) => /\/reject$/.test(url))).toBe(false); // nothing sent without one
  });

  it('says in plain words what a partial approval left out, and when today becomes reviewable', async () => {
    const today = new Date().toISOString().slice(0, 10);
    entriesData = [
      { ...entriesData[0], hours: 2, approval_status: 'approved', trimmed_hours: 6, can_review: false },
      { ...entriesData[1], work_date: today, finished: false, can_review: false },
    ];
    renderPage();

    expect(await screen.findByText('6 h not approved (unattended)')).toBeTruthy();
    expect(screen.getByText('Reviewable from tomorrow.')).toBeTruthy();
  });

  it('taking approved hours back asks for a reason and shows it', async () => {
    entriesData = [{ ...entriesData[0], approval_status: 'approved' }];
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Reject' }));
    const confirm = screen.getByRole('button', { name: 'Confirm reject' });
    expect(confirm.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Reason for rejecting these hours'), {
      target: { value: 'Wrong subtask' },
    });
    fireEvent.click(confirm);

    expect(await screen.findByText('Rejected')).toBeTruthy();
    expect(screen.getByText('Wrong subtask')).toBeTruthy();
    const call = fetch.mock.calls.find(([url]) => /\/time-log-entries\/1\/reject$/.test(url));
    expect(JSON.parse(call[1].body)).toEqual({ reason: 'Wrong subtask' });
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull(); // rejected hours are final here
  });
});
