// @vitest-environment jsdom
/** The phase cards' "+" add a task to that phase: the Add WBS Node dialog, phase chosen, no file picker. */
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

const ROUTES = [
  [/\/api\/projects$/, [{ id: 1, project_name: 'test', project_code: 'MAEC-001', my_role: 'lead' }]],
  [/\/api\/projects\/1\/wbs-structure/, []],
  [/\/api\/projects\/1\/booked-engineers$/, []],
];

function fakeApi(url) {
  const match = ROUTES.find(([pattern]) => pattern.test(url));
  const body = match ? match[1] : { detail: `No fixture for ${url}` };
  return Promise.resolve(new Response(JSON.stringify(body), { status: match ? 200 : 404 }));
}

describe('WBS phase cards (lead)', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn(fakeApi)));
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it.each(PHASES)('"+" on %s opens Add WBS Node with that phase chosen', async (phase) => {
    render(
      <MemoryRouter initialEntries={['/wbs-structure?projectId=1']}>
        <WbsStructurePage />
      </MemoryRouter>,
    );
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
