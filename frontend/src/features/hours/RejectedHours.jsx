import { useState } from 'react';
import { ErrorBanner } from '../../components/Feedback';
import { useReapproveHours, useRejectedHours } from '../../hooks/useRejectedHours';
import { describeTimeLeft } from '../../utils/hours';

const dayLabel = (isoDate) =>
  new Date(`${isoDate}T00:00:00`).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  });

/**
 * Rejected hours on a project that can still be approved again: by any of its leads or the
 * BU Head, within seven days of the rejection, with a reason. Hours stay on the subtask they
 * were logged on. Shows nothing when there are none.
 */
export function RejectedHoursPanel({ projectId, onChanged }) {
  const { data: rows = [], error } = useRejectedHours(projectId);
  const reapprove = useReapproveHours(projectId);
  const [open, setOpen] = useState(null); // { id, attendedOnly, reason } while a reason is being typed

  if (!error && rows.length === 0) return null;

  const submit = (event) => {
    event.preventDefault();
    reapprove.mutate(
      { id: open.id, reason: open.reason.trim(), attendedOnly: open.attendedOnly },
      {
        onSuccess: () => {
          setOpen(null);
          onChanged?.();
        },
      },
    );
  };

  return (
    <section className="rejected-panel" aria-label="Rejected hours">
      <h3>Rejected hours</h3>
      <p className="rejected-hint">
        Any lead of the project can approve these again within 7 days of the rejection, with a reason. After
        that the rejection is final. Hours the BU Head rejected are approved again only by the BU Head.
      </p>
      <ErrorBanner error={error || reapprove.error} />
      <ul className="rejected-list">
        {rows.map((row) => (
          <li key={row.id}>
            <span className="rejected-text">
              <strong>{row.employee_name}</strong>: {row.hours} h on {dayLabel(row.work_date)},{' '}
              {[row.wbs_code, row.task_name].filter(Boolean).join(' ')}
              <small>
                Rejected by {row.rejected_by || 'a reviewer'}
                {row.reason ? `: ${row.reason}` : ''}
              </small>
              <small>
                {row.clock_paused ? 'Project locked: the 7 days are paused. ' : ''}
                {describeTimeLeft(row.hours_left)}
                {row.unattended ? ` Unattended: ${row.attended_hours} h up to the last visit.` : ''}
              </small>
            </span>
            {row.can_reapprove && open?.id !== row.id && (
              <span className="review-actions">
                <button
                  type="button"
                  className="review-btn review-approve"
                  onClick={() => setOpen({ id: row.id, attendedOnly: false, reason: '' })}
                >
                  Approve
                </button>
                {row.unattended && (
                  <button
                    type="button"
                    className="review-btn review-approve"
                    onClick={() => setOpen({ id: row.id, attendedOnly: true, reason: '' })}
                  >
                    Approve up to last visit ({row.attended_hours} h)
                  </button>
                )}
              </span>
            )}
            {open?.id === row.id && (
              <form className="rejected-form" onSubmit={submit}>
                <input
                  aria-label="Reason for approving rejected hours"
                  placeholder="Why should these hours count? (required)"
                  maxLength={500}
                  value={open.reason}
                  onChange={(event) => setOpen({ ...open, reason: event.target.value })}
                />
                <button
                  type="submit"
                  className="review-btn review-approve"
                  disabled={!open.reason.trim() || reapprove.isPending}
                >
                  {open.attendedOnly ? `Approve ${row.attended_hours} h` : `Approve ${row.hours} h`}
                </button>
                <button type="button" className="review-btn" onClick={() => setOpen(null)}>
                  Cancel
                </button>
              </form>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
