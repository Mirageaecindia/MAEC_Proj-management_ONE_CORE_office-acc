// @vitest-environment jsdom
/**
 * Render smoke tests: each BU Head page mounts against a fake API and shows
 * real data, so runtime errors in the rewritten pages are caught before a
 * browser ever sees them.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { SharePointMirrorPage } from '../sharepoint/SharePointMirrorPage';
import { CreatedProjectsPage } from './CreatedProjectsPage';
import { CreateProjectPage } from './CreateProjectPage';
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
  summary: { scheduled_hours: 100, logged_hours: 90, approved_hours: 70, pending_hours: 20 },
  commercial_budget_burn: { currency: 'USD', total: 100000, consumed: 90000, remaining: 10000, percent: 90 },
  hours_consumption: { hours: 90, scheduled: 100, approved: 70, pending: 20, percent: 90 },
  governance_status: {
    status: 'exceeded',
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

const ROUTES = [
  [/\/api\/projects\/1\/executive-dashboard$/, DASHBOARD],
  [/\/api\/projects\/1\/work-summary$/, WORK_SUMMARY],
  [/\/api\/projects\/1\/sharepoint-mirror$/, MIRROR],
  [/\/api\/project-leads/, [{ id: 2, name: 'Anita Kumar', title: 'Electrical' }]],
  [/\/api\/projects$/, [PROJECT]],
];

function fakeApi(url) {
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const [status, body] = match ? [200, match[1]] : [404, { detail: `No fixture for ${url}` }];
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
    cleanup();
    vi.unstubAllGlobals();
  });

  it('Created Projects lists project cards with the right currency', async () => {
    renderAt(<CreatedProjectsPage />, '/created-projects');
    expect(await screen.findByText('Hotel Tower')).toBeTruthy();
    expect(screen.getByText('INR ₹250,000.00')).toBeTruthy();
    expect(screen.getByText('1 of 1 projects')).toBeTruthy();
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
    expect(await screen.findByText('EXCEEDED (90.0%)')).toBeTruthy();
    expect(screen.getByText('$90,000.00')).toBeTruthy();
    expect(screen.getByText('Scope creep')).toBeTruthy();
    expect(screen.getByText('Sep 2026')).toBeTruthy();
    expect(screen.getByText(/Requested extension of 40.0 Hrs/)).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Approve Extension' }).disabled).toBe(false);
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
