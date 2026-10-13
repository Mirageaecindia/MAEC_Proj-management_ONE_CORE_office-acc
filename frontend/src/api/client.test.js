// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { API_BASE_URL, ApiError, GATE_BLOCKED, api, apiFetch, reauthorizationWorked } from './client';

function mockFetch(status, body, headers = {}) {
  const response = new Response(body === undefined ? null : JSON.stringify(body), { status, headers });
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('api client', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("sends the JSON body on the same origin, with MAEC One's cookie and no token", async () => {
    localStorage.setItem('maec_token', 'left-over-from-the-old-login');
    const fetchMock = mockFetch(201, { id: 7 });

    const result = await api.post('/api/projects', { project_name: 'X' });

    expect(result).toEqual({ id: 7 });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe(`${API_BASE_URL}/api/projects`); // '' in the build: same origin
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('same-origin'); // the browser sends MAEC One's cookie itself
    expect(options.headers.Authorization).toBeUndefined();
    expect(options.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(options.body)).toEqual({ project_name: 'X' });
  });

  it('throws ApiError with the FastAPI detail, status and error code', async () => {
    mockFetch(400, { detail: 'Allocation limit reached.' }, { 'X-Error-Code': 'ALLOCATION_LIMIT' });

    const error = await api.get('/api/x').catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(400);
    expect(error.code).toBe('ALLOCATION_LIMIT');
    expect(error.message).toBe('Allocation limit reached.');
  });

  it('joins validation error messages (422)', async () => {
    mockFetch(422, { detail: [{ msg: 'Field required' }, { msg: 'Too long' }] });

    const error = await api.post('/api/x', {}).catch((e) => e);

    expect(error.message).toBe('Field required Too long');
  });

  it('falls back to a generic message for non-JSON errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Server exploded', { status: 500 })));

    const error = await api.get('/api/x').catch((e) => e);

    expect(error.message).toBe('Request failed (500)');
  });
});

describe('MAEC One refusals', () => {
  const LOGIN_URL = 'https://auth.mirageaec.com/?next=https%3A%2F%2Fpm.mirageaec.com%2Fapi%2Fauth%2Fme';
  let assign;
  let blocked;
  const onBlocked = (event) => blocked.push(event.detail);

  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState(null, '', '/wbs-structure?projectId=3');
    assign = vi.fn();
    vi.stubGlobal('location', {
      ...window.location,
      href: 'https://pm.mirageaec.com/wbs-structure?projectId=3',
      assign,
    });
    blocked = [];
    window.addEventListener(GATE_BLOCKED, onBlocked);
  });
  afterEach(() => {
    window.removeEventListener(GATE_BLOCKED, onBlocked);
    vi.unstubAllGlobals();
  });

  it('a 401 sends the window to sign in once, coming back to this page; again right after, it says so', async () => {
    mockFetch(401, { reason: 'not_signed_in', login_url: LOGIN_URL });

    await api.get('/api/auth/me').catch(() => {});

    expect(assign).toHaveBeenCalledTimes(1);
    const sentTo = new URL(assign.mock.calls[0][0]);
    expect(sentTo.origin).toBe('https://auth.mirageaec.com');
    expect(sentTo.searchParams.get('next')).toBe('https://pm.mirageaec.com/wbs-structure?projectId=3'); // the page
    expect(blocked).toEqual([]);

    mockFetch(401, { reason: 'not_signed_in', login_url: LOGIN_URL });
    await api.get('/api/projects').catch(() => {});

    expect(assign).toHaveBeenCalledTimes(1); // no loop
    expect(blocked).toEqual([{ kind: 'signed-out', message: expect.stringContaining('Open MAEC One') }]);

    reauthorizationWorked(); // /api/auth/me answered: a later sign-out may go to sign in once more
    mockFetch(401, { reason: 'not_signed_in', login_url: LOGIN_URL });
    await api.get('/api/projects').catch(() => {});
    expect(assign).toHaveBeenCalledTimes(2);
  });

  it("no seat, or no profile here, blocks the app with the reason; another 403 is the page's to show", async () => {
    mockFetch(403, {
      detail: 'Your account does not have access to Project Management.',
      reason: 'no_access',
      login_url: LOGIN_URL,
    });
    await apiFetch('/api/projects');

    mockFetch(403, { detail: 'Ask a Business Head.' }, { 'X-Error-Code': 'PROFILE_NOT_SET_UP' });
    await api.get('/api/auth/me').catch(() => {});

    mockFetch(403, { detail: 'Only a lead of this project can do this.' });
    const ruled = await api.post('/api/x', {}).catch((e) => e);

    expect(blocked).toEqual([
      {
        kind: 'no_access',
        message: 'Your account does not have access to Project Management.',
        maecOneUrl: 'https://auth.mirageaec.com/',
      },
      { kind: 'PROFILE_NOT_SET_UP', message: 'Ask a Business Head.', maecOneUrl: '' },
    ]);
    expect(ruled.message).toBe('Only a lead of this project can do this.');
    expect(assign).not.toHaveBeenCalled();
  });

  it('the pages that call fetch themselves get the same handling, and no token', async () => {
    const fetchMock = mockFetch(401, { reason: 'not_signed_in', login_url: LOGIN_URL });

    const response = await apiFetch('/api/projects/3/timeline-logs');

    expect(response.status).toBe(401);
    expect(fetchMock.mock.calls[0][1].credentials).toBe('same-origin');
    expect(fetchMock.mock.calls[0][1].headers).toBeUndefined();
    expect(assign).toHaveBeenCalledTimes(1);
  });
});
