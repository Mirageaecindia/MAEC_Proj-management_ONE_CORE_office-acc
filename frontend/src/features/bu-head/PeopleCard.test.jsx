// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PeopleCard } from './PeopleCard';
import { credentialsCsv } from './peopleCsv';

const IMPORTED = {
  created: [
    {
      username: 'kavya.raman@mirageaec.com',
      full_name: 'Kavya Raman',
      employee_code: 'M0101',
      temporary_password: 'abc23DEF45gh',
    },
  ],
  skipped: [{ row: 3, name: 'Arun Kumar', email: 'arun@mirageaec.com', reason: 'Already has an account.' }],
};

let people = [];
const PERSON = {
  id: 7,
  username: 'kavya.raman@mirageaec.com',
  full_name: 'Kavya Raman',
  role: 'engineer',
  employee_code: 'M0101',
  job_role: 'Senior Electrical Engineer',
  is_active: true,
  must_change_password: true,
  can_edit: true,
  can_delete: true,
};
const json = (body) =>
  Promise.resolve(
    new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  );

function fakeApi(url, options = {}) {
  const method = options.method || 'GET';
  if (url.endsWith('/api/people/import')) return json(IMPORTED);
  if (url.endsWith('/api/people/reset-password')) {
    return json({
      username: 'kavya.raman@mirageaec.com',
      full_name: 'Kavya Raman',
      temporary_password: 'NewTemp23xyz',
    });
  }
  if (url.endsWith('/api/people') && method === 'GET') return json(people);
  const deactivate = url.match(/\/api\/people\/(\d+)\/(deactivate|reactivate)$/);
  if (deactivate) {
    people = people.map((p) =>
      String(p.id) === deactivate[1] ? { ...p, is_active: deactivate[2] === 'reactivate' } : p,
    );
    return json(people[0]);
  }
  if (/\/api\/people\/\d+$/.test(url) && method === 'PATCH') {
    const id = url.match(/(\d+)$/)[1];
    people = people.map((p) => (String(p.id) === id ? { ...p, ...JSON.parse(options.body) } : p));
    return json(people[0]);
  }
  if (/\/api\/people\/\d+$/.test(url) && method === 'DELETE') {
    people = [];
    return json({ ok: true });
  }
  return Promise.resolve(new Response(JSON.stringify({ detail: `No fixture for ${url}` }), { status: 404 }));
}

const calls = (pattern, method) =>
  fetch.mock.calls.filter(([url, options]) => pattern.test(url) && (options?.method || 'GET') === method);

function renderCard() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PeopleCard />
    </QueryClientProvider>,
  );
}

describe('People card (BU Head onboarding)', () => {
  beforeEach(() => {
    people = [PERSON];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
    URL.createObjectURL = vi.fn(() => 'blob:passwords');
    URL.revokeObjectURL = vi.fn();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('uploads the HR export, reports what happened and offers the passwords as a file', async () => {
    renderCard();
    const file = new File(['Employee Id,Full Name,Work Email,Job Role\n'], 'people.csv', {
      type: 'text/csv',
    });

    fireEvent.change(screen.getByLabelText('Employee CSV file'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: /Import/ }));

    expect(await screen.findByText(/account created/)).toBeTruthy();
    expect(screen.getByText(/Line 3: Arun Kumar – Already has an account\./)).toBeTruthy();
    const [url, options] = calls(/\/api\/people\/import$/, 'POST')[0];
    expect(url).toMatch(/\/api\/people\/import$/);
    expect(options.body.get('file').name).toBe('people.csv');

    fireEvent.click(screen.getByRole('button', { name: /Download the temporary passwords/ }));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('abc23DEF45gh')).toBeNull(); // passwords are in the file, not on screen
  });

  it('resets a forgotten password and shows the new temporary one', async () => {
    renderCard();

    fireEvent.change(screen.getByLabelText('Username to reset'), {
      target: { value: ' kavya.raman@mirageaec.com ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Reset/ }));

    expect(await screen.findByText('NewTemp23xyz')).toBeTruthy();
    expect(JSON.parse(calls(/reset-password$/, 'POST')[0][1].body)).toEqual({
      username: 'kavya.raman@mirageaec.com',
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
        must_change_password: false,
        can_edit: false,
        can_delete: false,
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
    expect(screen.getByText('Not signed in yet')).toBeTruthy();
    expect(screen.getByText(/2 accounts · 1 not signed in yet/)).toBeTruthy();
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1); // not on the BU Head's row

    fireEvent.change(screen.getByLabelText('Search people'), { target: { value: 'M0101' } });
    expect(screen.queryByText('Mohan Daniel')).toBeNull();
  });

  it('corrects a name and email, deactivates, and deletes an account made by mistake', async () => {
    renderCard();
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Work email (signs in with)'), {
      target: { value: 'kavya.r@mirageaec.com' },
    });

    expect(screen.getByText(/They will sign in with the new email/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(await screen.findByText('kavya.r@mirageaec.com')).toBeTruthy();
    expect(JSON.parse(calls(/\/api\/people\/7$/, 'PATCH')[0][1].body)).toMatchObject({
      username: 'kavya.r@mirageaec.com',
    });

    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));
    expect(await screen.findByText('Deactivated')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
    await vi.waitFor(() => expect(calls(/\/api\/people\/7$/, 'DELETE')).toHaveLength(1));
  });
});

describe('credentialsCsv', () => {
  it('writes one quoted line per account, safe for names with commas or quotes', () => {
    const csv = credentialsCsv([
      { username: 'a@x.com', full_name: 'Raman, "KV"', employee_code: 'M1', temporary_password: 'p' },
    ]);

    expect(csv).toBe(
      '"Username","Full Name","Employee Id","Temporary Password"\r\n"a@x.com","Raman, ""KV""","M1","p"\r\n',
    );
  });
});
