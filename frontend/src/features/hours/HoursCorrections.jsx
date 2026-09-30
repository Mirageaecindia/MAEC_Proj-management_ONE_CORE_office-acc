import { useState } from 'react';
import { ErrorBanner } from '../../components/Feedback';
import { useCorrections, useDecideCorrection, useProposeCorrection } from '../../hooks/useCorrections';
import { describeCorrection } from '../../utils/hours';

const STATUS_LABELS = { pending: 'Waiting', approved: 'Moved', rejected: 'Refused', cancelled: 'Withdrawn' };
const STATUS_PILL = {
  pending: 'status-pending',
  approved: 'status-approved',
  rejected: 'status-rejected',
  cancelled: 'status-none',
};
const RECENT_SHOWN = 5;

/**
 * Corrections on a project: hours an engineer asked to move to another of their subtasks.
 * The lead of the task the hours move to decides (the BU Head for a lead's own hours).
 * Shows what is waiting, then the latest decisions; nothing at all when there are none.
 */
export function CorrectionsPanel({ projectId, onChanged }) {
  const { data: corrections = [], error } = useCorrections(projectId);
  const decide = useDecideCorrection(projectId);

  const pending = corrections.filter((correction) => correction.status === 'pending');
  const recent = corrections.filter((correction) => correction.status !== 'pending').slice(0, RECENT_SHOWN);
  if (!error && corrections.length === 0) return null;

  const act = (correction, action) =>
    decide.mutate({ id: correction.id, action }, { onSuccess: () => onChanged?.() });

  return (
    <section className="corrections-panel" aria-label="Corrections">
      <h3>Corrections</h3>
      <p className="corrections-hint">
        Hours logged on the wrong subtask. A correction only moves hours between an engineer&apos;s subtasks:
        the day&apos;s total stays the same.
      </p>
      <ErrorBanner error={error || decide.error} />
      <ul className="corrections-list">
        {[...pending, ...recent].map((correction) => (
          <li key={correction.id}>
            <span className={`approval-pill ${STATUS_PILL[correction.status] || 'status-none'}`}>
              {STATUS_LABELS[correction.status] || correction.status}
            </span>
            <span className="corrections-text">
              <strong>{correction.employee_name}</strong>: {describeCorrection(correction)}
              {correction.note && <small>“{correction.note}”</small>}
              {correction.status === 'pending' && correction.source_status === 'rejected' && (
                <small>
                  These hours were rejected on the source subtask
                  {correction.source_review_reason ? `: ${correction.source_review_reason}` : ''}.
                </small>
              )}
              {correction.decided_by && (
                <small>
                  by {correction.decided_by}
                  {correction.decision_reason ? `: ${correction.decision_reason}` : ''}
                </small>
              )}
            </span>
            {correction.can_decide && (
              <span className="review-actions">
                <button
                  type="button"
                  className="review-btn review-approve"
                  disabled={decide.isPending}
                  onClick={() => act(correction, 'approve')}
                >
                  Move the hours
                </button>
                <button
                  type="button"
                  className="review-btn review-reject"
                  disabled={decide.isPending}
                  onClick={() => act(correction, 'reject')}
                >
                  Refuse
                </button>
              </span>
            )}
            {correction.can_cancel && (
              <span className="review-actions">
                <button
                  type="button"
                  className="review-btn"
                  disabled={decide.isPending}
                  onClick={() => act(correction, 'cancel')}
                >
                  Withdraw
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * The engineer's form on one of their own day rows: move some of its hours to another of
 * their subtasks. `subtasks` are the possible targets.
 */
export function MoveHoursForm({ entry, subtasks, onDone, onCancel }) {
  const propose = useProposeCorrection(entry.project_id);
  const [hours, setHours] = useState(String(entry.hours));
  const [target, setTarget] = useState('');
  const [note, setNote] = useState('');

  const amount = Number(hours);
  const valid = target && amount > 0 && amount <= entry.hours;

  const submit = (event) => {
    event.preventDefault();
    propose.mutate(
      {
        work_date: entry.work_date,
        from_task_id: entry.task_id,
        to_task_id: Number(target),
        hours: amount,
        note: note.trim() || null,
      },
      { onSuccess: () => onDone?.() },
    );
  };

  if (subtasks.length === 0) {
    return (
      <span className="move-hours-form">
        <small className="review-progress">You have no other subtask on this project to move hours to.</small>
        <button type="button" className="review-btn" onClick={onCancel}>
          Close
        </button>
      </span>
    );
  }

  return (
    <form className="move-hours-form" onSubmit={submit}>
      <label>
        <span>Hours to move</span>
        <input
          type="number"
          min="0.01"
          max={entry.hours}
          step="0.01"
          value={hours}
          onChange={(event) => setHours(event.target.value)}
        />
      </label>
      <label>
        <span>To subtask</span>
        <select value={target} onChange={(event) => setTarget(event.target.value)}>
          <option value="">Choose…</option>
          {subtasks.map((subtask) => (
            <option key={subtask.id} value={subtask.id}>
              {[subtask.wbs_code, subtask.task_name].filter(Boolean).join(' ')}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Note (optional)</span>
        <input
          type="text"
          maxLength={500}
          placeholder="e.g. switched subtask at 14:00"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <ErrorBanner error={propose.error} />
      <span className="review-actions">
        <button type="submit" className="review-btn review-approve" disabled={!valid || propose.isPending}>
          {propose.isPending ? 'Sending…' : 'Ask to move'}
        </button>
        <button type="button" className="review-btn" onClick={onCancel}>
          Cancel
        </button>
      </span>
    </form>
  );
}
