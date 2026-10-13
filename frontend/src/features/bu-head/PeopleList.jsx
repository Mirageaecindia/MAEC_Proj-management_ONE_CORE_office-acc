import { useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ErrorBanner } from '../../components/Feedback';
import { useChangeRole, usePeople, useUpdatePerson } from '../../hooks/usePeople';

// Whether someone may sign in is MAEC One's to decide; a profile deactivated here before
// the move stays deactivated.
function statusOf(person) {
  return person.is_active ? ['Active', 'status-approved'] : ['Deactivated', 'status-none'];
}

const matches = (person, query) =>
  [person.full_name, person.username, person.employee_code, person.job_role].some((value) =>
    (value || '').toLowerCase().includes(query),
  );

/** One person's row, or their edit form. */
function PersonRow({ person, onChangeRole }) {
  const update = useUpdatePerson();
  const [editing, setEditing] = useState(null); // { full_name, job_role } while editing
  const [status, pill] = statusOf(person);
  const busy = update.isPending;

  if (editing) {
    const save = (event) => {
      event.preventDefault();
      update.mutate({ id: person.id, ...editing }, { onSuccess: () => setEditing(null) });
    };
    return (
      <tr className="people-editing">
        <td colSpan={6}>
          <form className="people-edit-form" onSubmit={save}>
            <label>
              <span>Name</span>
              <input
                value={editing.full_name}
                onChange={(event) => setEditing({ ...editing, full_name: event.target.value })}
              />
            </label>
            <label>
              <span>Job role</span>
              <input
                value={editing.job_role}
                onChange={(event) => setEditing({ ...editing, job_role: event.target.value })}
              />
            </label>
            <span className="review-actions">
              <button type="submit" className="review-btn review-approve" disabled={busy}>
                {update.isPending ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="review-btn" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </span>
            <ErrorBanner error={update.error} />
          </form>
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>
        <strong>{person.full_name || '—'}</strong>
        {person.role === 'bu_head' && <small className="people-role"> BU Head</small>}
      </td>
      <td>{person.username}</td>
      <td>{person.employee_code || '—'}</td>
      <td>{person.job_role || '—'}</td>
      <td>
        <span className={`approval-pill ${pill}`}>{status}</span>
      </td>
      <td>
        {person.can_remove_bu_head && (
          <span className="review-actions">
            <button type="button" className="review-btn" onClick={() => onChangeRole(person, false)}>
              Remove BU Head
            </button>
          </span>
        )}
        {person.can_edit && (
          <span className="review-actions">
            {person.can_make_bu_head && (
              <button
                type="button"
                className="review-btn"
                disabled={busy}
                onClick={() => onChangeRole(person, true)}
              >
                Make BU Head
              </button>
            )}
            <button
              type="button"
              className="review-btn"
              disabled={busy}
              onClick={() =>
                setEditing({
                  full_name: person.full_name || '',
                  job_role: person.job_role || '',
                })
              }
            >
              Edit
            </button>
          </span>
        )}
      </td>
    </tr>
  );
}

/**
 * Everyone with a profile. The BU Head corrects an engineer's name or job role, and makes
 * or unmakes a BU Head. The work email is who the person is in MAEC One: not edited here.
 */
export function PeopleList() {
  const { data: people = [], error, isLoading } = usePeople();
  const [query, setQuery] = useState('');
  const changeRole = useChangeRole();
  const [roleChange, setRoleChange] = useState(null); // { person, makeBuHead }

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? people.filter((person) => matches(person, needle)) : people;
  }, [people, query]);

  return (
    <div className="people-list">
      <h3>People in the app</h3>
      <div className="people-row">
        <input
          type="search"
          aria-label="Search people"
          placeholder="Search by name, email, employee ID or job role"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="people-count">
          {people.length} profile{people.length === 1 ? '' : 's'}
        </span>
      </div>
      <ErrorBanner error={error} />
      {isLoading ? (
        <p className="people-hint">Loading…</p>
      ) : (
        <div className="resource-table-wrap">
          <table className="resource-table people-table">
            <thead>
              <tr>
                <th>NAME</th>
                <th>WORK EMAIL</th>
                <th>EMPLOYEE ID</th>
                <th>JOB ROLE</th>
                <th>STATUS</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {shown.map((person) => (
                <PersonRow
                  key={person.id}
                  person={person}
                  onChangeRole={(target, makeBuHead) => {
                    changeRole.reset();
                    setRoleChange({ person: target, makeBuHead });
                  }}
                />
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={6} className="timesheet-empty-cell">
                    {people.length ? 'Nobody matches the search.' : 'No profiles yet.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="people-hint">
        A leaver&apos;s access is removed in MAEC One; their bookings and hours stay on record here. Make BU
        Head works only for someone on no live project, as engineer or lead.
      </p>
      {roleChange && (
        <ConfirmDialog
          title={
            roleChange.makeBuHead
              ? `Make ${roleChange.person.full_name || roleChange.person.username} a BU Head?`
              : `Remove the BU Head role from ${roleChange.person.full_name || roleChange.person.username}?`
          }
          tone="primary"
          confirmLabel={roleChange.makeBuHead ? 'Make BU Head' : 'Remove BU Head'}
          busyLabel="Saving…"
          busy={changeRole.isPending}
          error={changeRole.error}
          onConfirm={() =>
            changeRole.mutate(
              { id: roleChange.person.id, makeBuHead: roleChange.makeBuHead },
              { onSuccess: () => setRoleChange(null) },
            )
          }
          onCancel={() => setRoleChange(null)}
        >
          <p className="confirm-modal-subtext">
            {roleChange.makeBuHead
              ? 'A BU Head approves bookings and extensions, sees costs and can stop projects. They no longer lead projects, get booked or log hours. Only someone on no live project can be made a BU Head.'
              : 'They become an engineer again and can be booked and made a lead.'}{' '}
            Their pages follow the new role from their next click. The other BU Heads are notified.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
