import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const TASK_STATUS_STEPS = ['To Do', 'In-Progress', 'Submitted for Approval', 'Approved'];
const SUBTASK_STATUS_STEPS = ['To Do', 'In-Progress', 'Done'];

// Automatic working-time tracking: only active interaction is counted. The
// timer pauses when the tab is hidden or there is no input activity for the
// idle window, and the cumulative active seconds are reported to the backend
// on a heartbeat, which enforces the daily cap server-side. The Engineer only
// ever sees the Login/Logout state — never the duration.
const IDLE_TIMEOUT_MS = 2 * 60 * 1000;
const SYNC_INTERVAL_MS = 15000;

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
    const navigate = useNavigate();
    const { user, role, authHeaders } = useAuth();
    const isEngineer = role === 'engineer';
    const isLead = role === 'lead';

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
    const [pendingStatus, setPendingStatus] = useState(null);
    const [confirmError, setConfirmError] = useState('');

    // Automatic working-time tracking (Engineer, subtask pages only). The
    // Engineer sees only the Login/Logout state — no timer, no counters.
    const [session, setSession] = useState(null);
    const [paused, setPaused] = useState(false);
    const [trackingBusy, setTrackingBusy] = useState(false);
    const [otherSessionActive, setOtherSessionActive] = useState(false);

    const secondsRef = useRef(0);
    const lastActivityRef = useRef(Date.now());
    const sessionRef = useRef(null);
    sessionRef.current = session;
    const capToastAtRef = useRef(0);

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

    // Restore an active tracking session after a refresh (or report today's
    // banked hours when nothing is running), so tracking resumes seamlessly.
    const loadTrackingStatus = useCallback(async () => {
        if (!isEngineer) return;
        try {
            const resp = await fetch(`${API_BASE_URL}/api/subtask-tracking/status`, { headers: authHeaders() });
            if (!resp.ok) return;
            const data = await resp.json();
            const active = data.active_session || null;
            if (active && active.subtask_id === nodeId) {
                secondsRef.current = active.active_seconds || 0;
                setSession(active);
                setOtherSessionActive(false);
            } else {
                secondsRef.current = 0;
                setSession(null);
                setOtherSessionActive(Boolean(active));
            }
        } catch { /* tracking status is non-critical */ }
    }, [isEngineer, nodeId, authHeaders]);

    useEffect(() => {
        loadData();
        loadProject();
        loadTrackingStatus();
    }, [loadData, loadProject, loadTrackingStatus]);

    const statusSteps = node?.node_type === 'subtask' ? SUBTASK_STATUS_STEPS : TASK_STATUS_STEPS;
    const currentStatusIdx = statusSteps.indexOf(node?.deliverable_status || 'To Do');

    // The stepper is strictly sequential: an engineer can only act on the
    // single next step. 'Approved' (main tasks) is lead-only via /approve, so
    // it is never a clickable engineer target; 'Done' (subtasks) is the
    // engineer's final step and stays clickable until reached.
    const nextStatusIdx = currentStatusIdx + 1;
    const engineerCanAdvance = isEngineer
        && currentStatusIdx >= 0
        && nextStatusIdx < statusSteps.length
        && (node?.node_type === 'subtask' || nextStatusIdx < statusSteps.length - 1);

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

    async function confirmStatusChange() {
        if (!pendingStatus || !nodeId) return;
        if (pendingStatus === node.deliverable_status) {
            setPendingStatus(null);
            setConfirmError('');
            loadData();
            return;
        }
        setUpdating(true);
        setConfirmError('');
        try {
            const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${nodeId}/advance-status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ new_status: pendingStatus, comment: null }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(body.detail || 'Could not update status.');
            setPendingStatus(null);
            setConfirmError('');
            showToast('success', `Status updated to '${pendingStatus}'.`);
            loadData();
        } catch (err) {
            setConfirmError(err.message);
            showToast('error', err.message);
        } finally {
            setUpdating(false);
        }
    }

    async function handleApprove() {
        if (!nodeId) return;
        setUpdating(true);
        setError('');
        try {
            const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${nodeId}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ new_status: 'Approved', comment: commentText || null }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(body.detail || 'Could not approve the task.');
            setCommentText('');
            showToast('success', 'Task approved.');
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

    // Automatic working-time tracking logic (Engineer, subtask pages only).
    // Counting only advances on ticks that pass the idle/hidden gate; the
    // cumulative active seconds are reported to the backend on a heartbeat.
    // The Engineer never sees the timer or any hour values — only the
    // Login/Logout state.
    const setActive = useCallback(() => {
        lastActivityRef.current = Date.now();
        if (paused) setPaused(false);
    }, [paused]);

    useEffect(() => {
        if (!session || paused) return undefined;
        const tick = window.setInterval(() => {
            const now = Date.now();
            if (document.hidden) {
                setPaused(true);
                return;
            }
            if (now - lastActivityRef.current > IDLE_TIMEOUT_MS) {
                setPaused(true);
                return;
            }
            secondsRef.current = secondsRef.current + 1;
        }, 1000);
        return () => window.clearInterval(tick);
    }, [session, paused]);

    useEffect(() => {
        if (!session) return undefined;
        const handleVisibility = () => {
            if (document.hidden) {
                setPaused(true);
            } else {
                setActive();
            }
        };
        const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'];
        events.forEach((e) => window.addEventListener(e, setActive, { passive: true }));
        document.addEventListener('visibilitychange', handleVisibility);
        return () => {
            events.forEach((e) => window.removeEventListener(e, setActive));
            document.removeEventListener('visibilitychange', handleVisibility);
        };
    }, [session, setActive]);

    useEffect(() => {
        if (!session) return undefined;
        const sync = async () => {
            if (paused) return;
            try {
                const resp = await fetch(`${API_BASE_URL}/api/subtask-tracking/${session.id}/sync`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', ...authHeaders() },
                    body: JSON.stringify({ active_seconds: secondsRef.current }),
                });
                const body = await resp.json().catch(() => ({}));
                if (resp.status === 409) {
                    setPaused(true);
                    const now = Date.now();
                    if (now - capToastAtRef.current > 60000) {
                        capToastAtRef.current = now;
                        showToast('error', body.detail || 'You have reached the 8-hour daily working limit.');
                    }
                    return;
                }
                if (!resp.ok) return;
                if (body.active_seconds !== undefined && body.active_seconds !== null) {
                    secondsRef.current = body.active_seconds;
                }
            } catch { /* ignore transient sync errors; next beat retries */ }
        };
        const id = window.setInterval(sync, SYNC_INTERVAL_MS);
        return () => window.clearInterval(id);
    }, [session, paused, authHeaders, showToast]);

    async function startTracking() {
        if (!isEngineer || node?.node_type !== 'subtask' || trackingBusy) return;
        setTrackingBusy(true);
        try {
            const resp = await fetch(`${API_BASE_URL}/api/subtask-tracking/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ subtask_id: nodeId }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(body.detail || 'Could not start tracking.');
            secondsRef.current = body.active_seconds || 0;
            setSession(body);
            setOtherSessionActive(false);
            setActive();
            setPaused(false);
            showToast('success', 'Logged in — working time is now being tracked for this subtask.');
        } catch (err) {
            showToast('error', err.message);
        } finally {
            setTrackingBusy(false);
        }
    }

    async function endTracking() {
        if (!session || trackingBusy) return;
        setTrackingBusy(true);
        try {
            const resp = await fetch(`${API_BASE_URL}/api/subtask-tracking/${session.id}/end`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ active_seconds: secondsRef.current }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(body.detail || 'Could not stop tracking.');
            setSession(null);
            setOtherSessionActive(false);
            secondsRef.current = 0;
            setPaused(false);
            if (body.exceeded) {
                showToast('success', 'Logged out — time beyond the 8-hour daily limit was not counted.');
            } else {
                showToast('success', 'Logged out — working time saved to the subtask log.');
            }
        } catch (err) {
            showToast('error', err.message);
        } finally {
            setTrackingBusy(false);
        }
    }

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
                    <section className="allocation-card td-card">
                        {/* Header: title (left) + compact horizontal stepper (right) */}
                        <div className="td-head">
                            <div className="td-title td-card-heading">Task Details</div>
                            <div className="td-stepper">
                                {isEngineer && node.node_type === 'subtask' && (
                                    <button
                                        type="button"
                                        className={`td-login-btn${session ? ' logged-in' : ''}`}
                                        disabled={trackingBusy || (!session && otherSessionActive)}
                                        title={session
                                            ? 'Logout — stop tracking and save this subtask\u2019s working time'
                                            : otherSessionActive
                                                ? 'You already have an active session on another subtask'
                                                : 'Login — start tracking working time for this subtask'}
                                        onClick={session ? () => endTracking() : () => startTracking()}
                                    >
                                        {session ? 'Logout' : 'Login'}
                                    </button>
                                )}
                                {statusSteps.map((step, idx) => {
                                    const isCurrent = node.deliverable_status === step;
                                    const isPast = idx < currentStatusIdx;
                                    const isFinal = idx === statusSteps.length - 1;
                                    const pillClass = `td-pill${isCurrent ? ' current' : ''}${isPast ? ' past' : ''}${isCurrent && isFinal ? ' done-current' : ''}`;
                                    return (
                                        <Fragment key={step}>
                                            {isEngineer && engineerCanAdvance && idx === nextStatusIdx ? (
                                                <button
                                                    type="button"
                                                    className={pillClass}
                                                    aria-label={`Change status to ${step}`}
                                                    onClick={() => setPendingStatus(step)}
                                                >
                                                    {step}
                                                </button>
                                            ) : (
                                                <div className={pillClass}>
                                                    {step}
                                                </div>
                                            )}
                                            {idx < statusSteps.length - 1 && (
                                                <div className={`td-connector${idx < currentStatusIdx ? ' past' : ''}`} />
                                            )}
                                        </Fragment>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Detail fields — two-column compact block */}
                        <div className="td-body">
                            <div className="td-columns">
                                <div className="td-column td-column-left">
                                    <div className="td-field">
                                        <span>Title* :</span>
                                        <div>{node.wbs_code ? `${node.wbs_code} : ${node.task_name}` : node.task_name}</div>
                                    </div>
                                    <div className="td-field">
                                        <span>Description* :</span>
                                        <div>{node.description || '\u2014'}</div>
                                    </div>
                                    <div className="td-field">
                                        <span>Target Start Date* :</span>
                                        <div>{formatDate(node.start_date)}</div>
                                    </div>
                                    <div className="td-field">
                                        <span>Target End Date* :</span>
                                        <div>{formatDate(node.target_due_date || node.end_date)}</div>
                                    </div>
                                    <div className="td-field">
                                        <span>Severity Scale* :</span>
                                        <div>{node.severity || '\u2014'}</div>
                                    </div>
                                    <div className="td-field">
                                        <span>Linked* :</span>
                                        <div className="td-linked-list">
                                            {node.node_type === 'subtask'
                                                ? node.parent_id
                                                    ? (
                                                        <a
                                                            className="td-linked-item td-linked-link"
                                                            href={`/task-details?nodeId=${node.parent_id}&projectId=${node.project_id}`}
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                navigate(`/task-details?nodeId=${node.parent_id}&projectId=${node.project_id}`);
                                                            }}
                                                        >
                                                            {node.linked_code ? `${node.linked_code} \u2013 ${node.linked_task_name}` : node.linked_task_name}
                                                        </a>
                                                    )
                                                    : <span className="td-linked-item td-linked-empty">{'\u2014'}</span>
                                                : (node.children || []).length > 0
                                                    ? (node.children || []).map((child) => {
                                                        const childRoute = `/task-details?nodeId=${child.id}&projectId=${child.project_id || node.project_id}`;
                                                        return (
                                                            <a
                                                                key={child.id}
                                                                className="td-linked-item td-linked-link"
                                                                href={childRoute}
                                                                onClick={(e) => {
                                                                    e.preventDefault();
                                                                    navigate(childRoute);
                                                                }}
                                                            >
                                                                {child.wbs_code ? `${child.wbs_code} \u2013 ${child.task_name}` : child.task_name}
                                                                <em className="td-linked-status">{child.deliverable_status}</em>
                                                            </a>
                                                        );
                                                    })
                                                    : <span className="td-linked-item td-linked-empty">{'\u2014'}</span>}
                            </div>
                        </div>

                                </div>
                                <div className="td-column td-column-right">
                                    <div className="td-field">
                                        <span>Actual Start Date and Time* :</span>
                                        <div>{formatDateTime(node.actual_start_datetime)}</div>
                                    </div>
                                    <div className="td-field">
                                        <span>Actual End Date and Time* :</span>
                                        <div>{formatDateTime(node.actual_end_datetime)}</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* History / Comments — adjoining light panel */}
                        <div className="td-history">
                            <div className="td-history-title">History:</div>
                            {(!node.history || node.history.length === 0) ? (
                                <div className="td-history-empty">No history entries yet.</div>
                            ) : (
                                <div className="td-history-list">
                                    {node.history.map((entry) => (
                                        <div key={entry.id} className="td-history-item">
                                            <span className="who">{entry.user_name}</span>
                                            {entry.action === 'status_change'
                                                ? <> : Change {entry.old_status || '\u2014'} to {entry.new_status}</>
                                                : <> : Comment</>}
                                            <span className="when">- {formatDateTime(entry.created_at)}</span>
                                            {entry.comment && <div className="note">{entry.comment}</div>}
                                        </div>
                                    ))}
                                </div>
                            )}

                            {isEngineer && (
                                <div className="td-history-comment">
                                    <textarea
                                        placeholder="Add a comment to the history log..."
                                        value={commentText}
                                        onChange={(e) => setCommentText(e.target.value)}
                                    />
                                    <button
                                        className="button button-primary"
                                        type="button"
                                        disabled={!commentText.trim()}
                                        onClick={handleAddComment}
                                    >
                                        Add Comment
                                    </button>
                                </div>
                            )}
                        </div>

                        {/* Your Actions — Lead approval workflow */}
                        {isLead && node && (
                            <div className="td-actions">
                                <h3>Your Actions</h3>
                                {node.node_type === 'subtask' ? (
                                    maxAdvance ? (
                                        <div className="td-actions-row">
                                            <div className="td-actions-controls">
                                                <select
                                                    value={statusSelect}
                                                    onChange={(e) => setStatusSelect(e.target.value)}
                                                >
                                                    <option value="">Advance to {maxAdvance}...</option>
                                                    <option value={maxAdvance}>{maxAdvance}</option>
                                                </select>
                                                <textarea
                                                    placeholder="Comment (optional)"
                                                    value={commentText}
                                                    onChange={(e) => setCommentText(e.target.value)}
                                                />
                                            </div>
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
                                        <div className="td-actions-note">This subtask has reached its final status.</div>
                                    )
                                ) : node.deliverable_status === 'Submitted for Approval' ? (
                                    <div className="td-actions-row">
                                        <div className="td-actions-controls">
                                            <textarea
                                                placeholder="Approval comment (optional)"
                                                value={commentText}
                                                onChange={(e) => setCommentText(e.target.value)}
                                            />
                                        </div>
                                        <button
                                            className="button button-primary"
                                            type="button"
                                            disabled={updating}
                                            onClick={handleApprove}
                                        >
                                            {updating ? 'Approving...' : 'Approve Task'}
                                        </button>
                                    </div>
                                ) : currentStatusIdx >= statusSteps.length - 1 ? (
                                    <div className="td-actions-note">This task has reached its final status.</div>
                                ) : (
                                    <div className="td-actions-note">
                                        Task requires engineer submission; once submitted you can approve it here.
                                    </div>
                                )}
                            </div>
                        )}
                    </section>

                    {pendingStatus && (
                        <div className="modal-backdrop" role="presentation">
                            <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="status-confirm-title">
                                <div className="modal-heading">
                                    <h2 id="status-confirm-title">Confirm Status Change</h2>
                                    <button type="button" aria-label="Close" disabled={updating} onClick={() => { setPendingStatus(null); setConfirmError(''); }}>
                                        <X size={18} />
                                    </button>
                                </div>
                                <div className="confirm-modal-body">
                                    <p className="confirm-modal-text">
                                        Are you sure you want to change the task status to <strong>{pendingStatus}</strong>?
                                    </p>
                                    {confirmError && <div className="resource-error" role="alert">{confirmError}</div>}
                                </div>
                                <div className="modal-actions">
                                    <button className="button button-secondary" type="button" disabled={updating} onClick={() => { setPendingStatus(null); setConfirmError(''); }}>
                                        Cancel
                                    </button>
                                    <button className="button button-primary" type="button" disabled={updating} onClick={confirmStatusChange}>
                                        {updating ? 'Updating...' : 'Confirm'}
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}
                </>
            )}
        </main>
    );
}
