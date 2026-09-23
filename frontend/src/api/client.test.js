// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, TOKEN_KEY, api } from './client';

function mockFetch(status, body, headers = {}) {
  const response = new Response(body === undefined ? null : JSON.stringify(body), { status, headers });
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('api client', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it('sends the stored bearer token and JSON body', async () => {
    localStorage.setItem(TOKEN_KEY, 'abc123');
    const fetchMock = mockFetch(201, { id: 7 });

    const result = await api.post('/api/projects', { project_name: 'X' });

    expect(result).toEqual({ id: 7 });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/projects$/);
    expect(options.method).toBe('POST');
    expect(options.headers.Authorization).toBe('Bearer abc123');
    expect(options.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(options.body)).toEqual({ project_name: 'X' });
  });

  it('omits the auth header without a session', async () => {
    const fetchMock = mockFetch(200, []);

    await api.get('/api/projects');

    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined();
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
