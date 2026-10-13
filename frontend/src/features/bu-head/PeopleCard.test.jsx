// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { PeopleCard } from './PeopleCard';

vi.mock('../../AuthContext', () => ({ useAuth: () => ({ signOutUrl: 'https://auth.mirageaec.com/' }) }));

const IMPORTED = {
  created: [{ username: 'kavya.raman@mirageaec.com', full_name: 'Kavya Raman', employee_code: 'M0101' }],
  skipped: [{ row: 3, name: 'Arun Kumar', email: 'arun@mirageaec.com', reason: 'Already has a profile.' }],
};

let people = [];
let onLiveProject = false;
const PERSON = {
  id: 7,
  username: 'kavya.raman@mirageaec.com',
  full_name: 'Kavya Raman',
  role: 'engineer',
  employee_code: 'M0101',
  job_role: 'Senior Electrical Engineer',
  is_active: true,
  can_edit: true,
  can_make_bu_head: true,
  can_remove_bu_head: false,
};
const error = (status, detail) =>
  Promise.resolve(
    new Response(JSON.stringify({ detail }), { status, headers: { 'Content-Type': 'application/json' } }),
  );
const json = (body) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  );

function fakeApi(url, options = {}) {
  const method = options.method || 'GET';
  if (url.endsWith('/api/people/import')) return json(IMPORTED);
  if (url.endsWith('/api/people') && method === 'POST') {
    const person = JSON.parse(options.body);
    return json({
      username: person.email.toLowerCase(),
      full_name: person.full_name,
      employee_code: person.employee_code,
    });
  }
  if (url.endsWith('/api/people') && method === 'GET') return json(people);
  if (/\/api\/people\/\d+$/.test(url) && method === 'PATCH') {
    const id = url.match(/(\d+)$/)[1];
    people = people.map((p) => (String(p.id) === id ? { ...p, ...JSON.parse(options.body) } : p));
    return json(people[0]);
  }
  const role = url.match(/\/api\/people\/(\d+)\/(make-bu-head|remove-bu-head)$/);
  if (role) {
    if (JSON.parse(options.body).confirm !== true) return error(400, 'Confirm the role change first.');
    if (onLiveProject)
      return error(
        409,
        'Kavya Raman is assigned to Hotel Tower as engineer. Remove them from these projects before making them a BU Head.',
      );
    people = people.map((p) =>
      String(p.id) === role[1] ? { ...p, role: 'bu_head', can_edit: false, can_make_bu_head: false } : p,
    );
    return json(people[0]);
  }
  return Promise.resolve(new Response(JSON.stringify({ detail: `No fixture for ${url}` }), { status: 404 }));
}

const calls = (pattern, method) =>
  fetch.mock.calls.filter(([url, options]) => pattern.test(url) && (options?.method || 'GET') === method);

function renderCard() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PeopleCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('People card (BU Head onboarding)', () => {
  beforeEach(() => {
    people = [PERSON];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('says MAEC One manages sign-in, access and passwords, and links to it', async () => {
    renderCard();

    expect(screen.getByText(/Sign-in, access and passwords are managed in MAEC One/)).toBeTruthy();
    expect(screen.getByRole('link', { name: 'open MAEC One' }).getAttribute('href')).toBe(
      'https://auth.mirageaec.com/',
    );
    for (const gone of [/Reset/, /Deactivate/, /Reactivate/, /Delete/, /Download/]) {
      expect(screen.queryByRole('button', { name: gone })).toBeNull();
    }
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    expect(await screen.findByText('kavya.raman@mirageaec.com')).toBeTruthy();
  });

  it('uploads the HR export, reports what happened and reminds that each needs a seat in MAEC One', async () => {
    renderCard();
    const file = new File(['Employee Id,Full Name,Work Email,Job Role\n'], 'people.csv', {
      type: 'text/csv',
    });

    fireEvent.change(screen.getByLabelText('Employee CSV file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /Import/ }));

    expect(await screen.findByText(/profile created/)).toBeTruthy();
    expect(screen.getAllByText(/needs a seat on Project Management in MAEC One/).length).toBeGreaterThan(1);
    expect(screen.getByText(/Line 3: Arun Kumar – Already has a profile\./)).toBeTruthy();
    const [url, options] = calls(/\/api\/people\/import$/, 'POST')[0];
    expect(url).toMatch(/\/api\/people\/import$/);
    expect(options.body.get('file').name).toBe('people.csv');
  });

  it('adds one person who has a seat in MAEC One but no profile here', async () => {
    renderCard();
    const add = screen.getByRole('button', { name: /Add/ });
    expect(add.disabled).toBe(true); // every field first

    fireEvent.change(screen.getByLabelText('Employee Id'), { target: { value: 'M0301' } });
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Neha Rao' } });
    fireEvent.change(screen.getByLabelText('Work email'), { target: { value: 'Neha.Rao@mirageaec.com' } });
    fireEvent.change(screen.getByLabelText('Job role'), { target: { value: 'Intern' } });
    fireEvent.click(add);

    expect(await screen.findByText(/Profile created for/)).toBeTruthy();
    expect(JSON.parse(calls(/\/api\/people$/, 'POST')[0][1].body)).toEqual({
      employee_code: 'M0301',
      full_name: 'Neha Rao',
      email: 'Neha.Rao@mirageaec.com',
      job_role: 'Intern',
    });
  });
});

describe('People list (BU Head)', () => {
  beforeEach(() => {
    people = [
      PERSON,
      {
        ...PERSON,
        id: 1,
        username: 'mohan@mirageaec.com',
        full_name: 'Mohan Daniel',
        role: 'bu_head',
        employee_code: null,
        job_role: null,
        can_edit: false,
      },
    ];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('lists everyone with their email and status, and searches', async () => {
    renderCard();

    expect(await screen.findByText('kavya.raman@mirageaec.com')).toBeTruthy();
    expect(screen.getAllByText('Active')).toHaveLength(2);
    expect(screen.getByText('2 profiles')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1); // not on the BU Head's row

    fireEvent.change(screen.getByLabelText('Search people'), { target: { value: 'M0101' } });
    expect(screen.queryByText('Mohan Daniel')).toBeNull();
  });

  it('corrects a name or job role, never the email', async () => {
    renderCard();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    const form = within(document.querySelector('.people-edit-form'));

    expect(form.queryByLabelText(/email/i)).toBeNull(); // who they are in MAEC One
    fireEvent.change(form.getByLabelText('Job role'), { target: { value: 'Electrical Lead' } });
    fireEvent.click(form.getByRole('button', { name: 'Save' }));

    expect(await screen.findByText('Electrical Lead')).toBeTruthy();
    expect(JSON.parse(calls(/\/api\/people\/7$/, 'PATCH')[0][1].body)).toEqual({
      full_name: 'Kavya Raman',
      job_role: 'Electrical Lead',
    });
  });
});

describe('Making someone a BU Head', () => {
  beforeEach(() => {
    people = [PERSON];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    onLiveProject = false;
  });

  const openDialog = async () => {
    renderCard();
    fireEvent.click(await screen.findByRole('button', { name: 'Make BU Head' }));
    return screen.getByRole('dialog');
  };

  it('names the projects that block it, inside the dialog', async () => {
    onLiveProject = true;
    const dialog = await openDialog();
    const confirm = within(dialog).getByRole('button', { name: 'Make BU Head' });

    expect(within(dialog).queryByLabelText(/password/i)).toBeNull(); // confirmed in the dialog, no password
    fireEvent.click(confirm);

    expect(await within(dialog).findByText(/assigned to Hotel Tower as engineer/)).toBeTruthy();
    expect(screen.getByRole('dialog')).toBeTruthy(); // stays open
  });

  it('promotes once confirmed and closes', async () => {
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Make BU Head' }));

    await vi.waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByText('BU Head')).toBeTruthy();
    expect(JSON.parse(calls(/make-bu-head$/, 'POST')[0][1].body)).toEqual({ confirm: true });
  });
});
