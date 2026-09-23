import {
  AlertCircle,
  CheckCircle,
  ChevronRight,
  ExternalLink,
  FileText,
  FolderOpen,
  Loader2,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { ErrorBanner } from '../../components/Feedback';
import { PageHeader } from '../../components/PageHeader';
import { ProjectSwitcher } from '../../components/ProjectSwitcher';
import { useProjectSelection } from '../../hooks/useProjectSelection';
import { useSharePointMirror } from '../../hooks/useSharePointMirror';
import { formatBytes, formatDateTime } from '../../utils/format';
import { ROOT_FOLDER_ID, flattenFolders, folderPath, selectedFolderView } from './folderTree';
import './sharepoint.css';

const NOT_PROVISIONED = 'SharePoint directory not provisioned for this project.';

function SummaryCards({ mirror, isLoading, lastRefreshed }) {
  const connection = mirror?.connection ?? { connected: false, status: 'Unknown', error: 'No data' };
  return (
    <div className="summary-grid">
      <div className="summary-card">
        <span className="summary-label">SharePoint Target Location</span>
        <strong className="sp-location">
          {mirror?.target_location ? (
            <a href={mirror.target_location} target="_blank" rel="noopener noreferrer">
              {mirror.target_location}
            </a>
          ) : mirror?.provisioned === false ? (
            <span className="sp-status pending">
              Not provisioned — {mirror.error || 'No SharePoint folder configured'}
            </span>
          ) : (
            <span className="sp-status loading">{isLoading ? 'Loading...' : '—'}</span>
          )}
        </strong>
        <span className="summary-caption">Real folder path from Graph API</span>
      </div>

      <div className="summary-card">
        <span className="summary-label">Sync Status</span>
        <strong>
          {connection.connected ? (
            <span className="sp-status connected">
              <CheckCircle size={12} className="sp-status-icon" />
              Connected
            </span>
          ) : (
            <span className="sp-status error">
              <XCircle size={12} className="sp-status-icon" />
              {connection.status || 'Disconnected'}
            </span>
          )}
        </strong>
        <span className="summary-caption">{connection.error || 'Live Graph API connectivity check'}</span>
      </div>

      <div className="summary-card">
        <span className="summary-label">Document Repository Stats</span>
        <strong>{mirror?.stats?.total_files ?? 0} Files</strong>
        <span className="summary-caption green-caption">
          Total Size: {mirror?.stats?.total_size_formatted ?? '0 B'}
        </span>
      </div>

      <div className="summary-card bench-card">
        <span className="summary-label">Last Refreshed</span>
        <strong>{lastRefreshed ? lastRefreshed.toLocaleTimeString() : 'Never'}</strong>
        <span className="summary-caption">Manual on-demand fetch from Graph API</span>
      </div>
    </div>
  );
}

function NotProvisionedMessage({ mirror }) {
  return (
    <span className="sp-status error sp-empty-message">
      <AlertCircle size={20} color="#dda837" />
      {mirror?.error || NOT_PROVISIONED}
    </span>
  );
}

function FolderTree({ mirror, isLoading, selectedId, onSelect }) {
  const folders = useMemo(() => flattenFolders(mirror?.folder_hierarchy), [mirror]);
  const crumbs = [
    { id: ROOT_FOLDER_ID, name: 'Project Root' },
    ...(selectedId === ROOT_FOLDER_ID ? [] : folderPath(mirror?.folder_hierarchy, selectedId)),
  ];

  let emptyRow = null;
  if (folders.length === 0) {
    if (isLoading) {
      emptyRow = (
        <>
          <Loader2 size={24} className="spin sp-empty-icon sp-icon" />
          Loading folder hierarchy...
        </>
      );
    } else if (mirror?.provisioned) {
      emptyRow = (
        <>
          <FolderOpen size={24} className="sp-empty-icon" />
          No subfolders found in this project&apos;s SharePoint directory.
        </>
      );
    } else if (mirror?.provisioned === false) {
      emptyRow = <NotProvisionedMessage mirror={mirror} />;
    }
  }

  return (
    <div className="sp-tree-panel">
      <div className="resource-toolbar">
        <div className="breadcrumb sp-crumbs">
          {crumbs.map((crumb, index) => (
            <span key={crumb.id} className="sp-crumb">
              {index > 0 && <ChevronRight size={12} className="sp-crumb-separator" />}
              <button
                type="button"
                className={crumb.id === selectedId ? 'active' : ''}
                onClick={() => onSelect(crumb.id)}
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>
      </div>
      <div className="resource-table-wrap sp-scroll">
        <table className="resource-table wbs-table">
          <thead>
            <tr>
              <th>FOLDER STRUCTURE</th>
            </tr>
          </thead>
          <tbody>
            {emptyRow ? (
              <tr>
                <td className="sp-empty-cell">{emptyRow}</td>
              </tr>
            ) : (
              folders.map((folder) => (
                <tr
                  key={folder.id}
                  className={`sp-folder-row${selectedId === folder.id ? ' selected' : ''}`}
                  onClick={() => onSelect(folder.id)}
                >
                  <td className="sp-folder-cell">
                    <span className="sp-folder-label" style={{ paddingLeft: `${folder.depth * 20}px` }}>
                      <FolderOpen size={16} className="sp-icon" />
                      <strong>{folder.name}</strong>
                      {folder.children?.length > 0 && (
                        <span className="sp-folder-count">({folder.children.length})</span>
                      )}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FileList({ mirror, isLoading, folder }) {
  const files = folder.files;
  let emptyRow;
  if (mirror?.provisioned === false) emptyRow = <NotProvisionedMessage mirror={mirror} />;
  else if (isLoading || !mirror)
    emptyRow = (
      <>
        <Loader2 size={24} className="spin sp-empty-icon sp-icon" />
        Loading file listing...
      </>
    );
  else
    emptyRow = (
      <>
        <FileText size={24} className="sp-empty-icon" />
        No files in this folder.
      </>
    );

  return (
    <div className="sp-files-panel">
      <div className="resource-table-wrap sp-scroll">
        <table className="resource-table">
          <thead>
            <tr>
              <th style={{ width: '40%' }}>DOCUMENT NAME</th>
              <th style={{ width: '20%' }}>LAST MODIFIED</th>
              <th style={{ width: '20%' }}>MODIFIED BY</th>
              <th style={{ width: '15%' }}>SIZE</th>
              <th style={{ width: '5%' }} aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {files.length > 0 ? (
              files.map((file) => (
                <tr key={file.id}>
                  <td>
                    <div className="sp-file-name">
                      <FileText size={16} className="sp-icon" />
                      <span>{file.name}</span>
                    </div>
                  </td>
                  <td>{formatDateTime(file.last_modified_date_time, { fallback: '—' })}</td>
                  <td>{file.last_modified_by}</td>
                  <td>{formatBytes(file.size)}</td>
                  <td>
                    <a
                      href={file.web_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="wbs-eye sp-file-link"
                      title="Open in SharePoint"
                    >
                      <ExternalLink size={14} className="sp-icon" />
                    </a>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="sp-empty-cell">
                  {emptyRow}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {files.length > 0 && (
        <div className="allocation-footer sp-files-footer">
          <span>
            {files.length} file(s) in &quot;{folder.name}&quot;
          </span>
        </div>
      )}
    </div>
  );
}

/** Read-only view of a project's SharePoint folder, fetched on demand from Microsoft Graph. */
export function SharePointMirrorPage() {
  const {
    projects,
    projectId,
    selectProject,
    isLoading: loadingProjects,
    error: projectsError,
  } = useProjectSelection();
  const { data: mirror, error, isFetching, dataUpdatedAt, refetch } = useSharePointMirror(projectId);
  const [folderSelection, setFolderSelection] = useState({ projectId: null, folderId: ROOT_FOLDER_ID });

  // The folder selection belongs to one project; switching project starts at the root again.
  const selectedFolderId =
    folderSelection.projectId === projectId ? folderSelection.folderId : ROOT_FOLDER_ID;
  const selectFolder = (folderId) => setFolderSelection({ projectId, folderId });
  const folder = selectedFolderView(mirror, selectedFolderId);

  return (
    <main className="resource-page">
      <PageHeader
        breadcrumb={['Document Management', 'Cloud Storage Sync', 'SharePoint Integration']}
        title="Automated SharePoint Directory Mirror"
        description="View real-time folder hierarchy and file listings from the provisioned SharePoint directory. Data is fetched on-demand from Microsoft Graph API."
      >
        <ProjectSwitcher
          projects={projects}
          value={projectId}
          onChange={selectProject}
          disabled={loadingProjects}
        />
      </PageHeader>

      <ErrorBanner error={projectsError || error} />

      <SummaryCards
        mirror={mirror}
        isLoading={isFetching}
        lastRefreshed={dataUpdatedAt ? new Date(dataUpdatedAt) : null}
      />

      <section className="allocation-card">
        <div className="allocation-header">
          <div>
            <h2>SharePoint Folder Hierarchy</h2>
            <p>Real folder structure as it exists in SharePoint. Click a folder to view its files.</p>
          </div>
          <div className="sp-actions">
            <button
              className="button button-secondary"
              type="button"
              onClick={() => window.open(mirror.target_location, '_blank', 'noopener,noreferrer')}
              disabled={!mirror?.target_location}
              title="Open in SharePoint"
            >
              <ExternalLink size={14} /> Open in SharePoint
            </button>
            <button
              className="button button-primary"
              type="button"
              onClick={() => refetch()}
              disabled={isFetching || !projectId}
            >
              <RefreshCw size={14} className={isFetching ? 'spin' : ''} />
              {isFetching ? 'Refreshing...' : 'Force Resync'}
            </button>
          </div>
        </div>

        <div className="sp-layout">
          <FolderTree
            mirror={mirror}
            isLoading={isFetching}
            selectedId={selectedFolderId}
            onSelect={selectFolder}
          />
          <FileList mirror={mirror} isLoading={isFetching} folder={folder} />
        </div>
      </section>
    </main>
  );
}
