// @vitest-environment jsdom
/**
 * Render smoke tests: each BU Head page mounts against a fake API and shows
 * real data, so runtime errors in the rewritten pages are caught before a
 * browser ever sees them.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { NotificationBell } from '../../components/NotificationBell';
import { SharePointMirrorPage } from '../sharepoint/SharePointMirrorPage';
import { CreatedProjectsPage } from './CreatedProjectsPage';
import { CreateProjectPage, EditProjectPage } from './CreateProjectPage';
import { ExecutiveDashboardPage } from './ExecutiveDashboardPage';
import { ProjectWorkSummaryPage } from './ProjectWorkSummaryPage';

const PROJECT = {
  id: 1,
  project_name: 'Hotel Tower',
  project_code: 'MAEC-001',
  client_organization: 'Acme',
  project_lead_electrical: 'Anita Kumar',
  project_lead_mechanical: 'Priya Nair',
  project_lead_bim: 'Mohan Daniel',
  start_date: '2026-09-01',
  contract_value: 250000,
  contract_currency: 'INR',
  target_effort_hours: 500,
  governance_threshold_pct: 80,
};

const DASHBOARD = {
  project: { id: 1, project_name: 'Hotel Tower', contract_currency: 'USD' },
  summary: { scheduled_hours: 100, logged_hours: 110, approved_hours: 90, pending_hours: 20 },
  commercial_budget_burn: { currency: 'USD', total: 100000, consumed: 90000, remaining: 10000, percent: 90 },
  hours_consumption: { hours: 90, scheduled: 100, wbs_planned: 120, approved: 90, pending: 20, percent: 90 },
  governance_status: {
    status: 'exceeded',
    level: 'warning',
    configured: true,
    baseline_hours: 100,
    approved_hours: 90,
    lock_reason: null,
    threshold_pct: 80,
    consumption_pct: 90,
    max_discipline_pct: 90,
    max_discipline: 'Mechanical Engineer',
    soft_locked: false,
  },
  spi: { value: 0.7, note: 'Behind plan — 70 earned of 100 planned baseline hours.' },
  disciplines: [],
  exceptions: [{ discipline: 'Mechanical Engineer', consumption_pct: 90, threshold_pct: 80 }],
  monthly_data: [
    {
      month: '2026-09',
      month_label: 'Sep 2026',
      planned_baseline: 100,
      normal_consumption: 0,
      exceeded_threshold: 90,
    },
  ],
  extension_requests: [
    {
      id: 5,
      status: 'pending',
      status_label: 'Pending BU Head Approval',
      requested_hours: 40,
      requested_by: 'Anita Kumar',
      project_name: 'Hotel Tower',
      requested_at: '2026-09-20T10:00:00',
      justification: 'Scope creep',
    },
  ],
  governance_actions: [
    {
      id: 9,
      action: 'extension_request',
      requested_hours: 40,
      created_by: 'Anita Kumar',
      created_at: '2026-09-20',
    },
  ],
};

const WORK_SUMMARY = {
  project: { id: 1, project_name: 'Hotel Tower' },
  leads: [
    {
      name: 'Anita Kumar',
      phases: ['Space Planning'],
      nodes_managed: 3,
      phase_completion: { 'Space Planning': { total: 3, completed: 1 } },
      approved_hours: 10,
      logged_hours: 15,
      pending_approvals: 1,
    },
  ],
  engineers: [],
  phase_completion: {},
  summary: {
    total_nodes: 3,
    completed_nodes: 1,
    scheduled_hours: 120,
    approved_hours: 10,
    logged_hours: 15,
    pending_hours: 5,
    pending_entries: 1,
  },
};

const MIRROR = {
  provisioned: true,
  error: null,
  folder_hierarchy: [{ id: 'f1', name: '01_HVAC Discipline', children: [] }],
  files: [{ id: 'd1', name: 'Scope.pdf', size: 2048, last_modified_by: 'BU Head', web_url: 'https://sp/d1' }],
  stats: { total_files: 1, total_size_formatted: '2.00 KB' },
  connection: { connected: true, status: 'Connected', error: null },
  target_location: 'https://sp/hotel-tower',
};

const NOTIFICATIONS = [
  {
    id: 3,
    notification_type: 'threshold_warning',
    title: 'Alert threshold reached',
    message: "'Hotel Tower' has used 90 of 100 baseline hours (90%).",
    project_id: 1,
    is_read: false,
    created_at: '2026-09-21T09:00:00Z',
  },
  { id: 2, title: 'Old notice', message: 'Seen already', project_id: 1, is_read: true, created_at: null },
];

let dashboard = DASHBOARD;

const ARCHIVED = {
  ...PROJECT,
  id: 7,
  project_name: 'Old Mall',
  project_code: 'MAEC-007',
  archived_at: '2026-09-20T10:00:00Z',
};

const EDITABLE = {
  ...PROJECT,
  id: 5,
  project_lead_electrical_user_id: 2,
  project_lead_mechanical_user_id: 2,
  project_lead_bim_user_id: 2,
};

const ROUTES = [
  [/\/api\/projects\/5$/, EDITABLE],
  [/\/api\/projects\?include_archived=true$/, [PROJECT, ARCHIVED]],
  [/\/api\/projects\/1\/archive$/, { ...PROJECT, archived_at: '2026-09-26T10:00:00Z' }],
  [/\/api\/projects\/7$/, ARCHIVED],
  [
    /\/api\/projects\/7\/executive-dashboard$/,
    () => ({ ...DASHBOARD, project: { ...DASHBOARD.project, id: 7, archived_at: ARCHIVED.archived_at } }),
  ],
  [/\/api\/notifications$/, NOTIFICATIONS],
  [/\/api\/notifications\/3\/read$/, null],
  [/\/api\/projects\/1\/governance\/resume-execution$/, { id: 11, action: 'resume_execution' }],
  [/\/api\/projects\/1\/executive-dashboard$/, () => dashboard],
  [/\/api\/projects\/1\/work-summary$/, WORK_SUMMARY],
  [/\/api\/projects\/1\/sharepoint-mirror$/, MIRROR],
  [/\/api\/project-leads/, [{ id: 2, name: 'Anita Kumar', title: 'Electrical' }]],
  [/\/api\/projects$/, [PROJECT]],
];

function fakeApi(url) {
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const fixture = match && (typeof match[1] === 'function' ? match[1]() : match[1]);
  const [status, body] = match ? [200, fixture] : [404, { detail: `No fixture for ${url}` }];
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function renderAt(ui, route) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BU Head pages render with API data', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(fakeApi)));
  afterEach(() => {
    dashboard = DASHBOARD;
    cleanup();
    vi.unstubAllGlobals();
  });

  it('Created Projects lists project cards with the right currency', async () => {
    renderAt(<CreatedProjectsPage />, '/created-projects');
    expect(await screen.findByText('Hotel Tower')).toBeTruthy();
    expect(screen.getByText('INR ₹250,000.00')).toBeTruthy();
    expect(screen.getByText('1 of 1 projects')).toBeTruthy();
  });

  it('Created Projects shows archived projects only when asked, with Reopen instead of Archive', async () => {
    renderAt(<CreatedProjectsPage />, '/created-projects');
    expect(await screen.findByText('Hotel Tower')).toBeTruthy();
    expect(screen.queryByText('Old Mall')).toBeNull();

    fireEvent.click(screen.getByLabelText('Show archived'));

    expect(await screen.findByText('Old Mall')).toBeTruthy();
    expect(screen.getByText('Archived')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /Reopen/ })).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: /Archive/ })).toHaveLength(1); // only the active project
  });

  it('Archiving asks for confirmation, then calls the API', async () => {
    renderAt(<CreatedProjectsPage />, '/created-projects');
    fireEvent.click(await screen.findByRole('button', { name: /Archive/ }));
    expect(screen.getByText('Archive this project?')).toBeTruthy();

    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Archive' }));

    await vi.waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/api\/projects\/1\/archive$/),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  it('An archived project opens read-only on the Executive Dashboard', async () => {
    renderAt(<ExecutiveDashboardPage />, '/executive-dashboard?projectId=7');

    expect(await screen.findByText('Project archived: read-only')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Stop the Execution' }).disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Approve Extension' }).disabled).toBe(true);
  });

  it('Edit Project is the Create form filled in, without the SharePoint section', async () => {
    renderAt(<EditProjectPage />, '/edit-project?projectId=5');

    expect(await screen.findByDisplayValue('Hotel Tower')).toBeTruthy();
    expect(screen.getByDisplayValue('MAEC-001')).toBeTruthy();
    expect(screen.queryByText(/Automated SharePoint Directory Setup/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Save Changes' })).toBeTruthy();
  });

  it('Edit Project asks before changing the currency, then sends the confirmation', async () => {
    renderAt(<EditProjectPage />, '/edit-project?projectId=5');
    await screen.findByDisplayValue('Hotel Tower');
    await screen.findAllByRole('option', { name: 'Anita Kumar' }); // leads loaded

    fireEvent.change(screen.getByLabelText('Contract currency'), { target: { value: 'USD' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    expect(screen.getByText('Change the currency from INR to USD?')).toBeTruthy();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Change Currency' }));

    await vi.waitFor(() => {
      const put = fetch.mock.calls.find(([, options]) => options?.method === 'PUT');
      expect(put[0]).toMatch(/\/api\/projects\/5$/);
      expect(JSON.parse(put[1].body)).toMatchObject({
        contract_currency: 'USD',
        confirm_currency_change: true,
      });
    });
  });

  it('Create Project shows validation errors on an empty submit', async () => {
    renderAt(<CreateProjectPage />, '/create-project');
    expect(await screen.findAllByRole('option', { name: 'Anita Kumar' })).toHaveLength(3); // one per discipline dropdown
    fireEvent.click(screen.getByRole('button', { name: /Create Project & Build SharePoint Directory/ }));
    expect(screen.getByText('Project name is required.')).toBeTruthy();
    expect(screen.getByText('Enter a contract value greater than 0.')).toBeTruthy();
  });

  it('Executive Dashboard shows KPIs, the pending request and the audit log', async () => {
    renderAt(<ExecutiveDashboardPage />, '/executive-dashboard?projectId=1');
    expect(await screen.findByText('ALERT (90.0%)')).toBeTruthy();
    expect(screen.getByText('Alert Threshold Reached')).toBeTruthy();
    expect(screen.getByText(/20.0 Hrs pending review, not yet counted/)).toBeTruthy();
    expect(screen.getByText(/90.0 Hrs of 100.0 Hrs baseline hours approved/)).toBeTruthy();
    expect(screen.getByText('$90,000.00')).toBeTruthy();
    expect(screen.getByText('Scope creep')).toBeTruthy();
    expect(screen.getByText('Sep 2026')).toBeTruthy();
    expect(screen.getByText(/Requested extension of 40.0 Hrs/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Approve Extension' }).disabled).toBe(false);
    expect(screen.getByRole('button', { name: 'Stop the Execution' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Resume Execution' })).toBeNull();
  });

  it('Executive Dashboard offers Resume instead of Stop while timesheets are locked', async () => {
    dashboard = {
      ...DASHBOARD,
      governance_status: {
        ...DASHBOARD.governance_status,
        level: 'hard_stop',
        consumption_pct: 100,
        approved_hours: 100,
        soft_locked: true,
        lock_reason: 'auto',
      },
    };
    renderAt(<ExecutiveDashboardPage />, '/executive-dashboard?projectId=1');

    expect(await screen.findByText('BASELINE REACHED (100.0%)')).toBeTruthy();
    expect(screen.getAllByText('Timesheets Locked Automatically').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Stop the Execution' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Resume Execution' }));

    await vi.waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/governance\/resume-execution$/),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  it('Notification bell shows the unread count and marks a notification read', async () => {
    renderAt(<NotificationBell />, '/');

    const bell = await screen.findByRole('button', { name: 'Notifications (1 unread)' });
    fireEvent.click(bell);
    expect(screen.getByText('Alert threshold reached')).toBeTruthy();
    expect(screen.getByText('Old notice')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Mark read' }));

    await vi.waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/notifications\/3\/read$/),
        expect.objectContaining({ method: 'POST' }),
      ),
    );
  });

  it('Work Summary shows chips and lead oversight', async () => {
    renderAt(<ProjectWorkSummaryPage />, '/project-work-summary?projectId=1');
    expect(await screen.findByText('Space Planning: 1/3')).toBeTruthy();
    expect(screen.getByText('WBS Tasks')).toBeTruthy();
    expect(screen.getByText('10.0 hrs')).toBeTruthy();
  });

  it('SharePoint Mirror shows the folder tree and root files', async () => {
    renderAt(<SharePointMirrorPage />, '/sharepoint-mirror?projectId=1');
    expect(await screen.findByText('01_HVAC Discipline')).toBeTruthy();
    expect(screen.getByText('Scope.pdf')).toBeTruthy();
    expect(screen.getByText('Connected')).toBeTruthy();
  });
});
