import { AlertTriangle, ArrowRight, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { formatDateTimeIST } from '../../utils/displayTime';


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
  const [requestedHours, setRequestedHours] = useState('');
  const [justification, setJustification] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState('');

  const project = projects.find((p) => String(p.id) === String(selectedId));
  const projectId = project?.id;

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
    setData(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/executive-dashboard`, {
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`Failed to load dashboard (${response.status})`);
      setData(await response.json());
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [projectId, authHeaders]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  const submitRequest = useCallback(async () => {
    const hours = Number(requestedHours);
    if (!projectId || !Number.isFinite(hours) || hours <= 0 || submitting) return;
    setSubmitting(true);
    setActionError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/extension-requests`, {
        method: 'POST',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          requested_hours: hours,
          justification: justification.trim() || null,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
      setRequestedHours('');
      setJustification('');
      await fetchDashboard();
    } catch (submitError) {
      setActionError(submitError.message);
    } finally {
      setSubmitting(false);
    }
  }, [projectId, requestedHours, justification, submitting, authHeaders, fetchDashboard]);

  const currency = data?.project?.contract_currency || 'USD';
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

  const governance = data?.governance_status;
  const threshold = governance?.threshold_pct;
  const isExceeded = governance?.status === 'exceeded';
  const latestRequest = data?.extension_requests?.[0] || null;
  const pendingRequest = data?.current_extension_request || null;
  const hasProject = Boolean(project);
  const hasData = Boolean(data);

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
            Real-time health monitoring, financial variance, threshold exception tracking, and BU
            approval controls.
          </p>
        </div>

        <label className="project-switcher">
          <span>Project Name</span>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            <option value="">Select project</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>{project.project_name}</option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="resource-error">{error}</div>}

      <section className="ed-summary-cards">
        <div className="ed-card">
          <span className="ed-card-label">Commercial Budget Burn</span>
          <strong className="ed-card-value">{hasData ? money(data.commercial_budget_burn.consumed) : 'Not available'}</strong>
          <span className="ed-card-sub">
            {hasData ? `of ${money(data.commercial_budget_burn.total)} contract value` : 'No project selected'}
          </span>
          <div className="ed-progress ed-progress-blue">
            <span style={{ width: hasData ? `${Math.min(100, data.commercial_budget_burn.percent)}%` : '0%' }} />
          </div>
          <span className="ed-card-foot">
            {hasData ? formatPercent(data.commercial_budget_burn.percent) : 'No project data'}
          </span>
        </div>

        <div className="ed-card">
          <span className="ed-card-label">Total Hours Consumption</span>
          <strong className="ed-card-value">{hasData ? formatHours(data.hours_consumption.hours) : 'Not available'}</strong>
          <span className="ed-card-sub">{hasData ? `(${formatPercent(data.hours_consumption.percent)})` : 'No project selected'}</span>
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
              <strong className="ed-card-value">EXCEEDED ({formatPercent(governance.max_discipline_pct)})</strong>
              <span className="ed-card-sub">Threshold: {formatPercent(threshold)}</span>
              {governance.soft_locked && <span className="ed-softlock">Timesheets Soft-Locked for Approval</span>}
            </>
          ) : hasData ? (
            <>
              <strong className="ed-card-value">
                NORMAL <ShieldCheck size={18} className="ed-card-inline-icon" />
              </strong>
              <span className="ed-card-sub">
                Consumption {formatPercent(governance.consumption_pct)} at the {formatPercent(threshold)} threshold
              </span>
              {governance.soft_locked && <span className="ed-softlock">Timesheets Soft-Locked for Approval</span>}
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
          <strong className="ed-card-value ed-spi-value">{hasData ? formatValue(data.spi.value, 2) : 'Not available'}</strong>
          <span className="ed-card-sub ed-spi-note">{hasData ? data.spi.note : 'No project selected'}</span>
          <div className="ed-progress ed-progress-green">
            <span style={{ width: hasData && data.spi.value !== null ? `${Math.min(100, data.spi.value * 100)}%` : '0%' }} />
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
                    const value = Math.round((maxMonthlyValue * (4 - i)) / 4 * 10) / 10;
                    return <span key={i} className="ed-chart-y-label">{formatHours(value)}</span>;
                  })}
                </div>
                <div className="ed-chart-plot-area">
                  <div className="ed-chart-bars-grouped" role="img" aria-label="Monthly hours burndown chart">
                    {monthlyData.map((month, monthIndex) => (
                      <div key={month.month} className="ed-chart-month-group" style={{ '--month-index': monthIndex }}>
                        <div className="ed-bar-vertical-wrapper">
                          <div
                            className="ed-bar-vertical ed-bar-vertical-planned"
                            style={{ height: maxMonthlyValue > 0 ? `${(month.planned_baseline / maxMonthlyValue) * 100}%` : '0%' }}
                            title={`Planned Baseline: ${formatHours(month.planned_baseline)}`}
                          />
                        </div>
                        <div className="ed-bar-vertical-wrapper">
                          <div
                            className="ed-bar-vertical ed-bar-vertical-normal"
                            style={{ height: maxMonthlyValue > 0 ? `${(month.normal_consumption / maxMonthlyValue) * 100}%` : '0%' }}
                            title={`Normal Consumption: ${formatHours(month.normal_consumption)}`}
                          />
                        </div>
                        <div className="ed-bar-vertical-wrapper">
                          <div
                            className="ed-bar-vertical ed-bar-vertical-exceeded"
                            style={{ height: maxMonthlyValue > 0 ? `${(month.exceeded_threshold / maxMonthlyValue) * 100}%` : '0%' }}
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
              {hasData ? 'No monthly activity on this project yet.' : 'No project selected — assign engineers and log hours to populate the burndown chart.'}
            </div>
          )}

          <div className="ed-legend">
            <span><i className="ed-legend-swatch ed-swatch-planned" /> Planned Baseline</span>
            <span><i className="ed-legend-swatch ed-swatch-normal" /> Normal Consumption</span>
            <span><i className="ed-legend-swatch ed-swatch-exceeded" /> Exceeded Threshold</span>
          </div>
        </section>

        <div className="ed-right-col">
          <section className="allocation-card ed-controls-panel">
            <div className="allocation-header">
              <div>
                <h2>Lead Action</h2>
                <p>Review the selected project threshold and request additional governance hours.</p>
              </div>
            </div>

            {hasData && threshold === null && (
              <div className="ed-alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>Threshold Not Configured</strong>
                  <p>Consumption is {formatPercent(governance.consumption_pct)}; no project governance threshold is configured.</p>
                </div>
              </div>
            )}
            {hasData && threshold !== null && isExceeded && (
              <div className="ed-alert">
                <AlertTriangle size={16} />
                <div>
                  <strong>Threshold Action Required</strong>
                  <p>
                    {data.exceptions.map((exception) => `${exception.discipline} is at ${formatPercent(exception.consumption_pct)} against the ${formatPercent(exception.threshold_pct)} threshold`).join(' ')}
                  </p>
                </div>
              </div>
            )}
            {hasData && threshold !== null && !isExceeded && (
              <div className="ed-alert ed-alert-ok">
                <ShieldCheck size={16} />
                <div>
                  <strong>Within Threshold</strong>
                  <p>Current consumption is {formatPercent(governance.consumption_pct)} against the {formatPercent(threshold)} threshold.</p>
                </div>
              </div>
            )}
            {!hasData && (
              <div className="ed-alert ed-alert-ok">
                <ShieldCheck size={16} />
                <div>
                  <strong>No project selected</strong>
                  <p>Threshold information and extension actions will be available after selecting a project.</p>
                </div>
              </div>
            )}

            {latestRequest && (
              <div className="ed-request-status">
                <span>Current request status</span>
                <strong>{latestRequest.status_label}</strong>
                <span>Requested {formatHours(latestRequest.requested_hours)} · {formatDate(latestRequest.requested_at)}</span>
                {latestRequest.decided_at && <span>Decided {formatDate(latestRequest.decided_at)}{latestRequest.decided_by ? ` by ${latestRequest.decided_by}` : ''}</span>}
                {latestRequest.decision_comments && <span>{latestRequest.decision_comments}</span>}
              </div>
            )}
            {hasData && !latestRequest && (
              <div className="ed-request-status ed-request-status-empty">
                <span>Current request status</span>
                <strong>No extension request submitted</strong>
              </div>
            )}

            <label className="ed-field-label" htmlFor="lead-extension-hours">
              Request to Extend Limit <span className="required-asterisk">*</span>
            </label>
            <div className="ed-hours-input">
              <input
                id="lead-extension-hours"
                type="number"
                min="1"
                step="1"
                inputMode="decimal"
                placeholder="Enter additional hours"
                value={requestedHours}
                onChange={(event) => setRequestedHours(event.target.value)}
                disabled={!hasProject || Boolean(pendingRequest) || submitting}
              />
              <span>Hours</span>
            </div>

            <label className="ed-field-label" htmlFor="lead-extension-justification">
              Justification / Comment <span className="ed-optional-label">(optional)</span>
            </label>
            <textarea
              id="lead-extension-justification"
              className="ed-comments"
              placeholder="Add justification for the requested extension"
              value={justification}
              onChange={(event) => setJustification(event.target.value)}
              disabled={!hasProject || Boolean(pendingRequest) || submitting}
            />

            <button
              type="button"
              className="ed-btn ed-btn-submit"
              disabled={!hasProject || !requestedHours.trim() || Number(requestedHours) <= 0 || Boolean(pendingRequest) || submitting}
              onClick={submitRequest}
            >
              {submitting ? 'Submitting…' : 'Submit for Approval'}
            </button>
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
              <div className="timesheet-empty-cell">No project selected — governance audit logs are unavailable.</div>
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
                      {entry.action === 'extension_request' && `Requested extension of ${formatHours(entry.requested_hours)}`}
                      {entry.action === 'approve_extension' && `Approved extension of ${formatHours(entry.requested_hours)}`}
                      {entry.action === 'reject_extension' && `Rejected extension of ${formatHours(entry.requested_hours)}`}
                      {entry.action === 'stop_execution' && 'Stopped execution'}
                      {entry.action === 'hours_unapproved' && 'Approved hours taken back'}
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
          onClick={() => navigate(`/timeline-logs?projectId=${projectId}`)}
        >
          NEXT <ArrowRight size={16} />
        </button>
      </div>
    </main>
  );
}
