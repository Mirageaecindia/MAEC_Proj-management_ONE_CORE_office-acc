import {
  ChevronRight,
  ChevronDown,
  ExternalLink,
  RefreshCw,
  FolderOpen,
  FileText,
  AlertCircle,
  Loader2,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function formatSize(bytes) {
  if (bytes === 0 || bytes === null || bytes === undefined) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(dateString) {
  if (!dateString) return '—';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleString();
}

export function SharePointMirrorPage() {
  const { authHeaders } = useAuth();
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [mirrorData, setMirrorData] = useState(null);
  const [error, setError] = useState('');
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingMirror, setLoadingMirror] = useState(false);
  const [selectedFolderId, setSelectedFolderId] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() });
      if (!response.ok) throw new Error('Could not load projects.');
      const data = await response.json();
      setProjects(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingProjects(false);
    }
  }, [authHeaders]);

  const loadMirrorData = useCallback(
    async (projectId) => {
      if (!projectId) {
        setMirrorData(null);
        return;
      }
      setLoadingMirror(true);
      setError('');
      try {
        const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/sharepoint-mirror`, {
          headers: authHeaders(),
        });
        if (!response.ok) {
          const errData = await response.json().catch(() => ({}));
          throw new Error(errData.detail || `Failed to load SharePoint mirror (${response.status})`);
        }
        const data = await response.json();
        setMirrorData(data);
        setSelectedFolderId(data?.provisioned ? 'root' : null);
        setLastRefreshed(new Date());
      } catch (err) {
        setError(err.message);
        setMirrorData(null);
      } finally {
        setLoadingMirror(false);
      }
    },
    [authHeaders],
  );

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    if (selectedId) {
      loadMirrorData(selectedId);
    } else {
      setMirrorData(null);
    }
  }, [selectedId, loadMirrorData]);

  const handleRefresh = useCallback(() => {
    if (selectedId) {
      loadMirrorData(selectedId);
    }
  }, [selectedId, loadMirrorData]);

  const handleOpenInSharePoint = useCallback(() => {
    if (mirrorData?.target_location) {
      window.open(mirrorData.target_location, '_blank', 'noopener,noreferrer');
    }
  }, [mirrorData]);

  const selectedFolder = useMemo(() => {
    if (!mirrorData?.folder_hierarchy || selectedFolderId === 'root' || !selectedFolderId) {
      return {
        id: 'root',
        name: 'Project Root',
        children: mirrorData?.folder_hierarchy || [],
        files: mirrorData?.files || [],
      };
    }

    function findFolder(folders, targetId) {
      for (const folder of folders) {
        if (folder.id === targetId) return folder;
        if (folder.children) {
          const found = findFolder(folder.children, targetId);
          if (found) return found;
        }
      }
      return null;
    }

    return (
      findFolder(mirrorData.folder_hierarchy, selectedFolderId) || {
        id: 'root',
        name: 'Project Root',
        children: mirrorData.folder_hierarchy,
        files: mirrorData.files,
      }
    );
  }, [mirrorData, selectedFolderId]);

  const folderTree = useMemo(() => {
    if (!mirrorData?.folder_hierarchy) return [];

    const flatten = (folders, depth = 0) => {
      return folders.flatMap((folder) => [
        { ...folder, depth },
        ...(folder.children ? flatten(folder.children, depth + 1) : []),
      ]);
    };

    return flatten(mirrorData.folder_hierarchy);
  }, [mirrorData]);

  const breadcrumb = useMemo(() => {
    if (!mirrorData?.provisioned || selectedFolderId === 'root' || !selectedFolderId) {
      return [{ id: 'root', name: 'Project Root' }];
    }

    const crumbs = [{ id: 'root', name: 'Project Root' }];

    function buildPath(folders, targetId, path = []) {
      for (const folder of folders) {
        const newPath = [...path, { id: folder.id, name: folder.name }];
        if (folder.id === targetId) {
          return newPath;
        }
        if (folder.children) {
          const found = buildPath(folder.children, targetId, newPath);
          if (found) return found;
        }
      }
      return null;
    }

    const path = buildPath(mirrorData.folder_hierarchy, selectedFolderId);
    return path ? [...crumbs, ...path] : crumbs;
  }, [mirrorData, selectedFolderId]);

  const syncStatus = mirrorData?.connection || { connected: false, status: 'Unknown', error: 'No data' };
  const isConnected = syncStatus.connected === true;

  return (
    <main className="resource-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Document Management</span>
            <i>/</i>
            <span>Cloud Storage Sync</span>
            <i>/</i>
            <strong>SharePoint Integration</strong>
          </div>
          <h1>Automated SharePoint Directory Mirror</h1>
          <p>
            View real-time folder hierarchy and file listings from the provisioned SharePoint directory. Data
            is fetched on-demand from Microsoft Graph API.
          </p>
        </div>
        <label className="project-switcher">
          <span>Project Name</span>
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            disabled={loadingProjects}
          >
            <option value="">Select project</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.project_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="resource-error">{error}</div>}

      <div className="summary-grid">
        <div className="summary-card">
          <span className="summary-label">SharePoint Target Location</span>
          <strong style={{ fontSize: '12px', display: 'block', wordBreak: 'break-all', maxWidth: '100%' }}>
            {mirrorData?.target_location ? (
              <a
                href={mirrorData.target_location}
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: '#1671ad', textDecoration: 'underline' }}
              >
                {mirrorData.target_location}
              </a>
            ) : mirrorData?.provisioned === false ? (
              <span className="sp-status pending">
                Not provisioned — {mirrorData?.error || 'No SharePoint folder configured'}
              </span>
            ) : (
              <span className="sp-status loading">Loading...</span>
            )}
          </strong>
          <span className="summary-caption">Real folder path from Graph API</span>
        </div>

        <div className="summary-card">
          <span className="summary-label">Sync Status</span>
          <strong>
            {isConnected ? (
              <span className="sp-status connected">
                <CheckCircle
                  size={12}
                  style={{ display: 'inline-block', marginRight: '4px', verticalAlign: 'middle' }}
                />
                Connected
              </span>
            ) : (
              <span className="sp-status error">
                <XCircle
                  size={12}
                  style={{ display: 'inline-block', marginRight: '4px', verticalAlign: 'middle' }}
                />
                {syncStatus.status || 'Disconnected'}
              </span>
            )}
          </strong>
          <span className="summary-caption">{syncStatus.error || 'Live Graph API connectivity check'}</span>
        </div>

        <div className="summary-card">
          <span className="summary-label">Document Repository Stats</span>
          <strong>{mirrorData?.stats?.total_files ?? 0} Files</strong>
          <span className="summary-caption green-caption">
            Total Size: {mirrorData?.stats?.total_size_formatted ?? '0 B'}
          </span>
        </div>

        <div className="summary-card bench-card">
          <span className="summary-label">Last Refreshed</span>
          <strong>{lastRefreshed ? lastRefreshed.toLocaleTimeString() : 'Never'}</strong>
          <span className="summary-caption">Manual on-demand fetch from Graph API</span>
        </div>
      </div>

      <section className="allocation-card">
        <div className="allocation-header">
          <div>
            <h2>SharePoint Folder Hierarchy</h2>
            <p>Real folder structure as it exists in SharePoint. Click a folder to view its files.</p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="button button-secondary"
              type="button"
              onClick={handleOpenInSharePoint}
              disabled={!mirrorData?.target_location}
              title="Open in SharePoint"
            >
              <ExternalLink size={14} /> Open in SharePoint
            </button>
            <button
              className="button button-primary"
              type="button"
              onClick={handleRefresh}
              disabled={loadingMirror || !selectedId}
            >
              <RefreshCw size={14} className={loadingMirror ? 'spin' : ''} />
              {loadingMirror ? 'Refreshing...' : 'Force Resync'}
            </button>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '20px', padding: '0 20px 20px' }}>
          <div style={{ flex: '1', minWidth: '300px', maxWidth: '400px' }}>
            <div className="resource-toolbar" style={{ marginBottom: '12px' }}>
              <div className="breadcrumb" style={{ marginBottom: '8px', fontSize: '11px' }}>
                {breadcrumb.map((crumb, idx) => (
                  <span key={crumb.id} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    {idx > 0 && <ChevronRight size={12} style={{ color: '#b2bcc5' }} />}
                    <button
                      type="button"
                      className={crumb.id === selectedFolderId ? 'active' : ''}
                      onClick={() => setSelectedFolderId(crumb.id === 'root' ? null : crumb.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        padding: '0',
                        color: crumb.id === selectedFolderId ? '#1671ad' : '#4f6378',
                        fontWeight: crumb.id === selectedFolderId ? '700' : '500',
                        fontSize: '11px',
                        cursor: 'pointer',
                        textDecoration: crumb.id === selectedFolderId ? 'underline' : 'none',
                      }}
                    >
                      {crumb.name}
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div
              className="resource-table-wrap"
              style={{
                maxHeight: '500px',
                overflowY: 'auto',
                border: '1px solid #e0e7ed',
                borderRadius: '6px',
              }}
            >
              <table className="resource-table wbs-table">
                <thead>
                  <tr>
                    <th style={{ width: '100%' }}>FOLDER STRUCTURE</th>
                  </tr>
                </thead>
                <tbody>
                  {folderTree.length === 0 && mirrorData?.provisioned ? (
                    <tr>
                      <td style={{ padding: '20px', textAlign: 'center', color: '#8a93a0' }}>
                        <FolderOpen
                          size={24}
                          style={{ display: 'block', margin: '0 auto 8px', color: '#b2bcc5' }}
                        />
                        No subfolders found in this project's SharePoint directory.
                      </td>
                    </tr>
                  ) : folderTree.length === 0 && mirrorData?.provisioned === false ? (
                    <tr>
                      <td style={{ padding: '20px', textAlign: 'center', color: '#8a93a0' }}>
                        <span
                          className="sp-status error"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            marginBottom: '8px',
                          }}
                        >
                          <AlertCircle size={20} style={{ color: '#dda837' }} />
                          {mirrorData?.error || 'SharePoint directory not provisioned for this project.'}
                        </span>
                      </td>
                    </tr>
                  ) : (
                    folderTree.map((folder) => (
                      <tr
                        key={folder.id}
                        onClick={() => setSelectedFolderId(folder.id)}
                        style={{
                          cursor: 'pointer',
                          background: selectedFolderId === folder.id ? '#eef7fd' : 'transparent',
                          borderLeft: selectedFolderId === folder.id ? '3px solid #1671ad' : 'none',
                        }}
                      >
                        <td style={{ padding: '10px 14px', whiteSpace: 'nowrap' }}>
                          <span
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '8px',
                              paddingLeft: `${folder.depth * 20}px`,
                            }}
                          >
                            <FolderOpen size={16} style={{ color: '#1671ad' }} />
                            <strong>{folder.name}</strong>
                            {folder.children && folder.children.length > 0 && (
                              <span style={{ fontSize: '10px', color: '#8a93a0' }}>
                                ({folder.children.length})
                              </span>
                            )}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                  {loadingMirror && folderTree.length === 0 && (
                    <tr>
                      <td style={{ padding: '20px', textAlign: 'center', color: '#8a93a0' }}>
                        <Loader2
                          size={24}
                          className="spin"
                          style={{ display: 'block', margin: '0 auto 8px', color: '#1671ad' }}
                        />
                        Loading folder hierarchy...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ flex: '1.5', minWidth: '400px' }}>
            <div
              className="resource-table-wrap"
              style={{
                maxHeight: '500px',
                overflowY: 'auto',
                border: '1px solid #e0e7ed',
                borderRadius: '6px',
              }}
            >
              <table className="resource-table">
                <thead>
                  <tr>
                    <th style={{ width: '40%' }}>DOCUMENT NAME</th>
                    <th style={{ width: '20%' }}>LAST MODIFIED</th>
                    <th style={{ width: '20%' }}>MODIFIED BY</th>
                    <th style={{ width: '15%' }}>SIZE</th>
                    <th style={{ width: '5%' }}></th>
                  </tr>
                </thead>
                <tbody>
                  {selectedFolder?.files && selectedFolder.files.length > 0 ? (
                    selectedFolder.files.map((file) => (
                      <tr key={file.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <FileText size={16} style={{ color: '#1671ad' }} />
                            <span>{file.name}</span>
                          </div>
                        </td>
                        <td>{formatDate(file.last_modified_date_time)}</td>
                        <td>{file.last_modified_by}</td>
                        <td>{formatSize(file.size)}</td>
                        <td>
                          <a
                            href={file.web_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="wbs-eye"
                            title="Open in SharePoint"
                            style={{ textDecoration: 'none' }}
                          >
                            <ExternalLink size={14} style={{ color: '#1671ad' }} />
                          </a>
                        </td>
                      </tr>
                    ))
                  ) : mirrorData?.provisioned === false ? (
                    <tr>
                      <td colSpan={5} style={{ padding: '20px', textAlign: 'center', color: '#8a93a0' }}>
                        <span
                          className="sp-status error"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}
                        >
                          <AlertCircle size={20} style={{ color: '#dda837' }} />
                          {mirrorData?.error || 'SharePoint directory not provisioned for this project.'}
                        </span>
                      </td>
                    </tr>
                  ) : !mirrorData?.provisioned ? (
                    <tr>
                      <td colSpan={5} style={{ padding: '20px', textAlign: 'center', color: '#8a93a0' }}>
                        <Loader2
                          size={24}
                          className="spin"
                          style={{ display: 'block', margin: '0 auto 8px', color: '#1671ad' }}
                        />
                        Loading file listing...
                      </td>
                    </tr>
                  ) : (
                    <tr>
                      <td colSpan={5} style={{ padding: '20px', textAlign: 'center', color: '#8a93a0' }}>
                        <FileText
                          size={24}
                          style={{ display: 'block', margin: '0 auto 8px', color: '#b2bcc5' }}
                        />
                        No files in this folder.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {selectedFolder && selectedFolder.files && selectedFolder.files.length > 0 && (
              <div className="allocation-footer" style={{ marginTop: '12px', fontSize: '11px' }}>
                <span>
                  {selectedFolder.files.length} file(s) in "{selectedFolder.name}"
                </span>
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
