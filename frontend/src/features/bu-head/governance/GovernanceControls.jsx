import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { ErrorBanner } from '../../../components/Feedback';
import { useDecideExtension, useResumeExecution, useStopExecution } from '../../../hooks/useGovernance';
import { formatDateTime, formatHours, formatPercent } from '../../../utils/format';

function ThresholdAlert({ data }) {
  if (!data) {
    return (
      <Alert ok title="No project selected">
        Governance controls will be available after selecting a project.
      </Alert>
    );
  }
  const governance = data.governance_status;
  const usage = `${formatHours(governance.approved_hours)} of ${formatHours(governance.baseline_hours)} baseline hours approved (${formatPercent(governance.consumption_pct)})`;
  if (!governance.configured) {
    return (
      <Alert title="Baseline Not Configured">
        Set the project's target effort hours to enable threshold alerts and the automatic lock.
      </Alert>
    );
  }
  if (governance.soft_locked) {
    return (
      <Alert
        title={governance.lock_reason === 'auto' ? 'Timesheets Locked Automatically' : 'Execution Stopped'}
      >
        {usage}. Approve an extension or resume execution to reopen timesheets.
      </Alert>
    );
  }
  if (governance.level === 'hard_stop') {
    return <Alert title="Baseline Exceeded — Execution Resumed">{usage}.</Alert>;
  }
  if (governance.level === 'warning') {
    return (
      <Alert title="Alert Threshold Reached">
        {usage}, above the {formatPercent(governance.threshold_pct)} alert threshold. Timesheets lock
        automatically at 100%.
      </Alert>
    );
  }
  const threshold =
    governance.threshold_pct == null
      ? 'No alert threshold is configured'
      : `Alert threshold ${formatPercent(governance.threshold_pct)}`;
  return (
    <Alert ok title="Within Threshold">
      {usage}. {threshold}; timesheets lock automatically at 100%.
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

/** BU Head actions: review the pending extension request, approve/reject it, stop or resume execution. */
export function GovernanceControls({ projectId, projectName, data }) {
  const [comments, setComments] = useState('');
  const decide = useDecideExtension(projectId);
  const stop = useStopExecution(projectId);
  const resume = useResumeExecution(projectId);
  const pendingRequest = data?.extension_requests?.find((request) => request.status === 'pending') ?? null;
  const locked = Boolean(data?.governance_status?.soft_locked);
  const mutations = [decide, stop, resume];
  const busy = mutations.some((mutation) => mutation.isPending);
  const actionError = decide.error || stop.error || resume.error;

  const clearComments = { onSuccess: () => setComments('') };

  /** Clear the other actions' errors so only the latest action's outcome is shown. */
  function resetOthers(active) {
    mutations.filter((mutation) => mutation !== active).forEach((mutation) => mutation.reset());
  }

  function handleDecision(decision) {
    resetOthers(decide);
    decide.mutate(
      { requestId: pendingRequest.id, decision, comments: comments.trim() || null },
      clearComments,
    );
  }

  function handleStop() {
    resetOthers(stop);
    stop.mutate(
      { comments: comments.trim(), discipline: data?.exceptions?.[0]?.discipline ?? null },
      clearComments,
    );
  }

  function handleResume() {
    resetOthers(resume);
    resume.mutate({ comments: comments.trim() || null }, clearComments);
  }

  return (
    <section className="allocation-card ed-controls-panel">
      <div className="allocation-header">
        <div>
          <h2>BU Head Governance Controls</h2>
          <p>Review extension requests, approve or reject them, or stop and resume execution.</p>
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
        <span className="ed-optional-label">(required to stop execution)</span>
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
        {locked ? (
          <button type="button" className="ed-btn ed-btn-resume" disabled={busy} onClick={handleResume}>
            {resume.isPending ? 'Resuming…' : 'Resume Execution'}
          </button>
        ) : (
          <button
            type="button"
            className="ed-btn ed-btn-stop"
            disabled={!projectId || !comments.trim() || busy}
            onClick={handleStop}
          >
            {stop.isPending ? 'Stopping…' : 'Stop the Execution'}
          </button>
        )}
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
