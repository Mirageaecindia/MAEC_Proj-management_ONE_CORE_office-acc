// @vitest-environment jsdom
/** Subtask Login/Logout: the server counts Logout − Login; the page only shows the state. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { TaskDetailsPage } from './TaskDetailsPage';

const WAIT = { timeout: 5000 };

vi.mock('../../AuthContext', () => {
  const auth = { role: 'engineer', authHeaders: () => ({}), logout: vi.fn() }; // stable, like the real context
  return { useAuth: () => auth };
});

const SUBTASK = {
  id: 5,
  project_id: 1,
  parent_id: 4,
  node_type: 'subtask',
  wbs_code: '1.1',
  task_name: 'Cable schedule',
  deliverable_status: 'In-Progress',
  history: [],
  children: [],
};

let activeSession;
const session = (subtaskId) => ({
  id: 7,
  project_id: 1,
  task_id: 4,
  subtask_id: subtaskId,
  login_at: '2026-09-27T09:00:00Z',
});

function fakeApi(url, options = {}) {
  let body;
  if (/\/api\/wbs-nodes\/5$/.test(url)) body = SUBTASK;
  else if (/\/api\/projects\/1$/.test(url)) body = { id: 1, project_name: 'Hotel Tower' };
  else if (/\/subtask-tracking\/start$/.test(url)) {
    activeSession = session(JSON.parse(options.body).subtask_id);
    body = { active_session: activeSession };
  } else if (/\/subtask-tracking\/logout$/.test(url)) {
    activeSession = null;
    body = { active_session: null, limit_reached: false };
  } else if (/\/subtask-tracking\/heartbeat$/.test(url)) body = { active_session: activeSession };
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

    expect(JSON.parse(posts('/subtask-tracking/start')[0][1].body)).toEqual({ subtask_id: 5 });
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

  it('blocks Login while the engineer is logged in to another subtask', async () => {
    activeSession = session(9);
    renderPage();

    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Login' }).disabled).toBe(true), WAIT);
  });
});
