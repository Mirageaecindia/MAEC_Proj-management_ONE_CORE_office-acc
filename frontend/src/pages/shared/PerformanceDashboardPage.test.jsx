// @vitest-environment jsdom
/** One Performance Dashboard: the project a lead leads, then their own work; only their own work elsewhere. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { PerformanceDashboardPage } from './PerformanceDashboardPage';

const WAIT = { timeout: 5000 };

vi.mock('../../AuthContext', () => {
  const auth = {
    role: 'engineer',
    user: { id: 5, employee_id: 3 },
    authHeaders: () => ({}),
    logout: vi.fn(),
  };
  return { useAuth: () => auth };
});

const PROJECTS = [
  { id: 1, project_name: 'Hotel Tower', my_role: 'lead' },
  { id: 2, project_name: 'City Mall', my_role: 'engineer' },
];
const PROJECT_FIGURES = {
  project: { id: 1, project_name: 'Hotel Tower', contract_currency: 'USD' },
  summary: { approved_hours: 30, pending_hours: 10, rejected_hours: 5 },
  commercial_budget_burn: { currency: 'USD', total: 100000, consumed: 30000, remaining: 70000, percent: 30 },
  hours_consumption: { hours: 30, scheduled: 100, approved: 30, pending: 10, percent: 30 },
  governance_status: {
    status: 'normal',
    level: 'normal',
    configured: true,
    threshold_pct: 80,
    consumption_pct: 30,
  },
  spi: { value: 0.9, note: 'Close to plan.' },
  disciplines: [
    {
      name: 'Electrical Engineer',
      baseline_hours: 100,
      consumed_hours: 40,
      consumption_pct: 40,
      exceeded: false,
    },
  ],
  exceptions: [],
  monthly_data: [],
  extension_requests: [],
  current_extension_request: null,
  governance_actions: [],
};
const MY_WORK = {
  summary: {
    total_hours_consumption: 6,
    total_hours_scheduled: 16,
    total_hours_approved: 4,
    total_hours_pending: 2,
    consumption_pct: 37.5,
    total_tasks: 4,
    started_tasks: 3,
    completed_tasks: 1,
    completion_pct: 25,
    spi_value: 0.5,
    spi_note: 'Behind plan.',
  },
  monthly_breakdown: [],
};

const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
function fakeApi(url) {
  if (/\/api\/projects$/.test(url)) return json(PROJECTS);
  if (/\/api\/projects\/1\/executive-dashboard$/.test(url)) return json(PROJECT_FIGURES);
  if (/\/api\/engineer-performance-dashboard\?project_id=\d$/.test(url)) return json(MY_WORK);
  return json({ detail: `No fixture for ${url}` }, 404);
}

function renderAt(url) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <PerformanceDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const card = (title) => screen.getByRole('heading', { name: title }).closest('section');

describe('Performance Dashboard', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(fakeApi)));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('on a project they lead: the project figures and charts, the lead action, then their own work', async () => {
    renderAt('/engineer-performance-dashboard?projectId=1');

    expect(await screen.findByRole('heading', { name: 'Project: Hotel Tower' }, WAIT)).toBeTruthy();
    expect(await screen.findByText('Approved Hours Consumption', {}, WAIT)).toBeTruthy();
    expect(screen.queryByText('Commercial Budget Burn')).toBeNull(); // money is the BU Head's
    expect(screen.getByRole('heading', { name: 'Lead Action' })).toBeTruthy();
    const status = within(card('Hours by Review Status'));
    expect(await status.findByText('30.0 Hrs', {}, WAIT)).toBeTruthy(); // approved
    expect(status.getByText('Rejected')).toBeTruthy();
    expect(within(card('Consumption by Discipline')).getByText('Electrical Engineer')).toBeTruthy();
    expect(await screen.findByRole('heading', { name: 'My Work on This Project' }, WAIT)).toBeTruthy();
    expect(screen.getAllByText('Schedule Index (SPI)')).toHaveLength(1); // the project's, not repeated
  });

  it('on a project they only work on: their own work, and no project figures are asked for', async () => {
    renderAt('/engineer-performance-dashboard?projectId=2');

    expect(await screen.findByRole('heading', { name: 'My Work' }, WAIT)).toBeTruthy();
    expect(await screen.findByText('1 of 4', {}, WAIT)).toBeTruthy(); // tasks completed
    const tasks = within(card('My Tasks by Status'));
    expect(tasks.getByText('In Progress')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Lead Action' })).toBeNull();
    expect(fetch.mock.calls.some(([url]) => url.includes('executive-dashboard'))).toBe(false);
  });
});
