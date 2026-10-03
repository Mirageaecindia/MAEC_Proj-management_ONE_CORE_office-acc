import { useMemo, useState } from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { ErrorBanner } from '../../components/Feedback';
import { useDeletePerson, usePeople, useSetPersonActive, useUpdatePerson } from '../../hooks/usePeople';

function statusOf(person) {
  if (!person.is_active) return ['Deactivated', 'status-none'];
  if (person.must_change_password) return ['Not signed in yet', 'status-pending'];
  return ['Active', 'status-approved'];
}

const matches = (person, query) =>
  [person.full_name, person.username, person.employee_code, person.job_role].some((value) =>
    (value || '').toLowerCase().includes(query),
  );

/** One person's row, or their edit form. */
function PersonRow({ person, onDelete }) {
  const update = useUpdatePerson();
  const setActive = useSetPersonActive();
  const [editing, setEditing] = useState(null); // { full_name, username, job_role } while editing
  const [status, pill] = statusOf(person);
  const busy = update.isPending || setActive.isPending;

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
              <span>Work email (signs in with)</span>
              <input
                value={editing.username}
                onChange={(event) => setEditing({ ...editing, username: event.target.value })}
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
            {person.username !== editing.username.trim().toLowerCase() && (
              <small className="people-warning">
                They will sign in with the new email from now on: tell them.
              </small>
            )}
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
        {person.can_edit && (
          <span className="review-actions">
            <button
              type="button"
              className="review-btn"
              disabled={busy}
              onClick={() =>
                setEditing({
                  full_name: person.full_name || '',
                  username: person.username,
                  job_role: person.job_role || '',
                })
              }
            >
              Edit
            </button>
            <button
              type="button"
              className={person.is_active ? 'review-btn review-reject' : 'review-btn review-approve'}
              disabled={busy}
              onClick={() => setActive.mutate({ id: person.id, active: !person.is_active })}
            >
              {person.is_active ? 'Deactivate' : 'Reactivate'}
            </button>
            {person.can_delete && (
              <button
                type="button"
                className="review-btn review-reject"
                disabled={busy}
                onClick={() => onDelete(person)}
              >
                Delete
              </button>
            )}
          </span>
        )}
        <ErrorBanner error={setActive.error} />
      </td>
    </tr>
  );
}

/**
 * Everyone with an account (never passwords). The BU Head corrects an engineer's name, work
 * email or job role, deactivates a leaver, and deletes only an account created by mistake.
 */
export function PeopleList() {
  const { data: people = [], error, isLoading } = usePeople();
  const deletePerson = useDeletePerson();
  const [query, setQuery] = useState('');
  const [deleting, setDeleting] = useState(null);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? people.filter((person) => matches(person, needle)) : people;
  }, [people, query]);
  const waiting = people.filter((person) => person.is_active && person.must_change_password).length;

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
          {people.length} account{people.length === 1 ? '' : 's'}
          {waiting > 0 && ` · ${waiting} not signed in yet`}
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
                <PersonRow key={person.id} person={person} onDelete={setDeleting} />
              ))}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={6} className="timesheet-empty-cell">
                    {people.length ? 'Nobody matches the search.' : 'No accounts yet.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="people-hint">
        Deactivate a leaver: they can&apos;t sign in, and their bookings and hours stay on record. Delete is
        offered only for an account with no work on record, such as one imported by mistake.
      </p>
      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.full_name || deleting.username}?`}
          confirmLabel="Delete"
          busyLabel="Deleting…"
          busy={deletePerson.isPending}
          error={deletePerson.error}
          onConfirm={() => deletePerson.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
          onCancel={() => setDeleting(null)}
        >
          <p className="confirm-modal-text">This removes the account and its employee record.</p>
          <p className="confirm-modal-subtext">
            It has no work on record. To bring the person back later, import them again.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}
