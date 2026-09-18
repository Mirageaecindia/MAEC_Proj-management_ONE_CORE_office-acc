import { ChevronDown, ChevronUp, ChevronLeft, ChevronRight, ArrowRight } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const DAY_FIELDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

const WBS_PHASES = ['Space Planning', 'STR Coordination', 'ID Coordination', 'BoH Area RCP Coordination'];
const INITIAL_VIEWPORT_START = new Date(2026, 8, 1);
const INITIAL_VIEWPORT_END = new Date(2026, 11, 31, 23, 59, 59);
const INITIAL_VIEWPORT_MONTH_COUNT =
  (INITIAL_VIEWPORT_END.getFullYear() - INITIAL_VIEWPORT_START.getFullYear()) * 12 +
  INITIAL_VIEWPORT_END.getMonth() -
  INITIAL_VIEWPORT_START.getMonth() +
  1;

function getMonday(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  const monday = new Date(date.setDate(diff));
  monday.setHours(0, 0, 0, 0);
  return monday;
}

function formatDateStr(dateObj) {
  const y = dateObj.getFullYear();
  const m = String(dateObj.getMonth() + 1).padStart(2, '0');
  const d = String(dateObj.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function getWeekInfo(monday) {
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

export function TimelineLogsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { role, authHeaders } = useAuth();
  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;

  const [projects, setProjects] = useState([]);
  const [projectIndex, setProjectIndex] = useState(0);
  const [nodes, setNodes] = useState([]);
  const [entries, setEntries] = useState([]);
  const [currentMonday, setCurrentMonday] = useState(() => getMonday(new Date()));
  const [serverDate, setServerDate] = useState(null);

  const [rowHours, setRowHours] = useState({});
  const [error, setError] = useState('');
  const [savingKey, setSavingKey] = useState('');
  const [tick, setTick] = useState(0);

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
      } catch (err) {
        console.warn('Could not fetch server date, using local date');
        setServerDate(new Date());
      }
    };
    fetchServerDate();
    const interval = setInterval(fetchServerDate, 300000);
    return () => clearInterval(interval);
  }, []);

  const project = projects[projectIndex];
  const projectId = project?.id;
  const isEngineer = role === 'engineer';
  const isLead = role === 'lead';

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error('Could not fetch projects');
        return res.json();
      })
      .then((data) => {
        setProjects(data);
        if (Array.isArray(data) && data.length > 0) {
          if (targetProjectId) {
            const matchIdx = data.findIndex((p) => p.id === targetProjectId);
            if (matchIdx >= 0) {
              setProjectIndex(matchIdx);
              return;
            }
          }
          setProjectIndex(0);
        }
      })
      .catch((err) => setError(err.message));
  }, [targetProjectId, authHeaders]);

  const weekStartStr = useMemo(() => formatDateStr(currentMonday), [currentMonday]);

  const loadProjectData = async (id, weekStr) => {
    try {
      setError('');
      const [nodesRes, timesheetRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/projects/${id}/wbs-structure`, { headers: authHeaders() }),
        fetch(`${API_BASE_URL}/api/projects/${id}/timesheet?week_start=${weekStr}`, { headers: authHeaders() }),
      ]);

      if (!nodesRes.ok || !timesheetRes.ok) {
        throw new Error('Failed to load project timeline data.');
      }

      const nodesData = await nodesRes.json();
      const timesheetData = await timesheetRes.json();

      setNodes(nodesData);
      setEntries(timesheetData);

      const initialMap = {};
      timesheetData.forEach((entry) => {
        const key = `${entry.employee_id}_${entry.task_id}`;
        initialMap[key] = {
          id: entry.id,
          mon: Number(entry.mon_hours || 0),
          tue: Number(entry.tue_hours || 0),
          wed: Number(entry.wed_hours || 0),
          thu: Number(entry.thu_hours || 0),
          fri: Number(entry.fri_hours || 0),
          sat: Number(entry.sat_hours || 0),
          sun: Number(entry.sun_hours || 0),
          approval_status: entry.approval_status || 'pending_review',
        };
      });
      setRowHours(initialMap);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    if (projectId) {
      loadProjectData(projectId, weekStartStr);
    }
  }, [projectId, weekStartStr]);

  const phaseRows = useMemo(() => {
    const phaseMap = {};
    WBS_PHASES.forEach((phase) => {
      phaseMap[phase] = { phase, count: 0 };
    });
    if (nodes && nodes.length > 0) {
      nodes.forEach((node) => {
        const phaseName = node.phase || 'Space Planning';
        if (phaseMap[phaseName]) {
          phaseMap[phaseName].count += 1;
        } else {
          phaseMap[phaseName] = { phase: phaseName, count: 1 };
        }
      });
    }
    return Object.values(phaseMap).map((p) => ({ ...p, isRealData: p.count > 0 }));
  }, [nodes]);

  const { monthColumns, timelineStart, timelineEnd, quarterTitle } = useMemo(() => {
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
      monthColumns: cols,
      timelineStart: start,
      timelineEnd: end,
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

  const handleHourChange = (employeeId, taskId, day, val) => {
    const key = `${employeeId}_${taskId}`;
    const num = Math.min(24, Math.max(0, Number(val) || 0));
    setRowHours((prev) => ({
      ...prev,
      [key]: { ...prev[key], [day]: num },
    }));
  };

  const handleBlur = async (employeeId, taskId) => {
    const key = `${employeeId}_${taskId}`;
    const row = rowHours[key];
    if (!row) return;

    setSavingKey(key);
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/timesheet-entries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          task_id: taskId,
          week_start_date: weekStartStr,
          mon_hours: row.mon || 0,
          tue_hours: row.tue || 0,
          wed_hours: row.wed || 0,
          thu_hours: row.thu || 0,
          fri_hours: row.fri || 0,
          sat_hours: row.sat || 0,
          sun_hours: row.sun || 0,
        }),
      });

      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail || 'Could not save timesheet entry');
      }

      setRowHours((prev) => ({
        ...prev,
        [key]: {
          ...prev[key],
          id: body.id,
          approval_status: body.approval_status,
        },
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingKey('');
    }
  };

  const handleReview = async (entryId, action) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/time-log-entries/${entryId}/${action}`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || 'Could not update approval');
      }
      await loadProjectData(projectId, weekStartStr);
    } catch (err) {
      setError(err.message);
    }
  };

  const totalSpan = timelineEnd.getTime() - timelineStart.getTime();

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

        <div className="project-switcher">
          <span>Project Name</span>
          <div className="project-pill-box">
            <span className="project-pill-name" title={project?.project_name}>
              {project?.project_name || 'No projects yet — create one first'}
            </span>
            <div className="project-stepper-arrows">
              <button
                type="button"
                aria-label="Previous project"
                disabled={projectIndex === 0}
                onClick={() => setProjectIndex((index) => index - 1)}
              >
                <ChevronUp size={12} />
              </button>
              <button
                type="button"
                aria-label="Next project"
                disabled={projectIndex >= projects.length - 1}
                onClick={() => setProjectIndex((index) => index + 1)}
              >
                <ChevronDown size={12} />
              </button>
            </div>
          </div>
        </div>
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
                if (row.isRealData && row.start_date && row.end_date && totalSpan > 0) {
                  const tStart = new Date(row.start_date);
                  const tEnd = new Date(row.end_date);
                  if (!isNaN(tStart)) {
                    leftPct = Math.max(0, ((tStart.getTime() - timelineStart.getTime()) / totalSpan) * 100);
                  }
                  if (!isNaN(tEnd)) {
                    widthPct = Math.max(4, Math.min(100, ((tEnd.getTime() - timelineStart.getTime()) / totalSpan) * 100) - leftPct);
                  }
                }

                return (
                  <div key={row.phase} className="gantt-row">
                    <div className="gantt-task-info">
                      <strong>{row.phase}</strong>
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
                      <div className="gantt-bar gantt-bar-empty" style={{ left: `${leftPct}%`, width: `${widthPct}%` }}>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </section>

      <section className="allocation-card timesheet-card">
        <div className="allocation-header timesheet-header">
          <div>
            <h2>Weekly Hours Logging (Week {weekInfo.weekNum}: {weekInfo.rangeStr})</h2>
            <p>
              {isEngineer
                ? 'Log your daily engineering hours per assigned WBS task for this week.'
                : isLead
                  ? 'Review engineer hours for this week. Approve or reject entries in your scope.'
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
              {entries.length === 0 ? (
                <tr>
                  <td colSpan={10} className="timesheet-empty-cell">
                    {nodes.filter((n) => n.assigned_engineer_id).length === 0
                      ? 'No engineer-assigned WBS nodes in this project yet.'
                      : 'No hours logged for this week yet.'}
                  </td>
                </tr>
              ) : (
                entries.map((entry) => {
                  const key = `${entry.employee_id}_${entry.task_id}`;
                  const row = rowHours[key] || {
                    mon: Number(entry.mon_hours || 0),
                    tue: Number(entry.tue_hours || 0),
                    wed: Number(entry.wed_hours || 0),
                    thu: Number(entry.thu_hours || 0),
                    fri: Number(entry.fri_hours || 0),
                    sat: Number(entry.sat_hours || 0),
                    sun: Number(entry.sun_hours || 0),
                    approval_status: entry.approval_status || 'pending_review',
                  };

                  const totalHrs = DAY_FIELDS.reduce((sum, day) => sum + Number(row[day] || 0), 0);
                  const isSaving = savingKey === key;
                  const isApproved = row.approval_status === 'approved';
                  const isRejected = row.approval_status === 'rejected';

                  return (
                    <tr key={key}>
                      <td className="col-engineer">
                        <div className="timesheet-engineer-cell">
                          <strong>{entry.employee_name}</strong>
                          <small>
                            {entry.wbs_code ? `${entry.wbs_code} ` : ''}
                            {entry.task_name}
                          </small>
                        </div>
                      </td>

                      {DAY_FIELDS.map((day) => (
                        <td key={day} className="col-day">
                          <input
                            type="number"
                            min="0"
                            max="24"
                            step="0.5"
                            className="day-hour-input"
                            value={row[day] === 0 ? '' : row[day]}
                            placeholder="0"
                            disabled={!isEngineer}
                            onChange={(e) =>
                              handleHourChange(entry.employee_id, entry.task_id, day, e.target.value)
                            }
                            onBlur={() => handleBlur(entry.employee_id, entry.task_id)}
                          />
                        </td>
                      ))}

                      <td className="col-total">
                        <strong className="total-hours-blue">{totalHrs.toFixed(1)} hrs</strong>
                      </td>

                      <td className="col-approval">
                        {(isApproved || isLead) && (
                          <span
                            className={`approval-pill ${
                              isApproved ? 'status-approved' : isRejected ? 'status-rejected' : 'status-pending'
                            }`}
                          >
                            {isApproved ? 'Approved' : isRejected ? 'Rejected' : 'Pending Review'}
                          </span>
                        )}
                        {isLead && !isApproved && !isRejected && (
                          <span className="review-actions">
                            <button type="button" className="review-btn review-approve" onClick={() => handleReview(entry.id, 'approve')}>Approve</button>
                            <button type="button" className="review-btn review-reject" onClick={() => handleReview(entry.id, 'reject')}>Reject</button>
                          </span>
                        )}
                        {isSaving && <small className="saving-tag">Saving...</small>}
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
                ? 'Hour edits are saved automatically when you leave a field. Changes are sent to your lead for approval.'
                : 'Hours are submitted by engineers and approved by the assigned lead.'}
            </span>
          </div>
          <button
            type="button"
            className="button button-primary button-next"
            onClick={() => navigate(role === 'bu_head' ? '/executive-dashboard' : role === 'engineer' ? '/engineer-performance' : '/wbs-structure')}
          >
            NEXT <ArrowRight size={16} />
          </button>
        </div>
      </section>
    </main>
  );
}
