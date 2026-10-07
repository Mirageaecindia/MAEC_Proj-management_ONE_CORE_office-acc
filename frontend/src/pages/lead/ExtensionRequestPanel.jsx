import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { ErrorBanner } from '../../components/Feedback';
import { useRequestExtension } from '../../hooks/useGovernance';
import { formatDateTime, formatHours, formatPercent } from '../../utils/format';

/** The lead's governance panel: where the project stands against its threshold, and a request for more hours. */
export function ExtensionRequestPanel({ projectId, data }) {
  const [hours, setHours] = useState('');
  const [justification, setJustification] = useState('');
  const request = useRequestExtension(projectId);
  const governance = data?.governance_status;
  const latest = data?.extension_requests?.[0] ?? null;
  const pending = Boolean(data?.current_extension_request);
  const exceeded = governance?.status === 'exceeded';
  const valid = Number(hours) > 0;

  const submit = () =>
    request.mutate(
      { requestedHours: Number(hours), justification: justification.trim() },
      {
        onSuccess: () => {
          setHours('');
          setJustification('');
        },
      },
    );

  let standing = '';
  if (governance && exceeded) {
    standing = data.exceptions
      .map((e) => `${e.discipline} is at ${formatPercent(e.consumption_pct)} of the ${formatPercent(e.threshold_pct)} threshold.`)
      .join(' ');
  } else if (governance) {
    standing =
      governance.threshold_pct == null
        ? `Consumption is ${formatPercent(governance.consumption_pct)}; no threshold is set.`
        : `Consumption is ${formatPercent(governance.consumption_pct)} against the ${formatPercent(governance.threshold_pct)} threshold.`;
  }

  return (
    <section className="allocation-card ed-controls-panel">
      <div className="allocation-header">
        <div>
          <h2>Lead Action</h2>
          <p>Where the project stands against its threshold, and a request for more hours.</p>
        </div>
      </div>

      {governance && (
        <div className={exceeded ? 'ed-alert' : 'ed-alert ed-alert-ok'}>
          {exceeded ? <AlertTriangle size={16} /> : <ShieldCheck size={16} />}
          <div>
            <strong>{exceeded ? 'Threshold Action Required' : 'Within Threshold'}</strong>
            <p>{standing}</p>
          </div>
        </div>
      )}

      <div className={latest ? 'ed-request-status' : 'ed-request-status ed-request-status-empty'}>
        <span>Current request status</span>
        <strong>{latest ? latest.status_label : 'No extension request submitted'}</strong>
        {latest && (
          <>
            <span>
              Requested {formatHours(latest.requested_hours)} · {formatDateTime(latest.requested_at)}
            </span>
            {latest.decided_at && (
              <span>
                Decided {formatDateTime(latest.decided_at)}
                {latest.decided_by ? ` by ${latest.decided_by}` : ''}
              </span>
            )}
            {latest.decision_comments && <span>{latest.decision_comments}</span>}
          </>
        )}
      </div>

      <label className="ed-field-label" htmlFor="lead-extension-hours">
        Request to Extend Limit <span className="required-asterisk">*</span>
      </label>
      <div className="ed-hours-input">
        <input
          id="lead-extension-hours"
          type="number"
          min="1"
          step="1"
          placeholder="Enter additional hours"
          value={hours}
          onChange={(event) => setHours(event.target.value)}
          disabled={!projectId || pending || request.isPending}
        />
        <span>Hours</span>
      </div>
      <label className="ed-field-label" htmlFor="lead-extension-justification">
        Justification / Comment <span className="ed-optional-label">(optional)</span>
      </label>
      <textarea
        id="lead-extension-justification"
        className="ed-comments"
        placeholder="Why the project needs more hours"
        value={justification}
        onChange={(event) => setJustification(event.target.value)}
        disabled={!projectId || pending || request.isPending}
      />
      <button
        type="button"
        className="ed-btn ed-btn-submit"
        disabled={!projectId || !valid || pending || request.isPending}
        onClick={submit}
      >
        {request.isPending ? 'Submitting…' : pending ? 'A request is waiting for the BU Head' : 'Submit for Approval'}
      </button>
      <ErrorBanner error={request.error} />
    </section>
  );
}
