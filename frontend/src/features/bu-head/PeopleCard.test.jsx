// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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

function fakeApi(url) {
  const body = url.endsWith('/api/people/import')
    ? IMPORTED
    : { username: 'kavya.raman@mirageaec.com', full_name: 'Kavya Raman', temporary_password: 'NewTemp23xyz' };
  return Promise.resolve(
    new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  );
}

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
    const [url, options] = fetch.mock.calls[0];
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
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ username: 'kavya.raman@mirageaec.com' });
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
