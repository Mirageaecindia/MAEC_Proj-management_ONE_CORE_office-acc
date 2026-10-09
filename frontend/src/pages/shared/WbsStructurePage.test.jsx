// @vitest-environment jsdom
/** WBS page: a phase card's name adds one task, its "+" the phase's blueprint; each row adds a subtask ("+") and duplicates. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { WbsStructurePage } from './WbsStructurePage';

const WAIT = { timeout: 5000 };
const PHASES = [
  'Space Planning',
  'STR Coordination',
  'ID - RCP Coordination',
  'BoH Area RCP Coordination',
  'Submission',
];

vi.mock('../../AuthContext', () => {
  const auth = {
    user: { id: 1, employee_id: 3 },
    role: 'engineer',
    authHeaders: () => ({}),
    logout: vi.fn(),
  };
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
let myRole = 'lead'; // the viewer's role on the project

const BLUEPRINTS = PHASES.map((phase, index) => ({
  key: phase.toLowerCase().replace(/ /g, '-'),
  phase,
  tasks: 2,
  subtasks: 5 + index,
}));
let blueprintAdds = [];
let present = { tasks: 0, subtasks: 0 }; // how much of a blueprint the fake project already has
let deleted = [];

const ROUTES = [
  [/\/api\/wbs-blueprints$/, () => BLUEPRINTS],
  [
    /\/api\/projects\/1\/wbs-blueprints\/[a-z-]+(\?again=true)?$/,
    (url, options) => {
      const again = url.endsWith('?again=true');
      const key = url.replace('?again=true', '').split('/').at(-1);
      const blueprint = BLUEPRINTS.find((b) => b.key === key);
      if (options.method !== 'POST') {
        const total = blueprint.tasks + blueprint.subtasks;
        return {
          ...blueprint,
          present_tasks: present.tasks,
          present_subtasks: present.subtasks,
          missing: total - present.tasks - present.subtasks,
        };
      }
      blueprintAdds.push(again ? `${key} again` : key);
      nodes = [...nodes, node(30, '14.', 'Blueprint task'), node(31, '14.1', 'Blueprint step', 30)];
      return {
        phase: blueprint.phase,
        created: 2,
        skipped: again ? 0 : 7,
        created_ids: [30, 31],
        same_as: again ? { 30: '1.', 31: '1.1' } : {},
      };
    },
  ],
  [
    /\/api\/projects\/1\/wbs-nodes\/delete$/,
    (url, options) => {
      deleted = JSON.parse(options.body).node_ids;
      nodes = nodes.filter((n) => !deleted.includes(n.id));
      return { tasks: 1, subtasks: 1, hours_kept: 0, deleted_nodes: deleted };
    },
  ],
  [/\/api\/projects$/, () => [{ id: 1, project_name: 'test', project_code: 'MAEC-001', my_role: myRole }]],
  [/\/api\/projects\/1\/wbs-structure/, () => nodes],
  [/\/api\/projects\/1\/booked-engineers$/, () => booked],
  [
    /\/api\/wbs-nodes\/\d+$/,
    (url, options) => {
      const id = Number(url.split('/').at(-1));
      const body = JSON.parse(options.body);
      saved.push({ id, body });
      nodes = nodes.map((n) =>
        n.id === id
          ? {
              ...n,
              ...body,
              assigned_engineer_name: booked.find((e) => e.id === body.assigned_engineer_id)?.name,
            }
          : n,
      );
      return nodes.find((n) => n.id === id);
    },
  ],
  [
    /\/api\/wbs-nodes\/11\/subtasks$/,
    () => {
      nodes = [...nodes, node(13, '1.1.1', 'Sleeves', 11)];
      return nodes.at(-1);
    },
  ],
  [
    /\/api\/wbs-nodes\/11\/duplicate$/,
    () => {
      nodes = [...nodes, node(12, '1.2', 'Risers', 10)];
      return nodes.at(-1);
    },
  ],
];

let booked = [];
let saved = [];

function fakeApi(url, options = {}) {
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const body = match ? match[1](url, options) : { detail: `No fixture for ${url}` };
  return Promise.resolve(new Response(JSON.stringify(body), { status: match ? 200 : 404 }));
}

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/wbs-structure?projectId=1']}>
        <WbsStructurePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe('WBS phase cards (lead)', () => {
  beforeEach(() => {
    nodes = [];
    blueprintAdds = [];
    present = { tasks: 0, subtasks: 0 };
    deleted = [];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });

  it('when some of it is there: says how much, adds a second copy, marks each repeat, and undoes', async () => {
    present = { tasks: 2, subtasks: 4 }; // Space Planning: 2 tasks + 5 subtasks, one subtask missing
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Add the Space Planning blueprint' }, WAIT));
    const dialog = await screen.findByRole('dialog', {}, WAIT);
    await within(dialog).findByText(
      /2 tasks and 4 subtasks of the standard Space Planning list are already/,
      {},
      WAIT,
    );
    expect(within(dialog).getByRole('button', { name: 'Add the 1 missing' })).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add all 7 again' }));

    expect(await screen.findByText('New · same as 1.', {}, WAIT)).toBeTruthy();
    expect(screen.getByText('New · same as 1.1')).toBeTruthy();
    expect(blueprintAdds).toEqual(['space-planning again']);
    expect(screen.getByText('Blueprint task').closest('tr').className).toContain('wbs-row-new');
    expect(screen.getByText(/2 items added to Space Planning/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await vi.waitFor(() => expect(deleted).toEqual([30, 31]), WAIT);
    await vi.waitFor(() => expect(screen.queryByText('Blueprint task')).toBeNull(), WAIT);
  });

  it('Keep clears the highlight and leaves the rows', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Add the Submission blueprint' }, WAIT));
    const dialog = await screen.findByRole('dialog', {}, WAIT);
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Add tasks' }, WAIT));
    await screen.findByText(/2 items added to Submission/, {}, WAIT);

    fireEvent.click(screen.getByRole('button', { name: 'Keep' }));

    expect(screen.queryByText(/items added to/)).toBeNull();
    expect(screen.getByText('Blueprint task').closest('tr').className).not.toContain('wbs-row-new');
    expect(screen.queryByText(/^New/)).toBeNull();
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it.each(PHASES)(
    '"+" on %s adds the blueprint of that phase after saying how much it adds',
    async (phase) => {
      renderPage();
      const blueprint = BLUEPRINTS.find((b) => b.phase === phase);

      fireEvent.click(await screen.findByRole('button', { name: `Add the ${phase} blueprint` }, WAIT));
      const dialog = await screen.findByRole('dialog', {}, WAIT);
      await within(dialog).findByText(
        `2 tasks and ${blueprint.subtasks} subtasks from the standard ${phase} list.`,
        {},
        WAIT,
      );
      fireEvent.click(within(dialog).getByRole('button', { name: 'Add tasks' }));

      expect(await screen.findByText(`${phase}: 2 added, 7 already there.`, {}, WAIT)).toBeTruthy();
      expect(blueprintAdds).toEqual([blueprint.key]); // that phase only
      expect(await screen.findByText('Blueprint task', {}, WAIT)).toBeTruthy(); // the WBS is reloaded
    },
  );

  it('the phase name still adds a single task by hand, with the phase chosen', async () => {
    const phase = 'ID - RCP Coordination';
    renderPage();
    const filePicker = vi.spyOn(HTMLInputElement.prototype, 'click');

    fireEvent.click(await screen.findByRole('button', { name: phase }, WAIT));

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

describe('Sub-subtasks (lead)', () => {
  beforeEach(() => {
    nodes = [node(10, '1', 'Cable routing'), node(11, '1.1', 'Risers', 10)];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('"+" on a subtask adds a reference step under it, with no hours', async () => {
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Add a sub-subtask to Risers' }, WAIT));
    expect(screen.getByRole('heading', { name: 'Add WBS Sub-subtask' })).toBeTruthy();
    expect(screen.queryByPlaceholderText('1-8')).toBeNull(); // no hours to enter
    const form = screen.getByRole('heading', { name: 'Add WBS Sub-subtask' }).closest('form');
    fireEvent.change(screen.getByPlaceholderText('Enter task name'), { target: { value: 'Sleeves' } });
    fireEvent.submit(form);

    expect(await screen.findByText('1.1.1', {}, WAIT)).toBeTruthy();
    const [, options] = fetch.mock.calls.find(([url]) => url.endsWith('/api/wbs-nodes/11/subtasks'));
    expect(JSON.parse(options.body)).toMatchObject({
      task_name: 'Sleeves',
      parent_id: 11,
      estimated_hours: null,
    });
    expect(screen.queryByRole('button', { name: 'Add a sub-subtask to Sleeves' })).toBeNull(); // three levels at most
  });
});

describe('Editing in the table (lead)', () => {
  beforeEach(() => {
    booked = [{ id: 3, name: 'Ravi Kumar' }];
    saved = [];
    nodes = [
      node(10, '1', 'Cable routing'),
      { ...node(11, '1.1', 'Risers', 10), assigned_lead: 'Lead A', assigned_lead_user_id: 9 },
      { ...node(12, '1.2', 'Trays', 10), deliverable_status: 'In-Progress', assigned_engineer_name: 'Me' },
    ];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('assigns an engineer from the cell: pick, then the tick saves', async () => {
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Change engineer of Risers' }, WAIT));
    fireEvent.change(screen.getByLabelText('engineer of Risers'), { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save engineer of Risers' }));

    expect(await screen.findByText('Ravi Kumar', {}, WAIT)).toBeTruthy();
    expect(saved[0].id).toBe(11);
    expect(saved[0].body).toMatchObject({
      assigned_engineer_id: 3,
      assigned_lead_user_id: 9,
      task_name: 'Risers',
    });
  });

  it('a subtask date sets both its dates (one day of work)', async () => {
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Change start date of Risers' }, WAIT));
    fireEvent.change(screen.getByLabelText('start date of Risers'), { target: { value: '2026-10-12' } });
    fireEvent.keyDown(screen.getByLabelText('start date of Risers'), { key: 'Enter' });

    await vi.waitFor(() => expect(saved).toHaveLength(1), WAIT);
    expect(saved[0].body).toMatchObject({
      start_date: '2026-10-12',
      end_date: '2026-10-12',
      target_due_date: '2026-10-12',
    });
  });

  it('a started subtask keeps its plan: no editable cells, the reason on hover', async () => {
    renderPage();
    await screen.findByRole('button', { name: 'Change engineer of Risers' }, WAIT);

    expect(screen.queryByRole('button', { name: 'Change engineer of Trays' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Change hours of Trays' })).toBeNull();
    const trays = screen.getByText('Trays').closest('tr');
    expect(within(trays).getByText('Me').getAttribute('title')).toMatch(
      /^In-Progress: the engineer, hours and dates stay/,
    );
    expect(screen.queryByRole('button', { name: 'Change hours of Cable routing' })).toBeNull(); // a task: from its dates
  });
});

describe('WBS rows (engineer)', () => {
  beforeEach(() => {
    myRole = 'engineer';
    nodes = [
      {
        ...node(10, '1', 'Cable routing'),
        assigned_engineer_id: 3,
        assigned_engineer_name: 'Me',
        assigned_lead: 'Lead A',
      },
      {
        ...node(11, '1.1', 'Risers', 10),
        assigned_engineer_id: 3,
        assigned_engineer_name: 'Me',
        created_by_user_id: 1,
      },
      { ...node(12, '1.2', 'Trays', 10), assigned_engineer_id: 4, assigned_engineer_name: 'Ravi Kumar' },
    ];
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    myRole = 'lead';
  });

  it('shows who has each subtask, the reporter, and keeps every button in its place', async () => {
    renderPage();

    const colleague = (await screen.findByText('Trays', {}, WAIT)).closest('tr');
    const headers = [...document.querySelectorAll('table.wbs-table thead th')].map((th) =>
      th.textContent.trim(),
    );
    expect(headers.slice(1, 3)).toEqual(['ASSIGNED ENGINEER', 'REPORTER']);
    expect(colleague.textContent).toContain('Ravi Kumar');
    expect(colleague.className).not.toContain('wbs-row-clickable'); // a colleague's subtask doesn't open

    for (const row of document.querySelectorAll('tbody tr')) {
      const actions = row.querySelector('.wbs-cell-actions');
      if (actions) expect(actions.children).toHaveLength(4); // add, duplicate, edit, delete: fixed places
    }
    const mine = screen.getByText('Risers').closest('tr');
    const places = [...mine.querySelector('.wbs-cell-actions').children].map((el) =>
      el.getAttribute('aria-label'),
    );
    expect(places).toEqual(['Add a sub-subtask to Risers', 'Duplicate Risers', null, 'Delete Risers']); // no edit
  });
});
