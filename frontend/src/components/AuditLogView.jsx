import { Download } from 'lucide-react';
import { useState } from 'react';
import { auditApi } from '../api/audit';
import { useAuditLog } from '../hooks/useAudit';
import { formatDateTime } from '../utils/format';
import { ErrorBanner } from './Feedback';

const AUDIT_CATEGORIES = [
  ['account', 'Account'],
  ['people', 'People'],
  ['project', 'Projects'],
  ['booking', 'Bookings & team'],
  ['wbs', 'WBS'],
  ['time', 'Login / Logout'],
  ['hours', 'Hours review'],
  ['governance', 'Governance'],
];
const CATEGORY_LABEL = Object.fromEntries(AUDIT_CATEGORIES);
const ROLE_LABEL = { bu_head: 'BU Head', engineer: 'Engineer' };
const PAGE = 50;

function downloadCsv(text) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'promanage-audit-log.csv';
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * The audit log as a filtered, paged table. `everyone`: all people's entries with a
 * person filter, search and CSV download (BU Head); otherwise the viewer's own.
 */
export function AuditLogView({ everyone = false, people = [], projects = [], initialUserId = '' }) {
  const [filters, setFilters] = useState({
    user_id: initialUserId,
    project_id: '',
    category: '',
    date_from: '',
    date_to: '',
    q: '',
    offset: 0,
  });
  const request = { ...filters, limit: PAGE, ...(everyone ? {} : { user_id: undefined, q: undefined }) };
  const { data, error, isLoading, isPlaceholderData } = useAuditLog(request, { everyone });
  const [exportError, setExportError] = useState(null);
  const set = (field) => (event) => setFilters({ ...filters, [field]: event.target.value, offset: 0 });

  const events = data?.events ?? [];
  const total = data?.total ?? 0;
  const first = total ? filters.offset + 1 : 0;
  const last = Math.min(filters.offset + PAGE, total);

  const exportCsv = async () => {
    setExportError(null);
    try {
      downloadCsv(await auditApi.exportCsv(request));
    } catch (err) {
      setExportError(err);
    }
  };

  return (
    <section className="allocation-card audit-card">
      <div className="audit-filters">
        {everyone && (
          <select aria-label="Person" value={filters.user_id} onChange={set('user_id')}>
            <option value="">Everyone</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name || person.username}
                {person.role === 'bu_head' ? ' (BU Head)' : ''}
              </option>
            ))}
          </select>
        )}
        <select aria-label="Project" value={filters.project_id} onChange={set('project_id')}>
          <option value="">All projects</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.project_name}
            </option>
          ))}
        </select>
        <select aria-label="Type" value={filters.category} onChange={set('category')}>
          <option value="">All types</option>
          {AUDIT_CATEGORIES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label className="audit-date">
          <span>From</span>
          <input type="date" aria-label="From" value={filters.date_from} onChange={set('date_from')} />
        </label>
        <label className="audit-date">
          <span>To</span>
          <input type="date" aria-label="To" value={filters.date_to} onChange={set('date_to')} />
        </label>
        {everyone && (
          <input
            type="search"
            aria-label="Search the log"
            placeholder="Search names and actions"
            value={filters.q}
            onChange={set('q')}
          />
        )}
        {everyone && (
          <button type="button" className="button button-secondary" onClick={exportCsv} disabled={!total}>
            <Download size={15} /> Download CSV
          </button>
        )}
      </div>
      <ErrorBanner error={error || exportError} />

      <div className={`resource-table-wrap${isPlaceholderData ? ' is-refreshing' : ''}`}>
        <table className="resource-table audit-table">
          <thead>
            <tr>
              <th>WHEN</th>
              {everyone && <th>PERSON</th>}
              <th>TYPE</th>
              <th>ACTION</th>
              <th>PROJECT</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.id}>
                <td className="audit-when">{formatDateTime(event.at)}</td>
                {everyone && (
                  <td>
                    <strong>{event.user_name}</strong>
                    <small> {ROLE_LABEL[event.user_role] || event.user_role}</small>
                  </td>
                )}
                <td>
                  <span className="audit-type">{CATEGORY_LABEL[event.category] || event.category}</span>
                </td>
                <td className="audit-summary">{event.summary}</td>
                <td>{event.project_name || '—'}</td>
              </tr>
            ))}
            {!isLoading && events.length === 0 && (
              <tr>
                <td colSpan={everyone ? 5 : 4} className="timesheet-empty-cell">
                  Nothing recorded for these filters.
                </td>
              </tr>
            )}
            {isLoading && (
              <tr>
                <td colSpan={everyone ? 5 : 4} className="timesheet-empty-cell">
                  Loading…
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="audit-paging">
        <span>{total ? `${first}–${last} of ${total}` : ''}</span>
        <button
          type="button"
          className="button button-secondary"
          disabled={filters.offset === 0}
          onClick={() => setFilters({ ...filters, offset: Math.max(0, filters.offset - PAGE) })}
        >
          Newer
        </button>
        <button
          type="button"
          className="button button-secondary"
          disabled={last >= total}
          onClick={() => setFilters({ ...filters, offset: filters.offset + PAGE })}
        >
          Older
        </button>
      </div>
    </section>
  );
}
