// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom';
import { TimelineLogsPage } from './TimelineLogsPage';

let currentRole = 'engineer';
let submissions = [];
let timesheetData;

vi.mock('../../AuthContext', () => ({
  useAuth: () => ({ role: currentRole, authHeaders: () => ({}), logout: vi.fn() }),
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

const ENTRIES = [
  {
    id: 1,
    project_id: 1,
    task_id: 2,
    wbs_code: '1.1',
    task_name: 'subtask 1',
    employee_id: 3,
    employee_name: 'Ritu',
    week_start_date: '2026-09-21',
    mon_hours: 0,
    tue_hours: 0,
    wed_hours: 0,
    thu_hours: 0.02,
    fri_hours: 0,
    sat_hours: 0,
    sun_hours: 0,
    total_hours: 0.02,
    approval_status: 'pending_review',
    reviewed_by: null,
    reviewed_at: null,
  },
  {
    id: 2,
    project_id: 1,
    task_id: 4,
    wbs_code: null,
    task_name: 'subtask 2',
    employee_id: 3,
    employee_name: 'Ritu',
    week_start_date: '2026-09-21',
    mon_hours: 0,
    tue_hours: 0,
    wed_hours: 0,
    thu_hours: 0.01,
    fri_hours: 0,
    sat_hours: 0,
    sun_hours: 0,
    total_hours: 0.01,
    approval_status: 'pending_review',
    reviewed_by: null,
    reviewed_at: null,
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
];

function submission(status, overrides = {}) {
  return {
    id: 1,
    project_id: 1,
    employee_id: 3,
    employee_name: 'Ritu',
    week_start_date: '2026-09-21',
    status,
    status_label:
      status === 'submitted'
        ? 'Submitted for Approval'
        : status === 'approved'
          ? 'Approved'
          : status === 'rejected'
            ? 'Rejected'
            : 'Not Submitted',
    submitted_at: '2026-09-24T10:00:00+00:00',
    reviewed_by: null,
    reviewed_at: null,
    ...overrides,
  };
}

function fakeApi(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();

  if (method === 'POST') {
    if (/\/weekly-hours\/submit$/.test(url)) {
      submissions = [submission('submitted')];
      return Promise.resolve(new Response(JSON.stringify(submission('submitted')), { status: 200 }));
    }
    if (/\/weekly-hours\/approve$/.test(url)) {
      submissions = [submission('approved')];
      return Promise.resolve(new Response(JSON.stringify(submission('approved')), { status: 200 }));
    }
    if (/\/weekly-hours\/reject$/.test(url)) {
      submissions = [submission('rejected')];
      return Promise.resolve(new Response(JSON.stringify(submission('rejected')), { status: 200 }));
    }
  }

  if (/\/api\/projects\/1\/weekly-hours-submissions\?/.test(url)) {
    return Promise.resolve(new Response(JSON.stringify(submissions), { status: 200 }));
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
  return render(
    <MemoryRouter initialEntries={['/timeline-logs?projectId=1']}>
      <TimelineLogsPage />
    </MemoryRouter>,
  );
}

describe('Timeline Logs page groups the weekly log by engineer and navigates to details', () => {
  beforeEach(() => {
    currentRole = 'engineer';
    submissions = [];
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

  it('shows each engineer once as a link, no inline details, no approve/reject, only Submit', async () => {
    const { container } = renderPage();

    await screen.findByText('Ritu');

    expect(screen.getAllByText('Ritu')).toHaveLength(1);
    expect(container.querySelectorAll('tr.timesheet-engineer-group-row')).toHaveLength(1);
    expect(container.querySelector('.timesheet-expand-toggle')).toBeNull();
    expect(screen.queryByText(/pending review/)).toBeNull();
    expect(screen.getByText(/2 logged subtasks this week/)).toBeTruthy();

    const link = screen.getByRole('link', { name: /Ritu/ });
    expect(link.getAttribute('href')).toBe('/weekly-logs?projectId=1&employeeId=3&weekStart=2026-09-21');

    expect(screen.queryByText('subtask 1')).toBeNull();
    expect(screen.queryByText('subtask 2')).toBeNull();
    expect(container.querySelector('.timesheet-group-detail-row')).toBeNull();

    // week not yet submitted -> Not Submitted pill + Submit button for engineer
    expect(screen.getAllByText('Not Submitted').length).toBeGreaterThan(0);
    expect(screen.getByText('Submit for Approval')).toBeTruthy();
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
  });

  it('counts Saturday and Sunday hours in the weekly total (TODO N2)', async () => {
    timesheetData = [{ ...ENTRIES[0], sat_hours: 2, sun_hours: 1, total_hours: 3.02 }, ENTRIES[1]];
    renderPage();

    expect(await screen.findByText('3.03 hrs')).toBeTruthy(); // 0.02 + 0.01 weekday + 3 weekend
  });

  it('submitting the week hides Submit and shows Submitted for Approval', async () => {
    renderPage();
    await screen.findByText('Submit for Approval');

    fireEvent.click(screen.getByText('Submit for Approval'));

    expect((await screen.findAllByText('Submitted for Approval')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Submit for Approval')).toBeNull();
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
  });

  it('engineer sees no Submit or status pill on a week with no logged hours', async () => {
    timesheetData = [];
    submissions = [];
    renderPage();

    await screen.findByText('No hours logged for this week yet.');
    expect(screen.queryByText('Submit for Approval')).toBeNull();
    expect(screen.queryByText('Not Submitted')).toBeNull();
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

describe('Lead review of the weekly-hours submission', () => {
  beforeEach(() => {
    currentRole = 'lead';
    submissions = [];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('does not show approve/reject before the week is submitted', async () => {
    renderPage();

    await screen.findByText('Not Submitted');
    expect(screen.queryByText('Submit for Approval')).toBeNull();
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
  });

  it('shows approve/reject for a submitted week and persists the review', async () => {
    submissions = [submission('submitted', { can_review: true, reviewers_done: 0, reviewers_total: 1 })];
    renderPage();

    const approve = await screen.findByText('Approve');
    expect(approve).toBeTruthy();
    expect(screen.getByText('Reject')).toBeTruthy();
    expect(screen.getByText('Submitted for Approval')).toBeTruthy();

    fireEvent.click(approve);

    await screen.findByText('Approved');
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
    expect(submissions[0].status).toBe('approved');
  });

  it('shows a rejected week with no review buttons', async () => {
    submissions = [submission('rejected')];
    renderPage();

    await screen.findByText('Rejected');
    expect(screen.queryByText('Approve')).toBeNull();
    expect(screen.queryByText('Reject')).toBeNull();
  });
});

describe('Per-task review of a week', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(fakeApi)));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows Approve to whoever the server says has hours to review (e.g. the BU Head for a lead)', async () => {
    currentRole = 'bu_head';
    submissions = [submission('submitted', { can_review: true, reviewers_done: 0, reviewers_total: 1 })];
    renderPage();

    expect(await screen.findByText('Approve')).toBeTruthy();
  });

  it('hides it from a lead of the project who is not this week’s reviewer', async () => {
    currentRole = 'lead';
    submissions = [submission('submitted', { can_review: false, reviewers_done: 0, reviewers_total: 1 })];
    renderPage();

    await screen.findByText('Submitted for Approval');
    expect(screen.queryByText('Approve')).toBeNull();
  });

  it('shows how many of the week’s reviewers have approved', async () => {
    currentRole = 'lead';
    submissions = [
      submission('submitted', {
        can_review: false,
        reviewers_done: 1,
        reviewers_total: 2,
        waiting_on: ['Priya Nair'],
      }),
    ];
    renderPage();

    expect(await screen.findByText(/1 of 2 approved · waiting on Priya Nair/)).toBeTruthy();
  });
});
