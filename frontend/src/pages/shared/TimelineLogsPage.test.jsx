// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom';
import { TimelineLogsPage } from './TimelineLogsPage';

let currentRole = 'engineer';
let reviewBody = { reviewed: 0, skipped_over_mark: 0, action: 'approved' };
let timesheetData;
let rejectedData = [];

const authHeaders = () => ({}); // stable, like the real context
vi.mock('../../AuthContext', () => ({
  useAuth: () => ({ role: currentRole, authHeaders, logout: vi.fn() }),
}));

const SERVER_DATE = { date: '2026-09-24', datetime: '2026-09-24T10:00:00+00:00', timezone: 'UTC' };

const PROJECTS = [
  {
    id: 1,
    project_name: 'TEST 1',
    project_code: '1',
    client_organization: 'C1',
  },
];

const NODES = [
  {
    id: 1,
    project_id: 1,
    parent_id: null,
    wbs_code: '1',
    task_name: 'task 1',
    deliverable_status: 'Not Started',
    phase: 'Space Planning',
    assigned_engineer_id: 3,
    start_date: '2026-09-24',
    end_date: '2026-10-10',
    level: 1,
  },
  {
    id: 2,
    project_id: 1,
    parent_id: 1,
    wbs_code: '1.1',
    task_name: 'subtask 1',
    deliverable_status: 'Done',
    phase: 'Space Planning',
    assigned_engineer_id: 3,
    start_date: '2026-09-24',
    end_date: '2026-09-24',
    level: 2,
  },
  {
    id: 3,
    project_id: 1,
    parent_id: null,
    wbs_code: null,
    task_name: 'task 2',
    deliverable_status: 'Not Started',
    phase: 'ID Coordination',
    assigned_engineer_id: 3,
    start_date: '2026-09-24',
    end_date: '2026-10-10',
    level: 1,
  },
  {
    id: 4,
    project_id: 1,
    parent_id: 3,
    wbs_code: null,
    task_name: 'subtask 2',
    deliverable_status: 'Done',
    phase: 'ID Coordination',
    assigned_engineer_id: 3,
    start_date: '2026-09-25',
    end_date: '2026-09-25',
    level: 2,
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
  tasks: [
    {
      id: 1,
      task_name: 'task 1',
      phase: 'Space Planning',
      deliverable_status: 'Not Started',
      start_date: '2026-09-24',
      end_date: '2026-10-10',
    },
    {
      id: 2,
      task_name: 'subtask 1',
      phase: 'Space Planning',
      deliverable_status: 'Done',
      start_date: '2026-09-24',
      end_date: '2026-09-24',
    },
    {
      id: 3,
      task_name: 'task 2',
      phase: 'ID Coordination',
      deliverable_status: 'Not Started',
      start_date: '2026-09-24',
      end_date: '2026-10-10',
    },
    {
      id: 4,
      task_name: 'subtask 2',
      phase: 'ID Coordination',
      deliverable_status: 'Done',
      start_date: '2026-09-25',
      end_date: '2026-09-25',
    },
  ],
  phases: [
    { phase: 'ID Coordination', total_tasks: 2, completed_tasks: 1, percent_complete: 50 },
    { phase: 'Space Planning', total_tasks: 2, completed_tasks: 1, percent_complete: 50 },
  ],
};

const ROUTES = [
  [/\/api\/server-date$/, SERVER_DATE],
  [/\/api\/projects$/, () => PROJECTS.map((project) => ({ ...project, my_role: currentRole }))],
  [/\/api\/projects\/1\/wbs-structure$/, NODES],
  [/\/api\/projects\/1\/timeline-logs$/, TIMELINE],
  [/\/api\/projects\/1\/rejected-hours$/, () => rejectedData],
];

function fakeApi(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();

  if (method === 'POST' && /\/hours\/review$/.test(url)) {
    const body = JSON.parse(options.body);
    const mine = (entry) =>
      entry.can_review && (body.employee_id == null || entry.employee_id === body.employee_id);
    const overMark = timesheetData.filter((entry) => mine(entry) && entry.hours > 8).length;
    timesheetData = timesheetData.map((entry) =>
      mine(entry) && entry.hours <= 8 ? { ...entry, approval_status: body.action, can_review: false } : entry,
    );
    reviewBody = {
      reviewed: timesheetData.length - overMark,
      skipped_over_mark: overMark,
      action: body.action,
    };
    return Promise.resolve(new Response(JSON.stringify(reviewBody), { status: 200 }));
  }

  if (method === 'POST' && /\/time-log-entries\/\d+\/reapprove$/.test(url)) {
    rejectedData = [];
    return Promise.resolve(new Response(JSON.stringify({ approval_status: 'approved' }), { status: 200 }));
  }

  if (/\/api\/projects\/1\/timesheet\?/.test(url)) {
    return Promise.resolve(new Response(JSON.stringify(timesheetData), { status: 200 }));
  }

  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const fixture = match && (typeof match[1] === 'function' ? match[1]() : match[1]);
  const [status, body] = match ? [200, fixture] : [404, { detail: `No fixture for ${url}` }];
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function WeeklyLogsStub() {
  const [params] = useSearchParams();
  return (
    <div>
      weekly-logs reached: projectId={params.get('projectId')} employeeId={params.get('employeeId')}{' '}
      weekStart={params.get('weekStart')}
    </div>
  );
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/timeline-logs?projectId=1']}>
        <TimelineLogsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const reviewable = (entries) => entries.map((entry) => ({ ...entry, can_review: true }));

describe('Timeline Logs page groups the weekly log by engineer and navigates to details', () => {
  beforeEach(() => {
    currentRole = 'engineer';
    timesheetData = ENTRIES;
    vi.stubGlobal('fetch', vi.fn(fakeApi));
    // The page opens on the browser's current week; pin it to the fixtures' week.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(SERVER_DATE.datetime));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('shows each engineer once as a link with the week’s status, and nothing to approve', async () => {
    const { container } = renderPage();

    await screen.findByText('Ritu');

    expect(screen.getAllByText('Ritu')).toHaveLength(1);
    expect(container.querySelectorAll('tr.timesheet-engineer-group-row')).toHaveLength(1);
    expect(screen.getByText(/2 logged subtasks this week/)).toBeTruthy();
    const link = screen.getByRole('link', { name: /Ritu/ });
    expect(link.getAttribute('href')).toBe('/weekly-logs?projectId=1&employeeId=3&weekStart=2026-09-21');
    expect(screen.queryByText('subtask 1')).toBeNull();

    expect(screen.getByText('Pending review')).toBeTruthy();
    expect(screen.getByText('0 of 1 days approved')).toBeTruthy();
    expect(screen.queryByText('Submit for Approval')).toBeNull(); // no week submission any more
    expect(screen.queryByText('Approve week')).toBeNull();
  });

  it('counts Saturday and Sunday hours in the weekly total (TODO N2)', async () => {
    timesheetData = [...ENTRIES, { ...ENTRIES[0], id: 9, work_date: '2026-09-26', hours: 3 }];
    renderPage();

    expect(await screen.findByText('3.03 hrs')).toBeTruthy(); // 0.02 + 0.01 Thursday + 3 Saturday
  });

  it('shows no status on a week with no logged hours', async () => {
    timesheetData = [];
    renderPage();

    await screen.findByText('No hours logged for this week yet.');
    expect(screen.queryByText('Pending review')).toBeNull();
    expect(screen.getByText(/Weekly Hours Logging \(Week/)).toBeTruthy();
  });

  it('navigates to the engineer weekly log details page when the name is clicked', async () => {
    render(
      <MemoryRouter initialEntries={['/timeline-logs?projectId=1']}>
        <Routes>
          <Route path="/timeline-logs" element={<TimelineLogsPage />} />
          <Route path="/weekly-logs" element={<WeeklyLogsStub />} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('link', { name: /Ritu/ }));

    await screen.findByText(/weekly-logs reached: projectId=1 employeeId=3 weekStart=2026-09-21/);
  });
});

describe('Approving a week, day by day, from the Timeline Logs page', () => {
  beforeEach(() => {
    currentRole = 'lead';
    vi.stubGlobal('fetch', vi.fn(fakeApi));
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(SERVER_DATE.datetime));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('offers Approve week only when the server says pending days are this viewer’s to review', async () => {
    timesheetData = ENTRIES; // can_review: false
    renderPage();

    await screen.findByText('Pending review');
    expect(screen.queryByText('Approve week')).toBeNull();
    expect(screen.queryByText(/Approve all on my tasks/)).toBeNull();
  });

  it('approves the engineer’s pending days on my tasks and shows the week as approved', async () => {
    timesheetData = reviewable(ENTRIES);
    renderPage();

    fireEvent.click(await screen.findByText('Approve week'));

    await screen.findByText('Approved');
    expect(screen.queryByText('Approve week')).toBeNull();
    const call = fetch.mock.calls.find(
      ([url, options]) => /\/hours\/review$/.test(url) && options?.method === 'POST',
    );
    expect(JSON.parse(call[1].body)).toEqual({
      action: 'approved',
      week_start_date: '2026-09-21',
      employee_id: 3,
    });
  });

  it('approves everything pending on my tasks in one click', async () => {
    timesheetData = reviewable(ENTRIES);
    renderPage();

    fireEvent.click(await screen.findByText('Approve all on my tasks (2)'));

    await screen.findByText('Approved');
    const call = fetch.mock.calls.find(
      ([url, options]) => /\/hours\/review$/.test(url) && options?.method === 'POST',
    );
    expect(JSON.parse(call[1].body).employee_id).toBeNull();
  });

  it('a lead approves hours another lead rejected, with a reason', async () => {
    timesheetData = [];
    rejectedData = [
      {
        id: 31,
        employee_name: 'Ritu',
        work_date: '2026-09-21',
        hours: 3,
        wbs_code: '1.1',
        task_name: 'subtask 1',
        rejected_by: 'Anita Kumar',
        reason: 'Idle time',
        hours_left: 50,
        clock_paused: false,
        unattended: false,
        attended_hours: null,
        can_reapprove: true,
      },
    ];
    renderPage();

    expect(await screen.findByText(/Rejected by Anita Kumar: Idle time/)).toBeTruthy();
    expect(screen.getByText(/2 days left to approve/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
    const confirm = screen.getByRole('button', { name: 'Approve 3 h' });
    expect(confirm.disabled).toBe(true); // a reason is required
    fireEvent.change(screen.getByLabelText('Reason for approving rejected hours'), {
      target: { value: 'She was on the site survey' },
    });
    fireEvent.click(confirm);

    await vi.waitFor(() => expect(screen.queryByText(/Rejected by Anita Kumar/)).toBeNull());
    const call = fetch.mock.calls.find(([url]) => /\/time-log-entries\/31\/reapprove$/.test(url));
    expect(JSON.parse(call[1].body)).toEqual({ reason: 'She was on the site survey', attended_only: false });
  });
});
