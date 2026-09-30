import { ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { useServerToday } from '../../hooks/useServerToday';
import { RejectedHoursPanel } from '../../features/hours/RejectedHours';
import { DAY_KEYS, DAY_LEGEND, HOURS_STATUS_LABELS, HOURS_STATUS_PILL, bulkNotice, describeTotals, groupByEngineer, isOverMark, summarizeWeek } from '../../utils/hours';
import { formatDateStr, getMonday, getWeekInfo } from '../../utils/weeks';

const WBS_PHASES = ['Space Planning', 'STR Coordination', 'ID Coordination', 'BoH Area RCP Coordination'];
const INITIAL_VIEWPORT_START = new Date(2026, 8, 1);
const INITIAL_VIEWPORT_END = new Date(2026, 11, 31, 23, 59, 59);
const INITIAL_VIEWPORT_MONTH_COUNT =
  (INITIAL_VIEWPORT_END.getFullYear() - INITIAL_VIEWPORT_START.getFullYear()) * 12 +
  INITIAL_VIEWPORT_END.getMonth() -
  INITIAL_VIEWPORT_START.getMonth() +
  1;

function formatMonthHeader(dateObj) {
  return dateObj.toLocaleString('en-US', { month: 'short', year: 'numeric' }).toUpperCase();
}

function getQuarterFromMonth(dateObj) {
  const q = Math.floor(dateObj.getMonth() / 3) + 1;
  return `Q${q} ${dateObj.getFullYear()}`;
}

const COMPLETE_STATUSES = ['Done', 'Approved', 'Completed'];

function clampPct(value) {
  return Math.max(0, Math.min(100, value));
}

export function TimelineLogsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { role, authHeaders } = useAuth();
  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [nodes, setNodes] = useState([]);
  const [entries, setEntries] = useState([]);
  const [timelineTasks, setTimelineTasks] = useState([]);
  const [timelinePhases, setTimelinePhases] = useState([]);
  const { today, loaded: todayLoaded } = useServerToday(); // the server's day, never the browser's
  const [weekOffset, setWeekOffset] = useState(0); // weeks before (negative) or after the server's current week
  const currentMonday = useMemo(() => {
    const monday = getMonday(today);
    monday.setDate(monday.getDate() + 7 * weekOffset);
    return monday;
  }, [today, weekOffset]);

  const [error, setError] = useState('');
  const [sheetMessage, setSheetMessage] = useState(null); // { type, text }: shown beside the sheet's buttons
  const weekRequestRef = useRef('');

  const project = projects.find((p) => String(p.id) === String(selectedId));
  const projectId = project?.id;
  // Lead and engineer are roles on the selected project, not on the account.
  const isBuHead = role === 'bu_head';
  const isEngineer = project?.my_role === 'engineer';
  const isLead = project?.my_role === 'lead';

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error('Could not fetch projects');
        return res.json();
      })
      .then((data) => {
        setProjects(data);
        if (Array.isArray(data) && data.length > 0) {
          const selected = targetProjectId
            ? data.find((p) => p.id === targetProjectId)
            : data[0];
          setSelectedId(selected ? String(selected.id) : '');
        }
      })
      .catch((err) => setError(err.message));
  }, [targetProjectId, authHeaders]);

  const weekStartStr = useMemo(() => formatDateStr(currentMonday), [currentMonday]);
  // Tracks the week the user is actually viewing right now. Assigned during
  // render, so it can never lag behind a stale effect/closure: effect callbacks
  // that read it always act on the current week.
  const weekStartRef = useRef(weekStartStr);
  weekStartRef.current = weekStartStr;

  const loadProjectData = useCallback(async (id, weekStr) => {
    const requestKey = `${id}:${weekStr}`;
    weekRequestRef.current = requestKey;
    setError('');
    // The Weekly Hours sheet is scoped to the selected week: never keep the
    // previous week's rows/status lingering under a changed week header while
    // the new week's data is loading.
    setEntries([]);
    try {
      const [nodesRes, timesheetRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/projects/${id}/wbs-structure`, { headers: authHeaders() }),
        // One row per subtask, engineer and day, banked by Logout.
        fetch(`${API_BASE_URL}/api/projects/${id}/timesheet?week_start=${weekStr}`, { headers: authHeaders() }),
      ]);

      if (!nodesRes.ok || !timesheetRes.ok) {
        throw new Error('Failed to load project timeline data.');
      }

      const nodesData = await nodesRes.json();
      const timesheetData = await timesheetRes.json();

      // Ignore any response that is no longer the week the user is viewing:
      // re-entrant callbacks (e.g. a window focus listener) may still deliver
      // an older week, so compare both the latest request AND the currently
      // displayed week before committing anything.
      if (weekRequestRef.current !== requestKey || weekStartRef.current !== weekStr) return;

      setNodes(nodesData);
      setEntries(Array.isArray(timesheetData) ? timesheetData : []);

      if (isEngineer || isLead) {
        const timelineRes = await fetch(`${API_BASE_URL}/api/projects/${id}/timeline-logs`, { headers: authHeaders() });
        if (!timelineRes.ok) {
          throw new Error('Failed to load task timeline data.');
        }
        const timelineData = await timelineRes.json();
        if (weekRequestRef.current !== requestKey || weekStartRef.current !== weekStr) return;
        setTimelineTasks(Array.isArray(timelineData.tasks) ? timelineData.tasks : []);
        setTimelinePhases(Array.isArray(timelineData.phases) ? timelineData.phases : []);
      } else {
        setTimelineTasks([]);
        setTimelinePhases([]);
      }
    } catch (err) {
      if (weekRequestRef.current === requestKey && weekStartRef.current === weekStr) {
        setError(err.message);
      }
    }
  }, [authHeaders, isEngineer, isLead]);

  useEffect(() => {
    if (projectId) {
      loadProjectData(projectId, weekStartStr);
    }
  }, [projectId, weekStartStr, loadProjectData]);

  useEffect(() => {
    const onFocus = () => {
      if (projectId) {
        // Always refresh the week currently being viewed; the ref never holds
        // a stale closure, unlike the render value captured above.
        loadProjectData(projectId, weekStartRef.current);
      }
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [projectId, loadProjectData]);

  const phaseRows = useMemo(() => {
    const phaseMap = {};
    WBS_PHASES.forEach((phase) => {
      phaseMap[phase] = { phase, count: 0 };
    });
    const source = isEngineer
      ? (timelineTasks.length > 0 ? timelineTasks : nodes)
      : (isLead ? timelineTasks : nodes);
    if (source && source.length > 0) {
      source.forEach((node) => {
        const phaseName = node.phase || 'Space Planning';
        if (!phaseMap[phaseName]) {
          phaseMap[phaseName] = { phase: phaseName, count: 0, doneCount: 0, start_date: null, end_date: null };
        }
        const row = phaseMap[phaseName];
        if (isEngineer || isLead) {
          if (row.doneCount === undefined) row.doneCount = 0;
          if (COMPLETE_STATUSES.includes(node.deliverable_status)) row.doneCount += 1;
          const s = node.start_date ? new Date(node.start_date) : null;
          const e = node.end_date
            ? new Date(node.end_date)
            : node.target_due_date
              ? new Date(node.target_due_date)
              : s;
          if (s && (!row.start_date || s < row.start_date)) row.start_date = s;
          if (e && (!row.end_date || e > row.end_date)) row.end_date = e;
        }
        row.count += 1;
      });
    }
    return Object.values(phaseMap).map((p) => ({ ...p, isRealData: p.count > 0 }));
  }, [nodes, timelineTasks, isEngineer, isLead]);

  const { quarterTitle } = useMemo(() => {
    let minDate = null;
    let maxDate = null;

    const nodeDates = [];
    nodes.forEach((n) => {
      if (n.start_date) nodeDates.push(new Date(n.start_date));
      const ed = n.end_date || n.target_due_date;
      if (ed) nodeDates.push(new Date(ed));
    });

    const currentMonthStart = new Date(today.getFullYear(), today.getMonth(), 1);

    if (nodeDates.length > 0) {
      minDate = new Date(Math.min(...nodeDates));
      maxDate = new Date(Math.max(...nodeDates));
    } else if (project?.start_date) {
      minDate = new Date(project.start_date);
      if (project.target_end_date) {
        maxDate = new Date(project.target_end_date);
      } else {
        maxDate = new Date(minDate.getFullYear(), minDate.getMonth() + 6, 0);
      }
    } else {
      minDate = getMonday(today);
      maxDate = new Date(minDate.getFullYear(), minDate.getMonth() + 6, 0);
    }

    if (maxDate < currentMonthStart) {
      maxDate = new Date(currentMonthStart.getFullYear(), currentMonthStart.getMonth() + 6, 0);
    }

    const start = new Date(minDate.getFullYear(), minDate.getMonth(), 1);
    const end = new Date(maxDate.getFullYear(), maxDate.getMonth() + 1, 0, 23, 59, 59);

    const cols = [];
    const curr = new Date(start);
    while (curr <= end) {
      cols.push(new Date(curr));
      curr.setMonth(curr.getMonth() + 1);
    }

    const title = cols.length > 0 ? getQuarterFromMonth(cols[0]) : 'Upcoming Schedule';

    return {
      quarterTitle: title,
    };
  }, [nodes, project, today]);

  const visibleMonthColumns = useMemo(
    () => Array.from({ length: INITIAL_VIEWPORT_MONTH_COUNT }, (_, index) => {
      const colDate = new Date(INITIAL_VIEWPORT_START);
      colDate.setMonth(colDate.getMonth() + index);
      return colDate;
    }),
    [],
  );

  const todayPct = useMemo(() => {
    const total = INITIAL_VIEWPORT_END.getTime() - INITIAL_VIEWPORT_START.getTime();
    if (today < INITIAL_VIEWPORT_START || today > INITIAL_VIEWPORT_END || total <= 0) return null;
    const elapsed = today.getTime() - INITIAL_VIEWPORT_START.getTime();
    return Math.min(100, Math.max(0, (elapsed / total) * 100));
  }, [today]);

  const weekInfo = useMemo(() => getWeekInfo(currentMonday), [currentMonday]);

  // One row per engineer: their days, the week's status and what is waiting on this viewer.
  const groupRows = useMemo(
    () => groupByEngineer(entries).map((group) => ({ ...group, ...summarizeWeek(group.rows) })),
    [entries],
  );
  const reviewableAll = useMemo(() => groupRows.reduce((sum, group) => sum + group.reviewable, 0), [groupRows]);
  const heldAll = useMemo(() => groupRows.reduce((sum, group) => sum + group.held, 0), [groupRows]);

  const handlePrevWeek = () => setWeekOffset((offset) => offset - 1);
  const handleNextWeek = () => setWeekOffset((offset) => offset + 1);

  // Approve every pending, finished day this viewer is the reviewer of: one engineer's, or all.
  const handleApprove = async (employeeId = null) => {
    if (!projectId || !weekStartStr) return;
    try {
      setSheetMessage(null);
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/hours/review`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'approved', week_start_date: weekStartStr, employee_id: employeeId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not approve these hours.');
      const days = `${data.reviewed} day${data.reviewed === 1 ? '' : 's'}`;
      setSheetMessage({ type: 'done', text: bulkNotice(data) || `Approved ${days}. They count from now.` });
      await loadProjectData(projectId, weekStartStr);
    } catch (err) {
      setSheetMessage({ type: 'error', text: err.message });
    }
  };

  return (
    <main className="timeline-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Execution Tracking</span>
            <i>/</i>
            <span>{isEngineer ? 'My Timesheets' : 'Gantt & Timesheets'}</span>
            <i>/</i>
            <strong>{project?.project_name || 'Select Project'}</strong>
          </div>
          <h1>Timeline Schedule &amp; Weekly Timesheet Logs</h1>
          <p>
            {isEngineer
              ? 'Your assigned WBS schedule, and the hours recorded from Login/Logout on your subtasks.'
              : 'Track project progress on a weekly Gantt schedule and review actual labor hours against assigned WBS nodes.'}
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

      <section className="allocation-card gantt-card">
        <div className="allocation-header">
          <div>
            <h2>Project Gantt Timeline ({quarterTitle})</h2>
            <p>Visual schedule tracking of WBS node start / target due dates.</p>
          </div>
          {todayLoaded && (
            <div className="server-date-badge">
              <span>Server Date: </span>
              <strong>{today.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })}</strong>
            </div>
          )}
        </div>

          <div className="gantt-container">
            <div className="gantt-header-row">
              <div className="gantt-task-name-header" style={{ visibility: 'hidden' }} />
              <div className="gantt-timeline-header">
              {visibleMonthColumns.map((colDate, idx) => (
                <div key={idx} className="gantt-month-col">
                  {formatMonthHeader(colDate)}
                </div>
              ))}
              {todayPct !== null && (
                <div className="gantt-today-line" style={{ left: `${todayPct}%` }}>
                  <span className="gantt-today-tag">TODAY</span>
                </div>
              )}
            </div>
          </div>

          <div className="gantt-body">
            {phaseRows.length === 0 ? (
              <div className="gantt-empty-state">
                {isEngineer
                  ? 'No WBS nodes are assigned to you yet.'
                  : 'No WBS phases with scheduled dates yet.'}
              </div>
            ) : (
              phaseRows.map((row) => {
                let leftPct = 0;
                let widthPct = 100;
                let barTone = 'gantt-bar-empty';
                let barLabel = null;
                let fillPct = 0;
                let showFill = false;

                const phaseStat = timelinePhases.find((p) => p.phase === row.phase);
                const totalCount = phaseStat ? phaseStat.total_tasks : row.count;
                const doneCount = phaseStat ? phaseStat.completed_tasks : row.doneCount || 0;
                const percent =
                  phaseStat ? phaseStat.percent_complete
                  : totalCount > 0
                    ? Math.round((doneCount / totalCount) * 100)
                    : null;

                if (isEngineer || isLead) {
                const fixedTotal = INITIAL_VIEWPORT_END.getTime() - INITIAL_VIEWPORT_START.getTime();
                  if (totalCount > 0) {
                    if (row.start_date && row.end_date && fixedTotal > 0) {
                      const tStart = row.start_date.getTime();
                      const tEnd = Math.max(tStart, row.end_date.getTime());
                      leftPct = clampPct(((tStart - INITIAL_VIEWPORT_START.getTime()) / fixedTotal) * 100);
                      widthPct = Math.max(4, clampPct(((tEnd - INITIAL_VIEWPORT_START.getTime()) / fixedTotal) * 100) - leftPct);
                    }
                    if (doneCount >= totalCount) {
                      barTone = 'gantt-bar-completed';
                    } else if (doneCount > 0) {
                      barTone = 'gantt-bar-in_progress';
                      fillPct = percent;
                      showFill = true;
                    } else {
                      barTone = 'gantt-bar-scheduled';
                    }
                    barLabel = `${percent}%`;
                  }
                }

                return (
                  <div key={row.phase} className="gantt-row">
                    <div className="gantt-task-info">
                      <strong>{row.phase}</strong>
                      {(isEngineer || isLead) && (
                        <em className="gantt-phase-status">
                          {totalCount > 0
                            ? `${doneCount}/${totalCount} task${totalCount === 1 ? '' : 's'} complete · ${percent}%`
                            : 'No tasks yet'}
                        </em>
                      )}
                    </div>
                    <div className="gantt-row-timeline">
                      <div className="gantt-month-grid">
                        {visibleMonthColumns.map((_, idx) => (
                          <div key={idx} className="gantt-grid-cell" />
                        ))}
                      </div>
                      {todayPct !== null && (
                        <div className="gantt-today-line-segment" style={{ left: `${todayPct}%` }} />
                      )}
                      <div className={`gantt-bar ${barTone}`} style={{ left: `${leftPct}%`, width: `${widthPct}%` }}>
                        {(isEngineer || isLead) && showFill && (
                          <div className="gantt-progress-wrapper">
                            <div className="gantt-progress-fill" style={{ width: `${fillPct}%` }} />
                          </div>
                        )}
                        {(isEngineer || isLead) && barLabel && <span className="gantt-bar-label">{barLabel}</span>}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {(isEngineer || isLead) && (
            <div className="gantt-legend">
              <span className="gantt-legend-item"><i className="gantt-legend-dot gantt-legend-done" /> Done</span>
              <span className="gantt-legend-item"><i className="gantt-legend-dot gantt-legend-inprog" /> In progress</span>
              <span className="gantt-legend-item"><i className="gantt-legend-dot gantt-legend-scheduled" /> Scheduled</span>
              <span className="gantt-legend-note">Status reflects the current database state for each of your assigned tasks.</span>
            </div>
          )}
        </div>
      </section>

      <section className="allocation-card timesheet-card">
        <div className="allocation-header timesheet-header">
          <div>
            <h2>Weekly hours (Week {weekInfo.weekNum}: {weekInfo.rangeStr})</h2>
            <p>
              {isEngineer
                ? 'Your hours for this week, one row per subtask and day from Login/Logout. Each day is approved by the task’s lead once the day is over.'
                : isLead
                  ? 'Each day is approved by the lead of the task it was worked on, once the day is over. Approve here per engineer, or open the weekly log to decide day by day.'
                  : 'Logged hours for this week. You approve the project leads’ own days, and days on tasks without an active lead.'}
            </p>
          </div>

          {reviewableAll > 0 && (
            <button type="button" className="button button-primary week-nav-btn" onClick={() => handleApprove()}>
              Approve all on my tasks ({reviewableAll})
            </button>
          )}
          {heldAll > 0 && (
            <span className="sheet-held" title="Days over 8 hours and unattended days are approved one by one, in the engineer's weekly log">
              {heldAll} day{heldAll === 1 ? '' : 's'} to review one by one
            </span>
          )}
          <div className="week-navigation">
            <button type="button" className="button button-secondary week-nav-btn" onClick={handlePrevWeek}>
              <ChevronLeft size={16} /> Prev Week
            </button>
            <span className="week-pill">{weekInfo.rangeStr}</span>
            <button type="button" className="button button-secondary week-nav-btn" onClick={handleNextWeek}>
              Next Week <ChevronRight size={16} />
            </button>
          </div>
        </div>

        {sheetMessage && (
          <div className={sheetMessage.type === 'error' ? 'sheet-message is-error' : 'sheet-message'} role="status">
            {sheetMessage.text}
          </div>
        )}
        <div className="resource-table-wrap">
          <table className="resource-table timesheet-table">
            <thead>
              <tr>
                <th className="col-engineer">ENGINEER / WBS TASK</th>
                <th className="col-day">MON</th>
                <th className="col-day">TUE</th>
                <th className="col-day">WED</th>
                <th className="col-day">THU</th>
                <th className="col-day">FRI</th>
                <th className="col-day">SAT</th>
                <th className="col-day">SUN</th>
                <th className="col-total">TOTAL HRS</th>
                <th className="col-approval">APPROVAL</th>
              </tr>
            </thead>
            <tbody>
              {groupRows.length === 0 ? (
                <tr>
                  <td colSpan={10} className="timesheet-empty-cell">
                    {nodes.filter((n) => n.assigned_engineer_id).length === 0
                      ? 'No engineer-assigned WBS nodes in this project yet.'
                      : 'No hours logged for this week yet.'}
                  </td>
                </tr>
              ) : (
                groupRows.map((group) => (
                  <tr key={group.employee_id} className="timesheet-engineer-group-row">
                    <td className="col-engineer">
                      <Link
                        className="timesheet-task-link"
                        to={`/weekly-logs?projectId=${projectId}&employeeId=${group.employee_id}&weekStart=${weekStartStr}`}
                        title={`Open the weekly log details for ${group.employee_name}`}
                      >
                        <div className="timesheet-engineer-cell">
                          <strong>{group.employee_name}</strong>
                          <small>
                            {group.rows.length} logged subtask{group.rows.length === 1 ? '' : 's'} this week
                            {' · Open weekly log'}
                          </small>
                        </div>
                      </Link>
                    </td>

                    {group.days.map((day, index) => (
                      <td key={DAY_KEYS[index]} className="col-day">
                        {day.status === 'none' ? (
                          <span className="day-cell is-empty">–</span>
                        ) : (
                          <span
                            className={`day-cell ${HOURS_STATUS_PILL[day.status] || ''}${isOverMark(day.hours) ? ' is-over-mark' : ''}${day.unattended ? ' is-unattended' : ''}`}
                            title={`${group.employee_name}: ${HOURS_STATUS_LABELS[day.status] || 'partly rejected'}${isOverMark(day.hours) ? ', over 8 h' : ''}${day.unattended ? ', unattended' : ''}`}
                          >
                            {day.hours}
                          </span>
                        )}
                      </td>
                    ))}

                    <td className="col-total">
                      <strong className="total-hours-blue">{group.total.toFixed(2)} hrs</strong>
                      <small className="review-progress">{describeTotals(group)}</small>
                    </td>

                    <td className="col-approval">
                      <span className={`approval-pill ${HOURS_STATUS_PILL[group.status] || 'status-none'}`}>
                        {group.status === 'mixed' ? 'Partly rejected' : HOURS_STATUS_LABELS[group.status] || group.status}
                      </span>
                      {group.status === 'pending_review' && (
                        <small className="review-progress">
                          {group.daysApproved} of {group.daysLogged} days approved
                        </small>
                      )}
                      {group.reviewable > 0 && (
                        <button
                          type="button"
                          className="review-btn review-approve"
                          title={`Approve ${group.reviewable} pending day${group.reviewable === 1 ? '' : 's'} on your tasks`}
                          onClick={() => handleApprove(group.employee_id)}
                        >
                          Approve week
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
              </tbody>
            </table>
        </div>

        <div className="day-legend" aria-label="What the day colours mean">
          {DAY_LEGEND.map(([className, label]) => (
            <span key={className}>
              <i className={`day-cell ${className}`} /> {label}
            </span>
          ))}
          <span>The week&apos;s total counts approved and pending hours; rejected hours never count.</span>
        </div>

        {projectId && (isLead || isBuHead) && (
          <RejectedHoursPanel projectId={projectId} onChanged={() => loadProjectData(projectId, weekStartStr)} />
        )}

        <div className="timesheet-footer">
          <div className="footer-info">
            <span>
              {isEngineer
                ? 'Hours are recorded per subtask from Login/Logout: the time between them counts, except while the laptop was off.'
                : 'Each day is approved by the task’s lead once it is over; the week is the sum of its days.'}
            </span>
          </div>
          <button
            type="button"
            className="button button-primary button-next"
            onClick={() => navigate(isBuHead || isLead ? '/executive-dashboard' : '/engineer-performance-dashboard')}
          >
            NEXT <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </main>
  );
}
