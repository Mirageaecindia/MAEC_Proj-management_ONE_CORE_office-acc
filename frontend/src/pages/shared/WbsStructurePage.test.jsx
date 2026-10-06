// @vitest-environment jsdom
/** WBS page: the phase cards' "+" add a task to that phase; each row adds a subtask ("+") and duplicates. */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { WbsStructurePage } from './WbsStructurePage';

const WAIT = { timeout: 5000 };
const PHASES = [
  'Space Planning',
  'STR Coordination',
  'ID Coordination',
  'BoH Area RCP Coordination',
  'Submission',
];

vi.mock('../../AuthContext', () => {
  const auth = { user: { id: 1 }, role: 'engineer', authHeaders: () => ({}), logout: vi.fn() };
  return { useAuth: () => auth };
});

const node = (id, code, name, parentId = null) => ({
  id,
  wbs_code: code,
  task_name: name,
  parent_id: parentId,
  phase: 'Space Planning',
  deliverable_status: 'To Do',
  estimated_hours: 4,
  start_date: '2026-10-05',
  target_due_date: '2026-10-09',
});
let nodes = [];

const ROUTES = [
  [/\/api\/projects$/, () => [{ id: 1, project_name: 'test', project_code: 'MAEC-001', my_role: 'lead' }]],
  [/\/api\/projects\/1\/wbs-structure/, () => nodes],
  [/\/api\/projects\/1\/booked-engineers$/, () => []],
  [
    /\/api\/wbs-nodes\/11\/duplicate$/,
    () => {
      nodes = [...nodes, node(12, '1.2', 'Risers', 10)];
      return nodes.at(-1);
    },
  ],
];

function fakeApi(url) {
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const body = match ? match[1]() : { detail: `No fixture for ${url}` };
  return Promise.resolve(new Response(JSON.stringify(body), { status: match ? 200 : 404 }));
}

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/wbs-structure?projectId=1']}>
      <WbsStructurePage />
    </MemoryRouter>,
  );

describe('WBS phase cards (lead)', () => {
  beforeEach(() => {
    nodes = [];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it.each(PHASES)('"+" on %s opens Add WBS Node with that phase chosen', async (phase) => {
    renderPage();
    const filePicker = vi.spyOn(HTMLInputElement.prototype, 'click');

    fireEvent.click(await screen.findByRole('button', { name: `Add a task to ${phase}` }, WAIT));

    const heading = screen.getByRole('heading', { name: 'Add WBS Node' });
    const dialog = heading.closest('form') || heading.parentElement.parentElement;
    const phaseSelect = within(dialog)
      .getAllByRole('combobox')
      .find((select) => [...select.options].some((option) => option.value === phase));
    expect(phaseSelect.value).toBe(phase);
    expect(filePicker).not.toHaveBeenCalled(); // no Excel upload
    filePicker.mockRestore();
  });
});

describe('WBS rows (lead)', () => {
  it('shows the target start and end date of each row under their headers', async () => {
    nodes = [node(10, '1', 'Cable routing'), node(11, '1.1', 'Risers', 10)];
    renderPage();

    const row = (await screen.findByText('Risers', {}, WAIT)).closest('tr');
    const headers = [...document.querySelectorAll('table.wbs-table thead th')].map((th) =>
      th.textContent.trim(),
    );
    const cell = (header) => row.children[headers.indexOf(header)].textContent;
    expect(headers).not.toContain('TARGET DUE DATE');
    expect(cell('TARGET START DATE')).toBe('2026-10-05');
    expect(cell('TARGET END DATE')).toBe('2026-10-09');
  });

  beforeEach(() => {
    nodes = [node(10, '1', 'Cable routing'), node(11, '1.1', 'Risers', 10)];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('adds a subtask from a plain "+" and duplicates a row into the next free code', async () => {
    renderPage();

    const add = await screen.findByRole('button', { name: 'Add a subtask to Cable routing' }, WAIT);
    expect(add.textContent).toBe(''); // the icon only, no "Subtask" text
    expect(screen.getByRole('button', { name: 'Duplicate Cable routing' })).toBeTruthy(); // tasks too

    fireEvent.click(screen.getByRole('button', { name: 'Duplicate Risers' }));

    expect(await screen.findByText('Duplicated 1.1 as 1.2.', {}, WAIT)).toBeTruthy();
    expect(await screen.findByText('1.2', {}, WAIT)).toBeTruthy(); // the list is reloaded
    const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/api/wbs-nodes/11/duplicate'));
    expect(options.method).toBe('POST');
  });
});
