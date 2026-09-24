import { AlertTriangle, ArrowRight, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';
import { formatDateTimeIST } from '../../utils/displayTime';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function formatHours(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Not available';
  return `${Number(value).toFixed(1)} Hrs`;
}

function formatPercent(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Not available';
  return `${Number(value).toFixed(1)}%`;
}

function formatValue(value, digits = 1) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Not available';
  return Number(value).toFixed(digits);
}

function formatDate(value) {
  if (!value) return 'Not available';
  return formatDateTimeIST(value, { fallback: 'Not available' });
}

export function ExecutiveDashboardPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { authHeaders } = useAuth();
  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [comments, setComments] = useState('');
  const [actionError, setActionError] = useState('');
  const [submitting, setSubmitting] = useState('');

  const project = projects.find((p) => String(p.id) === String(selectedId));
  const projectId = project?.id;
  const governance = data?.governance_status;
  const threshold = governance?.threshold_pct;
  const isExceeded = governance?.status === 'exceeded';
  const pendingRequest = data?.extension_requests?.find((request) => request.status === 'pending') || null;
  const currency = data?.project?.contract_currency || 'USD';

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error(`Failed to load projects (${response.status})`);
        return response.json();
      })
      .then((list) => {
        setProjects(list);
        const selected = targetProjectId
          ? list.find((item) => item.id === targetProjectId)
          : list.length > 0
            ? list[0]
            : null;
        setSelectedId(selected ? String(selected.id) : '');
      })
      .catch((loadError) => setError(loadError.message));
  }, [authHeaders, targetProjectId]);

  const fetchDashboard = useCallback(async () => {
    if (!projectId) return;
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/executive-dashboard`, {
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`Failed to load dashboard (${response.status})`);
      setData(await response.json());
      setComments('');
      setActionError('');
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [projectId, authHeaders]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const runGovernanceAction = useCallback(
    async (action) => {
      if (!projectId || action !== 'stop-execution' || !comments.trim() || submitting) return;
      setSubmitting(action);
      setActionError('');
      try {
        const exception = data?.exceptions?.[0];
        const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/governance/${action}`, {
          method: 'POST',
          headers: {
            ...authHeaders(),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            comments: comments.trim(),
            discipline: exception ? exception.discipline : null,
          }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || `Action failed (${response.status})`);
        await fetchDashboard();
      } catch (actionErr) {
        setActionError(actionErr.message);
      } finally {
        setSubmitting('');
      }
    },
    [projectId, comments, submitting, authHeaders, data, fetchDashboard],
  );

  const decideExtensionRequest = useCallback(
    async (decision) => {
      if (!projectId || !pendingRequest || submitting) return;
      setSubmitting(`decision-${decision}`);
      setActionError('');
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/projects/${projectId}/extension-requests/${pendingRequest.id}/decision`,
          {
            method: 'POST',
            headers: {
              ...authHeaders(),
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              decision,
              comments: comments.trim() || null,
            }),
          },
        );
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || `Decision failed (${response.status})`);
        setComments('');
        await fetchDashboard();
      } catch (actionErr) {
        setActionError(actionErr.message);
      } finally {
        setSubmitting('');
      }
    },
    [projectId, pendingRequest, submitting, comments, authHeaders, fetchDashboard],
  );

  const money = useMemo(
    () => (value) => {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'Not available';
      return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(Number(value));
    },
    [currency],
  );

  const monthlyData = useMemo(() => data?.monthly_data || [], [data]);

  const maxMonthlyValue = useMemo(() => {
    if (!monthlyData.length) return 1;
    return Math.max(
      1,
      ...monthlyData.flatMap((m) => [m.planned_baseline, m.normal_consumption, m.exceeded_threshold]),
    );
  }, [monthlyData]);

  const hasData = Boolean(data);
  const hasProject = Boolean(project);
  const spikePct = isExceeded ? (governance.max_discipline_pct ?? governance.consumption_pct ?? 0) : 0;

  return (
    <main className="timeline-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Analytics</span>
            <i>/</i>
            <span>Portfolio Performance</span>
            <i>/</i>
            <strong>Executive Governance</strong>
          </div>
          <h1>Executive Dashboard &amp; Governance Controls</h1>
          <p>
            Real-time health monitoring, financial variance, threshold exception tracking, and BU approval
            controls.
          </p>
        </div>

        <label className="project-switcher">
          <span>Project Name</span>
          <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
            <option value="">Select project</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.project_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="resource-error">{error}</div>}

      <section className="ed-summary-cards">
        <div className="ed-card">
          <span className="ed-card-label">Commercial Budget Burn</span>
          <strong className="ed-card-value">
            {hasData ? money(data.commercial_budget_burn.consumed) : 'Not available'}
          </strong>
          <span className="ed-card-sub">
            {hasData
              ? `of ${money(data.commercial_budget_burn.total)} contract value`
              : 'No project selected'}
          </span>
          <div className="ed-progress ed-progress-blue">
            <span
              style={{ width: hasData ? `${Math.min(100, data.commercial_budget_burn.percent)}%` : '0%' }}
            />
          </div>
          <span className="ed-card-foot">
            {hasData ? formatPercent(data.commercial_budget_burn.percent) : 'No project data'}
          </span>
        </div>

        <div className="ed-card">
          <span className="ed-card-label">Total Hours Consumption</span>
          <strong className="ed-card-value">
            {hasData ? formatHours(data.hours_consumption.hours) : 'Not available'}
          </strong>
          <span className="ed-card-sub">
            {hasData ? `(${formatPercent(data.hours_consumption.percent)})` : 'No project selected'}
          </span>
          <div className="ed-progress ed-progress-orange">
            <span style={{ width: hasData ? `${Math.min(100, data.hours_consumption.percent)}%` : '0%' }} />
          </div>
          <span className="ed-card-foot">
            {hasData
              ? `${formatHours(data.hours_consumption.approved)} approved / ${formatHours(data.hours_consumption.pending)} pending of ${formatHours(data.hours_consumption.scheduled)}`
              : 'No project data'}
          </span>
        </div>

        <div className={`ed-card ${isExceeded ? 'ed-card-danger' : 'ed-card-ok'}`}>
          <span className="ed-card-label">Governance Threshold Status</span>
          {hasData && threshold === null ? (
            <>
              <strong className="ed-card-value">NOT CONFIGURED</strong>
              <span className="ed-card-sub">No governance threshold is configured for this project.</span>
            </>
          ) : hasData && isExceeded ? (
            <>
              <strong className="ed-card-value">EXCEEDED ({formatPercent(spikePct)})</strong>
              <span className="ed-card-sub">Threshold: {formatPercent(threshold)}</span>
              {governance.soft_locked && (
                <span className="ed-softlock">Timesheets Soft-Locked for Approval</span>
              )}
            </>
          ) : hasData ? (
            <>
              <strong className="ed-card-value">
                NORMAL <ShieldCheck size={18} className="ed-card-inline-icon" />
              </strong>
              <span className="ed-card-sub">
                Consumption {formatPercent(governance.consumption_pct)} at the {formatPercent(threshold)}{' '}
                threshold
              </span>
              {governance.soft_locked && (
                <span className="ed-softlock">Timesheets Soft-Locked for Approval</span>
              )}
            </>
          ) : (
            <>
              <strong className="ed-card-value">Not available</strong>
              <span className="ed-card-sub">No project selected</span>
            </>
          )}
        </div>

        <div className="ed-card">
          <span className="ed-card-label">Schedule Index (SPI)</span>
          <strong className="ed-card-value ed-spi-value">
            {hasData ? formatValue(data.spi.value, 2) : 'Not available'}
          </strong>
          <span className="ed-card-sub ed-spi-note">{hasData ? data.spi.note : 'No project selected'}</span>
          <div className="ed-progress ed-progress-green">
            <span
              style={{
                width: hasData && data.spi.value !== null ? `${Math.min(100, data.spi.value * 100)}%` : '0%',
              }}
            />
          </div>
        </div>
      </section>

      <div className="ed-two-panels">
        <section className="allocation-card ed-chart-panel">
          <div className="allocation-header">
            <div>
              <h2>Hours Burndown & Budget Consumption by Discipline</h2>
              <p>Planned baseline vs logged consumption per month.</p>
            </div>
          </div>

          {hasData && monthlyData.length > 0 ? (
            <div className="ed-chart ed-chart-vertical">
              <div className="ed-chart-vertical-wrapper">
                <div className="ed-chart-y-axis">
                  {Array.from({ length: 5 }, (_, i) => {
                    const value = Math.round(((maxMonthlyValue * (4 - i)) / 4) * 10) / 10;
                    return (
                      <span key={i} className="ed-chart-y-label">
                        {formatHours(value)}
                      </span>
                    );
                  })}
                </div>
                <div className="ed-chart-plot-area">
                  <div className="ed-chart-bars-grouped" role="img" aria-label="Monthly hours burndown chart">
                    {monthlyData.map((month, monthIndex) => (
                      <div
                        key={month.month}
                        className="ed-chart-month-group"
                        style={{ '--month-index': monthIndex }}
                      >
                        <div className="ed-bar-vertical-wrapper">
                          <div
                            className="ed-bar-vertical ed-bar-vertical-planned"
                            style={{
                              height:
                                maxMonthlyValue > 0
                                  ? `${(month.planned_baseline / maxMonthlyValue) * 100}%`
                                  : '0%',
                            }}
                            title={`Planned Baseline: ${formatHours(month.planned_baseline)}`}
                          />
                        </div>
                        <div className="ed-bar-vertical-wrapper">
                          <div
                            className="ed-bar-vertical ed-bar-vertical-normal"
                            style={{
                              height:
                                maxMonthlyValue > 0
                                  ? `${(month.normal_consumption / maxMonthlyValue) * 100}%`
                                  : '0%',
                            }}
                            title={`Normal Consumption: ${formatHours(month.normal_consumption)}`}
                          />
                        </div>
                        <div className="ed-bar-vertical-wrapper">
                          <div
                            className="ed-bar-vertical ed-bar-vertical-exceeded"
                            style={{
                              height:
                                maxMonthlyValue > 0
                                  ? `${(month.exceeded_threshold / maxMonthlyValue) * 100}%`
                                  : '0%',
                            }}
                            title={`Exceeded Threshold: ${formatHours(month.exceeded_threshold)}`}
                          />
                        </div>
                        <div className="ed-chart-month-label">{month.month_label}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="timesheet-empty-cell ed-chart-empty">
              {hasData
                ? 'No monthly activity on this project yet.'
                : 'No project selected — assign engineers and log hours to populate the burndown chart.'}
            </div>
          )}

          <div className="ed-legend">
            <span>
              <i className="ed-legend-swatch ed-swatch-planned" /> Planned Baseline
            </span>
            <span>
              <i className="ed-legend-swatch ed-swatch-normal" /> Normal Consumption
            </span>
            <span>
              <i className="ed-legend-swatch ed-swatch-exceeded" /> Exceeded Threshold
            </span>
          </div>
        </section>

        <div className="ed-right-col">
          <section className="allocation-card ed-controls-panel">
            <div className="allocation-header">
              <div>
                <h2>BU Head Governance Controls</h2>
                <p>Review extension requests, approve or reject them, or halt execution.</p>
              </div>
            </div>

            {hasData && threshold === null && (
              <div className="ed-alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>Threshold Not Configured</strong>
                  <p>
                    Consumption is {formatPercent(governance.consumption_pct)}; no project governance
                    threshold is configured.
                  </p>
                </div>
              </div>
            )}
            {hasData && threshold !== null && isExceeded && (
              <div className="ed-alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>Threshold Action Required</strong>
                  <p>
                    {data.exceptions
                      .map(
                        (exception) =>
                          `${exception.discipline} is at ${formatPercent(exception.consumption_pct)} against the ${formatPercent(exception.threshold_pct)} threshold`,
                      )
                      .join(' ')}
                  </p>
                </div>
              </div>
            )}
            {hasData && threshold !== null && !isExceeded && (
              <div className="ed-alert ed-alert-ok">
                <ShieldCheck size={16} />
                <div>
                  <strong>Within Threshold</strong>
                  <p>
                    Current consumption is {formatPercent(governance.consumption_pct)} against the{' '}
                    {formatPercent(threshold)} threshold.
                  </p>
                </div>
              </div>
            )}
            {!hasData && (
              <div className="ed-alert ed-alert-ok">
                <ShieldCheck size={16} />
                <div>
                  <strong>No project selected</strong>
                  <p>Governance controls will be available after selecting a project.</p>
                </div>
              </div>
            )}

            {pendingRequest && (
              <div className="ed-request-review">
                <div className="ed-request-review-header">
                  <h3>Extension Request</h3>
                  <span className="ed-status-pill ed-status-pending">{pendingRequest.status_label}</span>
                </div>
                <dl className="ed-request-details">
                  <div>
                    <dt>Requested additional hours</dt>
                    <dd>{formatHours(pendingRequest.requested_hours)}</dd>
                  </div>
                  <div>
                    <dt>Requesting Lead</dt>
                    <dd>{pendingRequest.requested_by || 'Not available'}</dd>
                  </div>
                  <div>
                    <dt>Project</dt>
                    <dd>{pendingRequest.project_name || project.project_name}</dd>
                  </div>
                  <div>
                    <dt>Request date/time</dt>
                    <dd>{formatDate(pendingRequest.requested_at)}</dd>
                  </div>
                  <div>
                    <dt>Current status</dt>
                    <dd>{pendingRequest.status_label}</dd>
                  </div>
                  <div>
                    <dt>Lead justification</dt>
                    <dd>{pendingRequest.justification || 'No justification provided'}</dd>
                  </div>
                </dl>
              </div>
            )}
            {hasData && !pendingRequest && (
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
              disabled={!hasProject || submitting}
            />

            <div className="ed-buttons">
              <button
                type="button"
                className="ed-btn ed-btn-stop"
                disabled={!hasProject || !comments.trim() || submitting === 'stop-execution'}
                onClick={() => runGovernanceAction('stop-execution')}
              >
                {submitting === 'stop-execution' ? 'Stopping…' : 'Stop the Execution'}
              </button>
              <button
                type="button"
                className="ed-btn ed-btn-approve"
                disabled={!pendingRequest || submitting === 'decision-approve'}
                onClick={() => decideExtensionRequest('approve')}
              >
                {submitting === 'decision-approve' ? 'Approving…' : 'Approve Extension'}
              </button>
              <button
                type="button"
                className="ed-btn ed-btn-reject"
                disabled={!pendingRequest || submitting === 'decision-reject'}
                onClick={() => decideExtensionRequest('reject')}
              >
                {submitting === 'decision-reject' ? 'Rejecting…' : 'Reject Extension'}
              </button>
            </div>
            {actionError && <div className="resource-error">{actionError}</div>}
          </section>

          <section className="allocation-card ed-audit-section">
            <div className="allocation-header">
              <div>
                <h2>Recent Governance Audit Log</h2>
                <p>Latest project governance actions and extension decisions.</p>
              </div>
            </div>
            {!hasData && (
              <div className="timesheet-empty-cell">
                No project selected — governance audit logs are unavailable.
              </div>
            )}
            {hasData && data.governance_actions.length === 0 && (
              <div className="timesheet-empty-cell">No governance actions recorded yet.</div>
            )}
            {hasData && data.governance_actions.length > 0 && (
              <div className="ed-audit-list">
                {data.governance_actions.map((entry) => (
                  <div className="ed-audit-item" key={entry.id}>
                    <span className="ed-audit-date">{formatDate(entry.created_at)}</span>
                    <span className="ed-audit-separator">: </span>
                    <span className="ed-audit-message">
                      {entry.action === 'extension_request' &&
                        `Requested extension of ${formatHours(entry.requested_hours)}`}
                      {entry.action === 'approve_extension' &&
                        `Approved extension of ${formatHours(entry.requested_hours)}`}
                      {entry.action === 'reject_extension' &&
                        `Rejected extension of ${formatHours(entry.requested_hours)}`}
                      {entry.action === 'stop_execution' && 'Stopped execution'}
                      {entry.comments && ` — ${entry.comments}`}
                      {entry.created_by && ` by ${entry.created_by}`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <div className="ed-next-row">
        <button
          type="button"
          className="button button-primary button-next"
          onClick={() => navigate(`/project-work-summary?projectId=${projectId}`)}
        >
          NEXT <ArrowRight size={16} />
        </button>
      </div>
    </main>
  );
}
