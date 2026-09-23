import { ErrorBanner } from '../../components/Feedback';
import { PageHeader } from '../../components/PageHeader';
import { ProjectSwitcher } from '../../components/ProjectSwitcher';
import { useWorkSummary } from '../../hooks/useGovernance';
import { useProjectSelection } from '../../hooks/useProjectSelection';
import { formatHours, formatInteger } from '../../utils/format';

const STATUS_CLASS = {
  Completed: 'status-approved',
  'In Progress': 'status-inprogress',
  'Not Started': 'status-pending',
};

const hrs = (value) => formatHours(value, { unit: 'hrs', fallback: '0.0 hrs' });

function StatusPill({ status }) {
  return <span className={`approval-pill ${STATUS_CLASS[status] || 'status-none'}`}>{status || '—'}</span>;
}

function completionText(phaseCompletion) {
  const entries = Object.entries(phaseCompletion || {});
  if (entries.length === 0) return '—';
  return entries.map(([phase, stats]) => `${phase}: ${stats.completed}/${stats.total}`).join(', ');
}

function SummaryChips({ summary }) {
  const chips = [
    ['WBS Tasks', formatInteger(summary.total_nodes)],
    ['Completed', formatInteger(summary.completed_nodes)],
    ['Approved Hrs', summary.approved_hours.toFixed(1)],
    ['Scheduled Hrs', formatInteger(summary.scheduled_hours)],
    ['Pending Entries', formatInteger(summary.pending_entries)],
  ];
  return (
    <div className="summary-chips">
      {chips.map(([label, value]) => (
        <div className="summary-chip" key={label}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

function LeadOversightTable({ leads }) {
  return (
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
            {leads.length === 0 ? (
              <tr>
                <td colSpan={7} className="timesheet-empty-cell">
                  No Lead activity on this project yet.
                </td>
              </tr>
            ) : (
              leads.map((lead) => (
                <tr key={lead.name}>
                  <td>
                    <div className="timesheet-engineer-cell">
                      <strong>{lead.name}</strong>
                    </div>
                  </td>
                  <td>{lead.phases.length > 0 ? lead.phases.join(', ') : '—'}</td>
                  <td>{lead.nodes_managed}</td>
                  <td>{completionText(lead.phase_completion)}</td>
                  <td>
                    <strong className="total-hours-blue">{hrs(lead.approved_hours)}</strong>
                  </td>
                  <td>{hrs(lead.logged_hours)}</td>
                  <td>{lead.pending_approvals}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
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
        <td>{engineer.phases.join(', ') || '—'}</td>
        <td>
          <strong className="total-hours-blue">{hrs(engineer.approved_hours)}</strong>
        </td>
        <td>{engineer.baseline_hours} hrs</td>
        <td>
          <StatusPill status={engineer.progress_status} />
        </td>
      </tr>
      {engineer.tasks.map((task) => (
        <tr key={task.task_id} className="ws-task-row">
          <td className="ws-task-cell">
            {task.wbs_code ? `${task.wbs_code} ` : ''}
            {task.task_name}
          </td>
          <td>{task.phase || '—'}</td>
          <td>{hrs(task.approved_hours)}</td>
          <td>{task.estimated_hours || 0} hrs</td>
          <td>
            <StatusPill status={task.status} />
          </td>
        </tr>
      ))}
    </>
  );
}

function EngineerContributionTable({ engineers }) {
  return (
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
            {engineers.length === 0 ? (
              <tr>
                <td colSpan={5} className="timesheet-empty-cell">
                  No engineers have WBS tasks assigned on this project yet.
                </td>
              </tr>
            ) : (
              engineers.map((engineer) => <EngineerRows key={engineer.employee_id} engineer={engineer} />)
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** BU Head view of who is doing what on a project. */
export function ProjectWorkSummaryPage() {
  const { projects, project, projectId, selectProject, error: projectsError } = useProjectSelection();
  const { data: summary, error } = useWorkSummary(projectId);
  const hasNoActivity = summary && summary.leads.length === 0 && summary.engineers.length === 0;

  return (
    <main className="timeline-page">
      <PageHeader
        breadcrumb={['Analytics', 'Portfolio Performance', project?.project_name || 'Project Work Summary']}
        title="Project Work Summary"
        description="Per-lead oversight and per-engineer contribution for the selected project, sourced from real WBS assignments and approved time logs."
      >
        <ProjectSwitcher projects={projects} value={projectId} onChange={selectProject} />
      </PageHeader>

      <ErrorBanner error={projectsError || error} />

      {summary && (
        <>
          <SummaryChips summary={summary.summary} />
          {hasNoActivity && (
            <div className="timesheet-empty-cell" style={{ marginBottom: '16px', padding: '18px' }}>
              This project has no Lead or Engineer activity yet. Create WBS nodes and assign engineers to see
              their contribution here.
            </div>
          )}
          <LeadOversightTable leads={summary.leads} />
          <EngineerContributionTable engineers={summary.engineers} />
        </>
      )}
    </main>
  );
}
