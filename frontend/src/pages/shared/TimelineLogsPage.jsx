import { ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';

export const DAY_FIELDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];
export const WEEKLY_SUBMISSION_LABELS = {
  not_submitted: 'Not Submitted',
  submitted: 'Submitted for Approval',
  approved: 'Approved',
  rejected: 'Rejected',
};
export const WEEKLY_SUBMISSION_PILL = {
  not_submitted: 'status-none',
  submitted: 'status-pending',
  approved: 'status-approved',
  rejected: 'status-rejected',
};

const WBS_PHASES = ['Space Planning', 'STR Coordination', 'ID Coordination', 'BoH Area RCP Coordination'];
const INITIAL_VIEWPORT_START = new Date(2026, 8, 1);
const INITIAL_VIEWPORT_END = new Date(2026, 11, 31, 23, 59, 59);
const INITIAL_VIEWPORT_MONTH_COUNT =
  (INITIAL_VIEWPORT_END.getFullYear() - INITIAL_VIEWPORT_START.getFullYear()) * 12 +
  INITIAL_VIEWPORT_END.getMonth() -
  INITIAL_VIEWPORT_START.getMonth() +
  1;

export function getMonday(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(date.setDate(diff));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

export function formatDateStr(dateObj) {
  const y = dateObj.getFullYear();
  const m = String(dateObj.getMonth() + 1).padStart(2, '0');
  const d = String(dateObj.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function getWeekInfo(monday) {
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  const target = new Date(monday.valueOf());
  const dayNr = (monday.getDay() + 6) % 7;
  target.setDate(target.getDate() - dayNr + 3);
  const firstThursday = target.valueOf();
  target.setMonth(0, 1);
  if (target.getDay() !== 4) {
    target.setMonth(0, 1 + ((4 - target.getDay() + 7) % 7));
  }
  const weekNum = 1 + Math.round((firstThursday - target.valueOf()) / 604800000);

  const startMonth = monday.toLocaleString('en-US', { month: 'short' });
  const endMonth = sunday.toLocaleString('en-US', { month: 'short' });
  const rangeStr = startMonth === endMonth
    ? `${startMonth} ${monday.getDate()} - ${sunday.getDate()}, ${monday.getFullYear()}`
    : `${startMonth} ${monday.getDate()} - ${endMonth} ${sunday.getDate()}, ${monday.getFullYear()}`;

  return { weekNum, rangeStr };
}

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
  const [submissions, setSubmissions] = useState([]);
  const [timelineTasks, setTimelineTasks] = useState([]);
  const [timelinePhases, setTimelinePhases] = useState([]);
  const [currentMonday, setCurrentMonday] = useState(() => getMonday(new Date()));
  const [serverDate, setServerDate] = useState(null);

  const [error, setError] = useState('');
  const [tick, setTick] = useState(0);
  const weekRequestRef = useRef('');

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 60000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const fetchServerDate = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/server-date`);
        if (response.ok) {
          const data = await response.json();
          setServerDate(new Date(data.date));
        }
      } catch {
        console.warn('Could not fetch server date, using local date');
        setServerDate(new Date());
      }
    };
    fetchServerDate();
    const interval = setInterval(fetchServerDate, 300000);
    return () => clearInterval(interval);
  }, []);

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

  const loadProjectData = async (id, weekStr) => {
    const requestKey = `${id}:${weekStr}`;
    weekRequestRef.current = requestKey;
    setError('');
    // The Weekly Hours sheet is scoped to the selected week: never keep the
    // previous week's rows/status lingering under a changed week header while
    // the new week's data is loading.
    setEntries([]);
    setSubmissions([]);
    try {
      const [nodesRes, timesheetRes, submissionsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/projects/${id}/wbs-structure`, { headers: authHeaders() }),
        // source=tracking feeds this sheet exclusively from automatic Engineer
        // subtask working-time logs: only subtasks that have tracked hours are
        // returned, each as its own row.
        fetch(`${API_BASE_URL}/api/projects/${id}/timesheet?week_start=${weekStr}&source=tracking`, { headers: authHeaders() }),
        fetch(`${API_BASE_URL}/api/projects/${id}/weekly-hours-submissions?week_start=${weekStr}`, { headers: authHeaders() }),
      ]);

      if (!nodesRes.ok || !timesheetRes.ok || !submissionsRes.ok) {
        throw new Error('Failed to load project timeline data.');
      }

      const nodesData = await nodesRes.json();
      const timesheetData = await timesheetRes.json();
      const submissionsData = await submissionsRes.json();

      // Ignore any response that is no longer the week the user is viewing:
      // re-entrant callbacks (e.g. a window focus listener) may still deliver
      // an older week, so compare both the latest request AND the currently
      // displayed week before committing anything.
      if (weekRequestRef.current !== requestKey || weekStartRef.current !== weekStr) return;

      setNodes(nodesData);
      setEntries(timesheetData);
      setSubmissions(Array.isArray(submissionsData) ? submissionsData : []);

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
  };

  useEffect(() => {
    if (projectId) {
      loadProjectData(projectId, weekStartStr);
    }
  }, [projectId, weekStartStr]);

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
  }, [projectId]);

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
  }, [nodes, timelineTasks, isEngineer]);

  const { quarterTitle } = useMemo(() => {
    let minDate = null;
    let maxDate = null;

    const nodeDates = [];
    nodes.forEach((n) => {
      if (n.start_date) nodeDates.push(new Date(n.start_date));
      const ed = n.end_date || n.target_due_date;
      if (ed) nodeDates.push(new Date(ed));
    });

    const now = new Date();
    const currentMonthStart = new Date(now.getFullYear(), now.getMonth(), 1);

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
      minDate = getMonday(now);
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
  }, [nodes, project]);

  const visibleMonthColumns = useMemo(
    () => Array.from({ length: INITIAL_VIEWPORT_MONTH_COUNT }, (_, index) => {
      const colDate = new Date(INITIAL_VIEWPORT_START);
      colDate.setMonth(colDate.getMonth() + index);
      return colDate;
    }),
    [],
  );

  const todayPct = useMemo(() => {
    const today = serverDate || new Date();
    const total = INITIAL_VIEWPORT_END.getTime() - INITIAL_VIEWPORT_START.getTime();
    if (today < INITIAL_VIEWPORT_START || today > INITIAL_VIEWPORT_END || total <= 0) return null;
    const elapsed = today.getTime() - INITIAL_VIEWPORT_START.getTime();
    return Math.min(100, Math.max(0, (elapsed / total) * 100));
  }, [tick, serverDate]);

  const weekInfo = useMemo(() => getWeekInfo(currentMonday), [currentMonday]);

  const fmtHrs = (value) => {
    const number = Number(value) || 0;
    return Math.round(number * 100) / 100;
  };

  // Weekly log entries are one row per subtask; group them by engineer so the
  // main list shows each engineer exactly once, with a link to that engineer's
  // weekly log details on a dedicated page.
  const engineerGroups = useMemo(() => {
    const groups = new Map();
    entries.forEach((entry) => {
      const key = String(entry.employee_id);
      if (!groups.has(key)) {
        groups.set(key, { employee_id: entry.employee_id, employee_name: entry.employee_name, entries: [] });
      }
      groups.get(key).entries.push(entry);
    });
    // A submitted week with no tracked hours must still surface a row so a
    // lead can approve/reject it (an engineer may submit even an empty week).
    submissions.forEach((sub) => {
      const key = String(sub.employee_id);
      if (!groups.has(key)) {
        groups.set(key, { employee_id: sub.employee_id, employee_name: sub.employee_name, entries: [] });
      }
    });
    return Array.from(groups.values()).sort((a, b) =>
      (a.employee_name || '').localeCompare(b.employee_name || ''),
    );
  }, [entries, submissions]);

  const submissionByEmployee = useMemo(() => {
    const map = {};
    submissions.forEach((sub) => {
      map[String(sub.employee_id)] = sub;
    });
    return map;
  }, [submissions]);

  const groupRows = useMemo(
    () =>
      engineerGroups.map((group) => {
        const days = {};
        DAY_FIELDS.forEach((day) => {
          days[day] = group.entries.reduce((sum, entry) => sum + fmtHrs(entry[`${day}_hours`] || 0), 0);
        });
        // All seven days count: offices work different weeks (TODO N2).
        const total = DAY_FIELDS.reduce((sum, day) => sum + days[day], 0);
        return {
          employee_id: group.employee_id,
          employee_name: group.employee_name,
          entries: group.entries,
          days,
          total,
          weekStatus: (submissionByEmployee[String(group.employee_id)] || {}).status || 'not_submitted',
          // Per task: the server says whether this user has hours to review in the week, and who is still pending.
          review: submissionByEmployee[String(group.employee_id)] || {},
        };
      }),
    [engineerGroups, submissionByEmployee],
  );

  const handlePrevWeek = () => {
    const prev = new Date(currentMonday);
    prev.setDate(prev.getDate() - 7);
    setCurrentMonday(prev);
  };

  const handleNextWeek = () => {
    const next = new Date(currentMonday);
    next.setDate(next.getDate() + 7);
    setCurrentMonday(next);
  };

  const handleSubmitWeek = async () => {
    if (!projectId || !weekStartStr) return;
    try {
      setError('');
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/weekly-hours/submit`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_start_date: weekStartStr }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || 'Could not submit this week for approval.');
      }
      await loadProjectData(projectId, weekStartStr);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleWeekReview = async (employeeId, action) => {
    if (!projectId || !weekStartStr) return;
    try {
      setError('');
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/weekly-hours/${action}`, {
        method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ week_start_date: weekStartStr, employee_id: employeeId }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `Could not ${action} these weekly hours.`);
      }
      await loadProjectData(projectId, weekStartStr);
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
            <span>{isEngineer ? 'My Timesheets' : 'Gantt & Timesheets'}</span>
            <i>/</i>
            <strong>{project?.project_name || 'Select Project'}</strong>
          </div>
          <h1>Timeline Schedule &amp; Weekly Timesheet Logs</h1>
          <p>
            {isEngineer
              ? 'Review your assigned WBS schedule and log actual labor hours for the week.'
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
          {serverDate && (
            <div className="server-date-badge">
              <span>Server Date: </span>
              <strong>{serverDate.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })}</strong>
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
            <h2>Weekly Hours Logging (Week {weekInfo.weekNum}: {weekInfo.rangeStr})</h2>
            <p>
              {isEngineer
                ? 'Your automatic subtask working-time for this week, recorded from Login/Logout: the time between them counts, except while the laptop was off.'
                : isLead
                  ? 'Review engineer hours for this week, recorded automatically per subtask. Approve or reject entries in your scope.'
                  : 'Review logged engineering hours for this week.'}
            </p>
          </div>

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
                groupRows.map((group) => {
                  const groupKey = String(group.employee_id);

                  return (
                    <tr key={groupKey} className="timesheet-engineer-group-row">
                      <td className="col-engineer">
                        <Link
                          className="timesheet-task-link"
                          to={`/weekly-logs?projectId=${projectId}&employeeId=${group.employee_id}&weekStart=${weekStartStr}`}
                          title={`Open the weekly log details for ${group.employee_name}`}
                        >
                          <div className="timesheet-engineer-cell">
                            <strong>{group.employee_name}</strong>
                            <small>
                              {group.entries.length} logged subtask{group.entries.length === 1 ? '' : 's'} this week
                              {' · Open weekly log'}
                            </small>
                          </div>
                        </Link>
                      </td>

                      {DAY_FIELDS.map((day) => (
                        <td key={day} className="col-day">
                          <input
                            type="number"
                            min="0"
                            max="24"
                            step="0.5"
                            className="day-hour-input"
                            value={group.days[day] === 0 ? '' : group.days[day]}
                            placeholder="0"
                            readOnly
                            title={group.employee_name}
                          />
                        </td>
                      ))}

                      <td className="col-total">
                        <strong className="total-hours-blue">{group.total.toFixed(2)} hrs</strong>
                      </td>

                      <td className="col-approval">
                        <span className={`approval-pill ${WEEKLY_SUBMISSION_PILL[group.weekStatus]}`}>
                          {WEEKLY_SUBMISSION_LABELS[group.weekStatus]}
                        </span>
                        {isEngineer && group.entries.length > 0 && (group.weekStatus === 'not_submitted' || group.weekStatus === 'rejected') && (
                          <button type="button" className="button button-primary week-nav-btn" onClick={handleSubmitWeek}>
                            Submit for Approval
                          </button>
                        )}
                        {group.weekStatus === 'submitted' && group.review.reviewers_total > 1 && (
                          <small className="review-progress">
                            {group.review.reviewers_done} of {group.review.reviewers_total} approved
                            {group.review.waiting_on?.length > 0 && ` · waiting on ${group.review.waiting_on.join(', ')}`}
                          </small>
                        )}
                        {group.weekStatus === 'submitted' && group.review.can_review && (
                          <span className="review-actions">
                            <button
                              type="button"
                              className="review-btn review-approve"
                              onClick={() => handleWeekReview(group.employee_id, 'approve')}
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              className="review-btn review-reject"
                              onClick={() => handleWeekReview(group.employee_id, 'reject')}
                            >
                              Reject
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
)}
              </tbody>
            </table>
        </div>

        <div className="timesheet-footer">
          <div className="footer-info">
            <span>
              {isEngineer
                ? 'Hours are recorded per subtask from Login/Logout: the time between them counts, except while the laptop was off.'
                : 'Hours are tracked automatically per subtask and approved by the assigned lead.'}
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
