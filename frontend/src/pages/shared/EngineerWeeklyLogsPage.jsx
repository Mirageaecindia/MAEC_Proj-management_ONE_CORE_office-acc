import { ArrowLeft } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { pickProject, rememberProject } from '../../hooks/currentProject';
import { useServerToday } from '../../hooks/useServerToday';
import {
  HOURS_STATUS_LABELS,
  HOURS_STATUS_PILL,
  describeSession,
  describeTotals,
  formatDuration,
  isOverMark,
  summarizeWeek,
} from '../../utils/hours';
import { formatDateStr, getMonday, getWeekInfo } from '../../utils/weeks';

export function EngineerWeeklyLogsPage() {
  const [searchParams] = useSearchParams();
  const { authHeaders } = useAuth();
  const { today, todayStr: todayUtc } = useServerToday(); // rows are dated by the server's UTC day

  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;
  const targetEmployeeId = searchParams.get('employeeId') ? String(searchParams.get('employeeId')) : '';
  const weekStartParam = searchParams.get('weekStart') || '';

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [nodes, setNodes] = useState([]);
  const [entries, setEntries] = useState([]);
  const [rejecting, setRejecting] = useState(null); // { id, reason } while a reason is being typed
  const [timelineEngineers, setTimelineEngineers] = useState([]);
  const [scopeEngineerName, setScopeEngineerName] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');

  const project = projects.find((p) => String(p.id) === String(selectedId));
  // Lead and engineer are roles on the selected project, not on the account.
  const isEngineer = project?.my_role === 'engineer';
  const isLead = project?.my_role === 'lead';
  const projectId = project?.id;

  const monday = useMemo(() => {
    if (weekStartParam) {
      return getMonday(new Date(`${weekStartParam}T00:00:00`));
    }
    return getMonday(today);
  }, [weekStartParam, today]);
  const weekStartStr = useMemo(() => formatDateStr(monday), [monday]);
  const weekInfo = useMemo(() => getWeekInfo(monday), [monday]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error('Could not fetch projects');
        return res.json();
      })
      .then((data) => {
        setProjects(data);
        if (!Array.isArray(data)) return;
        const selected = pickProject(data, targetProjectId);
        setSelectedId(selected ? String(selected.id) : '');
        rememberProject(selected?.id);
      })
      .catch((err) => setError(err.message));
  }, [targetProjectId, authHeaders]);

  // An engineer is always restricted to their OWN rows server-side, so even a
  // hand-edited employeeId in the URL cannot reveal another engineer's logs.
  const detailsRows = useMemo(() => {
    if (isEngineer) return entries;
    return entries.filter((entry) => String(entry.employee_id) === targetEmployeeId);
  }, [entries, isEngineer, targetEmployeeId]);

  const engineerName = useMemo(() => {
    if (detailsRows.length > 0 && detailsRows[0].employee_name) return detailsRows[0].employee_name;
    if (isEngineer && scopeEngineerName) return scopeEngineerName;
    const match = timelineEngineers.find((engineer) => String(engineer.id) === targetEmployeeId);
    return match ? match.name : '';
  }, [detailsRows, isEngineer, scopeEngineerName, timelineEngineers, targetEmployeeId]);

  const nodeMap = useMemo(() => {
    const map = {};
    nodes.forEach((node) => {
      map[node.id] = node;
    });
    return map;
  }, [nodes]);

  const totals = useMemo(() => summarizeWeek(detailsRows), [detailsRows]);

  const loadDetails = useCallback(
    async (projectIdNum, weekStr) => {
      try {
        setError('');
        // Only the first load says "Loading"; after an approval the table stays and updates.
        const requests = [
          fetch(`${API_BASE_URL}/api/projects/${projectIdNum}/wbs-structure`, { headers: authHeaders() }),
          fetch(`${API_BASE_URL}/api/projects/${projectIdNum}/timesheet?week_start=${weekStr}`, {
            headers: authHeaders(),
          }),
        ];
        if (isEngineer || isLead) {
          requests.push(
            fetch(`${API_BASE_URL}/api/projects/${projectIdNum}/timeline-logs`, { headers: authHeaders() }),
          );
        }
        const [nodesRes, timesheetRes, timelineRes] = await Promise.all(requests);
        if (!nodesRes.ok || !timesheetRes.ok) {
          throw new Error('Failed to load the engineer weekly log data.');
        }
        const nodesData = await nodesRes.json();
        const timesheetData = await timesheetRes.json();
        setNodes(nodesData);
        setEntries(Array.isArray(timesheetData) ? timesheetData : []);
        if (timelineRes) {
          const timelineData = await timelineRes.json();
          setTimelineEngineers(Array.isArray(timelineData.engineers) ? timelineData.engineers : []);
          setScopeEngineerName(timelineData.scope?.engineer_name || '');
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoaded(true);
      }
    },
    [authHeaders, isEngineer, isLead],
  );

  useEffect(() => {
    if (projectId) {
      loadDetails(projectId, weekStartStr);
    }
  }, [projectId, weekStartStr, loadDetails]);

  const dayLabel = (isoDate) =>
    new Date(`${isoDate}T00:00:00`).toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });

  // One day's hours: approved or rejected by its reviewer. Every rejection needs a reason.
  const decide = async (entry, action, reason = null) => {
    try {
      setError('');
      const response = await fetch(`${API_BASE_URL}/api/time-log-entries/${entry.id}/${action}`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `Could not ${action} these hours.`);
      }
      setRejecting(null);
      await loadDetails(projectId, weekStartStr);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <main className="timeline-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Execution Tracking</span>
            <i>/</i>
            <span>Timeline &amp; Logs</span>
            <i>/</i>
            <strong>{project?.project_name || 'Select Project'}</strong>
          </div>
          <h1>Engineer Weekly Logs</h1>
          <p>
            Detailed weekly work log for <strong>{engineerName || 'the selected engineer'}</strong> · Week{' '}
            {weekInfo.weekNum}: {weekInfo.rangeStr}.
          </p>
        </div>
      </div>

      {error && <div className="resource-error">{error}</div>}

      <section className="allocation-card timesheet-card">
        <div className="allocation-header timesheet-header">
          <div>
            <h2>
              {engineerName || 'Engineer'} — Weekly Log Details ({weekInfo.rangeStr})
            </h2>
            <p>
              {isEngineer
                ? 'Your hours for this week, one row per subtask and day from Login/Logout. Each day is approved by the task’s lead once the day is over.'
                : `Logged hours for ${engineerName || 'the selected engineer'} this week, one row per subtask and day. Approve or reject each finished day you are the reviewer of.`}
            </p>
          </div>

          <div className="week-navigation">
            <Link
              className="button button-secondary week-nav-btn"
              to={`/timeline-logs${projectId ? `?projectId=${projectId}` : ''}`}
            >
              <ArrowLeft size={16} /> Back to Timeline &amp; Logs
            </Link>
            <span className="week-pill">{weekInfo.rangeStr}</span>
            <span className="week-pill">
              Total: <strong className="total-hours-blue">{totals.total.toFixed(2)} hrs</strong>
              {describeTotals(totals) && <small> ({describeTotals(totals)})</small>}
            </span>
          </div>
        </div>

        <div className="resource-table-wrap">
          {!loaded ? (
            <div className="timesheet-empty-cell">Loading engineer weekly log…</div>
          ) : detailsRows.length === 0 ? (
            <div className="timesheet-empty-cell">
              No work logged by {engineerName || 'this engineer'} during {weekInfo.rangeStr}.
            </div>
          ) : (
            <table className="resource-table details-table">
              <thead>
                <tr>
                  <th>DATE</th>
                  <th>PROJECT</th>
                  <th>WBS CODE</th>
                  <th>PARENT TASK</th>
                  <th>SUBTASK</th>
                  <th>STATUS</th>
                  <th>HOURS</th>
                  <th>APPROVAL</th>
                </tr>
              </thead>
              <tbody>
                {detailsRows.map((entry) => {
                  const node = nodeMap[entry.task_id];
                  const parent = node && node.parent_id ? nodeMap[node.parent_id] : null;
                  const pending = entry.approval_status === 'pending_review';

                  return (
                    <tr key={entry.id}>
                      <td>
                        <span className="time-log-item">{dayLabel(entry.work_date)}</span>
                      </td>
                      <td>{project?.project_name || '—'}</td>
                      <td>{entry.wbs_code || '—'}</td>
                      <td>{parent?.task_name || '—'}</td>
                      <td>
                        <Link
                          className="timesheet-task-link"
                          to={`/task-details?nodeId=${entry.task_id}&projectId=${projectId}`}
                          title="Open this task / subtask"
                        >
                          {entry.task_name}
                        </Link>
                      </td>
                      <td>{node?.deliverable_status || '—'}</td>
                      <td>
                        <strong className="total-hours-blue">{entry.hours.toFixed(2)} hrs</strong>
                        {isOverMark(entry.hours) && (
                          <span className="over-mark-flag" title="More than 8 hours on this day">
                            over 8 h
                          </span>
                        )}
                        {entry.unattended && (
                          <span
                            className="over-mark-flag is-unattended"
                            title="A session on this day ended more than 2 hours after the engineer's last visit to the app"
                          >
                            unattended
                          </span>
                        )}
                        {entry.trimmed_hours > 0 && (
                          <small className="review-progress is-trimmed">
                            {formatDuration(entry.trimmed_hours)} not approved (unattended)
                          </small>
                        )}
                        {(entry.sessions || []).map((session) => (
                          <small className="review-progress" key={session.login_at}>
                            {describeSession(session)}
                          </small>
                        ))}
                      </td>
                      <td className="col-approval">
                        <span
                          className={`approval-pill ${HOURS_STATUS_PILL[entry.approval_status] || 'status-none'}`}
                        >
                          {HOURS_STATUS_LABELS[entry.approval_status] || entry.approval_status}
                        </span>
                        {entry.reviewed_by && (
                          <small className="review-progress">by {entry.reviewed_by}</small>
                        )}
                        {entry.review_reason && (
                          <small className="review-progress">{entry.review_reason}</small>
                        )}
                        {pending && !entry.finished && (
                          <small className="review-progress">
                            {entry.work_date === todayUtc
                              ? 'Reviewable once the subtask is Done, or from tomorrow.'
                              : 'Reviewable once the session still running from that day has closed.'}
                          </small>
                        )}
                        {entry.can_review &&
                          entry.approval_status !== 'rejected' &&
                          rejecting?.id !== entry.id && (
                            <span className="review-actions">
                              {pending && (
                                <button
                                  type="button"
                                  className="review-btn review-approve"
                                  onClick={() => decide(entry, 'approve')}
                                >
                                  Approve
                                </button>
                              )}
                              {pending && entry.unattended && (
                                <button
                                  type="button"
                                  className="review-btn review-approve"
                                  title="Approve only the time up to the engineer's last visit; the rest is kept on the row as not approved"
                                  onClick={() => decide(entry, 'approve-attended')}
                                >
                                  Approve up to last visit ({entry.attended_hours} h)
                                </button>
                              )}
                              <button
                                type="button"
                                className="review-btn review-reject"
                                onClick={() => setRejecting({ id: entry.id, reason: '' })}
                              >
                                Reject
                              </button>
                            </span>
                          )}
                        {rejecting?.id === entry.id && (
                          <span className="review-actions">
                            <input
                              aria-label="Reason for rejecting these hours"
                              placeholder="Reason (required)"
                              value={rejecting.reason}
                              onChange={(e) => setRejecting({ id: entry.id, reason: e.target.value })}
                            />
                            <button
                              type="button"
                              className="review-btn review-reject"
                              disabled={!rejecting.reason.trim()}
                              onClick={() => decide(entry, 'reject', rejecting.reason.trim())}
                            >
                              Confirm reject
                            </button>
                            <button type="button" className="review-btn" onClick={() => setRejecting(null)}>
                              Cancel
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="timesheet-footer">
          <div className="footer-info">
            <span>
              {isEngineer
                ? 'You can only view your own logs. Hours are recorded per subtask from Login/Logout; each day is reviewed once it is over.'
                : 'Rejected hours can be approved again for 7 days, by a lead of the project, from Rejected hours on Timeline & Logs.'}
            </span>
          </div>
          <Link
            className="button button-primary button-next"
            to={`/timeline-logs${projectId ? `?projectId=${projectId}` : ''}`}
          >
            <ArrowLeft size={16} /> Back
          </Link>
        </div>
      </section>
    </main>
  );
}

export default EngineerWeeklyLogsPage;
