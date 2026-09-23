import { ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { ErrorBanner } from '../../components/Feedback';
import { MonthlyHoursChart } from '../../components/MonthlyHoursChart';
import { PageHeader } from '../../components/PageHeader';
import { ProjectSwitcher } from '../../components/ProjectSwitcher';
import { useExecutiveDashboard } from '../../hooks/useGovernance';
import { useProjectSelection } from '../../hooks/useProjectSelection';
import { GovernanceAuditLog } from './governance/GovernanceAuditLog';
import { GovernanceControls } from './governance/GovernanceControls';
import { GovernanceSummaryCards } from './governance/GovernanceSummaryCards';

/** BU Head Executive Dashboard: project health KPIs and governance actions. */
export function ExecutiveDashboardPage() {
  const navigate = useNavigate();
  const { projects, project, projectId, selectProject, error: projectsError } = useProjectSelection();
  const { data, error } = useExecutiveDashboard(projectId);

  return (
    <main className="timeline-page">
      <PageHeader
        breadcrumb={['Analytics', 'Portfolio Performance', 'Executive Governance']}
        title="Executive Dashboard & Governance Controls"
        description="Real-time health monitoring, financial variance, threshold exception tracking, and BU approval controls."
      >
        <ProjectSwitcher projects={projects} value={projectId} onChange={selectProject} />
      </PageHeader>

      <ErrorBanner error={projectsError || error} />

      <GovernanceSummaryCards data={data} />

      <div className="ed-two-panels">
        <section className="allocation-card ed-chart-panel">
          <div className="allocation-header">
            <div>
              <h2>Monthly Hours: Planned vs Consumed</h2>
              <p>Planned baseline vs logged consumption per month.</p>
            </div>
          </div>
          <MonthlyHoursChart
            months={data?.monthly_data}
            emptyMessage={
              data
                ? 'No monthly activity on this project yet.'
                : 'No project selected — assign engineers and log hours to populate the chart.'
            }
          />
        </section>

        <div className="ed-right-col">
          {/* Keyed by project so a half-typed comment never carries over to another project. */}
          <GovernanceControls
            key={projectId ?? 'none'}
            projectId={projectId}
            projectName={project?.project_name}
            data={data}
          />
          <GovernanceAuditLog actions={data?.governance_actions} />
        </div>
      </div>

      <div className="ed-next-row">
        <button
          type="button"
          className="button button-primary button-next"
          disabled={!projectId}
          onClick={() => navigate(`/project-work-summary?projectId=${projectId}`)}
        >
          NEXT <ArrowRight size={16} />
        </button>
      </div>
    </main>
  );
}
