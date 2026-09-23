import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { ErrorBanner } from '../../../components/Feedback';
import { useDecideExtension, useStopExecution } from '../../../hooks/useGovernance';
import { formatDateTime, formatHours, formatPercent } from '../../../utils/format';

function ThresholdAlert({ data }) {
  if (!data) {
    return (
      <Alert ok title="No project selected">
        Governance controls will be available after selecting a project.
      </Alert>
    );
  }
  const { governance_status: governance, exceptions } = data;
  const threshold = governance.threshold_pct;
  if (threshold === null || threshold === undefined) {
    return (
      <Alert title="Threshold Not Configured">
        Consumption is {formatPercent(governance.consumption_pct)}; no project governance threshold is
        configured.
      </Alert>
    );
  }
  if (governance.status === 'exceeded') {
    return (
      <Alert title="Threshold Action Required">
        {exceptions
          .map(
            (exception) =>
              `${exception.discipline} is at ${formatPercent(exception.consumption_pct)} against the ${formatPercent(exception.threshold_pct)} threshold`,
          )
          .join(' ')}
      </Alert>
    );
  }
  return (
    <Alert ok title="Within Threshold">
      Current consumption is {formatPercent(governance.consumption_pct)} against the{' '}
      {formatPercent(threshold)} threshold.
    </Alert>
  );
}

function Alert({ ok = false, title, children }) {
  const Icon = ok ? ShieldCheck : AlertTriangle;
  return (
    <div className={`ed-alert${ok ? ' ed-alert-ok' : ''}`}>
      <Icon size={16} />
      <div>
        <strong>{title}</strong>
        <p>{children}</p>
      </div>
    </div>
  );
}

function PendingRequest({ request, projectName }) {
  const details = [
    ['Requested additional hours', formatHours(request.requested_hours)],
    ['Requesting Lead', request.requested_by || 'Not available'],
    ['Project', request.project_name || projectName],
    ['Request date/time', formatDateTime(request.requested_at)],
    ['Current status', request.status_label],
    ['Lead justification', request.justification || 'No justification provided'],
  ];
  return (
    <div className="ed-request-review">
      <div className="ed-request-review-header">
        <h3>Extension Request</h3>
        <span className="ed-status-pill ed-status-pending">{request.status_label}</span>
      </div>
      <dl className="ed-request-details">
        {details.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** BU Head actions: review the pending extension request, approve/reject it, or stop execution. */
export function GovernanceControls({ projectId, projectName, data }) {
  const [comments, setComments] = useState('');
  const decide = useDecideExtension(projectId);
  const stop = useStopExecution(projectId);
  const pendingRequest = data?.extension_requests?.find((request) => request.status === 'pending') ?? null;
  const busy = decide.isPending || stop.isPending;
  const actionError = decide.error || stop.error;

  const clearComments = { onSuccess: () => setComments('') };

  function handleDecision(decision) {
    stop.reset();
    decide.mutate(
      { requestId: pendingRequest.id, decision, comments: comments.trim() || null },
      clearComments,
    );
  }

  function handleStop() {
    decide.reset();
    stop.mutate(
      { comments: comments.trim(), discipline: data?.exceptions?.[0]?.discipline ?? null },
      clearComments,
    );
  }

  return (
    <section className="allocation-card ed-controls-panel">
      <div className="allocation-header">
        <div>
          <h2>BU Head Governance Controls</h2>
          <p>Review extension requests, approve or reject them, or halt execution.</p>
        </div>
      </div>

      <ThresholdAlert data={data} />

      {pendingRequest && <PendingRequest request={pendingRequest} projectName={projectName} />}
      {data && !pendingRequest && (
        <div className="ed-request-review ed-request-review-empty">
          <h3>Extension Requests</h3>
          <p>No pending extension request for this project.</p>
        </div>
      )}

      <label className="ed-field-label" htmlFor="ed-comments">
        BU Head Decision Comments / Justification{' '}
        <span className="ed-optional-label">(optional for extension decisions)</span>
      </label>
      <textarea
        id="ed-comments"
        className="ed-comments"
        placeholder="Enter comments for the selected governance action"
        value={comments}
        onChange={(event) => setComments(event.target.value)}
        disabled={!projectId || busy}
      />

      <div className="ed-buttons">
        <button
          type="button"
          className="ed-btn ed-btn-stop"
          disabled={!projectId || !comments.trim() || busy}
          onClick={handleStop}
        >
          {stop.isPending ? 'Stopping…' : 'Stop the Execution'}
        </button>
        <button
          type="button"
          className="ed-btn ed-btn-approve"
          disabled={!pendingRequest || busy}
          onClick={() => handleDecision('approve')}
        >
          {decide.isPending && decide.variables?.decision === 'approve' ? 'Approving…' : 'Approve Extension'}
        </button>
        <button
          type="button"
          className="ed-btn ed-btn-reject"
          disabled={!pendingRequest || busy}
          onClick={() => handleDecision('reject')}
        >
          {decide.isPending && decide.variables?.decision === 'reject' ? 'Rejecting…' : 'Reject Extension'}
        </button>
      </div>
      <ErrorBanner error={actionError} />
    </section>
  );
}
