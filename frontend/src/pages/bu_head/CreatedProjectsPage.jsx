import { AlertCircle, PlusCircle, Search, Trash2, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = 'http://localhost:8000';

const currencies = [
  { code: 'USD', symbol: '$' },
  { code: 'INR', symbol: '₹' },
  { code: 'EUR', symbol: '€' },
  { code: 'GBP', symbol: '£' },
  { code: 'AED', symbol: 'د.إ' },
  { code: 'AUD', symbol: 'A$' },
  { code: 'CAD', symbol: 'C$' },
  { code: 'SGD', symbol: 'S$' },
];

function currencySymbol(currency) {
  return currencies.find((item) => item.code === currency)?.symbol || '$';
}

/** Format a number string/float with thousands separators and 2 decimals (e.g. "480,000.00"). */
function formatCurrencyValue(value) {
  if (value === '' || value === null || value === undefined) return '—';
  const num = Number(String(value).replace(/[^0-9.]/g, ''));
  if (!Number.isFinite(num)) return '—';
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ProjectCard({ project, onDelete }) {
  const fields = [
    ['Client / Customer', project.client_organization || '—'],
    ['Assigned Project Lead | Electrical', project.project_lead_electrical || '—'],
    ['Assigned Project Lead | Mechanical', project.project_lead_mechanical || '—'],
    ['Assigned Project Lead | BIM', project.project_lead_bim || '—'],
    ['Target Start Date', project.start_date || '—'],
    [
      'Total Commercial Contract Value (USD)',
      project.contract_value != null
        ? `${project.contract_currency || 'USD'} ${currencySymbol(project.contract_currency)}${formatCurrencyValue(project.contract_value)}`
        : '—',
    ],
    [
      'Target Effort Hours Baseline',
      project.target_effort_hours != null ? `${Number(project.target_effort_hours).toLocaleString('en-US')} Hrs` : '—',
    ],
    ['Governance Threshold', project.governance_threshold_pct != null ? `${project.governance_threshold_pct}%` : '—'],
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
  const { authHeaders } = useAuth();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [projectsError, setProjectsError] = useState('');
  const [search, setSearch] = useState('');
  const [projectPendingDelete, setProjectPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const filteredProjects = projects.filter((project) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return [
      project.project_name,
      project.project_code,
      project.client_organization,
      project.project_lead_electrical,
      project.project_lead_mechanical,
      project.project_lead_bim,
    ]
      .filter(Boolean)
      .some((value) => value.toLowerCase().includes(q));
  });

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() });
      if (!response.ok) throw new Error(`Failed to load projects (${response.status})`);
      setProjects(await response.json());
    } catch (error) {
      setProjectsError(error.message);
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  async function handleConfirmDelete() {
    if (!projectPendingDelete) return;
    setDeleteError('');
    setDeleting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectPendingDelete.id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!response.ok) {
        let detail = `Failed to delete project (${response.status})`;
        try {
          const body = await response.json();
          if (body.detail) detail = body.detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }
      setProjects((current) => current.filter((p) => p.id !== projectPendingDelete.id));
      setProjectPendingDelete(null);
    } catch (error) {
      setDeleteError(error.message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main className="page-shell">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Projects</span>
            <i>/</i>
            <strong>Created Projects</strong>
          </div>
          <h1>Created Projects</h1>
          <p>Projects created under this Business Unit with their commercial baselines and governance settings.</p>
        </div>
        <button type="button" className="button button-primary" onClick={() => navigate('/create-project')}>
          <PlusCircle size={16} /> Create Project
        </button>
      </div>

      {projectsError && (
        <div className="notice error" role="status"><AlertCircle size={18} /><div><strong>{projectsError}</strong></div></div>
      )}
      {!projectsError && loading && (
        <div className="empty-state">Loading projects…</div>
      )}
      {!projectsError && !loading && projects.length === 0 && (
        <div className="empty-state">No projects created yet — use Create Project to add one.</div>
      )}
      {!projectsError && !loading && projects.length > 0 && (
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
          <span className="created-projects-count">{filteredProjects.length} of {projects.length} projects</span>
        </div>
      )}
      {!projectsError && !loading && projects.length > 0 && (
        filteredProjects.length > 0 ? (
          <div className="created-projects-grid">
            {filteredProjects.map((project) => (
              <ProjectCard key={project.id} project={project} onDelete={() => setProjectPendingDelete(project)} />
            ))}
          </div>
        ) : (
          <div className="empty-state">No projects match "{search.trim()}".</div>
        )
      )}

      {projectPendingDelete && (
        <div className="modal-backdrop" role="presentation">
          <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-delete-title">
            <div className="modal-heading">
              <h2 id="confirm-delete-title">Delete Project</h2>
              <button type="button" aria-label="Close" disabled={deleting} onClick={() => setProjectPendingDelete(null)}>
                <X size={18} />
              </button>
            </div>
            <div className="confirm-modal-body">
              <p className="confirm-modal-text">Are you sure you want to delete this project?</p>
              <p className="confirm-modal-subtext">
                <strong>{projectPendingDelete.project_name}</strong> ({projectPendingDelete.project_code || '—'}) and all of
                its data will be permanently deleted from the backend.
              </p>
              {deleteError && <div className="resource-error">{deleteError}</div>}
            </div>
            <div className="modal-actions">
              <button className="button button-secondary" type="button" disabled={deleting} onClick={() => setProjectPendingDelete(null)}>
                Cancel
              </button>
              <button className="button button-danger" type="button" disabled={deleting} onClick={handleConfirmDelete}>
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}