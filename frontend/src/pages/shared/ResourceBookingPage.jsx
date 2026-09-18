import { ChevronDown, ChevronUp, Search, UserPlus, X } from 'lucide-react';
import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = 'http://localhost:8000';

function money(value, currency = 'USD') {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value || 0));
}

function initials(name) {
  return name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase();
}

function statusClass(status) {
  if (status === 'Fully Booked') return 'status-full';
  if (status === 'Near Capacity') return 'status-near';
  return 'status-bench';
}

export function ResourceBookingPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { role, authHeaders } = useAuth();
  const isLead = role === 'lead';
  const isBuHead = role === 'bu_head';

  const rawTargetId = searchParams.get('projectId') || location.state?.projectId;
  const targetProjectId = rawTargetId ? Number(rawTargetId) : null;

  const [projects, setProjects] = useState([]);
  const [projectIndex, setProjectIndex] = useState(0);
  const [employees, setEmployees] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [summary, setSummary] = useState(null);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('All Roles');
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({ employee_id: '', planned_hours: '', utilization_rate: '' });
  const [error, setError] = useState('');
  const [notifications, setNotifications] = useState([]);

  const project = projects[projectIndex];
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
  }, []);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error('Could not fetch projects');
        return response.json();
      })
      .then((projectData) => {
        setProjects(projectData);
        if (Array.isArray(projectData) && projectData.length > 0) {
          if (targetProjectId) {
            const matchIdx = projectData.findIndex((p) => p.id === targetProjectId);
            if (matchIdx >= 0) {
              setProjectIndex(matchIdx);
              return;
            }
          }
          setProjectIndex(0);
        }
      })
      .catch((loadError) => setError(loadError.message));
  }, [targetProjectId]);

  useEffect(() => {
    if (targetProjectId && projects.length > 0) {
      const matchIdx = projects.findIndex((p) => p.id === targetProjectId);
      if (matchIdx >= 0 && matchIdx !== projectIndex) {
        setProjectIndex(matchIdx);
      }
    }
  }, [targetProjectId, projects, projectIndex]);

  useEffect(() => {
    if (projectId) loadProjectData(projectId);
  }, [projectId, loadProjectData]);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/employees`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error('Could not load employees');
        return response.json();
      })
      .then((data) => setEmployees(data))
      .catch(() => {});
  }, []);

  const intervalRef = useRef(null);
  useEffect(() => {
    if (!isBuHead || !projectId) return;

    function startPolling() {
      if (intervalRef.current) clearInterval(intervalRef.current);
      intervalRef.current = setInterval(() => {
        if (document.visibilityState === 'visible') {
          loadProjectData(projectId);
          loadNotifications();
        }
      }, 5000);
    }

    function handleVisibility() {
      if (document.visibilityState === 'visible') {
        loadProjectData(projectId);
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
      loadNotifications();
    });

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      window.removeEventListener('focus', () => {
        loadProjectData(projectId);
        loadNotifications();
      });
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isBuHead, projectId, loadProjectData, loadNotifications]);

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

  async function assignEngineer(event) {
    event.preventDefault();
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/resource-bookings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          employee_id: Number(form.employee_id),
          planned_hours: Number(form.planned_hours),
          utilization_rate: Number(form.utilization_rate),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'Could not assign engineer.');
      setForm({ employee_id: '', planned_hours: '', utilization_rate: '' });
      setModalOpen(false);
      await loadProjectData(projectId);
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
      if (!response.ok) throw new Error(body.detail || 'Could not submit for approval.');
      await Promise.all([loadProjectData(projectId), loadNotifications()]);
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
      if (!response.ok) throw new Error(body.detail || 'Could not approve allocation.');
      await Promise.all([loadProjectData(projectId), loadNotifications()]);
    } catch (approveError) {
      setError(approveError.message);
    }
  }

  function jumpToProject(id) {
    const matchIndex = projects.findIndex((p) => p.id === id);
    if (matchIndex >= 0) setProjectIndex(matchIndex);
  }

  async function markNotificationRead(id) {
    try {
      await fetch(`${API_BASE_URL}/api/notifications/${id}/read`, {
        method: 'POST',
        headers: authHeaders(),
      });
    } catch { /* ignore */ }
  }

  return (
    <main className="resource-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb"><span>Resource Planning</span><i>/</i><span>Capacity Allocation</span><i>/</i><strong>{project?.project_name || 'Select Project'}</strong></div>
          <h1>Resource Booking &amp; Bench Capacity View</h1>
          <p>Allocate engineering teams against target baseline hours, manage billing rates, and discover unallocated bench capacity.</p>
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
      <div className="summary-grid">
        <div className="summary-card"><span className="summary-label">Target Baseline Hours</span><strong>{summary?.target_baseline_hours ?? 0}<small> Hrs</small></strong><span className="summary-caption">Commercial Limit</span></div>
        <div className="summary-card"><span className="summary-label">Total Booked Hours</span><strong className="blue-value">{summary?.total_booked_hours ?? 0}<small> Hrs</small></strong><span className="summary-caption blue-caption">{Number(summary?.allocated_pct || 0).toFixed(0)}% Allocated</span></div>
        <div className="summary-card"><span className="summary-label">Planned Labor Cost</span><strong>{money(summary?.planned_labor_cost, summary?.contract_currency)} </strong><span className="summary-caption green-caption">Within {money(summary?.contract_value, summary?.contract_currency)} Limit</span></div>
        <div className="summary-card bench-card"><span className="summary-label">Available Bench Engineers</span><strong>{summary?.available_bench_engineers ?? 0}<small> Engineers</small></strong><span className="summary-caption">Partial/Unassigned</span></div>
      </div>

      <section className="allocation-card">
        <div className="allocation-header">
          <div>
            <h2>Project Team Allocation &amp; Bench Roster</h2>
            <p>Assigned resources and utilization against the project baseline.</p>
          </div>
          {isLead && (
            <button className="button button-primary" type="button" onClick={() => setModalOpen(true)}>
              <UserPlus size={16} /> Assign Engineer
            </button>
          )}
        </div>
        <div className="resource-toolbar"><div className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search engineer or discipline..." /></div><div className="role-filter"><select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>{roles.map((roleOption) => <option key={roleOption}>{roleOption}</option>)}</select><ChevronDown size={15} /></div></div>
        <div className="resource-table-wrap"><table className="resource-table"><thead><tr><th>RESOURCE NAME</th><th>MEP DISCIPLINE &amp; ROLE</th><th>PLANNED HRS</th><th>COST/HR ({summary?.contract_currency || 'USD'})</th><th>TOTAL COST ({summary?.contract_currency || 'USD'})</th><th>UTILIZATION RATE</th><th>BENCH STATUS</th></tr></thead><tbody>{visibleBookings.map((booking) => <tr key={booking.id}><td><div className="resource-name"><span>{initials(booking.employee_name)}</span><strong>{booking.employee_name}</strong><small>{booking.employee_code}</small></div></td><td><strong>{booking.discipline}</strong><small>{booking.role_title}</small></td><td>{booking.planned_hours} Hrs</td><td>{money(booking.cost_per_hour, summary?.contract_currency)}</td><td><strong>{money(booking.total_cost, summary?.contract_currency)}</strong></td><td><div className="utilization"><div><span style={{ width: `${booking.utilization_rate}%` }} className={statusClass(booking.bench_status)} /></div><strong>{Number(booking.utilization_rate).toFixed(0)}%</strong></div></td><td><span className={`status-pill ${statusClass(booking.bench_status)}`}>{booking.bench_status}</span></td></tr>)}</tbody></table></div>

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
            <button
              className="button button-primary"
              type="button"
              style={{ background: approvalStatus === 'approved' ? '#277551' : '#b8860b', borderColor: approvalStatus === 'approved' ? '#277551' : '#b8860b' }}
              disabled={approvalStatus !== 'pending_approval'}
              onClick={approveAllocation}
            >
              {approvalStatus === 'approved' ? 'Approved' : 'Approve'}
            </button>
          ) : null}
        </div>
      </section>

      {isLead && modalOpen && (
        <div className="modal-backdrop" role="presentation">
          <form className="booking-modal" onSubmit={assignEngineer}>
            <div className="modal-heading"><h2>Assign Engineer</h2><button type="button" aria-label="Close" onClick={() => setModalOpen(false)}><X size={18} /></button></div>
            <label className="field"><span className="field-label">Engineer *</span><select value={form.employee_id} onChange={(event) => setForm({ ...form, employee_id: event.target.value })} required><option value="">Select employee</option>{employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name} · {employee.role_title}</option>)}</select></label>
            <label className="field"><span className="field-label">Planned Hours *</span><input type="number" min="1" value={form.planned_hours} onChange={(event) => setForm({ ...form, planned_hours: event.target.value })} required /></label>
            <label className="field"><span className="field-label">Utilization Rate (%) *</span><input type="number" min="0" max="100" step="0.01" value={form.utilization_rate} onChange={(event) => setForm({ ...form, utilization_rate: event.target.value })} required /></label>
            <div className="modal-actions"><button className="button button-secondary" type="button" onClick={() => setModalOpen(false)}>Cancel</button><button className="button button-primary" type="submit">Assign Engineer</button></div>
          </form>
        </div>
      )}
    </main>
  );
}
