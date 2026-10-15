// @vitest-environment jsdom
/** Project Estimation: dates every N days as columns, a code per row (its role follows), hours, totals, saved by name. */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectEstimationPage } from './ProjectEstimationPage';

const WAIT = { timeout: 5000 };
const CODES = [
  { code: 'SME', role: 'Senior Mechanical Engineer' },
  { code: 'BL', role: 'BIM Manager' },
  { code: 'BL', role: 'BIM Coordinator' },
];
const SAVED = {
  id: 7,
  name: 'DCH A9 tender',
  start_date: '2027-01-01',
  end_date: '2027-01-15',
  interval_days: 7,
  row_count: 1,
  total_hours: 12,
  rows: [{ code: 'BL', role: 'BIM Coordinator', hours: { '2027-01-08': 12 }, total: 12 }],
  stages: { '2027-01-08': 'DD' },
};

let saved;
let posted;

function fakeApi(url, options = {}) {
  const json = (body, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
  if (url.endsWith('/api/estimations/codes')) return json(CODES);
  if (url.endsWith('/api/estimations') && options.method === 'POST') {
    posted = JSON.parse(options.body);
    const created = { ...posted, id: 8, row_count: posted.rows.length, total_hours: 0 };
    saved = [...saved, created];
    return json(created, 201);
  }
  if (url.endsWith('/api/estimations')) return json(saved);
  if (url.endsWith('/api/estimations/7')) return json(SAVED);
  return json({ detail: `No fixture for ${url}` }, 404);
}

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ProjectEstimationPage />
    </QueryClientProvider>,
  );

const field = (label) => screen.getByLabelText(label, { selector: 'input' });
const headings = () =>
  [...document.querySelectorAll('.estimation-grid thead tr:first-child th')].map((th) => th.textContent);

describe('Project Estimation', () => {
  beforeEach(() => {
    saved = [];
    posted = null;
    vi.stubGlobal('fetch', vi.fn(fakeApi));
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('makes a column every N days, adds up hours per row and per date, and saves only the grid', async () => {
    renderPage();
    await screen.findByText('No estimations saved yet. Fill in the one below and save it.', {}, WAIT);

    fireEvent.change(field(/Estimation name/), { target: { value: 'Tower B' } });
    fireEvent.change(field('Start date'), { target: { value: '2027-01-01' } });
    fireEvent.change(field('End date'), { target: { value: '2027-02-01' } });
    expect(headings()).toEqual([
      '#',
      'CODE',
      'STAFF ROLE',
      'TOTAL HOURS',
      '01 Jan 27',
      '08 Jan 27',
      '15 Jan 27',
      '22 Jan 27',
      '29 Jan 27',
      '',
    ]);
    expect(screen.getByText(/5 date columns: 01 Jan 27 to 29 Jan 27/)).toBeTruthy();

    const code = await screen.findByLabelText('Code of row 1');
    await within(code).findByText('SME — Senior Mechanical Engineer', {}, WAIT);
    fireEvent.change(code, { target: { value: 'SME|Senior Mechanical Engineer' } });
    const row = code.closest('tr');
    expect(within(row).getByText('Senior Mechanical Engineer', { selector: 'td' })).toBeTruthy(); // the role follows
    fireEvent.change(field('Hours of row 1 on 01 Jan 27'), { target: { value: '9' } });
    fireEvent.change(field('Hours of row 1 on 08 Jan 27'), { target: { value: '5' } });
    fireEvent.change(field('Hours of row 1 on 15 Jan 27'), { target: { value: '22.5' } });
    expect(row.querySelector('.est-total').textContent).toBe('36.5');

    fireEvent.click(screen.getByRole('button', { name: /Add row/ }));
    fireEvent.change(screen.getByLabelText('Code of row 2'), { target: { value: 'BL|BIM Coordinator' } });
    fireEvent.change(field('Hours of row 2 on 01 Jan 27'), { target: { value: '4' } });
    const footer = [...document.querySelectorAll('.estimation-grid tfoot td')].map((td) => td.textContent);
    expect(footer.slice(1, 6)).toEqual(['Total', '', '40.5', '13', '5']); // grand total, then 01 and 08 Jan

    const stage = (day) => screen.getByLabelText(`Stage on ${day}`);
    expect([...stage('01 Jan 27').options].map((option) => option.value)).toEqual([
      '',
      'CD',
      'SD',
      'DD',
      'TD',
      'IFC',
    ]);
    expect(stage('01 Jan 27').value).toBe(''); // empty until chosen
    fireEvent.change(stage('01 Jan 27'), { target: { value: 'CD' } });
    fireEvent.change(stage('08 Jan 27'), { target: { value: 'SD' } });

    fireEvent.change(field('Days between columns'), { target: { value: '14' } }); // 08 Jan is no column now
    expect(screen.getByText(/5 hours are on dates no longer in the grid/)).toBeTruthy();
    expect(screen.getByText(/1 stage is on dates no longer in the grid/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Save estimation' }));

    expect(await screen.findByText('Saved "Tower B".', {}, WAIT)).toBeTruthy();
    expect(posted).toEqual({
      name: 'Tower B',
      start_date: '2027-01-01',
      end_date: '2027-02-01',
      interval_days: 14,
      rows: [
        { code: 'SME', role: 'Senior Mechanical Engineer', hours: { '2027-01-01': 9, '2027-01-15': 22.5 } },
        { code: 'BL', role: 'BIM Coordinator', hours: { '2027-01-01': 4 } },
      ],
      stages: { '2027-01-01': 'CD' }, // 08 Jan's SD went with its column
    });
  });

  it('reopens a saved estimation from the list', async () => {
    saved = [SAVED];
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Open DCH A9 tender' }, WAIT));

    expect(await screen.findByDisplayValue('DCH A9 tender', {}, WAIT)).toBeTruthy();
    expect(screen.getByLabelText('Code of row 1').value).toBe('BL|BIM Coordinator');
    expect(field('Hours of row 1 on 08 Jan 27').value).toBe('12');
    expect(screen.getByLabelText('Stage on 08 Jan 27').value).toBe('DD');
    expect(screen.getByLabelText('Stage on 01 Jan 27').value).toBe(''); // none chosen
    expect(headings().slice(4, -1)).toEqual(['01 Jan 27', '08 Jan 27', '15 Jan 27']);
  });

  it('asks for a code on every row before saving', async () => {
    renderPage();
    await screen.findByText(/No estimations saved yet/, {}, WAIT);
    fireEvent.change(field(/Estimation name/), { target: { value: 'Tower B' } });
    fireEvent.change(field('Start date'), { target: { value: '2027-01-01' } });
    fireEvent.change(field('End date'), { target: { value: '2027-01-15' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save estimation' }));

    expect(
      await screen.findByText('Choose a code for every row, or remove the empty rows.', {}, WAIT),
    ).toBeTruthy();
    expect(posted).toBeNull();
  });
});
