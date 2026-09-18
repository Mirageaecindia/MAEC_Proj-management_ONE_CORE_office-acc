import { ChevronDown, ChevronUp } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = 'http://localhost:8000';

function completionText(phaseCompletion) {
  const entries = Object.entries(phaseCompletion || {});
  if (entries.length === 0) return '—';
  return entries.map(([phase, stats]) => `${phase}: ${stats.completed}/${stats.total}`).join(', ');
}

function statusPill(status) {
  const cls = status === 'Completed'
    ? 'status-approved'
    : status === 'In Progress'
      ? 'status-inprogress'
      : status === 'Not Started'
        ? 'status-pending'
        : 'status-none';
  return <span className={`approval-pill ${cls}`}>{status || '—'}</span>;
}

function EngineerRows({ engineer }) {
  return (
    <>
      <tr className="ws-engineer-row">
        <td>
          <div className="timesheet-engineer-cell">
            <strong>{engineer.name}</strong>
            <small>{engineer.role_title}</small>
          </div>
        </td>
        <td>{(engineer.phases || []).join(', ') || '—'}</td>
        <td><strong className="total-hours-blue">{engineer.approved_hours.toFixed(1)} hrs</strong></td>
        <td>{engineer.baseline_hours} hrs</td>
        <td>{statusPill(engineer.progress_status)}</td>
      </tr>
      {engineer.tasks.map((task) => (
        <tr key={task.task_id} className="ws-task-row">
          <td className="ws-task-cell">
            {task.wbs_code ? `${task.wbs_code} ` : ''}
            {task.task_name}
          </td>
          <td>{task.phase || '—'}</td>
          <td>{task.approved_hours.toFixed(1)} hrs</td>
          <td>{task.estimated_hours || 0} hrs</td>
          <td>{statusPill(task.status)}</td>
        </tr>
      ))}
    </>
  );
}

export function ProjectWorkSummaryPage() {
  const [searchParams] = useSearchParams();
  const { authHeaders } = useAuth();
  const targetProjectId = searchParams.get('projectId') ? Number(searchParams.get('projectId')) : null;

  const [projects, setProjects] = useState([]);
  const [projectIndex, setProjectIndex] = useState(0);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');

  const safeProjectIndex = Math.min(projectIndex, Math.max(0, projects.length - 1));
  const project = projects[safeProjectIndex];
  const projectId = project?.id;

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) throw new Error(`Failed to load projects (${response.status})`);
        return response.json();
      })
      .then((list) => {
        setProjects(list);
        if (list.length > 0) {
          const index = targetProjectId ? list.findIndex((p) => p.id === targetProjectId) : -1;
          setProjectIndex(index >= 0 ? index : 0);
        }
      })
      .catch((loadError) => setError(loadError.message));
  }, [authHeaders, targetProjectId]);

  const fetchSummary = useCallback(async () => {
    if (!projectId) return;
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/work-summary`, {
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error(`Failed to load work summary (${response.status})`);
      setSummary(await response.json());
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [projectId, authHeaders]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const chips = useMemo(() => {
    if (!summary) return [];
    const s = summary.summary;
    return [
      { label: 'WBS Tasks', value: s.total_nodes },
      { label: 'Completed', value: s.completed_nodes },
      { label: 'Approved Hrs', value: s.approved_hours },
      { label: 'Scheduled Hrs', value: s.scheduled_hours },
      { label: 'Pending Entries', value: s.pending_entries },
    ];
  }, [summary]);

  const hasNoActivity = summary && summary.leads.length === 0 && summary.engineers.length === 0;

  return (
    <main className="timeline-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Analytics</span>
            <i>/</i>
            <span>Portfolio Performance</span>
            <i>/</i>
            <strong>{project?.project_name || 'Project Work Summary'}</strong>
          </div>
          <h1>Project Work Summary</h1>
          <p>
            Per-lead oversight and per-engineer contribution for the selected project, sourced from real WBS
            assignments and approved time logs.
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
                disabled={safeProjectIndex === 0}
                onClick={() => setProjectIndex((index) => index - 1)}
              >
                <ChevronUp size={12} />
              </button>
              <button
                type="button"
                aria-label="Next project"
                disabled={safeProjectIndex >= projects.length - 1}
                onClick={() => setProjectIndex((index) => index + 1)}
              >
                <ChevronDown size={12} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {error && <div className="resource-error">{error}</div>}

      {summary && (
        <>
          <div className="summary-chips">
            {chips.map((chip) => (
              <div className="summary-chip" key={chip.label}>
                <strong>{typeof chip.value === 'number' ? chip.value.toFixed(1) : chip.value}</strong>
                <span>{chip.label}</span>
              </div>
            ))}
          </div>

          {hasNoActivity && (
            <div className="timesheet-empty-cell" style={{ marginBottom: '16px', padding: '18px' }}>
              This project has no Lead or Engineer activity yet. Create WBS nodes and assign engineers to see
              their contribution here.
            </div>
          )}

          <section className="allocation-card">
            <div className="allocation-header">
              <div>
                <h2>Lead Oversight</h2>
                <p>WBS phases each lead manages, approved hours, and approvals still pending review.</p>
              </div>
            </div>
            <div className="resource-table-wrap">
              <table className="resource-table">
                <thead>
                  <tr>
                    <th>LEAD</th>
                    <th>PHASES</th>
                    <th>NODES</th>
                    <th>PHASE COMPLETION</th>
                    <th>APPROVED HRS</th>
                    <th>LOGGED HRS</th>
                    <th>PENDING APPROVALS</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.leads.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="timesheet-empty-cell">
                        No Lead activity on this project yet.
                      </td>
                    </tr>
                  ) : (
                    summary.leads.map((lead) => (
                      <tr key={lead.name}>
                        <td>
                          <div className="timesheet-engineer-cell">
                            <strong>{lead.name}</strong>
                          </div>
                        </td>
                        <td>{lead.phases.length > 0 ? lead.phases.join(', ') : '—'}</td>
                        <td>{lead.nodes_managed}</td>
                        <td>{completionText(lead.phase_completion)}</td>
                        <td><strong className="total-hours-blue">{lead.approved_hours.toFixed(1)} hrs</strong></td>
                        <td>{lead.logged_hours.toFixed(1)} hrs</td>
                        <td>{lead.pending_approvals}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="allocation-card timesheet-card">
            <div className="allocation-header timesheet-header">
              <div>
                <h2>Engineer Contribution</h2>
                <p>
                  Assigned WBS tasks per engineer with approved hours logged against their baseline. Only{' '}
                  <strong>approved</strong> time logs count toward the hours shown.
                </p>
              </div>
            </div>
            <div className="resource-table-wrap">
              <table className="resource-table">
                <thead>
                  <tr>
                    <th>ENGINEER / WBS TASK</th>
                    <th>PHASE</th>
                    <th>APPROVED HRS</th>
                    <th>BASELINE HRS</th>
                    <th>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.engineers.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="timesheet-empty-cell">
                        No engineers have WBS tasks assigned on this project yet.
                      </td>
                    </tr>
                  ) : (
                    summary.engineers.map((engineer) => (
                      <EngineerRows key={engineer.employee_id} engineer={engineer} />
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}