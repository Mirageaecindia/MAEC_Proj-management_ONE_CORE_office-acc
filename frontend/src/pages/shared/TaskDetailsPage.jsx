import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const TASK_STATUS_STEPS = ['To Do', 'In-Progress', 'Submitted for Review', 'Approved'];
const SUBTASK_STATUS_STEPS = ['To Do', 'In-Progress', 'Done'];

function formatDateTime(isoStr) {
    if (!isoStr) return '\u2014';
    try {
        const d = new Date(isoStr);
        return d.toLocaleString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
        });
    } catch { return isoStr; }
}

function formatDate(dateStr) {
    if (!dateStr) return '\u2014';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch { return dateStr; }
}

export function TaskDetailsPage() {
    const [searchParams] = useSearchParams();
    const { user, role, authHeaders } = useAuth();
    const isEngineer = role === 'engineer';

    const nodeId = Number(searchParams.get('nodeId')) || null;
    const projectId = Number(searchParams.get('projectId')) || null;

    const [node, setNode] = useState(null);
    const [project, setProject] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [commentText, setCommentText] = useState('');
    const [statusSelect, setStatusSelect] = useState('');
    const [updating, setUpdating] = useState(false);
    const [toast, setToast] = useState(null);

    const showToast = useCallback((type, message) => {
        setToast({ type, message });
        setTimeout(() => setToast(null), 5000);
    }, []);

    const loadData = useCallback(async () => {
        if (!nodeId) return;
        setLoading(true);
        setError('');
        try {
            const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${nodeId}`, { headers: authHeaders() });
            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                throw new Error(body.detail || 'Could not load task details.');
            }
            const data = await resp.json();
            setNode(data);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, [nodeId, authHeaders]);

    const loadProject = useCallback(async () => {
        if (!projectId) return;
        try {
            const resp = await fetch(`${API_BASE_URL}/api/projects/${projectId}`, { headers: authHeaders() });
            if (resp.ok) setProject(await resp.json());
        } catch { /* project optional */ }
    }, [projectId, authHeaders]);

    useEffect(() => {
        loadData();
        loadProject();
    }, [loadData, loadProject]);

    const statusSteps = node?.node_type === 'subtask' ? SUBTASK_STATUS_STEPS : TASK_STATUS_STEPS;
    const currentStatusIdx = statusSteps.indexOf(node?.deliverable_status || 'To Do');

    async function handleAdvanceStatus() {
        if (!statusSelect || !nodeId) return;
        setUpdating(true);
        setError('');
        try {
            const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${nodeId}/advance-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({
                    new_status: statusSelect,
                    comment: commentText || null,
                }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(body.detail || 'Could not update status.');
            setCommentText('');
            setStatusSelect('');
            showToast('success', `Status updated to '${statusSelect}'.`);
            loadData();
        } catch (err) {
            setError(err.message);
            showToast('error', err.message);
        } finally {
            setUpdating(false);
        }
    }

    async function handleAddComment() {
        if (!commentText.trim() || !nodeId) return;
        try {
            const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${nodeId}/comments`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ comment: commentText }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(body.detail || 'Could not add comment.');
            setCommentText('');
            showToast('success', 'Comment added.');
            loadData();
        } catch (err) {
            setError(err.message);
            showToast('error', err.message);
        }
    }

    const maxAdvance = node && currentStatusIdx >= 0 && currentStatusIdx < statusSteps.length - 1
        ? statusSteps[currentStatusIdx + 1]
        : null;

    return (
        <main className="resource-page">
            <div className="resource-heading-row">
                <div>
                    <div className="breadcrumb">
                        <span>WBS Structure</span>
                        {node?.phase && <>
                            <i>/</i>
                            <strong>{node.phase}</strong>
                        </>}
                        {node?.wbs_code && <>
                            <i>/</i>
                            <strong>{node.wbs_code}</strong>
                        </>}
                    </div>
                    <h1>Work Breakdown Structure (WBS) &amp; Task Deliverables</h1>
                    <p>{node ? `${node.task_name} — Detail view` : 'Loading task details...'}</p>
                </div>
                <label className="project-switcher">
                    <span>Project Name</span>
                    <div className="project-pill-box">
                        <span className="project-pill-name" title={project?.project_name}>
                            {project?.project_name || (node ? `Project #${node.project_id}` : 'Select project')}
                        </span>
                    </div>
                </label>
            </div>

            {toast && (
                <div className={`upload-toast ${toast.type}`} role="status" onClick={() => setToast(null)}>
                    {toast.message}
                </div>
            )}

            {error && <div className="resource-error">{error}</div>}

            {loading && (
                <div className="resource-error">Loading task details...</div>
            )}

            {node && !loading && (
                <>
                    {/* Status Stepper */}
                    <section className="allocation-card" style={{ marginBottom: 20 }}>
                        <div className="allocation-header">
                            <div>
                                <h2>Status Progress</h2>
                            </div>
                        </div>
                        <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            {statusSteps.map((step, idx) => {
                                const isCurrent = node.deliverable_status === step;
                                const isPast = idx < currentStatusIdx;
                                return (
                                    <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                        <div
                                            style={{
                                                padding: '5px 14px',
                                                borderRadius: 16,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                background: isCurrent ? '#1671ad' : isPast ? '#2b9c6c' : '#e5ebef',
                                                color: isCurrent || isPast ? '#fff' : '#6d7e91',
                                                border: isCurrent ? '2px solid #0f4d78' : '1px solid transparent',
                                            }}
                                        >
                                            {step}
                                        </div>
                                        {idx < statusSteps.length - 1 && (
                                            <div style={{
                                                width: 28, height: 2,
                                                background: idx < currentStatusIdx ? '#2b9c6c' : '#c5d9ea',
                                            }} />
                                        )}
                                    </div>
                                );
                            })}
                            <span style={{ marginLeft: 12, fontSize: 11, color: '#6d7e91' }}>
                                Current: <strong style={{ color: '#1671ad' }}>{node.deliverable_status}</strong>
                            </span>
                        </div>
                    </section>

                    {/* Detail Fields */}
                    <section className="allocation-card">
                        <div className="allocation-header">
                            <div>
                                <h2>
                                    {node.wbs_code} : {node.task_name}
                                </h2>
                                <p>{node.node_type === 'subtask' ? 'Subtask' : 'Task'} detail</p>
                            </div>
                        </div>
                        <div style={{ padding: '16px 20px' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px 24px' }}>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>TITLE:</span>
                                    <div style={{ fontSize: 14, fontWeight: 600, color: '#21334a', marginTop: 2 }}>
                                        {node.wbs_code || ''} {node.task_name || ''}
                                    </div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Linked:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>
                                        {node.linked_code ? `${node.linked_code} (parent)` : node.node_type === 'subtask' ? 'Root task' : 'N/A'}
                                    </div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Description:</span>
                                    <div style={{ fontSize: 13, color: '#21334a', marginTop: 2, whiteSpace: 'pre-wrap' }}>
                                        {node.description || '\u2014'}
                                    </div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Severity Scale:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>
                                        {node.severity || '\u2014'}
                                    </div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Target Start Date:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{formatDate(node.start_date)}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Actual Start Date and Time:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{formatDateTime(node.actual_start_datetime)}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Target End Date:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{formatDate(node.target_due_date)}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Actual End Date and Time:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{formatDateTime(node.actual_end_datetime)}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Assigned Lead:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{node.assigned_lead || '\u2014'}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Estimated Hours:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{node.estimated_hours ?? '\u2014'}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Phase:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{node.phase || '\u2014'}</div>
                                </div>
                                <div>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: '#6d8090', textTransform: 'uppercase', letterSpacing: '.04em' }}>Engineer:</span>
                                    <div style={{ fontSize: 14, color: '#21334a', marginTop: 2 }}>{node.assigned_engineer_name || '\u2014'}</div>
                                </div>
                            </div>

                            {/* Engineer Actions */}
                            {isEngineer && (
                                <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #e5ebef' }}>
                                    <h3 style={{ margin: '0 0 10px', fontSize: 13, color: '#243e57' }}>Your Actions</h3>
                                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                                        {maxAdvance ? (
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                                                <select
                                                    value={statusSelect}
                                                    onChange={(e) => setStatusSelect(e.target.value)}
                                                    style={{ height: 39, padding: '0 12px', border: '1px solid #cfd9e2', borderRadius: 5, fontSize: 12, minWidth: 200 }}
                                                >
                                                    <option value="">Advance to {maxAdvance}...</option>
                                                    <option value={maxAdvance}>{maxAdvance}</option>
                                                </select>
                                                <textarea
                                                    placeholder="Comment (optional)"
                                                    value={commentText}
                                                    onChange={(e) => setCommentText(e.target.value)}
                                                    style={{ width: '100%', minHeight: 60, padding: '8px 12px', border: '1px solid #cfd9e2', borderRadius: 5, fontSize: 12, resize: 'vertical', fontFamily: 'inherit' }}
                                                />
                                                <button
                                                    className="button button-primary"
                                                    type="button"
                                                    disabled={updating || !statusSelect}
                                                    onClick={handleAdvanceStatus}
                                                >
                                                    {updating ? 'Updating...' : `Advance to ${maxAdvance}`}
                                                </button>
                                            </div>
                                        ) : (
                                            <div style={{ fontSize: 12, color: '#6d7e91' }}>
                                                {currentStatusIdx >= statusSteps.length - 1
                                                    ? 'This task has reached its final status.'
                                                    : 'No further status transitions available.'}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </section>

                    {/* History / Comments */}
                    <section className="allocation-card" style={{ marginTop: 20 }}>
                        <div className="allocation-header">
                            <div>
                                <h2>History / Comment Log</h2>
                            </div>
                        </div>
                        <div style={{ padding: '16px 20px' }}>
                            {(!node.history || node.history.length === 0) ? (
                                <div style={{ fontSize: 12, color: '#8898a8', fontStyle: 'italic' }}>No history entries yet.</div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                    {node.history.map((entry) => (
                                        <div key={entry.id} style={{ padding: '10px 14px', background: '#f8fbfd', border: '1px solid #edf1f4', borderRadius: 6 }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                                                <strong style={{ fontSize: 12, color: '#21334a' }}>
                                                    {entry.user_name}
                                                    {entry.action === 'status_change' && (
                                                        <span style={{ marginLeft: 6, fontSize: 10, color: '#1671ad', fontWeight: 700 }}>
                                                            {entry.old_status || '—'} &#8594; {entry.new_status}
                                                        </span>
                                                    )}
                                                    {entry.action === 'comment' && (
                                                        <span style={{ marginLeft: 6, fontSize: 10, color: '#6d7e91' }}>Comment</span>
                                                    )}
                                                </strong>
                                                <span style={{ fontSize: 10, color: '#8a93a0' }}>
                                                    {new Date(entry.created_at).toLocaleString('en-US', {
                                                        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', year: 'numeric',
                                                    })}
                                                </span>
                                            </div>
                                            {entry.comment && (
                                                <div style={{ fontSize: 12, color: '#40566b', marginTop: 4 }}>{entry.comment}</div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {isEngineer && (
                                <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid #e5ebef' }}>
                                    <textarea
                                        placeholder="Add a comment to the history log..."
                                        value={commentText}
                                        onChange={(e) => setCommentText(e.target.value)}
                                        style={{ width: '100%', minHeight: 60, padding: '8px 12px', border: '1px solid #cfd9e2', borderRadius: 5, fontSize: 12, resize: 'vertical', fontFamily: 'inherit' }}
                                    />
                                    <button
                                        className="button button-primary"
                                        type="button"
                                        disabled={!commentText.trim()}
                                        onClick={handleAddComment}
                                        style={{ marginTop: 8 }}
                                    >
                                        Add Comment
                                    </button>
                                </div>
                            )}
                        </div>
                    </section>
                </>
            )}
        </main>
    );
}
