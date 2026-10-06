// @vitest-environment jsdom
/** Subtask Login/Logout: the server counts Logout − Login; the page only shows the state. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { TaskDetailsPage } from './TaskDetailsPage';

const WAIT = { timeout: 5000 };

vi.mock('../../AuthContext', () => {
  const auth = { role: 'engineer', user: { employee_id: 3 }, authHeaders: () => ({}), logout: vi.fn() }; // stable
  return { useAuth: () => auth };
});

const SUBTASK = {
  id: 5,
  project_id: 1,
  parent_id: 4,
  assigned_engineer_id: 3,
  node_type: 'subtask',
  wbs_code: '1.1',
  task_name: 'Cable schedule',
  deliverable_status: 'In-Progress',
  history: [],
  children: [],
};

let heartbeatExtra = {};
let subtaskStatus = 'In-Progress';
let activeSession;
const session = (subtaskId) => ({
  id: 7,
  project_id: 1,
  task_id: 4,
  subtask_id: subtaskId,
  subtask_name: `1.${subtaskId} Subtask ${subtaskId}`,
  login_at: '2026-09-27T09:00:00Z',
});

function fakeApi(url, options = {}) {
  let body;
  if (/\/api\/wbs-nodes\/5$/.test(url)) body = { ...SUBTASK, deliverable_status: subtaskStatus };
  else if (/\/api\/wbs-nodes\/5\/advance-status$/.test(url)) {
    subtaskStatus = JSON.parse(options.body).new_status;
    if (subtaskStatus === 'Done' && activeSession?.subtask_id === 5) activeSession = null; // the server logs out
    body = { ok: true };
  } else if (/\/api\/projects\/1$/.test(url))
    body = { id: 1, project_name: 'Hotel Tower', my_role: 'engineer' };
  else if (/\/subtask-tracking\/start$/.test(url)) {
    activeSession = session(JSON.parse(options.body).subtask_id);
    body = { active_session: activeSession };
  } else if (/\/subtask-tracking\/logout$/.test(url)) {
    activeSession = null;
    body = { active_session: null, over_mark: false };
  } else if (/\/subtask-tracking\/heartbeat$/.test(url))
    body = { active_session: activeSession, ...heartbeatExtra };
  else
    return Promise.resolve(
      new Response(JSON.stringify({ detail: `No fixture for ${url}` }), { status: 404 }),
    );
  return Promise.resolve(new Response(JSON.stringify(body), { status: url.includes('/start') ? 201 : 200 }));
}

const posts = (path) =>
  fetch.mock.calls.filter(([url, options]) => url.endsWith(path) && options?.method === 'POST');

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/task-details?nodeId=5&projectId=1']}>
        <TaskDetailsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Task Details: subtask Login/Logout', () => {
  beforeEach(() => {
    activeSession = null;
    subtaskStatus = 'In-Progress';
    heartbeatExtra = {};
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('logs in and out on request only; the page never reports time', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Login' }, WAIT));

    fireEvent.click(await screen.findByRole('button', { name: 'Logout' }, WAIT));
    expect(await screen.findByRole('button', { name: 'Login' }, WAIT)).toBeTruthy();

    expect(JSON.parse(posts('/subtask-tracking/start')[0][1].body)).toEqual({ subtask_id: 5, switch: false });
    expect(posts('/subtask-tracking/logout')[0][1].body).toBeUndefined(); // no durations are sent
  });

  it('keeps Login when an older heartbeat answers afterwards', async () => {
    let answerHeartbeat;
    fetch.mockImplementation((url, options) => {
      if (!url.endsWith('/subtask-tracking/heartbeat') || answerHeartbeat) return fakeApi(url, options);
      return new Promise((resolve) => {
        answerHeartbeat = () => resolve(new Response(JSON.stringify({ active_session: null })));
      });
    });
    renderPage();
    await vi.waitFor(() => expect(answerHeartbeat).toBeDefined(), WAIT);

    fireEvent.click(await screen.findByRole('button', { name: 'Login' }, WAIT));
    await screen.findByRole('button', { name: 'Logout' }, WAIT);
    answerHeartbeat(); // sent before Login: "not logged in"

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole('button', { name: 'Logout' })).toBeTruthy();
  });

  it('restores the logged-in state from the heartbeat after a reload', async () => {
    activeSession = session(5);
    renderPage();

    expect(await screen.findByRole('button', { name: 'Logout' }, WAIT)).toBeTruthy();
    expect(posts('/subtask-tracking/heartbeat').length).toBeGreaterThan(0);
  });

  it('reports the last visit with each heartbeat', async () => {
    activeSession = session(5);
    renderPage();
    fireEvent(window, new Event('pointerdown'));

    await screen.findByRole('button', { name: 'Logout' }, WAIT);
    const [, options] = posts('/subtask-tracking/heartbeat')[0];
    expect(JSON.parse(options.body)).toHaveProperty('last_active_at');
  });

  it('switches subtask in one confirmed step when logged in to another one', async () => {
    activeSession = session(9);
    renderPage();
    const login = await screen.findByRole('button', { name: 'Login' }, WAIT);
    await vi.waitFor(() => expect(login.title).toMatch(/1\.9 Subtask 9/), WAIT);

    fireEvent.click(login);

    expect(await screen.findByText('You are logged in to 1.9 Subtask 9.')).toBeTruthy();
    expect(posts('/subtask-tracking/start')).toHaveLength(0); // nothing happens until it is confirmed
    fireEvent.click(screen.getByRole('button', { name: 'Log out there and log in here' }));

    expect(await screen.findByRole('button', { name: 'Logout' }, WAIT)).toBeTruthy();
    expect(JSON.parse(posts('/subtask-tracking/start')[0][1].body)).toEqual({ subtask_id: 5, switch: true });
    expect(screen.queryByText('Switch subtask?')).toBeNull();
  });

  it('changes a status without blanking the page', async () => {
    subtaskStatus = 'In-Progress';
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Change status to Done' }, WAIT));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull(), WAIT);
    expect(screen.queryByText(/Loading task details/)).toBeNull(); // the card stayed on screen
    expect(screen.getAllByText('Cable schedule', { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Change status to Done' })).toBeNull(); // shows Done at once
  });

  it('setting Done logs out of the subtask, says so first, and Login stays off', async () => {
    subtaskStatus = 'In-Progress';
    activeSession = session(5);
    renderPage();
    await screen.findByRole('button', { name: 'Logout' }, WAIT);

    fireEvent.click(screen.getByRole('button', { name: 'Change status to Done' }));
    expect(screen.getByText(/You will be logged out of this subtask/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    const login = await screen.findByRole('button', { name: 'Login' }, WAIT);
    expect(login.disabled).toBe(true);
    expect(login.title).toBe('This subtask is Done, so no more time can be logged on it.');
  });
});
