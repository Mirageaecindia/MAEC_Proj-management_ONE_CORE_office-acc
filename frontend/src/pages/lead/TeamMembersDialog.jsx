import { useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';

const matches = (employee, needle) =>
  [employee.name, employee.employee_code, employee.role_title, employee.discipline].some((value) =>
    (value || '').toLowerCase().includes(needle),
  );

/**
 * The lead picks their team for the project from everyone in the app. Assign Engineer
 * then lists only these people. Ticks are kept while searching; Save stores the team.
 */
export function TeamMembersDialog({ employees, teamIds, saving, error, onSave, onCancel }) {
  const [picked, setPicked] = useState(() => new Set(teamIds));
  const [query, setQuery] = useState('');
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? employees.filter((employee) => matches(employee, needle)) : employees;
  }, [employees, query]);

  const toggle = (id) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <ConfirmDialog
      title="Team Members"
      tone="primary"
      confirmLabel="Save team"
      busyLabel="Saving…"
      busy={saving}
      error={error}
      onConfirm={() => onSave([...picked])}
      onCancel={onCancel}
    >
      <p className="confirm-modal-subtext">
        Pick the people you work with on this project. <strong>Assign Engineer</strong> lists only them.
      </p>
      <div className="team-picker-bar">
        <input
          type="search"
          aria-label="Search people"
          placeholder="Search by name, employee ID or job role"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="team-picker-count">{picked.size} in the team</span>
      </div>
      <ul className="team-picker-list">
        {shown.map((employee) => (
          <li key={employee.id}>
            <label>
              <input type="checkbox" checked={picked.has(employee.id)} onChange={() => toggle(employee.id)} />
              <span>
                <strong>{employee.name}</strong>
                {employee.employee_code ? ` (${employee.employee_code})` : ''}
                <small>{employee.role_title || employee.discipline || ''}</small>
              </span>
            </label>
          </li>
        ))}
        {shown.length === 0 && <li className="team-picker-empty">Nobody matches the search.</li>}
      </ul>
    </ConfirmDialog>
  );
}
