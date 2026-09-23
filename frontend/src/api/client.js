/**
 * The single HTTP client for the MAEC API.
 *
 * - Base URL comes from VITE_API_BASE_URL (never hardcoded in pages).
 * - The bearer token is read from the session store on every request.
 * - Non-2xx responses throw an ApiError carrying the status, the
 *   `X-Error-Code` header and FastAPI's `detail` message.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(
  /\/+$/,
  '',
);

/** localStorage key holding the session token (shared with AuthContext). */
export const TOKEN_KEY = 'maec_token';

export class ApiError extends Error {
  constructor(message, { status, code = null, body = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

function readToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

async function parseBody(response) {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** FastAPI returns `detail` as a string, or as a list of validation errors (422). */
function errorMessage(body, status) {
  const detail = body && typeof body === 'object' ? body.detail : null;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg || String(item)).join(' ');
  }
  return `Request failed (${status})`;
}

export async function apiRequest(path, { method = 'GET', body, headers = {}, signal } = {}) {
  const token = readToken();
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    signal,
    headers: {
      ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  const data = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(errorMessage(data, response.status), {
      status: response.status,
      code: response.headers.get('X-Error-Code'),
      body: data,
    });
  }
  return data;
}

export const api = {
  get: (path, options) => apiRequest(path, options),
  post: (path, body, options) => apiRequest(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => apiRequest(path, { ...options, method: 'PUT', body }),
  delete: (path, options) => apiRequest(path, { ...options, method: 'DELETE' }),
};
