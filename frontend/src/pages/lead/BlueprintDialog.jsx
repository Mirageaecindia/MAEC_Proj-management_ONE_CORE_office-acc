import { useMutation, useQuery } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { wbsBlueprintsApi } from '../../api/wbsBlueprints';
import { ErrorBanner } from '../../components/Feedback';

/**
 * "+" on a phase card: what the phase's blueprint would add, and what is already there.
 * Nothing there yet: add it. Some or all of it there: add only what is missing, or the whole
 * list again as a second copy at the bottom of the phase. `onAdded(result)` gets the new ids.
 */
export function BlueprintDialog({ projectId, blueprintKey, phase, onAdded, onCancel }) {
  const preview = useQuery({
    queryKey: ['wbs-blueprint-preview', String(projectId), blueprintKey],
    queryFn: () => wbsBlueprintsApi.preview(projectId, blueprintKey),
    staleTime: 0,
  });
  const add = useMutation({
    mutationFn: (again) => wbsBlueprintsApi.add(projectId, blueprintKey, again),
    onSuccess: onAdded,
  });
  const p = preview.data;
  const total = p ? p.tasks + p.subtasks : 0;
  const present = p ? p.present_tasks + p.present_subtasks : 0;
  const busy = add.isPending;

  return (
    <div className="modal-backdrop" role="presentation">
      <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="blueprint-dialog-title">
        <div className="modal-heading">
          <h2 id="blueprint-dialog-title">Add the {phase} blueprint?</h2>
          <button type="button" aria-label="Close" disabled={busy} onClick={onCancel}>
            <X size={18} />
          </button>
        </div>
        <div className="confirm-modal-body">
          {!p ? (
            <p className="confirm-modal-text">Checking what is already in the project…</p>
          ) : present === 0 ? (
            <p className="confirm-modal-text">
              {p.tasks} tasks and {p.subtasks} subtasks from the standard {phase} list.
            </p>
          ) : (
            <>
              <p className="confirm-modal-text">
                {p.present_tasks} tasks and {p.present_subtasks} subtasks of the standard {phase} list are already in
                the project{p.missing ? `; ${p.missing} are missing` : ''}.
              </p>
              <p className="confirm-modal-subtext">
                <strong>Add all again</strong> adds a second copy of all {total} at the bottom of {phase}, each
                marked with the line it repeats, for you to keep or undo.
              </p>
            </>
          )}
          <p className="confirm-modal-subtext">
            Engineers, dates and hours are set afterwards. To add one task by hand, click the phase name instead.
          </p>
          <ErrorBanner error={preview.error || add.error} />
        </div>
        <div className="modal-actions">
          <button className="button button-secondary" type="button" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
          {p && present > 0 && p.missing > 0 && (
            <button className="button button-secondary" type="button" disabled={busy} onClick={() => add.mutate(false)}>
              Add the {p.missing} missing
            </button>
          )}
          {p && (
            <button
              className="button button-primary"
              type="button"
              disabled={busy}
              onClick={() => add.mutate(present > 0)}
            >
              {busy ? 'Adding…' : present > 0 ? `Add all ${total} again` : 'Add tasks'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
