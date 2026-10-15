import { Archive, ArchiveRestore, BarChart3, Pencil, PlusCircle, Search, Trash2, Users } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { EmptyState, ErrorBanner, Notice } from '../../components/Feedback';
import { PageHeader } from '../../components/PageHeader';
import { currencySymbol } from '../../constants/currencies';
import {
  useArchiveProject,
  useDeleteProject,
  useProjects,
  useUnarchiveProject,
} from '../../hooks/useProjects';
import { formatAmount, formatInteger } from '../../utils/format';
import { PeopleCard } from './PeopleCard';

const SEARCH_FIELDS = [
  'project_name',
  'project_code',
  'client_organization',
  'project_lead_electrical',
  'project_lead_mechanical',
  'project_lead_bim',
];

/** Confirmation text for each card action. */
const ACTIONS = {
  archive: {
    title: 'Archive Project',
    confirmLabel: 'Archive',
    busyLabel: 'Archiving…',
    text: 'Archive this project?',
    detail:
      'It becomes read-only and disappears for Leads and Engineers. Active time tracking is ended and a pending extension request is cancelled. You can reopen it later.',
  },
  unarchive: {
    title: 'Reopen Project',
    confirmLabel: 'Reopen',
    busyLabel: 'Reopening…',
    text: 'Reopen this project?',
    detail: 'It comes back exactly as it was, including any timesheet lock.',
  },
  delete: {
    title: 'Delete Project',
    confirmLabel: 'Delete',
    busyLabel: 'Deleting…',
    text: 'Delete this project permanently?',
    detail: 'Only a project without any recorded work or history can be deleted. Otherwise, archive it.',
  },
};

function matchesSearch(project, query) {
  return SEARCH_FIELDS.some((field) => project[field]?.toLowerCase().includes(query));
}

function contractValueText(project) {
  if (project.contract_value == null) return '—';
  const currency = project.contract_currency || 'USD';
  return `${currency} ${currencySymbol(currency)}${formatAmount(project.contract_value)}`;
}

function ProjectCard({ project, onAction }) {
  const archived = Boolean(project.archived_at);
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
    <article className={`created-project-card${archived ? ' created-project-card-archived' : ''}`}>
      <div className="created-project-card-head">
        <div className="created-project-title">
          <h3>{project.project_name}</h3>
          <span className="created-project-code">{project.project_code || '—'}</span>
          {archived && <span className="created-project-archived">Archived</span>}
        </div>
        <div className="created-project-actions">
          <Link className="created-project-action" to={`/executive-dashboard?projectId=${project.id}`}>
            <BarChart3 size={14} /> Dashboard
          </Link>
          {archived ? (
            <button type="button" className="created-project-action" onClick={() => onAction('unarchive')}>
              <ArchiveRestore size={14} /> Reopen
            </button>
          ) : (
            <>
              <Link className="created-project-action" to={`/edit-project?projectId=${project.id}`}>
                <Pencil size={14} /> Edit
              </Link>
              <button type="button" className="created-project-action" onClick={() => onAction('archive')}>
                <Archive size={14} /> Archive
              </button>
              <button
                type="button"
                className="created-project-delete"
                onClick={() => onAction('delete')}
                aria-label={`Delete project ${project.project_name}`}
              >
                <Trash2 size={14} /> Delete
              </button>
            </>
          )}
        </div>
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
  const [showArchived, setShowArchived] = useState(false);
  const { data: projects = [], isLoading, error } = useProjects({ includeArchived: showArchived });
  const mutations = {
    archive: useArchiveProject(),
    unarchive: useUnarchiveProject(),
    delete: useDeleteProject(),
  };
  const [showPeople, setShowPeople] = useState(false); // onboarding, until the global admin app
  const [search, setSearch] = useState('');
  const [pending, setPending] = useState(null); // { type, project }
  // A notice handed over by Project Kickoff (e.g. the SharePoint outcome).
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

  const pendingMutation = pending ? mutations[pending.type] : null;

  function closeDialog() {
    pendingMutation?.reset();
    setPending(null);
  }

  function confirmAction() {
    const { type, project } = pending;
    const variables = type === 'delete' ? project.id : { projectId: project.id, comments: null };
    pendingMutation.mutate(variables, { onSuccess: closeDialog });
  }

  return (
    <main className="page-shell">
      <PageHeader
        breadcrumb={['Projects', 'Created Projects']}
        title="Created Projects"
        description="Projects created under this Business Unit with their commercial baselines and governance settings."
      >
        <button
          type="button"
          className="button button-secondary"
          onClick={() => setShowPeople((open) => !open)}
        >
          <Users size={16} /> {showPeople ? 'Hide people' : 'People'}
        </button>
        <button type="button" className="button button-primary" onClick={() => navigate('/create-project')}>
          <PlusCircle size={16} /> Project Kickoff
        </button>
      </PageHeader>

      {showPeople && <PeopleCard />}

      {notice && <Notice {...notice} onDismiss={() => setNotice(null)} />}
      <ErrorBanner error={error} />

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
        <label className="created-projects-filter">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
          />
          Show archived
        </label>
        <span className="created-projects-count">
          {filteredProjects.length} of {projects.length} projects
        </span>
      </div>

      {!error && isLoading && <EmptyState>Loading projects…</EmptyState>}
      {!error && !isLoading && projects.length === 0 && (
        <EmptyState>No projects created yet — use Project Kickoff to add one.</EmptyState>
      )}
      {!error &&
        projects.length > 0 &&
        (filteredProjects.length > 0 ? (
          <div className="created-projects-grid">
            {filteredProjects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onAction={(type) => setPending({ type, project })}
              />
            ))}
          </div>
        ) : (
          <EmptyState>No projects match &quot;{search.trim()}&quot;.</EmptyState>
        ))}

      {pending && (
        <ConfirmDialog
          title={ACTIONS[pending.type].title}
          confirmLabel={ACTIONS[pending.type].confirmLabel}
          busyLabel={ACTIONS[pending.type].busyLabel}
          busy={pendingMutation.isPending}
          error={pendingMutation.error}
          onConfirm={confirmAction}
          onCancel={closeDialog}
        >
          <p className="confirm-modal-text">{ACTIONS[pending.type].text}</p>
          <p className="confirm-modal-subtext">
            <strong>{pending.project.project_name}</strong> ({pending.project.project_code || '—'}).{' '}
            {ACTIONS[pending.type].detail}
          </p>
        </ConfirmDialog>
      )}
    </main>
  );
}
