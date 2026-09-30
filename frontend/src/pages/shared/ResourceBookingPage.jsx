import { ChevronDown, Pencil, Search, Trash2, UserPlus, X } from 'lucide-react';
import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { useServerToday } from '../../hooks/useServerToday';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { useRejectResourceBookings } from '../../hooks/useResourceBookings';
import { bookingPlannedHours, countWorkingDays } from '../../lib/hours';

function formatMonthHeader(dateObj) {
  return dateObj.toLocaleString('en-US', { month: 'short', year: 'numeric' }).toUpperCase();
}

const BOOKING_PROJECT_COLORS = ['#1671ad', '#2b9c6c', '#b8860b', '#8a5aa8', '#c2453e', '#2d7d8a', '#d9701b', '#4a6fa5'];

function measureTextWidth(text) {
  if (typeof document === 'undefined' || !text) return 0;
  const ctx = measureTextWidth._ctx || (measureTextWidth._ctx = (() => {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    context.font = '700 10px Inter, system-ui, sans-serif';
    return context;
  })());
  return ctx.measureText(text).width;
}

function formatLongDate(dateStr) {
  if (!dateStr) return '—';
  const parsed = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateStr;
  return parsed.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
}

function money(value, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value || 0));
}

/** "Structural · Engineer II" on one line; shown once when both are the same. */
function disciplineAndRole(booking) {
  const parts = [booking.discipline, booking.role_title].filter(Boolean);
  return [...new Set(parts)].join(' · ');
}

/** Timeline with no engineers (no project selected yet). One shared value, never rebuilt. */
const EMPTY_GANTT = { engineers: [], date_range: { start: null, end: null }, count: 0 };

function statusClass(status) {
  if (status === 'Fully Booked') return 'status-full';
  if (status === 'Near Capacity') return 'status-near';
  return 'status-bench';
}

export function ResourceBookingPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { role, authHeaders, logout } = useAuth();
  const isBuHead = role === 'bu_head';

  const rawTargetId = searchParams.get('projectId') || location.state?.projectId;
  const targetProjectId = rawTargetId ? Number(rawTargetId) : null;

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [employees, setEmployees] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('All Roles');
  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('create');
  const [editingBookingId, setEditingBookingId] = useState(null);
  const [form, setForm] = useState({ employee_id: '', start_date: '', end_date: '', utilization_rate: '' });
  const [error, setError] = useState('');
  const [capError, setCapError] = useState('');
  const [rejectReason, setRejectReason] = useState(null); // null = dialog closed
  const rejectBookings = useRejectResourceBookings();
  const [notifications, setNotifications] = useState([]);
  const [ganttData, setGanttData] = useState(EMPTY_GANTT);
  const { today: serverDate } = useServerToday(); // the "today" marker follows the server's day
  const [hoveredBarId, setHoveredBarId] = useState(null);
  const [pinnedBarId, setPinnedBarId] = useState(null);
  const ganttTrackElRef = useRef(null);
  const [ganttTrackWidth, setGanttTrackWidth] = useState(0);

  const ganttTrackMeasureRef = useCallback((el) => {
    if (!el) return;
    if (el === ganttTrackElRef.current) return;
    ganttTrackElRef.current = el;
    const observe = () => {
      if (ganttTrackElRef.current === el) setGanttTrackWidth(el.clientWidth);
    };
    observe();
    const resizeObserver = new ResizeObserver(observe);
    resizeObserver.observe(el);
  }, []);


  const project = projects.find((p) => String(p.id) === String(selectedId));
  const isLead = project?.my_role === 'lead'; // a role on the selected project, not on the account
  const projectId = project?.id;

  const approvalStatus = useMemo(() => {
    if (!bookings.length) return 'draft';
    const statuses = new Set(bookings.map((b) => b.approval_status || 'draft'));
    if (statuses.size === 1 && statuses.has('approved')) return 'approved';
    if (statuses.has('pending_approval')) return 'pending_approval';
    return 'draft';
  }, [bookings]);

  const pendingNotifications = useMemo(
    () => (notifications || []).filter((n) => !n.is_read && n.notification_type === 'resource_booking_approval'),
    [notifications],
  );

  const loadNotifications = useCallback(async () => {
    if (!isBuHead) { setNotifications([]); return; }
    try {
      const response = await fetch(`${API_BASE_URL}/api/notifications`, { headers: authHeaders() });
      if (response.ok) setNotifications(await response.json());
    } catch { /* ignore */ }
  }, [isBuHead, authHeaders]);

  const loadProjectData = useCallback(async (id) => {
    try {
      const [bookingResponse, summaryResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/projects/${id}/resource-bookings`, { headers: authHeaders() }),
        fetch(`${API_BASE_URL}/api/projects/${id}/resource-summary`, { headers: authHeaders() }),
      ]);
      if (!bookingResponse.ok || !summaryResponse.ok) throw new Error('Could not load resource data.');
      setBookings(await bookingResponse.json());
      setSummary(await summaryResponse.json());
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [authHeaders]);

  // The timeline shows the selected project's engineers (with their other commitments).
  const loadGantt = useCallback(async () => {
    if (!projectId) {
      setGanttData(EMPTY_GANTT); // the same object each time, so React skips the re-render
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/resource-bookings/gantt?project_id=${projectId}`, { headers: authHeaders() });
      if (response.ok) {
        const data = await response.json();
        setGanttData(data);
      }
    } catch { /* ignore */ }
  }, [authHeaders, projectId]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error('Could not fetch projects');
        return response.json();
      })
      .then((projectData) => {
        setProjects(projectData);
        if (Array.isArray(projectData) && projectData.length > 0) {
          const selected = targetProjectId
            ? projectData.find((p) => p.id === targetProjectId)
            : projectData[0];
          setSelectedId(selected ? String(selected.id) : '');
        }
      })
      .catch((loadError) => setError(loadError.message));
  }, [targetProjectId, authHeaders]);

  useEffect(() => {
    if (targetProjectId && projects.length > 0) {
      const match = projects.find((p) => p.id === targetProjectId);
      if (match && String(match.id) !== selectedId) {
        setSelectedId(String(match.id));
      }
    }
  }, [targetProjectId, projects, selectedId]);

  useEffect(() => {
    if (projectId) loadProjectData(projectId);
    loadGantt();
  }, [projectId, loadProjectData, loadGantt]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/employees`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error('Could not load employees');
        return response.json();
      })
      .then((data) => setEmployees(data))
      .catch(() => {});
  }, [authHeaders]);

  const intervalRef = useRef(null);
  useEffect(() => {
    if (!isBuHead || !projectId) return;

    function startPolling() {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(() => {
        if (document.visibilityState === 'visible') {
          loadProjectData(projectId);
          loadGantt();
          loadNotifications();
        }
      }, 5000);
    }

    function handleVisibility() {
      if (document.visibilityState === 'visible') {
        loadProjectData(projectId);
        loadGantt();
        loadNotifications();
        startPolling();
      } else {
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    }

    document.addEventListener('visibilitychange', handleVisibility);
    startPolling();
    window.addEventListener('focus', () => {
      loadProjectData(projectId);
      loadGantt();
      loadNotifications();
    });

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('focus', () => {
        loadProjectData(projectId);
        loadGantt();
        loadNotifications();
      });
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isBuHead, projectId, loadProjectData, loadNotifications, loadGantt]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  const roles = useMemo(() => ['All Roles', ...new Set(bookings.map((booking) => booking.role_title))], [bookings]);
  const visibleBookings = bookings.filter((booking) => {
    const query = search.toLowerCase();
    const matchesSearch = !query || `${booking.employee_name} ${booking.discipline} ${booking.role_title}`.toLowerCase().includes(query);
    return matchesSearch && (roleFilter === 'All Roles' || booking.role_title === roleFilter);
  });
  const benchTip = [...bookings].sort((a, b) => Number(a.utilization_rate) - Number(b.utilization_rate))[0];

  const bookingDays = useMemo(() => countWorkingDays(form.start_date, form.end_date), [form.start_date, form.end_date]);
  const computedPlannedHours = bookingPlannedHours(form.start_date, form.end_date, form.utilization_rate);

  function openCreateModal() {
    setModalMode('create');
    setEditingBookingId(null);
    setForm({ employee_id: '', start_date: '', end_date: '', utilization_rate: '' });
    setModalOpen(true);
  }

  function openEditModal(booking) {
    setModalMode('edit');
    setEditingBookingId(booking.id);
    setForm({
      employee_id: String(booking.employee_id),
      start_date: booking.start_date || '',
      end_date: booking.end_date || '',
      utilization_rate: String(Number(booking.utilization_rate)),
    });
    setModalOpen(true);
  }

  async function deleteBooking(booking) {
    if (!projectId) return;
    if (!window.confirm('Are you sure you want to remove this resource booking?')) return;
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/resource-bookings/${booking.id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'Could not delete booking.');
      await loadProjectData(projectId);
      loadGantt();
    } catch (deleteError) {
      setError(deleteError.message);
    }
  }

  async function assignEngineer(event) {
    event.preventDefault();
    setError('');
    setCapError('');
    if (!form.employee_id) { setError('Please select an engineer.'); return; }
    if (!form.utilization_rate) { setError('Please select a booking percentage.'); return; }
    try {
      if (!form.start_date || !form.end_date) throw new Error('Give the booking a start and an end date: they decide when the engineer’s time is taken.');
      if (form.end_date < form.start_date) throw new Error('End date cannot be before start date.');
      const url = modalMode === 'edit'
        ? `${API_BASE_URL}/api/projects/${projectId}/resource-bookings/${editingBookingId}`
        : `${API_BASE_URL}/api/projects/${projectId}/resource-bookings`;
      const response = await fetch(url, {
        method: modalMode === 'edit' ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          employee_id: Number(form.employee_id),
          planned_hours: computedPlannedHours,
          utilization_rate: Number(form.utilization_rate),
          start_date: form.start_date || null,
          end_date: form.end_date || null,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        if (response.status === 401) {
          await logout();
          return;
        }
        if (response.headers.get('X-Error-Code') === 'ALLOCATION_LIMIT') {
          setCapError(body.detail || 'Allocation limit reached.');
        } else {
          setError(body.detail || 'Could not save the resource booking.');
        }
        return;
      }
      setForm({ employee_id: '', start_date: '', end_date: '', utilization_rate: '' });
      setModalOpen(false);
      setModalMode('create');
      setEditingBookingId(null);
      await loadProjectData(projectId);
      loadGantt();
    } catch (assignError) {
      setError(assignError.message);
    }
  }

  async function submitForApproval() {
    if (!projectId) return;
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/resource-bookings/submit`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const body = await response.json();
      if (response.status === 401) { await logout(); return; }
      if (!response.ok) throw new Error(body.detail || 'Could not submit for approval.');
      await Promise.all([loadProjectData(projectId), loadNotifications()]);
      loadGantt();
    } catch (submitError) {
      setError(submitError.message);
    }
  }

  async function approveAllocation() {
    if (!projectId) return;
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/resource-bookings/approve`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const body = await response.json();
      if (response.status === 401) { await logout(); return; }
      if (!response.ok) throw new Error(body.detail || 'Could not approve allocation.');
      await Promise.all([loadProjectData(projectId), loadNotifications()]);
      loadGantt();
    } catch (approveError) {
      setError(approveError.message);
    }
  }

  function closeRejectDialog() {
    rejectBookings.reset();
    setRejectReason(null);
  }

  function rejectAllocation() {
    rejectBookings.mutate(
      { projectId, reason: rejectReason.trim() },
      {
        onSuccess: async () => {
          closeRejectDialog();
          await Promise.all([loadProjectData(projectId), loadNotifications()]);
          loadGantt();
        },
      },
    );
  }

  function jumpToProject(id) {
    const match = projects.find((p) => p.id === id);
    if (match) setSelectedId(String(match.id));
  }

  async function markNotificationRead(id) {
    try {
      await fetch(`${API_BASE_URL}/api/notifications/${id}/read`, {
        method: 'POST',
        headers: authHeaders(),
      });
    } catch { /* ignore */ }
  }

  const ganttEngineers = useMemo(() => ganttData?.engineers || [], [ganttData]);
  const dateRange = ganttData?.date_range || { start: null, end: null };

  const projectColors = useMemo(() => {
    const map = {};
    ganttEngineers.forEach((engineer) => {
      (engineer.assignments || []).forEach((assignment) => {
        if (assignment.project_id != null && !(assignment.project_id in map)) {
          map[assignment.project_id] = BOOKING_PROJECT_COLORS[Object.keys(map).length % BOOKING_PROJECT_COLORS.length];
        }
      });
    });
    return map;
  }, [ganttEngineers]);

  const { monthColumns, timelineStart, timelineEnd } = useMemo(() => {
    if (!dateRange.start || !dateRange.end) return { monthColumns: [], timelineStart: null, timelineEnd: null };
    const start = new Date(`${dateRange.start}T00:00:00`);
    const end = new Date(`${dateRange.end}T23:59:59`);
    const cols = [];
    const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
    while (cursor <= end) {
      cols.push(new Date(cursor));
      cursor.setMonth(cursor.getMonth() + 1);
    }
    return { monthColumns: cols, timelineStart: start, timelineEnd: end };
  }, [dateRange.start, dateRange.end]);

  const totalSpan = timelineStart && timelineEnd ? timelineEnd.getTime() - timelineStart.getTime() : 0;

  const todayPct = useMemo(() => {
    if (!timelineStart || !timelineEnd || totalSpan <= 0) return null;
    const t = serverDate.getTime();
    if (t < timelineStart.getTime() || t > timelineEnd.getTime()) return null;
    return Math.min(100, Math.max(0, ((t - timelineStart.getTime()) / totalSpan) * 100));
  }, [serverDate, timelineStart, timelineEnd, totalSpan]);

  const ganttRows = useMemo(() => ganttEngineers.map((engineer) => {
    const withDates = (engineer.assignments || []).filter((a) => a.has_date_range);
    const noDates = (engineer.assignments || []).filter((a) => !a.has_date_range);
    const lanes = [];
    const trackPx = ganttTrackWidth > 0 ? ganttTrackWidth : Infinity;
    const placed = withDates.map((assignment) => {
      const start = new Date(`${assignment.start_date}T00:00:00`).getTime();
      const end = new Date(`${assignment.end_date}T23:59:59`).getTime();
      const laneIndex = lanes.findIndex((lane) => lane.every((booked) => booked.end < start));
      const lane = laneIndex === -1 ? lanes.length : laneIndex;
      if (laneIndex === -1) lanes.push([{ start, end }]);
      else lanes[laneIndex].push({ start, end });
      const leftPct = Math.max(0, ((start - timelineStart.getTime()) / totalSpan) * 100);
      const widthPct = Math.min(100 - leftPct, Math.max(2, ((end - start) / totalSpan) * 100));
      const barPx = (widthPct / 100) * trackPx;
      const labelOverflow = ganttTrackWidth > 0 && (measureTextWidth(assignment.project_name) + 6 > barPx);
      return { ...assignment, lane, start, end, leftPct, widthPct, labelOverflow };
    });
    return { ...engineer, assignments: placed, noDates, laneCount: Math.max(1, lanes.length) };
  }), [ganttEngineers, ganttTrackWidth, timelineStart, totalSpan]);

  return (
    <main className="resource-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb"><span>Resource Planning</span><i>/</i><span>Capacity Allocation</span><i>/</i><strong>{project?.project_name || 'Select Project'}</strong></div>
          <h1>Resource Booking &amp; Bench Capacity View</h1>
          <p>Allocate engineering teams against target baseline hours, manage billing rates, and discover unallocated bench capacity.</p>
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
      {isBuHead && pendingNotifications.length > 0 && (
        <div className="resource-notices">
          <strong>{pendingNotifications.length} pending approval{pendingNotifications.length > 1 ? 's' : ''}</strong>
          {pendingNotifications.map((notification) => {
            const matchProject = projects.find((p) => p.id === notification.project_id);
            return (
              <div className="resource-notice" key={notification.id}>
                <div>
                  <span className="notice-dot" />
                  <strong>{notification.title}</strong>
                  <span>{notification.message}</span>
                  <small>{matchProject ? matchProject.project_name : notification.actor_name ? `Submitted by ${notification.actor_name}` : ''}</small>
                </div>
                <div className="notice-actions">
                  {matchProject && (
                    <button className="button button-secondary button-small" type="button" onClick={() => jumpToProject(matchProject.id)}>Open Project</button>
                  )}
                  <button className="link-button" type="button" onClick={() => markNotificationRead(notification.id)}>Dismiss</button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div className={`summary-grid${isLead ? ' lead-summary-grid' : ''}`}>
        <div className="summary-card"><span className="summary-label">Target Baseline Hours</span><strong>{summary?.target_baseline_hours ?? 0}<small> Hrs</small></strong><span className="summary-caption">Commercial Limit</span></div>
        <div className="summary-card"><span className="summary-label">Total Booked Hours</span><strong className="blue-value">{summary?.total_booked_hours ?? 0}<small> Hrs</small></strong><span className="summary-caption blue-caption">{Number(summary?.allocated_pct || 0).toFixed(0)}% Allocated</span></div>
        {!isLead && <div className="summary-card"><span className="summary-label">Planned Labor Cost</span><strong>{money(summary?.planned_labor_cost, summary?.contract_currency)} </strong><span className="summary-caption green-caption">Within {money(summary?.contract_value, summary?.contract_currency)} Limit</span></div>}
        <div className="summary-card bench-card"><span className="summary-label">Available Bench Engineers</span><strong>{summary?.available_bench_engineers ?? 0}<small> Engineers</small></strong><span className="summary-caption">Partial/Unassigned</span></div>
      </div>

      <section className="allocation-card">
        <div className="allocation-header">
          <div>
            <h2>Project Team Allocation &amp; Bench Roster</h2>
            <p>Assigned resources and utilization against the project baseline.</p>
          </div>
          {isLead && (
            <button className="button button-primary" type="button" onClick={openCreateModal}>
              <UserPlus size={16} /> Assign Engineer
            </button>
          )}
        </div>
        <div className="resource-toolbar"><div className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search engineer or discipline..." /></div><div className="role-filter"><select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>{roles.map((roleOption) => <option key={roleOption}>{roleOption}</option>)}</select><ChevronDown size={15} /></div></div>
        <div className="resource-table-wrap"><table className="resource-table"><thead><tr><th>RESOURCE NAME</th><th>MEP DISCIPLINE &amp; ROLE</th><th>PLANNED HRS</th>{!isLead && (<><th>COST/HR ({summary?.contract_currency || 'USD'})</th><th>TOTAL COST ({summary?.contract_currency || 'USD'})</th></>) }<th>UTILIZATION RATE</th><th>BENCH STATUS</th>{isLead && <th aria-label="Actions" />}</tr></thead><tbody>{visibleBookings.map((booking) => <tr key={booking.id}><td className="resource-name-cell"><strong>{booking.employee_name}</strong>{booking.employee_code ? ` (${booking.employee_code})` : ''}</td><td className="resource-name-cell">{disciplineAndRole(booking)}</td><td>{booking.planned_hours} Hrs</td>{!isLead && (<><td>{money(booking.cost_per_hour, summary?.contract_currency)}</td><td><strong>{money(booking.total_cost, summary?.contract_currency)}</strong></td></>) }<td><div className="utilization"><div><span style={{ width: `${booking.utilization_rate}%` }} className={statusClass(booking.bench_status)} /></div><strong>{Number(booking.utilization_rate).toFixed(0)}%</strong></div></td><td><span className={`status-pill ${statusClass(booking.bench_status)}`}>{booking.bench_status}</span></td>{isLead && (<td className="booking-actions"><button className="icon-action" type="button" aria-label="Edit booking" title="Edit booking" onClick={() => openEditModal(booking)}><Pencil size={14} /></button><button className="icon-action icon-action-danger" type="button" aria-label="Delete booking" title="Delete booking" onClick={() => deleteBooking(booking)}><Trash2 size={14} /></button></td>)}</tr>)}</tbody></table></div>

        <div className="bench-tip">
          <div>
            <strong>{isBuHead ? 'Bench Optimization Tip (BU Head View):' : 'Bench Optimization Tip (Lead View):'}</strong>
            <p>{benchTip ? `${benchTip.employee_name} is currently sitting at ${100 - Number(benchTip.utilization_rate)}% bench capacity. Consider reassigning hours to maximize billable efficiency.` : 'Assign an engineer to see bench optimization guidance.'}</p>
          </div>
          {isBuHead && (
            <button className="button button-tip" type="button">Reallocate Bench</button>
          )}
        </div>

        <div className="allocation-footer">
          <span>Displaying {bookings.length} of {employees.length} assigned engineers across {new Set(bookings.map((booking) => booking.discipline)).size} MEP disciplines</span>
          {isLead ? (
            <button
              className="button button-primary"
              type="button"
              disabled={approvalStatus === 'pending_approval' || approvalStatus === 'approved' || bookings.length === 0}
              onClick={submitForApproval}
            >
              {approvalStatus === 'pending_approval' ? 'Submitted — Pending Approval' : approvalStatus === 'approved' ? 'Approved' : 'Submit for Approval'}
            </button>
          ) : isBuHead ? (
            <div className="booking-decision">
              {approvalStatus === 'pending_approval' && (
                <button className="button button-secondary" type="button" onClick={() => setRejectReason('')}>
                  Reject
                </button>
              )}
              <button
                className={`button button-primary${approvalStatus === 'approved' ? ' is-done' : ''}`}
                type="button"
                style={{ background: approvalStatus === 'approved' ? '#277551' : '#b8860b', borderColor: approvalStatus === 'approved' ? '#277551' : '#b8860b' }}
                disabled={approvalStatus !== 'pending_approval'}
                onClick={approveAllocation}
              >
                {approvalStatus === 'approved' ? 'Approved' : 'Approve'}
              </button>
            </div>
          ) : null}
        </div>
      </section>

      <section className="allocation-card gantt-card assignment-gantt-card">
        <div className="allocation-header">
          <div>
            <h2>Engineer Assignment Timeline</h2>
            <p>Each engineer's real project assignments across time — bars on the same row show concurrent commitments.</p>
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
            <div className="gantt-task-name-header">Engineer</div>
            <div className="gantt-timeline-header">
              {monthColumns.map((colDate, idx) => (
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
            {ganttRows.length === 0 ? (
              <div className="gantt-empty-state">
                {isLead
                  ? 'No engineers are booked on your projects yet — real assignments will appear here.'
                  : 'No engineers are booked yet — real assignments will appear here.'}
              </div>
            ) : (
              ganttRows.map((engineer) => (
                <div key={engineer.employee_id} className="gantt-row">
                  <div className="gantt-task-info">
                    <strong>{engineer.name}</strong>
                    <small>{engineer.employee_code} · {engineer.discipline || engineer.role_title} · {engineer.total_allocation_pct}% allocated</small>
                    {engineer.noDates.length > 0 && (
                      <small className="no-date-hint">+ {engineer.noDates.length} booking{engineer.noDates.length > 1 ? 's' : ''} without dates</small>
                    )}
                  </div>
                  <div className="gantt-row-timeline" style={{ height: engineer.laneCount * 30 + 8 }} ref={ganttTrackMeasureRef}>
                    <div className="gantt-month-grid">
                      {monthColumns.map((_, idx) => (
                        <div key={idx} className="gantt-grid-cell" />
                      ))}
                    </div>
                    {todayPct !== null && (
                      <div className="gantt-today-line-segment" style={{ left: `${todayPct}%` }} />
                    )}
                    {engineer.assignments.map((assignment) => {
                      const isActive = hoveredBarId === assignment.booking_id || pinnedBarId === assignment.booking_id;
                      return (
                        <div
                          key={assignment.booking_id}
                          className={`gantt-bar-slot${isActive ? ' gantt-bar-active' : ''}`}
                          role="button"
                          tabIndex={0}
                          aria-label={`${engineer.name} on ${assignment.project_name}: ${formatLongDate(assignment.start_date)} to ${formatLongDate(assignment.end_date)}`}
                          onMouseEnter={() => setHoveredBarId(assignment.booking_id)}
                          onMouseLeave={() => setHoveredBarId((id) => (id === assignment.booking_id ? null : id))}
                          onClick={(event) => {
                            event.stopPropagation();
                            setPinnedBarId((id) => (id === assignment.booking_id ? null : assignment.booking_id));
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault();
                              setPinnedBarId((id) => (id === assignment.booking_id ? null : assignment.booking_id));
                            }
                          }}
                          style={{
                            left: `${assignment.leftPct}%`,
                            width: `${assignment.widthPct}%`,
                            top: assignment.lane * 30 + 5,
                          }}
                        >
                          <div className="gantt-bar gantt-bar-booking" style={{ background: projectColors[assignment.project_id] }}>
                            {!assignment.labelOverflow && (
                              <span className="gantt-bar-label">{assignment.project_name}</span>
                            )}
                          </div>
                          {assignment.labelOverflow && (
                            <span className="gantt-bar-label gantt-bar-label-outside">{assignment.project_name}</span>
                          )}
                          {isActive && (
                            <div className="gantt-bar-tooltip">
                              <span className="gantt-tooltip-title">{assignment.project_name}</span>
                              <span className="gantt-tooltip-row"><span>Start</span><strong>{formatLongDate(assignment.start_date)}</strong></span>
                              <span className="gantt-tooltip-row"><span>End</span><strong>{formatLongDate(assignment.end_date)}</strong></span>
                              <span className="gantt-tooltip-row"><span>Allocation</span><strong>{assignment.utilization_rate}%</strong></span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {engineer.assignments.length === 0 && (
                      <div className="gantt-bar gantt-bar-empty gantt-bar-no-dates" style={{ left: 0, width: '100%' }}>
                        No date range set
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      {isLead && modalOpen && (
        <div className="modal-backdrop" role="presentation">
          <form className="booking-modal" onSubmit={assignEngineer}>
            <div className="modal-heading"><h2>{modalMode === 'edit' ? 'Edit Resource Booking' : 'Assign Engineer'}</h2><button type="button" aria-label="Close" onClick={() => setModalOpen(false)}><X size={18} /></button></div>
            <label className="field"><span className="field-label">Engineer *</span><select value={form.employee_id} onChange={(event) => setForm({ ...form, employee_id: event.target.value })} required><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name} · {employee.role_title}</option>)}</select></label>
            <label className="field"><span className="field-label">Start Date *</span><input type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} required /></label>
            <label className="field"><span className="field-label">End Date *</span><input type="date" min={form.start_date || undefined} value={form.end_date} onChange={(event) => setForm({ ...form, end_date: event.target.value })} required /></label>
            <p className="wbs-field-hint">Planned Hours: {computedPlannedHours} Hrs ({bookingDays} working days × 8 hrs/day × {Number(form.utilization_rate) || 0}%)</p>
            <label className="field"><span className="field-label">Booking % *</span><select value={form.utilization_rate} onChange={(event) => setForm({ ...form, utilization_rate: event.target.value })} required><option value="">Select booking %</option><option value="20">20%</option><option value="40">40%</option><option value="60">60%</option><option value="80">80%</option><option value="100">100%</option></select></label>
            <div className="modal-actions"><button className="button button-secondary" type="button" onClick={() => setModalOpen(false)}>Cancel</button><button className="button button-primary" type="submit">{modalMode === 'edit' ? 'Save Changes' : 'Assign Engineer'}</button></div>
          </form>
        </div>
      )}

      {isLead && capError && (
        <div className="modal-backdrop" role="presentation">
          <div className="booking-modal cap-error-modal">
            <div className="modal-heading"><h2>Allocation Limit Reached</h2><button type="button" aria-label="Close" onClick={() => setCapError('')}><X size={18} /></button></div>
            <p className="cap-error-message">{capError}</p>
            <div className="modal-actions"><button className="button button-primary" type="button" onClick={() => setCapError('')}>OK</button></div>
          </div>
        </div>
      )}
      {rejectReason !== null && (
        <ConfirmDialog
          title="Reject Resource Booking"
          confirmLabel="Reject"
          busyLabel="Rejecting…"
          busy={rejectBookings.isPending}
          confirmDisabled={!rejectReason.trim()}
          error={rejectBookings.error}
          onConfirm={rejectAllocation}
          onCancel={closeRejectDialog}
        >
          <p className="confirm-modal-text">Send this submission back to the Lead?</p>
          <p className="confirm-modal-subtext">
            Every booking returns to draft so the Lead can adjust it and submit again. The Lead sees your reason.
          </p>
          <label className="booking-reject-reason">
            <span>Reason for the Lead</span>
            <textarea
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              placeholder="e.g. Arjun is needed on Hotel Tower in September"
              rows={3}
            />
          </label>
        </ConfirmDialog>
      )}
    </main>
  );
}
