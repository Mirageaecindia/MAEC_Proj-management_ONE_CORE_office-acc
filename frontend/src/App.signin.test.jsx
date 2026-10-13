// @vitest-environment jsdom
/** Signing in happens at MAEC One: the app shows who it says, or why it refuses. */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const CORE = 'https://auth.mirageaec.com';
const BU_HEAD = {
  id: 1,
  username: 'bu.head@mirageaec.com',
  full_name: 'Test BU Head',
  role: 'bu_head',
  employee_id: null,
  leads_projects: false,
  core_url: CORE,
};

const reply = (status, body, headers = {}) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json', ...headers },
    }),
  );

function serve(me) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url) => (String(url).endsWith('/api/auth/me') ? me() : reply(200, []))),
  );
}

describe('signing in at MAEC One', () => {
  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState(null, '', '/');
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('shows the app to the person MAEC One vouched for, with Sign out and Change password at MAEC One', async () => {
    serve(() => reply(200, BU_HEAD));
    render(<App />);

    fireEvent.click(await screen.findByRole('button', { name: /Test BU Head/ }));

    expect(screen.getByRole('menuitem', { name: /Sign out/ }).getAttribute('href')).toBe(`${CORE}/`);
    expect(screen.getByRole('menuitem', { name: /Change password/ }).getAttribute('href')).toBe(
      `${CORE}/change-password`,
    );
    expect(localStorage.getItem('maec_token')).toBeNull();
  });

  it('a person without a seat sees "No access" instead of the app', async () => {
    serve(() =>
      reply(403, {
        detail: 'Your account does not have access to Project Management.',
        reason: 'no_access',
        login_url: `${CORE}/?next=x`,
      }),
    );
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'No access' })).toBeTruthy();
    expect(screen.getByText('Your account does not have access to Project Management.')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Open MAEC One' }).getAttribute('href')).toBe(`${CORE}/`);
    expect(screen.queryByRole('navigation')).toBeNull();
  });

  it('someone with a seat but no profile here is told to ask a Business Head', async () => {
    serve(() =>
      reply(
        403,
        { detail: "Your Project Management profile hasn't been set up yet. Ask a Business Head." },
        { 'X-Error-Code': 'PROFILE_NOT_SET_UP' },
      ),
    );
    render(<App />);

    expect(
      await screen.findByText("Your Project Management profile hasn't been set up yet. Ask a Business Head."),
    ).toBeTruthy();
    expect(screen.queryByRole('navigation')).toBeNull();
  });

  it('MAEC One unreachable: says so, with a way to try again', async () => {
    serve(() => reply(503, { detail: 'MAEC One is unavailable' }));
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Project Management is unavailable' })).toBeTruthy();
    expect(screen.getByText('MAEC One is unavailable')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });
});
