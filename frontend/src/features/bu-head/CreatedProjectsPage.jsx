import { PlusCircle, Search, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { EmptyState, ErrorBanner, Notice } from '../../components/Feedback';
import { PageHeader } from '../../components/PageHeader';
import { currencySymbol } from '../../constants/currencies';
import { useDeleteProject, useProjects } from '../../hooks/useProjects';
import { formatAmount, formatInteger } from '../../utils/format';

const SEARCH_FIELDS = [
  'project_name',
  'project_code',
  'client_organization',
  'project_lead_electrical',
  'project_lead_mechanical',
  'project_lead_bim',
];

function matchesSearch(project, query) {
  return SEARCH_FIELDS.some((field) => project[field]?.toLowerCase().includes(query));
}

function contractValueText(project) {
  if (project.contract_value == null) return '—';
  const currency = project.contract_currency || 'USD';
  return `${currency} ${currencySymbol(currency)}${formatAmount(project.contract_value)}`;
}

function ProjectCard({ project, onDelete }) {
  const fields = [
    ['Client / Customer', project.client_organization || '—'],
    ['Assigned Project Lead | Electrical', project.project_lead_electrical || '—'],
    ['Assigned Project Lead | Mechanical', project.project_lead_mechanical || '—'],
    ['Assigned Project Lead | BIM', project.project_lead_bim || '—'],
    ['Target Start Date', project.start_date || '—'],
    ['Total Commercial Contract Value', contractValueText(project)],
    [
      'Target Effort Hours Baseline',
      project.target_effort_hours != null ? `${formatInteger(project.target_effort_hours)} Hrs` : '—',
    ],
    [
      'Governance Threshold',
      project.governance_threshold_pct != null ? `${project.governance_threshold_pct}%` : '—',
    ],
  ];

  return (
    <article className="created-project-card">
      <div className="created-project-card-head">
        <div className="created-project-title">
          <h3>{project.project_name}</h3>
          <span className="created-project-code">{project.project_code || '—'}</span>
        </div>
        <button
          type="button"
          className="created-project-delete"
          onClick={onDelete}
          aria-label={`Delete project ${project.project_name}`}
        >
          <Trash2 size={14} /> Delete
        </button>
      </div>
      <dl className="created-project-fields">
        {fields.map(([label, value]) => (
          <div className="created-project-field" key={label}>
            <dt>{label}</dt>
            <dd title={value}>{value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

export function CreatedProjectsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: projects = [], isLoading, error } = useProjects();
  const deleteProject = useDeleteProject();
  const [search, setSearch] = useState('');
  const [pendingDelete, setPendingDelete] = useState(null);
  // A notice handed over by Create Project (e.g. the SharePoint outcome).
  const [notice, setNotice] = useState(() => location.state?.notice ?? null);

  useEffect(() => {
    // Consume the hand-over so a refresh or back-navigation does not repeat it.
    if (location.state?.notice) navigate(location.pathname, { replace: true, state: null });
  }, [location, navigate]);

  const query = search.trim().toLowerCase();
  const filteredProjects = useMemo(
    () => (query ? projects.filter((project) => matchesSearch(project, query)) : projects),
    [projects, query],
  );

  function closeDeleteDialog() {
    setPendingDelete(null);
    deleteProject.reset();
  }

  function confirmDelete() {
    deleteProject.mutate(pendingDelete.id, { onSuccess: closeDeleteDialog });
  }

  return (
    <main className="page-shell">
      <PageHeader
        breadcrumb={['Projects', 'Created Projects']}
        title="Created Projects"
        description="Projects created under this Business Unit with their commercial baselines and governance settings."
      >
        <button type="button" className="button button-primary" onClick={() => navigate('/create-project')}>
          <PlusCircle size={16} /> Create Project
        </button>
      </PageHeader>

      {notice && <Notice {...notice} onDismiss={() => setNotice(null)} />}
      <ErrorBanner error={error} />

      {!error && isLoading && <EmptyState>Loading projects…</EmptyState>}
      {!error && !isLoading && projects.length === 0 && (
        <EmptyState>No projects created yet — use Create Project to add one.</EmptyState>
      )}
      {!error && projects.length > 0 && (
        <>
          <div className="created-projects-toolbar">
            <label className="created-projects-search">
              <Search size={16} />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by project name, code or client…"
              />
            </label>
            <span className="created-projects-count">
              {filteredProjects.length} of {projects.length} projects
            </span>
          </div>
          {filteredProjects.length > 0 ? (
            <div className="created-projects-grid">
              {filteredProjects.map((project) => (
                <ProjectCard key={project.id} project={project} onDelete={() => setPendingDelete(project)} />
              ))}
            </div>
          ) : (
            <EmptyState>No projects match &quot;{search.trim()}&quot;.</EmptyState>
          )}
        </>
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Delete Project"
          confirmLabel="Delete"
          busyLabel="Deleting…"
          busy={deleteProject.isPending}
          error={deleteProject.error}
          onConfirm={confirmDelete}
          onCancel={closeDeleteDialog}
        >
          <p className="confirm-modal-text">Are you sure you want to delete this project?</p>
          <p className="confirm-modal-subtext">
            <strong>{pendingDelete.project_name}</strong> ({pendingDelete.project_code || '—'}) and all of its
            data will be permanently deleted from the backend.
          </p>
        </ConfirmDialog>
      )}
    </main>
  );
}
