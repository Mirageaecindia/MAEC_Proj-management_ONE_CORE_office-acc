import { Fragment, useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { useLogoutTracking, useStartTracking, useTrackingState } from '../../hooks/useTracking';
import { formatDateTimeIST } from '../../utils/displayTime';


const TASK_STATUS_STEPS = ['To Do', 'In-Progress', 'Submitted for Approval', 'Approved'];
const SUBTASK_STATUS_STEPS = ['To Do', 'In-Progress', 'Done'];

function formatDateTime(isoStr) {
    if (!isoStr) return '\u2014';
    return formatDateTimeIST(isoStr, { fallback: '\u2014' });
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
    const { user, role, authHeaders, logout } = useAuth();
    const isStaff = role === 'engineer'; // everyone but the BU Head
    const isBuHead = role === 'bu_head';

    const nodeId = Number(searchParams.get('nodeId')) || null;
    const projectId = Number(searchParams.get('projectId')) || null;

    const [node, setNode] = useState(null);
    const [project, setProject] = useState(null);
    // Leading is a role on this project. Working on the node (status, Login/Logout, comments)
    // belongs to whoever it is assigned to: an engineer, or a lead doing their own subtask.
    const isLead = project?.my_role === 'lead';
    const isEngineer = Boolean(user?.employee_id) && node?.assigned_engineer_id === user?.employee_id;
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [commentText, setCommentText] = useState('');
    const [statusSelect, setStatusSelect] = useState('');
    const [updating, setUpdating] = useState(false);
    const [toast, setToast] = useState(null);
    const [pendingStatus, setPendingStatus] = useState(null);
    const [confirmError, setConfirmError] = useState('');

    // Subtask Login/Logout (Engineer). The heartbeat runs app-wide (App.jsx);
    // the Engineer sees only which subtask they are logged in to, never hours.
    const tracking = useTrackingState({ enabled: isStaff });
    const startTracking = useStartTracking();
    const logoutTracking = useLogoutTracking();
    const activeSession = tracking.data?.active_session ?? null;
    const overMark = Boolean(tracking.data?.over_mark);
    const systemLogout = tracking.data?.system_logout ?? null;
    const loggedInHere = activeSession?.subtask_id === nodeId;
    const loggedInElsewhere = Boolean(activeSession) && !loggedInHere;
    const trackingBusy = startTracking.isPending || logoutTracking.isPending;

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
            if (resp.status === 401) { await logout(); return; }
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
            if (resp.status === 401) { await logout(); return; }
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
            if (resp.status === 401) { await logout(); return; }
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
            if (resp.status === 401) { await logout(); return; }
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

    function toggleTracking() {
        const onError = (err) => showToast('error', err.message);
        if (loggedInHere) {
            logoutTracking.mutate(undefined, {
                onSuccess: ({ over_mark }) => showToast('success', over_mark
                    ? 'Logged out. Your working time is saved; today is over 8 hours, so your lead reviews the day.'
                    : 'Logged out. Your working time is saved.'),
                onError,
            });
        } else {
            startTracking.mutate(nodeId, {
                onSuccess: () => showToast('success', 'Logged in. Your time on this subtask counts until you log out.'),
                onError,
            });
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

            {isStaff && activeSession && overMark && (
                <div className="tracking-notice" role="status">
                    <strong>Over 8 hours today.</strong> Every hour still counts, but keep visiting this app at least
                    every 30 minutes (a click or a key press here is enough). If you don&apos;t, you are logged out at
                    your last visit.
                </div>
            )}
            {isStaff && !activeSession && systemLogout && (
                <div className="tracking-notice is-logout" role="status">
                    <strong>You were logged out at {new Date(systemLogout.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</strong>,
                    your last visit, after 30 minutes away past the 8-hour mark. Today&apos;s time so far is{' '}
                    {systemLogout.day_hours} h and it is saved. Log in again if you are still working.
                </div>
            )}

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
                                        className={`td-login-btn${loggedInHere ? ' logged-in' : ''}`}
                                        disabled={trackingBusy || loggedInElsewhere}
                                        title={loggedInHere
                                            ? 'Logout: stop working on this subtask'
                                            : loggedInElsewhere
                                                ? 'You are logged in to another subtask. Log out there first.'
                                                : 'Login: start working on this subtask'}
                                        onClick={toggleTracking}
                                    >
                                        {loggedInHere ? 'Logout' : 'Login'}
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

                        {/* Your Actions: the lead's; the BU Head approves a task its lead worked on themselves */}
                        {node && (isLead || (isBuHead && node.node_type === 'task' && node.deliverable_status === 'Submitted for Approval')) && (
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
                                        {isBuHead && (
                                            <div className="td-actions-note">
                                                You approve a task when its lead did part of the work themselves; otherwise its lead approves it.
                                            </div>
                                        )}
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
