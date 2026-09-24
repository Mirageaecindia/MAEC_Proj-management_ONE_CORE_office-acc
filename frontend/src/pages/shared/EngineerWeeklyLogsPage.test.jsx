// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { EngineerWeeklyLogsPage } from './EngineerWeeklyLogsPage';

let currentRole = 'engineer';
vi.mock('../../AuthContext', () => ({
  useAuth: () => ({ role: currentRole, authHeaders: () => ({}), logout: vi.fn() }),
}));

const PROJECTS = [
  { id: 1, project_name: 'TEST 1' },
];

const NODES = [
  { id: 1, project_id: 1, parent_id: null, wbs_code: '1', task_name: 'task 1', deliverable_status: 'Not Started', assigned_engineer_id: 3 },
  { id: 2, project_id: 1, parent_id: 1, wbs_code: '1.1', task_name: 'subtask 1', deliverable_status: 'Done', assigned_engineer_id: 3 },
  { id: 3, project_id: 1, parent_id: null, wbs_code: null, task_name: 'task 2', deliverable_status: 'Not Started', assigned_engineer_id: 3 },
  { id: 4, project_id: 1, parent_id: 3, wbs_code: null, task_name: 'subtask 2', deliverable_status: 'Done', assigned_engineer_id: 3 },
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
    mon_hours: 0, tue_hours: 0, wed_hours: 0, thu_hours: 0.02, fri_hours: 0, sat_hours: 0, sun_hours: 0,
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
    mon_hours: 0, tue_hours: 0, wed_hours: 0, thu_hours: 0.01, fri_hours: 0, sat_hours: 0, sun_hours: 0,
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

const ROUTES = [
  [/\/api\/projects$/, PROJECTS],
  [/\/api\/projects\/1\/wbs-structure$/, NODES],
  [/\/api\/projects\/1\/timesheet\?/, ENTRIES],
  [/\/api\/projects\/1\/timeline-logs$/, TIMELINE],
];

function fakeApi(url) {
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const [status, body] = match ? [200, match[1]] : [404, { detail: `No fixture for ${url}` }];
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
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

  it('engineer role never sees Approve/Reject controls or the pending pill', async () => {
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: 'Reject' })).toHaveLength(0);
    expect(screen.queryByText('Pending Review')).toBeNull();
  });

  it('tampering with employeeId in the URL still shows only the engineer’s own rows and no approval controls', async () => {
    renderPage('/weekly-logs?projectId=1&employeeId=9999&weekStart=2026-09-21');

    expect(await screen.findByText('Ritu')).toBeTruthy();
    expect(screen.getByText('subtask 1')).toBeTruthy();
    expect(screen.queryAllByRole('button', { name: 'Approve' })).toHaveLength(0);
  });

  it('lead role sees Approve/Reject controls for scoped engineer rows', async () => {
    currentRole = 'lead';
    renderPage();

    await screen.findByText('subtask 1');
    expect(screen.getAllByText('Pending Review')).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Approve' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Reject' })).toHaveLength(2);
  });
});