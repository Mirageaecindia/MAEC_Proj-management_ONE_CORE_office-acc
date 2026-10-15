import { FilePlus2, FolderOpen, Plus, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { EmptyState, ErrorBanner, Notice } from '../../components/Feedback';
import { PageHeader } from '../../components/PageHeader';
import {
  useDeleteEstimation,
  useEstimation,
  useEstimationCodes,
  useEstimations,
  useSaveEstimation,
} from '../../hooks/useEstimations';
import {
  columnDates,
  columnLabel,
  columnTotals,
  hoursOf,
  hoursOutsideGrid,
  rowTotal,
  toPayload,
} from '../../utils/estimation';

/**
 * Project Estimation (BU Head, decided 2026-10-15): a resourcing estimate made before a project
 * exists, laid out like the company's resourcing sheet. Columns are dates from the start date
 * every N days to the end date; each row is a staff code (its role follows) with hours per date
 * and a total. Estimations are saved by name and reopened from the list.
 */

let nextKey = 1;
const newRow = (row = {}) => ({ key: nextKey++, code: '', role: '', hours: {}, ...row });
const EMPTY = { name: '', startDate: '', endDate: '', intervalDays: '7', rows: [newRow()] };

function draftFrom(saved) {
  return {
    name: saved.name,
    startDate: saved.start_date,
    endDate: saved.end_date,
    intervalDays: String(saved.interval_days),
    rows: saved.rows.length
      ? saved.rows.map((row) => newRow({ code: row.code, role: row.role, hours: row.hours }))
      : [newRow()],
  };
}

const formatHours = (value) => (value ? Number(value.toFixed(2)).toLocaleString('en-US') : '0');

export function ProjectEstimationPage() {
  const { codes } = useEstimationCodes();
  const list = useEstimations();
  const save = useSaveEstimation();
  const remove = useDeleteEstimation();

  const [openId, setOpenId] = useState(null); // the saved estimation in the editor; null: a new one
  const opened = useEstimation(openId);
  const [draft, setDraft] = useState(EMPTY);
  const [dirty, setDirty] = useState(false);
  const [pendingSwitch, setPendingSwitch] = useState(undefined); // what to open once changes are discarded
  const [pendingDelete, setPendingDelete] = useState(null);
  const [problem, setProblem] = useState('');
  const [notice, setNotice] = useState(null);

  // A saved estimation, once loaded (or just saved), fills the editor.
  useEffect(() => {
    if (opened.data && opened.data.id === openId) {
      setDraft(draftFrom(opened.data));
      setDirty(false);
    }
  }, [opened.data, openId]);

  const { dates, error: datesError } = useMemo(
    () => columnDates(draft.startDate, draft.endDate, draft.intervalDays),
    [draft.startDate, draft.endDate, draft.intervalDays],
  );
  const totals = useMemo(() => columnTotals(draft.rows, dates), [draft.rows, dates]);
  const grandTotal = totals.reduce((sum, value) => sum + value, 0);
  const leftOut = useMemo(() => hoursOutsideGrid(draft.rows, dates), [draft.rows, dates]);
  const mostPerCell = Number(draft.intervalDays) * 24;

  const change = (patch) => {
    setDraft((current) => ({ ...current, ...patch }));
    setDirty(true);
    setProblem('');
  };
  const changeRow = (key, patch) =>
    change({ rows: draft.rows.map((row) => (row.key === key ? { ...row, ...patch } : row)) });
  const setHours = (key, day, value) => {
    const row = draft.rows.find((item) => item.key === key);
    changeRow(key, { hours: { ...row.hours, [day]: value } });
  };

  function open(target) {
    // target: an estimation id, or 'new'
    setNotice(null);
    setProblem('');
    save.reset();
    if (target === 'new') {
      setOpenId(null);
      setDraft({ ...EMPTY, rows: [newRow()] });
      setDirty(false);
    } else {
      setOpenId(target);
    }
  }

  const askToOpen = (target) => (dirty ? setPendingSwitch(target) : open(target));

  function problems() {
    if (!draft.name.trim()) return 'Give the estimation a name.';
    if (datesError) return datesError;
    if (draft.rows.some((row) => !row.code)) return 'Choose a code for every row, or remove the empty rows.';
    const wrong = draft.rows.some((row) =>
      dates.some((day) => hoursOf(row.hours[day]) < 0 || hoursOf(row.hours[day]) > mostPerCell),
    );
    if (wrong) return `Hours must be between 0 and ${mostPerCell} in each date column.`;
    return '';
  }

  function submit() {
    const found = problems();
    setProblem(found);
    if (found) return;
    save.mutate(
      { estimationId: openId, payload: toPayload(draft, dates) },
      {
        onSuccess: (saved) => {
          setOpenId(saved.id);
          setDraft(draftFrom(saved));
          setDirty(false);
          setNotice({ type: 'success', message: `Saved "${saved.name}".` });
        },
      },
    );
  }

  function confirmDelete() {
    remove.mutate(pendingDelete.id, {
      onSuccess: () => {
        if (pendingDelete.id === openId) open('new');
        setNotice({ type: 'success', message: `Deleted "${pendingDelete.name}".` });
        setPendingDelete(null);
      },
    });
  }

  const estimations = list.data ?? [];

  return (
    <main className="page-shell estimation-page">
      <PageHeader
        breadcrumb={['Projects', 'Project Estimation']}
        title="Project Estimation"
        description="Estimate a project's resourcing before it starts: the hours of each staff role per date, as on the resourcing sheet."
      >
        <button type="button" className="button button-primary" onClick={() => askToOpen('new')}>
          <FilePlus2 size={16} /> New estimation
        </button>
      </PageHeader>

      {notice && <Notice {...notice} onDismiss={() => setNotice(null)} />}

      <section className="allocation-card estimation-list">
        <div className="allocation-header">
          <h2>Saved estimations</h2>
        </div>
        <ErrorBanner error={list.error} />
        {list.isLoading && <EmptyState>Loading estimations…</EmptyState>}
        {!list.isLoading && !list.error && estimations.length === 0 && (
          <EmptyState>No estimations saved yet. Fill in the one below and save it.</EmptyState>
        )}
        {estimations.length > 0 && (
          <div className="resource-table-wrap">
            <table className="resource-table">
              <thead>
                <tr>
                  <th>NAME</th>
                  <th>PERIOD</th>
                  <th>EVERY</th>
                  <th>ROWS</th>
                  <th>TOTAL HOURS</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {estimations.map((item) => (
                  <tr key={item.id} className={item.id === openId ? 'estimation-open' : undefined}>
                    <td className="estimation-name">{item.name}</td>
                    <td>
                      {columnLabel(item.start_date)} – {columnLabel(item.end_date)}
                    </td>
                    <td>{item.interval_days === 1 ? 'day' : `${item.interval_days} days`}</td>
                    <td>{item.row_count}</td>
                    <td>{formatHours(item.total_hours)}</td>
                    <td className="estimation-actions">
                      <button
                        type="button"
                        className="button button-secondary"
                        aria-label={`Open ${item.name}`}
                        onClick={() => askToOpen(item.id)}
                      >
                        <FolderOpen size={14} /> Open
                      </button>
                      <button
                        type="button"
                        className="wbs-icon-btn wbs-icon-delete"
                        aria-label={`Delete ${item.name}`}
                        title="Delete"
                        onClick={() => setPendingDelete(item)}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="allocation-card estimation-editor">
        <div className="allocation-header">
          <div>
            <h2>{openId ? draft.name || 'Estimation' : 'New estimation'}</h2>
            <p>{dirty ? 'Unsaved changes' : openId ? 'Saved' : 'Not saved yet'}</p>
          </div>
          <button type="button" className="button button-primary" disabled={save.isPending} onClick={submit}>
            {save.isPending ? 'Saving…' : 'Save estimation'}
          </button>
        </div>
        {openId && opened.isLoading && <EmptyState>Loading the estimation…</EmptyState>}

        <div className="estimation-body">
          <div className="estimation-settings">
            <label className="field">
              <span className="field-label">
                Estimation name<b aria-hidden="true"> *</b>
              </span>
              <input
                value={draft.name}
                maxLength={200}
                placeholder="e.g. DCH A9 & A10 tender"
                onChange={(event) => change({ name: event.target.value })}
              />
            </label>
            <label className="field">
              <span className="field-label">Start date</span>
              <input
                type="date"
                value={draft.startDate}
                onChange={(event) => change({ startDate: event.target.value })}
              />
            </label>
            <label className="field">
              <span className="field-label">End date</span>
              <input
                type="date"
                value={draft.endDate}
                onChange={(event) => change({ endDate: event.target.value })}
              />
            </label>
            <label className="field">
              <span className="field-label">Days between columns</span>
              <input
                type="number"
                min="1"
                max="366"
                value={draft.intervalDays}
                onChange={(event) => change({ intervalDays: event.target.value })}
              />
            </label>
          </div>
          <p className="field-hint">
            {datesError ||
              `${dates.length} date column${dates.length === 1 ? '' : 's'}: ${columnLabel(dates[0])} to ${columnLabel(dates[dates.length - 1])}.`}
            {leftOut > 0 &&
              ` ${formatHours(leftOut)} hours are on dates no longer in the grid; they are left out when you save.`}
          </p>

          {!datesError && (
            <div className="estimation-grid-wrap">
              <table className="estimation-grid">
                <thead>
                  <tr>
                    <th className="est-fixed est-no">#</th>
                    <th className="est-fixed est-code">CODE</th>
                    <th className="est-fixed est-role">STAFF ROLE</th>
                    <th className="est-fixed est-total">TOTAL HOURS</th>
                    {dates.map((day) => (
                      <th key={day} className="est-day">
                        {columnLabel(day)}
                      </th>
                    ))}
                    <th className="est-remove" aria-label="Remove" />
                  </tr>
                </thead>
                <tbody>
                  {draft.rows.map((row, index) => (
                    <tr key={row.key}>
                      <td className="est-fixed est-no">{index + 1}</td>
                      <td className="est-fixed est-code">
                        <select
                          aria-label={`Code of row ${index + 1}`}
                          value={row.code ? `${row.code}|${row.role}` : ''}
                          onChange={(event) => {
                            const [code = '', role = ''] = event.target.value
                              ? event.target.value.split('|')
                              : [];
                            changeRow(row.key, { code, role });
                          }}
                        >
                          <option value="">Select code</option>
                          {codes.map(({ code, role }) => (
                            <option key={`${code}|${role}`} value={`${code}|${role}`}>
                              {code} — {role}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="est-fixed est-role">{row.role || '—'}</td>
                      <td className="est-fixed est-total">{formatHours(rowTotal(row.hours, dates))}</td>
                      {dates.map((day) => {
                        const value = row.hours[day] ?? '';
                        const wrong = value !== '' && (hoursOf(value) < 0 || hoursOf(value) > mostPerCell);
                        return (
                          <td key={day} className="est-day">
                            <input
                              type="number"
                              min="0"
                              step="0.5"
                              inputMode="decimal"
                              aria-label={`Hours of row ${index + 1} on ${columnLabel(day)}`}
                              aria-invalid={wrong || undefined}
                              value={value}
                              onChange={(event) => setHours(row.key, day, event.target.value)}
                            />
                          </td>
                        );
                      })}
                      <td className="est-remove">
                        <button
                          type="button"
                          className="wbs-icon-btn wbs-icon-delete"
                          aria-label={`Remove row ${index + 1}`}
                          title="Remove row"
                          onClick={() => change({ rows: draft.rows.filter((item) => item.key !== row.key) })}
                        >
                          <Trash2 size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td className="est-fixed est-no" />
                    <td className="est-fixed est-code">Total</td>
                    <td className="est-fixed est-role" />
                    <td className="est-fixed est-total">{formatHours(grandTotal)}</td>
                    {totals.map((value, index) => (
                      <td key={dates[index]} className="est-day">
                        {formatHours(value)}
                      </td>
                    ))}
                    <td className="est-remove" />
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          <div className="estimation-footer">
            <button
              type="button"
              className="button button-secondary"
              onClick={() => change({ rows: [...draft.rows, newRow()] })}
            >
              <Plus size={15} /> Add row
            </button>
            <ErrorBanner error={problem || save.error} />
          </div>
        </div>
      </section>

      {pendingSwitch !== undefined && (
        <ConfirmDialog
          title="Discard unsaved changes?"
          confirmLabel="Discard"
          onConfirm={() => {
            open(pendingSwitch);
            setPendingSwitch(undefined);
          }}
          onCancel={() => setPendingSwitch(undefined)}
        >
          <p className="confirm-modal-text">The changes to this estimation are not saved yet.</p>
        </ConfirmDialog>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title={`Delete "${pendingDelete.name}"?`}
          confirmLabel="Delete"
          busyLabel="Deleting…"
          busy={remove.isPending}
          error={remove.error}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        >
          <p className="confirm-modal-text">This cannot be undone.</p>
        </ConfirmDialog>
      )}
    </main>
  );
}
