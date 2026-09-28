import { ArrowLeft } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import {
  DAY_FIELDS,
  getMonday,
  formatDateStr,
  getWeekInfo,
  WEEKLY_SUBMISSION_LABELS,
  WEEKLY_SUBMISSION_PILL,
} from './TimelineLogsPage';

export function EngineerWeeklyLogsPage() {
  const [searchParams] = useSearchParams();
  const { authHeaders } = useAuth();

  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;
  const targetEmployeeId = searchParams.get('employeeId') ? String(searchParams.get('employeeId')) : '';
  const weekStartParam = searchParams.get('weekStart') || '';

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [nodes, setNodes] = useState([]);
  const [entries, setEntries] = useState([]);
  const [submissions, setSubmissions] = useState([]);
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
    return getMonday(new Date());
  }, [weekStartParam]);
  const weekStartStr = useMemo(() => formatDateStr(monday), [monday]);
  const weekInfo = useMemo(() => getWeekInfo(monday), [monday]);
  const dayDates = useMemo(
    () =>
      DAY_FIELDS.map(
        (_, index) => new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + index),
      ),
    [monday],
  );

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error('Could not fetch projects');
        return res.json();
      })
      .then((data) => {
        setProjects(data);
        if (!Array.isArray(data)) return;
        const selected = targetProjectId ? data.find((p) => p.id === targetProjectId) : data[0];
        setSelectedId(selected ? String(selected.id) : '');
      })
      .catch((err) => setError(err.message));
  }, [targetProjectId, authHeaders]);

  // An engineer is always restricted to their OWN rows server-side, so even a
  // hand-edited employeeId in the URL cannot reveal another engineer's logs.
  const detailsRows = useMemo(() => {
    if (isEngineer) return entries;
    return entries.filter((entry) => String(entry.employee_id) === targetEmployeeId);
  }, [entries, isEngineer, targetEmployeeId]);

  // The week-level submission record that drives the APPROVAL column. Approval
  // happens once per engineer per week, not per entry, so the engineer's own
  // record (engineer view) or the selected engineer's record (lead view) rules.
  const weekSubmission = useMemo(() => {
    if (isEngineer) return submissions[0] || null;
    return submissions.find((submission) => String(submission.employee_id) === targetEmployeeId) || null;
  }, [submissions, isEngineer, targetEmployeeId]);

  const weeklyStatus = useMemo(
    () => (weekSubmission ? weekSubmission.status : 'not_submitted'),
    [weekSubmission],
  );

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

  const grandTotal = useMemo(
    () => detailsRows.reduce((sum, entry) => sum + (Number(entry.total_hours) || 0), 0),
    [detailsRows],
  );

  const loadDetails = async (projectIdNum, weekStr) => {
    try {
      setError('');
      setLoaded(false);
      const requests = [
        fetch(`${API_BASE_URL}/api/projects/${projectIdNum}/wbs-structure`, { headers: authHeaders() }),
        fetch(
          `${API_BASE_URL}/api/projects/${projectIdNum}/timesheet?week_start=${weekStr}&source=tracking`,
          { headers: authHeaders() },
        ),
        fetch(`${API_BASE_URL}/api/projects/${projectIdNum}/weekly-hours-submissions?week_start=${weekStr}`, {
          headers: authHeaders(),
        }),
      ];
      if (isEngineer || isLead) {
        requests.push(
          fetch(`${API_BASE_URL}/api/projects/${projectIdNum}/timeline-logs`, { headers: authHeaders() }),
        );
      }
      const [nodesRes, timesheetRes, submissionsRes, timelineRes] = await Promise.all(requests);
      if (!nodesRes.ok || !timesheetRes.ok || !submissionsRes.ok) {
        throw new Error('Failed to load the engineer weekly log data.');
      }
      const nodesData = await nodesRes.json();
      const timesheetData = await timesheetRes.json();
      const submissionsData = await submissionsRes.json();
      setNodes(nodesData);
      setEntries(timesheetData);
      setSubmissions(Array.isArray(submissionsData) ? submissionsData : []);
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
  };

  useEffect(() => {
    if (projectId) {
      loadDetails(projectId, weekStartStr);
    }
  }, [projectId, weekStartStr]);

  const fmtHours = (value) => {
    const number = Number(value) || 0;
    return Math.round(number * 100) / 100;
  };

  const workedDaysFor = (entry) =>
    DAY_FIELDS.map((day, index) => {
      const hours = fmtHours(entry[`${day}_hours`] || 0);
      if (hours <= 0) return null;
      return {
        date: dayDates[index].toLocaleDateString('en-US', {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
        }),
        hours,
      };
    }).filter(Boolean);

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
                ? 'Your automatic subtask working-time for this week, recorded from Login/Logout: the time between them counts, except while the laptop was off.'
                : `Logged hours for ${engineerName || 'the selected engineer'} this week, recorded automatically per subtask. The week is approved by the assigned lead after you submit it for review.`}
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
              Total: <strong className="total-hours-blue">{grandTotal.toFixed(2)} hrs</strong>
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
                  <th>ACTUAL HOURS</th>
                  <th>TIME LOG &amp; DETAILS</th>
                  <th>APPROVAL</th>
                </tr>
              </thead>
              <tbody>
                {detailsRows.map((entry) => {
                  const node = nodeMap[entry.task_id];
                  const parent = node && node.parent_id ? nodeMap[node.parent_id] : null;
                  const workedDays = workedDaysFor(entry);

                  return (
                    <tr key={entry.id}>
                      <td>
                        {workedDays.length === 0 ? (
                          <span className="time-log-empty">—</span>
                        ) : (
                          workedDays.map(({ date }) => (
                            <span key={date} className="time-log-item">
                              {date}
                            </span>
                          ))
                        )}
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
                        <strong className="total-hours-blue">{entry.total_hours.toFixed(2)} hrs</strong>
                      </td>
                      <td className="col-time-log">
                        {workedDays.length === 0 ? (
                          <span className="time-log-empty">No tracked hours this week</span>
                        ) : (
                          workedDays.map(({ date, hours }) => (
                            <span key={date} className="time-log-item">
                              {date} · {hours.toFixed(2)} hrs
                            </span>
                          ))
                        )}
                      </td>
                      <td>
                        <span
                          className={`approval-pill ${WEEKLY_SUBMISSION_PILL[weeklyStatus] || 'status-none'}`}
                        >
                          {WEEKLY_SUBMISSION_LABELS[weeklyStatus] || weeklyStatus}
                        </span>
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
                ? 'You can only view your own weekly logs. Submit a week for your lead’s review; hours are recorded automatically per subtask via Login/Logout tracking — active time only.'
                : 'Read-only detail view. Approve or reject this week from the Approval column on the Timeline & Logs page.'}
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
