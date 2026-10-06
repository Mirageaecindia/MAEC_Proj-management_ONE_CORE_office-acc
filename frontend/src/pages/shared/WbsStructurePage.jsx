import { Copy, Pencil, Plus, Trash2 } from 'lucide-react';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { countWorkingDays, plannedHoursForRange } from '../../lib/hours';
import { canDelete, describeCount, impliedSelection, summarizeSelection } from '../../utils/wbsSelection';


const PHASES = ['Space Planning', 'STR Coordination', 'ID Coordination', 'BoH Area RCP Coordination', 'Submission'];

const EMPTY_NODE = {
  wbs_code: '',
  task_name: '',
  parent_id: null,
  assigned_engineer_id: null,
  estimated_hours: null,
  deliverable_status: 'To Do',
  start_date: '',
  target_due_date: '',
  end_date: '',
  subtask: '',
  phase: '',
};

/** A checkbox that can show a partial selection; clicks never open the row underneath. */
function SelectBox({ checked, indeterminate = false, disabled = false, label, onChange }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate && !checked;
  }, [indeterminate, checked]);
  return (
    <input
      ref={ref}
      type="checkbox"
      className="wbs-check"
      aria-label={label}
      checked={checked}
      disabled={disabled}
      onChange={(e) => onChange(e.target.checked)}
      onClick={(e) => e.stopPropagation()}
    />
  );
}

export function WbsStructurePage() {
  const navigate = useNavigate();
  const { user, role, authHeaders } = useAuth();
  const isBuHead = role === 'bu_head';
  const employeeId = user?.employee_id;
  const isAssignedToMe = (task) => task.assigned_engineer_id === employeeId;

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [tasks, setTasks] = useState([]);
  const [engineers, setEngineers] = useState([]);
  const [error, setError] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const loaded = lastUpdated !== null; // the tree is drawn once, complete, not phase rows first
  const [expanded, setExpanded] = useState({});
  const [phaseFilters, setPhaseFilters] = useState({});
  const [nodeForm, setNodeForm] = useState(EMPTY_NODE);
  const [nodeMode, setNodeMode] = useState('node');
  const [editNodeId, setEditNodeId] = useState(null);
  const [showNodeForm, setShowNodeForm] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [toast, setToast] = useState(null);
  const [selected, setSelected] = useState([]); // ids ticked for deletion
  const [pendingDelete, setPendingDelete] = useState(null); // what the confirm dialog is about
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const fileInputRef = useRef(null);
  // Lead and engineer are roles on the selected project, not on the account.
  const project = projects.find((p) => String(p.id) === String(selectedId));
  const isLead = project?.my_role === 'lead';
  const isEngineer = project?.my_role === 'engineer';

  const loadTasks = useCallback(async (projectId = selectedId) => {
    if (!projectId) {
      setTasks([]);
      return;
    }
    setError('');
    const ancestorParam = isEngineer ? '?include_ancestors=true' : '';
    try {
      const resp = await fetch(`${API_BASE_URL}/api/projects/${projectId}/wbs-structure${ancestorParam}`, { headers: authHeaders() });
      if (!resp.ok) throw new Error('Could not load WBS tasks.');
      const data = await resp.json();
      const list = Array.isArray(data) ? data : [];
      setTasks(list);
      setSelected((prev) => prev.filter((id) => list.some((task) => task.id === id)));
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    }
  }, [selectedId, authHeaders, isEngineer]);

  useEffect(() => {
    let active = true;
    setError('');
    fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() })
      .then(async (projectsResp) => {
        if (!projectsResp.ok) throw new Error('Could not load projects.');
        const projs = await projectsResp.json();
        if (!active) return;
        const projectList = Array.isArray(projs) ? projs : [];
        setProjects(projectList);
        setSelectedId((current) => {
          if (projectList.some((project) => String(project.id) === String(current))) return current;
          return projectList[0] ? String(projectList[0].id) : '';
        });
      }).catch((err) => {
        if (active) setError(err.message);
      });
    return () => { active = false; };
  }, [authHeaders]);

  useEffect(() => {
    let active = true;
    setSelected([]);
    if (!selectedId) {
      setEngineers([]);
      return undefined;
    }
    setEngineers([]);
    if (!isLead) return undefined; // only a lead assigns engineers; the list is theirs to read
    // The Assign Engineer dropdown lists only engineers booked onto THIS
    // project via Resource Booking, refreshed whenever the project changes.
    fetch(`${API_BASE_URL}/api/projects/${selectedId}/booked-engineers`, { headers: authHeaders() })
      .then(async (resp) => {
        if (!resp.ok) return;
        const list = await resp.json();
        if (active) setEngineers(Array.isArray(list) ? list : []);
      })
      .catch(() => {});
    return () => { active = false; };
  }, [selectedId, authHeaders, isLead]);

  useEffect(() => {
    if (!selectedId) {
      setTasks([]);
      return undefined;
    }
    let active = true;
    loadTasks().catch((err) => {
      if (active) setError(err.message);
    });
    // Refresh when the user comes back to the tab (other people's changes), not on a timer:
    // a large WBS is hundreds of rows, and every action on this page reloads it anyway.
    const onFocus = () => {
      if (active && document.visibilityState === 'visible') loadTasks().catch(() => {});
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    return () => {
      active = false;
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  }, [selectedId, loadTasks]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  // Assignable engineers = booked onto this project. If the node being edited
  // is already assigned to someone whose booking was later removed, keep that
  // person in the list so the existing assignment is not silently dropped.
  const assignableEngineers = useMemo(() => {
    const list = (Array.isArray(engineers) ? engineers : []).slice();
    if (nodeForm.assigned_engineer_id !== null && nodeForm.assigned_engineer_id !== '') {
      const targetId = Number(nodeForm.assigned_engineer_id);
      if (!list.some((e) => Number(e.id) === targetId)) {
        const current = tasks.find((t) => Number(t.assigned_engineer_id) === targetId);
        list.push({
          id: targetId,
          name: current?.assigned_engineer_name || `#${targetId}`,
          role_title: '',
        });
      }
    }
    return list;
  }, [engineers, nodeForm.assigned_engineer_id, tasks]);

  // Estimated Hours preview: inclusive weekdays (Mon–Fri) between Start and
  // End × 8 hrs per working day. Weekends are not working days — same rule the
  // backend enforces, so the shown value always matches what gets saved.
  const estimatedPreview = useMemo(() => {
    if (!nodeForm.start_date || !nodeForm.end_date) return null;
    const start = new Date(`${nodeForm.start_date}T00:00:00`);
    const end = new Date(`${nodeForm.end_date}T00:00:00`);
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    if (end < start) return { error: true };
    const days = countWorkingDays(nodeForm.start_date, nodeForm.end_date);
    return { days, hours: plannedHoursForRange(nodeForm.start_date, nodeForm.end_date) };
  }, [nodeForm.start_date, nodeForm.end_date]);

  async function addNode(event) {
    event.preventDefault();
    setError('');
    const isEdit = nodeMode === 'edit' && editNodeId;
    try {
      if (!nodeForm.task_name.trim()) {
        setError('Task Name is required.');
        return;
      }
      let hours = null;
      if (nodeMode === 'subtask' || (nodeMode === 'edit' && nodeForm.parent_id)) {
        const rawHours = String(nodeForm.estimated_hours === null || nodeForm.estimated_hours === '' ? '' : nodeForm.estimated_hours).trim();
        if (rawHours === '') {
          setError('Subtask planned hours must be between 1 and 8 hours.');
          return;
        }
        hours = Number(rawHours);
        if (!Number.isInteger(hours) || hours < 1 || hours > 8) {
          setError('Subtask planned hours must be between 1 and 8 hours.');
          return;
        }
        if (nodeForm.start_date || nodeForm.end_date) {
          if (!nodeForm.start_date || !nodeForm.end_date || nodeForm.start_date !== nodeForm.end_date) {
            setError('A subtask must be completed within a single working day — Start Date and End Date must be identical.');
            return;
          }
        }
      } else {
        if (estimatedPreview && estimatedPreview.error) {
          setError('End Date must be on or after Start Date.');
          return;
        }
        hours = estimatedPreview
          ? estimatedPreview.hours
          : nodeForm.estimated_hours === '' || nodeForm.estimated_hours === null
            ? null
            : Number(nodeForm.estimated_hours);
        if (hours !== null && Number.isNaN(hours)) {
          setError('Estimated Hours must be a number.');
          return;
        }
      }
      const payload = {
        wbs_code: nodeForm.wbs_code ? String(nodeForm.wbs_code).trim() : null,
        task_name: nodeForm.task_name.trim(),
        parent_id: nodeForm.parent_id ? Number(nodeForm.parent_id) : null,
        assigned_lead: user.full_name || null,
        assigned_lead_user_id: user.id ?? null,
        assigned_engineer_id: nodeForm.assigned_engineer_id ?? null,
        estimated_hours: hours,
        deliverable_status: nodeForm.deliverable_status || 'To Do',
        start_date: nodeForm.start_date || null,
        target_due_date: nodeForm.target_due_date || null,
        end_date: nodeForm.end_date || null,
        subtask: isEdit ? null : (nodeForm.subtask ? String(nodeForm.subtask).trim() : null),
        phase: nodeForm.phase || null,
      };
      const createUrl =
        nodeMode === 'subtask' && nodeForm.parent_id
          ? `${API_BASE_URL}/api/wbs-nodes/${nodeForm.parent_id}/subtasks`
          : `${API_BASE_URL}/api/projects/${selectedId}/wbs-nodes`;
      const resp = await fetch(
        isEdit ? `${API_BASE_URL}/api/wbs-nodes/${editNodeId}` : createUrl,
        {
          method: isEdit ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify(payload),
        },
      );
      if (!resp.ok) throw new Error((await resp.json()).detail || 'Could not save WBS node.');
      setNodeForm(EMPTY_NODE);
      setShowNodeForm(false);
      setEditNodeId(null);
      await loadTasks();
      setToast({ type: 'success', message: isEdit ? 'WBS node updated successfully.' : nodeMode === 'subtask' ? 'Subtask created successfully.' : 'WBS node created successfully.' });
    } catch (err) {
      setError(err.message);
      setToast({ type: 'error', message: err.message });
    }
  }

  function openEditForm(task) {
    setError('');
    setNodeMode('edit');
    setEditNodeId(task.id);
    setNodeForm({
      ...EMPTY_NODE,
      wbs_code: task.wbs_code || '',
      task_name: task.task_name || '',
      parent_id: task.parent_id ?? null,
      assigned_engineer_id: task.assigned_engineer_id ?? null,
      estimated_hours: task.estimated_hours === null || task.estimated_hours === '' ? null : task.estimated_hours,
      deliverable_status: task.deliverable_status || 'To Do',
      start_date: task.start_date || '',
      target_due_date: task.target_due_date || '',
      end_date: task.end_date || '',
      phase: task.phase || '',
    });
    setShowNodeForm(true);
  }

  // Deleting: a lead deletes tasks and subtasks, an engineer only subtasks under their own
  // tasks; one confirmation for any number of them. Worked hours are kept by the server.
  const byId = useMemo(() => Object.fromEntries(tasks.map((task) => [task.id, task])), [tasks]);
  const userId = user?.id;
  const deletable = (task) => canDelete(task, { isLead, userId });
  const deletableIds = useMemo(
    () => tasks.filter((task) => canDelete(task, { isLead, userId })).map((task) => task.id),
    [tasks, isLead, userId],
  );
  const implied = useMemo(() => impliedSelection(selected, tasks), [selected, tasks]);
  const selection = useMemo(() => summarizeSelection(selected, tasks), [selected, tasks]);

  const setSelectedMany = (ids, on) =>
    setSelected((prev) => (on ? [...new Set([...prev, ...ids])] : prev.filter((id) => !ids.includes(id))));
  const selectAllBox = (label) => (
    <SelectBox
      label={label}
      checked={deletableIds.length > 0 && deletableIds.every((id) => implied.has(id))}
      indeterminate={deletableIds.some((id) => implied.has(id))}
      disabled={deletableIds.length === 0}
      onChange={(on) => setSelectedMany(deletableIds, on)}
    />
  );

  // Duplicating: a copy next to the original with the next free WBS code, To Do, no hours
  // (a task's copy brings copies of its subtasks). Leads duplicate anything; an engineer
  // only their own subtasks under a task assigned to them. The server decides the code.
  const [duplicating, setDuplicating] = useState(false);
  const duplicable = (task) =>
    isLead ||
    (task.parent_id != null && employeeId != null &&
      task.assigned_engineer_id === employeeId && byId[task.parent_id]?.assigned_engineer_id === employeeId);

  async function duplicateNode(task) {
    setDuplicating(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${task.id}/duplicate`, { method: 'POST', headers: authHeaders() });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.detail || 'Could not duplicate.');
      setToast({ type: 'success', message: `Duplicated ${task.wbs_code || task.task_name} as ${body.wbs_code || 'a new item'}.` });
      await loadTasks();
    } catch (err) {
      setToast({ type: 'error', message: err.message });
    } finally {
      setDuplicating(false);
    }
  }

  function requestDelete(ids) {
    setDeleteError(null);
    setPendingDelete(summarizeSelection(ids, tasks));
  }

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      const resp = await fetch(`${API_BASE_URL}/api/projects/${selectedId}/wbs-nodes/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ node_ids: pendingDelete.ids }),
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(body.detail || 'Could not delete.');
      setPendingDelete(null);
      setSelected([]);
      await loadTasks();
      const kept = body.hours_kept > 0 ? ` ${body.hours_kept} h of worked time kept.` : '';
      setToast({ type: 'success', message: `Deleted ${describeCount(body)}.${kept}` });
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setDeleting(false);
    }
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (file && selectedId) {
      setShowUpload(true);
      setError('');
      try {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch(`${API_BASE_URL}/api/projects/${selectedId}/wbs-upload`, {
          method: 'POST',
          headers: authHeaders(),
          body: form,
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || 'Could not upload WBS file.');
        const result = await resp.json();
        setToast({ type: 'success', message: `Uploaded: ${result.created} created, ${result.updated} updated.` });
        await loadTasks();
      } catch (err) {
        setError(err.message);
        setToast({ type: 'error', message: `Upload failed: ${err.message}` });
      } finally {
        setShowUpload(false);
        event.target.value = '';
      }
    }
  }

  /** The Add WBS Node dialog, with the phase already chosen when it is opened from a phase card. */
  function openNodeForm(phase = '') {
    setError('');
    setNodeMode('node');
    setEditNodeId(null);
    setNodeForm({ ...EMPTY_NODE, phase });
    setShowNodeForm(true);
  }

  function openSubtaskForm(task) {
    setError('');
    setNodeMode('subtask');
    setEditNodeId(null);
    const phase = task.phase || PHASES[0];
    setNodeForm({ ...EMPTY_NODE, parent_id: task.id, wbs_code: '', phase, assigned_engineer_id: task.assigned_engineer_id ?? null });
    setShowNodeForm(true);
  }

  const children = useMemo(() => tasks.reduce((map, task) => {
    (map[task.parent_id || 0] ||= []).push(task);
    return map;
  }, {}), [tasks]);

  const phaseAggregates = useMemo(() => PHASES.map((phase) => {
    const phaseTasks = tasks.filter((task) => task.phase === phase);
    const assignedLead = [...new Set(phaseTasks.map((task) => task.assigned_lead).filter(Boolean))];
    const assignedEngineers = [...new Set(phaseTasks.map((task) => task.assigned_engineer_name).filter(Boolean))];
    const totalHours = phaseTasks.reduce((sum, task) => sum + (Number(task.estimated_hours) || 0), 0);
    const statuses = [...new Set(phaseTasks.map((task) => task.deliverable_status).filter(Boolean))];
    const dueDates = phaseTasks.map((task) => task.target_due_date || task.end_date).filter(Boolean).sort();
    const startDates = phaseTasks.map((task) => task.start_date).filter(Boolean).sort();
    return {
      phase,
      count: phaseTasks.length,
      assignedLead: assignedLead.length ? assignedLead.join(' / ') : '',
      assignedEngineers: assignedEngineers.length ? assignedEngineers.join(' / ') : '',
      totalHours,
      status: statuses.length === 1 ? statuses[0] : phaseTasks.length === 0 ? '' : 'Mixed',
      targetStartDate: startDates[0] || '', // the phase starts with its earliest item
      targetDueDate: dueDates.length ? dueDates[dueDates.length - 1] : '',
    };
  }), [tasks]);

  const visibleSections = useMemo(() => {
    const sections = [];
    PHASES.forEach((phase) => {
      const agg = phaseAggregates.find((item) => item.phase === phase);
      const rows = [];
      const walk = (nodes, depth) => {
        nodes.forEach((node) => {
          rows.push({ ...node, depth });
          if (expanded[node.id] !== false) walk(children[node.id] || [], depth + 1);
        });
      };
      if (phaseFilters[phase] !== false) walk((children[0] || []).filter((node) => node.phase === phase), 1);
      sections.push({ agg, rows });
    });
    return loaded ? sections : [];
  }, [children, expanded, phaseFilters, phaseAggregates, loaded]);

  const expandAll = () => {
    setPhaseFilters(Object.fromEntries(PHASES.map((phase) => [phase, true])));
    setExpanded(Object.fromEntries(tasks.map((task) => [task.id, true])));
  };

  const collapseAll = () => {
    setPhaseFilters(Object.fromEntries(PHASES.map((phase) => [phase, false])));
    setExpanded(Object.fromEntries(tasks.map((task) => [task.id, false])));
  };

  const setPhaseCollapsed = (phase, value) => {
    const ids = tasks.filter((task) => task.phase === phase).map((task) => task.id);
    setExpanded((prev) => {
      const next = { ...prev };
      ids.forEach((id) => { next[id] = value; });
      return next;
    });
    setPhaseFilters((prev) => ({ ...prev, [phase]: value }));
  };

  const togglePhase = (phase) => setPhaseCollapsed(phase, phaseFilters[phase] === false);

  // The row's buttons, always in four fixed places (add, duplicate, edit, delete): a button
  // this viewer doesn't get leaves its place empty, so the others never move.
  const slot = <span className="wbs-icon-slot" aria-hidden="true" />;
  const canAddChild = (task) => task.depth === 1 && (isLead || task.assigned_engineer_id === employeeId);
  const rowActions = (task) => (
    <div className="wbs-cell-actions">
      {canAddChild(task) ? (
        <button className="wbs-icon-btn wbs-icon-add" type="button" title="Add a subtask" aria-label={`Add a subtask to ${task.task_name}`} onClick={(e) => { e.stopPropagation(); openSubtaskForm(task); }}><Plus size={14} /></button>
      ) : slot}
      {duplicable(task) ? (
        <button className="wbs-icon-btn wbs-icon-copy" type="button" title={task.depth === 1 ? 'Duplicate task and its subtasks' : 'Duplicate subtask'} aria-label={`Duplicate ${task.task_name}`} disabled={duplicating} onClick={(e) => { e.stopPropagation(); duplicateNode(task); }}><Copy size={14} /></button>
      ) : slot}
      {isLead ? (
        <button className="wbs-icon-btn wbs-icon-edit" type="button" title="Edit task" aria-label={`Edit ${task.task_name}`} onClick={(e) => { e.stopPropagation(); openEditForm(task); }}><Pencil size={14} /></button>
      ) : slot}
      {deletable(task) ? (
        <button className="wbs-icon-btn wbs-icon-delete" type="button" title={task.depth === 1 ? 'Delete task and its subtasks' : 'Delete subtask'} aria-label={`Delete ${task.task_name}`} disabled={deleting} onClick={(e) => { e.stopPropagation(); requestDelete([task.id]); }}><Trash2 size={14} /></button>
      ) : slot}
    </div>
  );

  const hours = (task) => (task.estimated_hours === null || task.estimated_hours === '' ? '' : `${task.estimated_hours} hrs`);

  const rowTask = (task, engineerView = false, buHeadView = false) => {
    // An engineer opens only what is theirs; a colleague's subtask is shown for who has it and its status.
    const opens = !engineerView || task.assigned_engineer_id === employeeId;
    return (
    <tr key={task.id} className={opens ? 'wbs-row-clickable' : undefined} onClick={opens ? () => navigate(`/task-details?nodeId=${task.id}&projectId=${selectedId}`) : undefined}>
      <td>
        <span style={{ paddingLeft: `${(task.depth - 1) * 24}px` }}>
          {!buHeadView && deletable(task) && (
            <SelectBox
              label={`Select ${task.task_name}`}
              checked={implied.has(task.id)}
              disabled={task.parent_id != null && implied.has(task.parent_id)}
              onChange={(on) => setSelectedMany([task.id], on)}
            />
          )}
          {children[task.id]?.length ? (
            <button className="wbs-expand" type="button" onClick={(e) => { e.stopPropagation(); setExpanded((prev) => ({ ...prev, [task.id]: prev[task.id] === false })); }}>
              {expanded[task.id] === false ? '▶' : '▼'}
            </button>
          ) : (
            <span className="wbs-connector" aria-hidden="true">{'└─'}</span>
          )}
          <strong>{task.wbs_code}</strong> {task.task_name}
        </span>
      </td>
      <td><div className="wbs-readonly">{task.assigned_engineer_name || ''}</div></td>
      {(engineerView || buHeadView) && <td><div className="wbs-readonly">{task.assigned_lead || '—'}</div></td>}
      <td><div className="wbs-readonly">{hours(task)}</div></td>
      <td><div className="wbs-readonly">{task.deliverable_status || ''}</div></td>
      <td><div className="wbs-readonly">{task.start_date || ''}</div></td>
      <td><div className="wbs-readonly">{task.target_due_date || task.end_date || ''}</div></td>
      <td>{buHeadView ? <div className="wbs-readonly">{'—'}</div> : rowActions(task)}</td>
    </tr>
    );
  };

  const phaseDeletableIds = (phase) => deletableIds.filter((id) => byId[id]?.phase === phase);

  const phaseRow = (agg, engineerView = false, buHeadView = false) => (
    <tr className="wbs-phase-row" key={agg.phase}>
      <td>
        {!buHeadView && phaseDeletableIds(agg.phase).length > 0 && (
          <SelectBox
            label={`Select all in ${agg.phase}`}
            checked={phaseDeletableIds(agg.phase).every((id) => implied.has(id))}
            indeterminate={phaseDeletableIds(agg.phase).some((id) => implied.has(id))}
            onChange={(on) => setSelectedMany(phaseDeletableIds(agg.phase), on)}
          />
        )}
        <button className="wbs-expand" type="button" aria-label={`${phaseFilters[agg.phase] === false ? 'Expand' : 'Collapse'} ${agg.phase}`} onClick={() => togglePhase(agg.phase)}>
          {phaseFilters[agg.phase] === false ? '\u25b6' : '\u25bc'}
        </button>
        <strong className="wbs-phase-name">{agg.phase}</strong>
      </td>
      <td><div className="wbs-readonly">{agg.assignedEngineers}</div></td>
      {(engineerView || buHeadView) && <td><div className="wbs-readonly">{agg.assignedLead}</div></td>}
      <td><div className="wbs-readonly">{agg.totalHours ? `${agg.totalHours} hrs` : ''}</div></td>
      <td><div className="wbs-readonly">{agg.status}</div></td>
      <td><div className="wbs-readonly">{agg.targetStartDate}</div></td>
      <td><div className="wbs-readonly">{agg.targetDueDate}</div></td>
      <td><div className="wbs-readonly">{buHeadView ? '—' : ''}</div></td>
    </tr>
  );

  return (
    <main className="resource-page">
      {pendingDelete && (
        <ConfirmDialog
          title={`Delete ${describeCount(pendingDelete)}?`}
          confirmLabel="Delete"
          busyLabel="Deleting…"
          busy={deleting}
          error={deleteError}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        >
          <ul className="confirm-modal-list">
            {pendingDelete.names.slice(0, 8).map((name, index) => <li key={index}>{name}</li>)}
            {pendingDelete.names.length > 8 && <li>… and {pendingDelete.names.length - 8} more</li>}
          </ul>
          <p className="confirm-modal-text">This cannot be undone.</p>
          <p className="confirm-modal-subtext">
            {pendingDelete.tasks > 0 && 'Deleting a task also deletes its subtasks. '}
            Hours already worked on these subtasks are <strong>kept</strong> and still count toward working time.
            Anyone logged in to one of them is logged out now and their time is saved.
          </p>
        </ConfirmDialog>
      )}
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Project Controls</span><i>/</i><strong>WBS Structure</strong>
          </div>
          <h1>WBS Structure</h1>
          <p>{isLead ? 'Decompose MEP scope into disciplined phases, assign engineers, and set milestone budget allocations.' : isBuHead ? 'Read-only visibility of WBS nodes and Engineer assignments.' : 'Your tasks, each with all its subtasks and who has them.'}</p>
        </div>
        <label className="project-switcher">
          <span>Project Name</span>
          <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
            <option value="">Select project</option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.project_name}</option>)}
          </select>
        </label>
      </div>

      {toast && <div className={`upload-toast ${toast.type}`} role="status" onClick={() => setToast(null)}>{toast.message}</div>}

      {showNodeForm && (
        <div className="modal-backdrop" role="presentation">
          <form className="wbs-node-form wbs-node-modal" onSubmit={addNode}>
            <div className="modal-heading">
              <h2>{nodeMode === 'edit' ? 'Edit WBS Node' : nodeMode === 'subtask' ? 'Add WBS Subtask' : 'Add WBS Node'}</h2>
              <button className="modal-close" type="button" aria-label="Close" onClick={() => { setShowNodeForm(false); setNodeForm(EMPTY_NODE); setEditNodeId(null); setError(''); }}>X</button>
            </div>
            {error && <div className="modal-error" role="alert">{error}</div>}
            <label className="wbs-field-sm">
              <span>WBS Code</span>
              <input placeholder="e.g. 100." value={nodeForm.wbs_code} onChange={(e) => setNodeForm({ ...nodeForm, wbs_code: e.target.value })} />
            </label>
            <label className="wbs-field-sm">
              <span>Task Name <em className="req">*</em></span>
              <input placeholder="Enter task name" value={nodeForm.task_name} onChange={(e) => setNodeForm({ ...nodeForm, task_name: e.target.value })} required />
            </label>
            <label className="wbs-field-sm">
              <span>Phase <em className="req">*</em></span>
              <select value={nodeForm.phase || ''} onChange={(e) => setNodeForm({ ...nodeForm, phase: e.target.value })}>
                <option value="">Select Phase</option>
                {PHASES.map((phase) => <option key={phase} value={phase}>{phase}</option>)}
              </select>
            </label>
            <label className="wbs-field-sm">
              <span>Assign Engineer</span>
              <select value={nodeForm.assigned_engineer_id || ''} onChange={(e) => {
                  const id = e.target.value ? Number(e.target.value) : null;
                  setNodeForm({ ...nodeForm, assigned_engineer_id: id });
                }}>
                <option value="">Select engineer</option>
                {assignableEngineers.map((engineer) => <option key={engineer.id} value={engineer.id}>{engineer.name}{engineer.role_title ? ` - ${engineer.role_title}` : ''}</option>)}
              </select>
            </label>
            <label className="wbs-field-sm">
              <span>Start Date</span>
              <input type="date" value={nodeForm.start_date} onChange={(e) => setNodeForm({ ...nodeForm, start_date: e.target.value })} />
            </label>
            <label className="wbs-field-sm">
              <span>End Date</span>
              <input type="date" value={nodeForm.end_date} onChange={(e) => setNodeForm({ ...nodeForm, end_date: e.target.value })} />
            </label>
            {nodeMode === 'subtask' || (nodeMode === 'edit' && nodeForm.parent_id) ? (
              <div className="wbs-subtask-fields">
                <label className="wbs-field-sm">
                  <span>Estimated Hours <em className="req">*</em></span>
                  <input
                    type="number"
                    min="1"
                    max="8"
                    step="1"
                    placeholder="1-8"
                    value={nodeForm.estimated_hours === null || nodeForm.estimated_hours === '' ? '' : nodeForm.estimated_hours}
                    onChange={(e) => setNodeForm({ ...nodeForm, estimated_hours: e.target.value })}
                  />
                </label>
                {nodeForm.start_date && nodeForm.end_date && nodeForm.start_date !== nodeForm.end_date && (
                  <div className="wbs-hours-calc warn" role="alert">A subtask must be completed within a single working day — Start Date and End Date must be identical.</div>
                )}
                {nodeForm.estimated_hours !== null && nodeForm.estimated_hours !== '' && (
                  <div className="wbs-hours-calc">
                    Estimated Hours: <strong>{nodeForm.estimated_hours} hrs</strong>
                  </div>
                )}
              </div>
            ) : estimatedPreview && estimatedPreview.error ? (
              <div className="wbs-hours-calc warn" role="alert">End Date must be on or after Start Date.</div>
            ) : estimatedPreview ? (
              <div className="wbs-hours-calc">
                Estimated Hours: <strong>{estimatedPreview.hours} hrs</strong>
                <em>({estimatedPreview.days} working {estimatedPreview.days === 1 ? 'day' : 'days'} &times; 8 hrs)</em>
              </div>
            ) : nodeForm.estimated_hours !== null && nodeForm.estimated_hours !== '' ? (
              <div className="wbs-hours-calc">
                Estimated Hours: <strong>{nodeForm.estimated_hours} hrs</strong>
                <em>(entered previously — add dates to recalculate)</em>
              </div>
            ) : null}
            {nodeMode === 'node' && (
              <label className="wbs-field">
                <span>Subtask</span>
                <input placeholder="Subtask name or description (saved as a child node)" value={nodeForm.subtask} onChange={(e) => setNodeForm({ ...nodeForm, subtask: e.target.value })} />
              </label>
            )}
            {nodeMode === 'edit' && (
              <label className="wbs-field">
                <span>Deliverable Status</span>
                <select value={nodeForm.deliverable_status || 'To Do'} onChange={(e) => setNodeForm({ ...nodeForm, deliverable_status: e.target.value })}>
                  {['To Do', 'In-Progress', 'Submitted for Approval', 'Approved', 'Done'].map((status) => <option key={status} value={status}>{status}</option>)}
                </select>
              </label>
            )}
            <div className="modal-actions">
              <button className="button button-secondary" type="button" onClick={() => { setShowNodeForm(false); setNodeForm(EMPTY_NODE); setEditNodeId(null); setError(''); }}>Cancel</button>
              <button className="button button-primary" type="submit" disabled={!nodeForm.task_name.trim()}>{nodeMode === 'edit' ? 'Save Changes' : 'Save Node'}</button>
            </div>
          </form>
        </div>
      )}

      {isLead ? (
        <>
          <div className="wbs-phase-toolbar">
            <div className="wbs-phase-cards">
              {PHASES.map((phase) => (
                <div className="wbs-phase-card" key={phase}>
                  <button type="button" className="wbs-phase-card-node" onClick={() => openNodeForm(phase)}>{phase}</button>
                  <button type="button" className="wbs-phase-card-plus" aria-label={`Add a task to ${phase}`} title={`Add a task to ${phase}`} onClick={() => openNodeForm(phase)}>+</button>
                </div>
              ))}
            </div>
            <div className="wbs-upload-tools">
              <button className="button button-secondary" type="button" onClick={() => fileInputRef.current?.click()} disabled={showUpload}>{showUpload ? 'Uploading...' : 'Upload WBS (Excel)'}</button>
              <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls" hidden onChange={handleUpload} />
              <a href="/wbs-upload-template.xlsx" download title="Column A: the phase. Column B: tasks in bold, subtasks in normal text.">Download the Excel template</a>
            </div>
          </div>

          <section className="allocation-card">
            <div className="allocation-header">
              <div>
                <h2>Project Scope Breakdown (3 Level Hierarchy)</h2>
                <p>{lastUpdated ? `Last refreshed ${lastUpdated.toLocaleTimeString()}` : 'Loading hierarchy...'}</p>
              </div>
              <div className="wbs-actions">
                <button className="button button-secondary" type="button" onClick={expandAll}>Expand All</button>
                <button className="button button-secondary" type="button" onClick={collapseAll}>Collapse All</button>
                {selection.ids.length > 0 && (
                  <>
                    <button className="button button-danger" type="button" disabled={deleting} onClick={() => requestDelete(selected)}>Delete {describeCount(selection)}</button>
                    <button className="button button-secondary" type="button" onClick={() => setSelected([])}>Clear selection</button>
                  </>
                )}
                <button className="button button-primary" type="button" onClick={() => openNodeForm()}>+ Add WBS Node</button>
              </div>
            </div>
            <div className="resource-table-wrap">
              <table className="resource-table wbs-table wbs-lead-table">
                <thead>
                  <tr>
                    <th>{selectAllBox('Select all tasks and subtasks')} WBS CODE & TASK NAME</th>
                    <th>ASSIGNED ENGINEER</th>
                    <th>ESTIMATED HOURS</th>
                    <th>DELIVERABLE STATUS</th>
                    <th>TARGET START DATE</th>
                    <th>TARGET END DATE</th>
                    <th className="wbs-col-actions" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
{visibleSections.map(({ agg, rows }) => (
                      <Fragment key={agg.phase}>
                        {phaseRow(agg, false)}
                        {rows.map((r) => rowTask(r, false))}
                      </Fragment>
                    ))}
                  {!loaded && <tr><td colSpan={7} className="timesheet-empty-cell">Loading…</td></tr>}
                  {loaded && tasks.length === 0 && (
                    <tr><td colSpan={7}>No WBS nodes uploaded or created for this project.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : isBuHead ? (
        <section className="allocation-card">
          <div className="allocation-header">
            <div>
              <h2>Project Scope Breakdown</h2>
              <p>Lead updates and Engineer assignments are visible here.</p>
            </div>
            <button className="button button-secondary" type="button" onClick={() => { setPhaseFilters(Object.fromEntries(PHASES.map((phase) => [phase, true]))); loadTasks().catch((err) => setError(err.message)); }}>Expand All</button>
            <button className="button button-secondary" type="button" onClick={collapseAll}>Collapse All</button>
            <button className="button button-secondary" type="button" onClick={() => loadTasks().catch((err) => setError(err.message))}>Refresh</button>
          </div>
          <div className="resource-table-wrap">
            <table className="resource-table wbs-table">
              <thead>
                <tr>
                  <th>WBS CODE &amp; TASK NAME</th>
                  <th>ASSIGNED ENGINEER</th>
                  <th>REPORTER</th>
                  <th>ESTIMATED HOURS</th>
                  <th>DELIVERABLE STATUS</th>
                  <th>TARGET START DATE</th>
                  <th>TARGET END DATE</th>
                  <th className="wbs-col-actions" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {visibleSections.map(({ agg, rows }) => (
                  <Fragment key={agg.phase}>
                    {phaseRow(agg, false, true)}
                    {rows.map((r) => rowTask(r, false, true))}
                  </Fragment>
                ))}
                {!loaded && <tr><td colSpan={8} className="timesheet-empty-cell">Loading…</td></tr>}
                {loaded && tasks.length === 0 && (
                  <tr><td colSpan={8}>No WBS nodes available for this project.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
          <>
            <section className="allocation-card">
              <div className="allocation-header">
                <div>
                  <h2>Project Scope Breakdown (3 Level Hierarchy)</h2>
                  <p>{lastUpdated ? `Last refreshed ${lastUpdated.toLocaleTimeString()}` : 'Loading hierarchy...'}</p>
                </div>
                <div className="wbs-actions">
                  <button className="button button-secondary" type="button" onClick={expandAll}>Expand All</button>
                  <button className="button button-secondary" type="button" onClick={collapseAll}>Collapse All</button>
                {selection.ids.length > 0 && (
                    <>
                      <button className="button button-danger" type="button" disabled={deleting} onClick={() => requestDelete(selected)}>Delete {describeCount(selection)}</button>
                      <button className="button button-secondary" type="button" onClick={() => setSelected([])}>Clear selection</button>
                    </>
                  )}
                  <button className="button button-secondary" type="button" onClick={() => loadTasks().catch((err) => setError(err.message))}>Refresh</button>
                </div>
              </div>
              <div className="resource-table-wrap">
                <table className="resource-table wbs-table">
<thead>
                      <tr>
                        <th>{selectAllBox('Select all my subtasks')} WBS CODE & TASK NAME</th>
                        <th>ASSIGNED ENGINEER</th>
                        <th>REPORTER</th>
                        <th>ESTIMATED HOURS</th>
                        <th>DELIVERABLE STATUS</th>
                        <th>TARGET START DATE</th>
                        <th>TARGET END DATE</th>
                        <th className="wbs-col-actions" aria-label="Actions" />
                      </tr>
                    </thead>
                  <tbody>
                    {visibleSections.map(({ agg, rows }) => (
                      <Fragment key={agg.phase}>
                        {agg.count > 0 && phaseRow(agg, true)}
                        {/* The server sends each of the engineer's tasks whole: colleagues' subtasks too. */}
                        {rows.map((r) => rowTask(r, true))}
                      </Fragment>
                    ))}
                    {!loaded && <tr><td colSpan={8} className="timesheet-empty-cell">Loading…</td></tr>}
                    {loaded && tasks.length === 0 && (
                      <tr><td colSpan={8}>No WBS nodes assigned to you in this project.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="allocation-footer">
                <div className="footer-info">
                  Assigned Hours Total: <strong>{tasks.filter((t) => isAssignedToMe(t)).reduce((sum, t) => sum + (Number(t.estimated_hours) || 0), 0)}</strong>
                </div>
                <div className="footer-info">
                  Baseline Hours Total: <strong>{tasks.filter((t) => isAssignedToMe(t)).reduce((sum, t) => sum + (Number(t.baseline_hours) || 0), 0)}</strong>
                </div>
                <button className="button button-next" type="button" onClick={() => navigate('/timeline-logs')}>NEXT</button>
              </div>
            </section>
          </>
        )}
    </main>
  );
}