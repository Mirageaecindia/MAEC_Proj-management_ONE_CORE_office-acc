// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
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
  scope: { role: 'engineer', engineer_id: 3, engineer_name: 'Ritu' },
  engineers: [{ id: 3, name: 'Ritu', employee_code: 'M0182' }],
  tasks: [],
  phases: [],
};

let submissionsData = [];

const ROUTES = [
  [/\/api\/projects$/, () => PROJECTS.map((project) => ({ ...project, my_role: currentRole }))],
  [/\/api\/projects\/1\/wbs-structure$/, NODES],
  [/\/api\/projects\/1\/timesheet\?/, ENTRIES],
  [/\/api\/projects\/1\/weekly-hours-submissions\?/, submissionsData],
  [/\/api\/projects\/1\/timeline-logs$/, TIMELINE],
];

function fakeApi(url, options) {
  const method = (options && options.method) || 'GET';
  console.log('FETCH', method, url);
  if (method === 'POST') {
    if (/\/weekly-hours\/approve$/.test(url)) {
      submissionsData.length = 0;
      submissionsData.push({ employee_id: 3, status: 'approved', week_start_date: '2026-09-21' });
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }
    if (/\/weekly-hours\/reject$/.test(url)) {
      submissionsData.length = 0;
      submissionsData.push({ employee_id: 3, status: 'rejected', week_start_date: '2026-09-21' });
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }
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
    <MemoryRouter initialEntries={[route]}>
      <EngineerWeeklyLogsPage />
    </MemoryRouter>,
  );
}

describe('Engineer Weekly Logs details page', () => {
  beforeEach(() => {
    currentRole = 'engineer';
    submissionsData.length = 0;
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows the engineer, week range, and every subtask as a separate entry', async () => {
    const { container } = renderPage();

    expect(await screen.findByText('Ritu')).toBeTruthy();
    expect(screen.getAllByText(/Sep 21 - 27, 2026/).length).toBeGreaterThan(0);

    const details = container.querySelector('.details-table');
    expect(within(details).getByText('subtask 1')).toBeTruthy();
    expect(within(details).getByText('subtask 2')).toBeTruthy();
    expect(within(details).getByText('task 1')).toBeTruthy();
    expect(within(details).getByText('task 2')).toBeTruthy();
    expect(within(details).getByText('1.1')).toBeTruthy();
    expect(within(details).getAllByText('Done')).toHaveLength(2);
    expect(within(details).getByText(/Thu, Sep 24 · 0\.02 hrs/)).toBeTruthy();
    expect(within(details).getByText(/Thu, Sep 24 · 0\.01 hrs/)).toBeTruthy();
    expect(within(details).getByText('0.02 hrs')).toBeTruthy();
    expect(within(details).getByText('0.01 hrs')).toBeTruthy();
  });

  it('engineer sees only the read-only approval status in the APPROVAL column — no Submit, no Approve/Reject', async () => {
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.getAllByText('Not Submitted')).toHaveLength(2);
    expect(screen.queryAllByRole('button', { name: 'Submit for Approval' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });

  it('engineer APPROVAL column reflects the real week status (submitted/approved) as a read-only display, no action buttons', async () => {
    submissionsData.push({ employee_id: 3, status: 'submitted', week_start_date: '2026-09-21' });
    renderPage();

    expect(await screen.findByText('subtask 1'));
    expect(screen.getAllByText('Submitted for Approval')).toHaveLength(2);
    expect(screen.queryAllByRole('button', { name: 'Submit for Approval' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });

  it('tampering with employeeId in the URL still shows only the engineer’s own rows with no approval controls', async () => {
    renderPage('/weekly-logs?projectId=1&employeeId=9999&weekStart=2026-09-21');

    expect(await screen.findByText('Ritu')).toBeTruthy();
    expect(screen.getByText('subtask 1')).toBeTruthy();
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
  });

  it('lead viewing the engineer’s weekly log detail sees a read-only view — no Approve/Reject (approval lives on the Timeline & Logs page)', async () => {
    currentRole = 'lead';
    submissionsData.push({ employee_id: 3, status: 'submitted', week_start_date: '2026-09-21' });
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.getAllByText('Submitted for Approval')).toHaveLength(2);
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });

  it('lead still sees full log details (hours/dates/status) in the read-only detail view', async () => {
    currentRole = 'lead';
    submissionsData.push({ employee_id: 3, status: 'submitted', week_start_date: '2026-09-21' });
    const { container } = renderPage();

    await screen.findByText('subtask 1');
    const details = container.querySelector('.details-table');
    expect(within(details).getByText('subtask 1')).toBeTruthy();
    expect(within(details).getByText('subtask 2')).toBeTruthy();
    expect(within(details).getByText(/Thu, Sep 24 · 0\.02 hrs/)).toBeTruthy();
    expect(within(details).getByText(/Thu, Sep 24 · 0\.01 hrs/)).toBeTruthy();
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });

  it('lead sees the approved status as read-only after the week was approved on the main page', async () => {
    currentRole = 'lead';
    submissionsData.push({ employee_id: 3, status: 'approved', week_start_date: '2026-09-21' });
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.getAllByText('Approved')).toHaveLength(2);
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });

  it('lead sees the rejected status as read-only after the week was rejected on the main page', async () => {
    currentRole = 'lead';
    submissionsData.push({ employee_id: 3, status: 'rejected', week_start_date: '2026-09-21' });
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.getAllByText('Rejected')).toHaveLength(2);
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
  });
});
