import { ErrorBanner } from '../../components/Feedback';
import { MonthlyHoursChart } from '../../components/MonthlyHoursChart';
import { PageHeader } from '../../components/PageHeader';
import { ProjectSwitcher } from '../../components/ProjectSwitcher';
import { StatCard } from '../../components/StatCard';
import { DisciplineBars } from '../../components/charts/DisciplineBars';
import { ShareBar } from '../../components/charts/ShareBar';
import { GovernanceAuditLog } from '../../features/bu-head/governance/GovernanceAuditLog';
import { GovernanceSummaryCards } from '../../features/bu-head/governance/GovernanceSummaryCards';
import { useExecutiveDashboard } from '../../hooks/useGovernance';
import { useMyPerformance } from '../../hooks/usePerformance';
import { useProjectSelection } from '../../hooks/useProjectSelection';
import { formatDecimal, formatHours, formatPercent } from '../../utils/format';
import { ExtensionRequestPanel } from '../lead/ExtensionRequestPanel';

// Status palette (fixed, validated): approved = good, pending = warning, rejected = critical.
const HOURS_STATUS = [
  { key: 'approved_hours', label: 'Approved', color: '#0ca30c' },
  { key: 'pending_hours', label: 'Pending review', color: '#fab219' },
  { key: 'rejected_hours', label: 'Rejected', color: '#d03b3b' },
];
// Ordinal blue ramp (steps 250 / 450 / 700, validated with --ordinal): not started -> done.
const TASK_STATES = { todo: '#86b6ef', progress: '#2a78d6', done: '#0d366b' };

const hrs = (value) => formatHours(value, { fallback: '0.0 Hrs' });

function taskParts(summary) {
  const total = summary?.total_tasks ?? 0;
  const started = summary?.started_tasks ?? 0;
  const done = summary?.completed_tasks ?? 0;
  return [
    { key: 'todo', label: 'To Do', value: Math.max(0, total - started), color: TASK_STATES.todo },
    {
      key: 'progress',
      label: 'In Progress',
      value: Math.max(0, started - done),
      color: TASK_STATES.progress,
    },
    { key: 'done', label: 'Done', value: done, color: TASK_STATES.done },
  ];
}

function ChartCard({ title, note, children }) {
  return (
    <section className="allocation-card perf-chart-card">
      <div className="allocation-header">
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
      </div>
      <div className="perf-chart-body">{children}</div>
    </section>
  );
}

/** The project as its lead sees it: health, governance, where the hours stand, and the lead's actions. */
function ProjectSection({ project, data }) {
  return (
    <>
      <h2 className="perf-section-title">Project: {project.project_name}</h2>
      <GovernanceSummaryCards data={data} />
      <div className="ed-two-panels">
        <section className="allocation-card ed-chart-panel">
          <div className="allocation-header">
            <div>
              <h2>Monthly Hours: Planned vs Consumed</h2>
              <p>Planned baseline vs logged consumption per month, all engineers.</p>
            </div>
          </div>
          <MonthlyHoursChart
            months={data?.monthly_data}
            emptyMessage={data ? 'No monthly activity on this project yet.' : 'Loading the project…'}
          />
        </section>
        <div className="ed-right-col">
          <ExtensionRequestPanel key={project.id} projectId={project.id} data={data} />
          <GovernanceAuditLog actions={data?.governance_actions} />
        </div>
      </div>
      <div className="perf-chart-row">
        <ChartCard
          title="Hours by Review Status"
          note="Every hour logged on the project, by where its review stands."
        >
          <ShareBar
            label="Hours by review status"
            parts={HOURS_STATUS.map((status) => ({ ...status, value: data?.summary?.[status.key] ?? 0 }))}
            format={hrs}
            emptyMessage={data ? 'No hours logged on this project yet.' : 'Loading…'}
          />
        </ChartCard>
        <ChartCard
          title="Consumption by Discipline"
          note="Each discipline's logged hours against its booked baseline."
        >
          <DisciplineBars
            disciplines={data?.disciplines}
            thresholdPct={data?.governance_status?.threshold_pct}
          />
        </ChartCard>
      </div>
    </>
  );
}

/** The signed-in person's own work: in full for an engineer, as one compact row for a lead. */
function MyWorkSection({ data, compact }) {
  const summary = data?.summary;
  const hasOwnWork = (summary?.total_tasks ?? 0) > 0 || (summary?.total_hours_consumption ?? 0) > 0;
  const heading = <h2 className="perf-section-title">My Work{compact ? ' on This Project' : ''}</h2>;
  if (compact && data && !hasOwnWork) {
    return (
      <>
        {heading}
        <div className="timesheet-empty-cell perf-empty">
          You have no subtasks of your own on this project.
        </div>
      </>
    );
  }
  const tasks = (
    <ChartCard title="My Tasks by Status" note="The tasks and subtasks assigned to you.">
      <ShareBar
        label="My tasks by status"
        parts={taskParts(summary)}
        emptyMessage={data ? 'No tasks assigned to you yet.' : 'Loading…'}
      />
    </ChartCard>
  );
  return (
    <>
      {heading}
      <section className="ed-summary-cards">
        <StatCard
          label="My Hours"
          value={summary ? hrs(summary.total_hours_consumption) : 'Not available'}
          sub={summary ? `${formatPercent(summary.consumption_pct)} of my planned hours` : undefined}
          progress={summary ? { tone: 'orange', percent: summary.consumption_pct } : undefined}
          foot={
            summary
              ? `${hrs(summary.total_hours_approved)} approved / ${hrs(summary.total_hours_pending)} pending of ${hrs(summary.total_hours_scheduled)}`
              : undefined
          }
        />
        <StatCard
          label="My Tasks Completed"
          value={summary ? `${summary.completed_tasks} of ${summary.total_tasks}` : 'Not available'}
          sub={summary ? `${summary.completion_pct}% complete` : undefined}
          progress={summary ? { tone: 'green', percent: summary.completion_pct } : undefined}
        />
        {!compact && (
          <StatCard
            label="Schedule Index (SPI)"
            value={summary ? formatDecimal(summary.spi_value, 2, { fallback: 'N/A' }) : 'Not available'}
            sub={summary?.spi_note}
            valueClassName="ed-spi-value"
          />
        )}
      </section>
      {compact ? (
        <div className="perf-chart-row perf-chart-row-single">{tasks}</div>
      ) : (
        <div className="perf-chart-row">
          <ChartCard title="My Monthly Hours: Planned vs Consumed" note="From your approved time entries.">
            <MonthlyHoursChart
              months={data?.monthly_breakdown}
              emptyMessage={data ? 'No monthly activity yet.' : 'Loading…'}
            />
          </ChartCard>
          {tasks}
        </div>
      )}
    </>
  );
}

/**
 * Performance Dashboard (decided 2026-10-07): one page for everyone who works on
 * projects. On a project they lead, a lead sees the project's health and governance
 * (what the Executive Dashboard showed) and, below it, their own work; on any other
 * project, and for engineers, it is their own work. Nothing is shown twice.
 */
export function PerformanceDashboardPage() {
  const { projects, project, projectId, selectProject, error: projectsError } = useProjectSelection();
  const leads = project?.my_role === 'lead';
  const projectData = useExecutiveDashboard(projectId, { enabled: leads });
  const mine = useMyPerformance(projectId);

  return (
    <main className="timeline-page">
      <PageHeader
        breadcrumb={['My Workspace', 'Performance Dashboard']}
        title="Performance Dashboard"
        description={
          leads
            ? 'The project you lead: health, hours, governance and your requests, then your own work.'
            : 'Your hours, tasks and schedule on the selected project.'
        }
      >
        <ProjectSwitcher projects={projects} value={projectId} onChange={selectProject} />
      </PageHeader>

      <ErrorBanner error={projectsError || projectData.error || mine.error} />
      {!project && (
        <div className="page-loading">{projects.length ? 'Loading…' : 'No projects to show yet.'}</div>
      )}
      {project && leads && <ProjectSection project={project} data={projectData.data} />}
      {project && <MyWorkSection data={mine.data} compact={leads} />}
    </main>
  );
}
