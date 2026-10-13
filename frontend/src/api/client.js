/**
 * The single HTTP client for the MAEC API.
 *
 * - Same origin: the browser calls /api on the server that served the page (the
 *   frontend container proxies it to the backend; `npm run dev` proxies it too, see
 *   vite.config.js). VITE_API_BASE_URL overrides it, never a page.
 * - Nobody signs in here: MAEC One does. Its session cookie (set for the parent domain)
 *   rides along on every request by itself; the backend asks MAEC One about it
 *   (backend/app/api/gate.py). No token is kept in the browser.
 * - An API 401 means MAEC One doesn't know this browser (signed out, or the session
 *   ended): the window goes to MAEC One's sign-in once (`reauthorize`). A 403 from MAEC
 *   One (no seat), or from this app (no profile here), blocks the app with the reason
 *   (`GATE_BLOCKED`, shown by App.jsx).
 * - Non-2xx responses throw an ApiError carrying the status, the `X-Error-Code` header
 *   and FastAPI's `detail` message.
 */

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '');

/** Fired on window when MAEC One, or this app, refuses the person: `detail` says why. */
export const GATE_BLOCKED = 'maec:gate-blocked';

// One trip to sign-in per visit. The trip reloads the page, so a plain variable would
// forget it had happened, and if the next answer is a 401 too that is a loop between
// two services with the user watching it flicker. sessionStorage survives the trip; a
// successful /api/auth/me clears it, so a later sign-out may go to sign-in once more.
// (Engineering Tools does the same.)
const REAUTH_MARK = 'maec:reauthorizing';

/** Core's login_url, coming back to THIS page rather than the API call it was built for:
 *  following /api/... after sign-in would show raw JSON. Same origin, so Core treats it
 *  exactly as it would the API's address. */
function returningHere(loginUrl) {
  try {
    const url = new URL(loginUrl);
    url.searchParams.set('next', window.location.href);
    return url.toString();
  } catch {
    return loginUrl;
  }
}

/** Send the window to MAEC One's sign-in. False if it was tried already this visit. */
export function reauthorize(loginUrl) {
  try {
    if (sessionStorage.getItem(REAUTH_MARK)) return false;
    sessionStorage.setItem(REAUTH_MARK, String(Date.now()));
  } catch {
    /* private mode: go once anyway */
  }
  window.location.assign(loginUrl ? returningHere(loginUrl) : window.location.href);
  return true;
}

/** /api/auth/me answered: the trip worked, so a later sign-out may go once more. */
export function reauthorizationWorked() {
  try {
    sessionStorage.removeItem(REAUTH_MARK);
  } catch {
    /* nothing to clear */
  }
}

const SIGNED_OUT_AGAIN =
  'You are signed out, and signing in again did not bring you back. Open MAEC One and sign in there.';

function originOf(url) {
  try {
    return `${new URL(url).origin}/`;
  } catch {
    return '';
  }
}

function blocked(detail) {
  window.dispatchEvent(new CustomEvent(GATE_BLOCKED, { detail }));
}

/** What a refusal means for the whole app, decided once for every request. A 401 sends
 *  the window to sign in (or, the second time, blocks with a message instead of looping);
 *  a 403 from MAEC One, or this app's "no profile here", blocks with the reason. Other
 *  403s (a rule of this app) are the caller's to show. */
export function handleGateRefusal(status, body, code) {
  if (status === 401) {
    if (!reauthorize(body?.login_url)) blocked({ kind: 'signed-out', message: SIGNED_OUT_AGAIN });
    return;
  }
  if (status === 403 && (body?.reason || code === 'PROFILE_NOT_SET_UP' || code === 'PROFILE_INACTIVE')) {
    blocked({
      kind: body?.reason || code,
      message: body?.detail || 'No access.',
      maecOneUrl: originOf(body?.login_url),
    });
  }
}

/** fetch() for the API, for the pages that still call it directly: same-origin cookies,
 *  and MAEC One's refusals handled as everywhere else. Returns the Response. */
export async function apiFetch(path, init = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'same-origin', ...init });
  if (response.status === 401 || response.status === 403) {
    const body = await response
      .clone()
      .json()
      .catch(() => null);
    handleGateRefusal(response.status, body, response.headers.get('X-Error-Code'));
  }
  return response;
}

export class ApiError extends Error {
  constructor(message, { status, code = null, body = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.body = body;
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
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    signal,
    credentials: 'same-origin',
    headers: {
      ...(body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  const data = await parseBody(response);
  if (!response.ok) {
    const code = response.headers.get('X-Error-Code');
    handleGateRefusal(response.status, data, code);
    throw new ApiError(errorMessage(data, response.status), {
      status: response.status,
      code,
      body: data,
    });
  }
  return data;
}

export const api = {
  get: (path, options) => apiRequest(path, options),
  post: (path, body, options) => apiRequest(path, { ...options, method: 'POST', body }),
  put: (path, body, options) => apiRequest(path, { ...options, method: 'PUT', body }),
  patch: (path, body, options) => apiRequest(path, { ...options, method: 'PATCH', body }),
  delete: (path, options) => apiRequest(path, { ...options, method: 'DELETE' }),
};
