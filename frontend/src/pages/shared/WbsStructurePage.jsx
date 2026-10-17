import { ChevronDown, ChevronRight, Copy, Pencil, Plus, Trash2 } from 'lucide-react';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { wbsBlueprintsApi } from '../../api/wbsBlueprints';
import { apiFetch } from '../../api/client';
import { useAuth } from '../../AuthContext';
import { pickProject, useProjectChoice } from '../../hooks/currentProject';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { InlineEditCell } from '../../components/InlineEditCell';
import { BlueprintDialog } from '../lead/BlueprintDialog';
import { countWorkingDays, plannedHoursForRange } from '../../lib/hours';
import { canDelete, describeCount, impliedSelection, summarizeSelection } from '../../utils/wbsSelection';
import { formatDayIST } from '../../utils/displayTime';


// The five original phases: no longer offered (2026-10-15), shown after the WBS nodes for the work
// already filed under them.
// The node cards are folded away unless the viewer opened them (remembered in this browser only).
const NODES_OPEN_KEY = 'promanage.wbsNodesOpen';

function nodesOpenAtFirst() {
  try {
    return localStorage.getItem(NODES_OPEN_KEY) === 'true';
  } catch {
    return false; // storage blocked: folded
  }
}

function rememberNodesOpen(open) {
  try {
    localStorage.setItem(NODES_OPEN_KEY, String(open));
  } catch {
    /* storage blocked: nothing to remember */
  }
}

// The lead's own node (2026-10-16): no standard tasks, any tasks and subtasks added by hand; after the DD
// nodes. The server knows it too (app/domain/wbs_nodes.py, OTHERS_NODE).
const OTHERS_NODE = 'Others';

const LEGACY_PHASES = ['Space Planning', 'STR Coordination', 'ID - RCP Coordination', 'BoH Area RCP Coordination', 'Submission'];

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
  const { user, role } = useAuth();
  const isBuHead = role === 'bu_head';
  const employeeId = user?.employee_id;
  const isAssignedToMe = (task) => task.assigned_engineer_id === employeeId;

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [searchParams] = useSearchParams();
  const requestedId = searchParams.get('projectId');
  const chooseProject = useProjectChoice(selectedId, setSelectedId);
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
  const [toast, setToast] = useState(null);
  const [selected, setSelected] = useState([]); // ids ticked for deletion
  const [pendingDelete, setPendingDelete] = useState(null); // what the confirm dialog is about
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
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
      const resp = await apiFetch(`/api/projects/${projectId}/wbs-structure${ancestorParam}`);
      if (!resp.ok) throw new Error('Could not load WBS tasks.');
      const data = await resp.json();
      const list = Array.isArray(data) ? data : [];
      setTasks(list);
      setSelected((prev) => prev.filter((id) => list.some((task) => task.id === id)));
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    }
  }, [selectedId, isEngineer]);

  useEffect(() => {
    let active = true;
    setError('');
    apiFetch(`/api/projects`)
      .then(async (projectsResp) => {
        if (!projectsResp.ok) throw new Error('Could not load projects.');
        const projs = await projectsResp.json();
        if (!active) return;
        const projectList = Array.isArray(projs) ? projs : [];
        setProjects(projectList);
      }).catch((err) => {
        if (active) setError(err.message);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    setSelectedId((current) => String(pickProject(projects, requestedId ?? current)?.id ?? ''));
  }, [projects, requestedId]);

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
    apiFetch(`/api/projects/${selectedId}/booked-engineers`)
      .then(async (resp) => {
        if (!resp.ok) return;
        const list = await resp.json();
        if (active) setEngineers(Array.isArray(list) ? list : []);
      })
      .catch(() => {});
    return () => { active = false; };
  }, [selectedId, isLead]);

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

  // A sub-subtask's form: its parent is itself a subtask (adding under a subtask, or editing a step).
  const formParent = tasks.find((task) => task.id === Number(nodeForm.parent_id));
  const formIsStep = nodeMode !== 'node' && formParent?.parent_id != null;

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
      if (formIsStep) {
        hours = null; // a sub-subtask is for reference: no estimate, no hours
      } else if (nodeMode === 'subtask' || (nodeMode === 'edit' && nodeForm.parent_id)) {
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
          ? `/api/wbs-nodes/${nodeForm.parent_id}/subtasks`
          : `/api/projects/${selectedId}/wbs-nodes`;
      const resp = await apiFetch(
        isEdit ? `/api/wbs-nodes/${editNodeId}` : createUrl,
        {
          method: isEdit ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );
      if (!resp.ok) throw new Error((await resp.json()).detail || 'Could not save WBS node.');
      setNodeForm(EMPTY_NODE);
      setShowNodeForm(false);
      setEditNodeId(null);
      await loadTasks();
      setToast({ type: 'success', message: isEdit ? 'WBS node updated successfully.' : formIsStep ? 'Sub-subtask created successfully.' : nodeMode === 'subtask' ? 'Subtask created successfully.' : 'WBS node created successfully.' });
    } catch (err) {
      setError(err.message);
      setToast({ type: 'error', message: err.message });
    }
  }

  function openEditForm(task) {
    setError('');
    setEditStatus(task.deliverable_status || 'To Do');
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

  // The status the item had when the Edit dialog opened: started or finished work keeps its plan.
  const [editStatus, setEditStatus] = useState('To Do');
  const planLocked = nodeMode === 'edit' && editStatus !== 'To Do';

  // Inline editing (decided 2026-10-08): the lead clicks a row's engineer, hours or a date and
  // changes it there; the tick saves, the cross cancels. Same rules as the Edit dialog, checked
  // again by the server.
  const planLock = (task) =>
    task.deliverable_status && task.deliverable_status !== 'To Do'
      ? `${task.deliverable_status}: the engineer, hours and dates stay as they are. Move it back to To Do to change them.`
      : null;
  const engineerOptions = (task) => {
    const list = (Array.isArray(engineers) ? engineers : []).map((e) => ({ value: String(e.id), label: e.name }));
    if (task.assigned_engineer_id != null && !list.some((o) => o.value === String(task.assigned_engineer_id))) {
      list.push({ value: String(task.assigned_engineer_id), label: task.assigned_engineer_name || `#${task.assigned_engineer_id}` });
    }
    return list;
  };

  async function saveInline(task, changes) {
    const payload = {
      wbs_code: task.wbs_code || null,
      task_name: task.task_name,
      parent_id: task.parent_id ?? null,
      assigned_lead: task.assigned_lead ?? null,
      assigned_lead_user_id: task.assigned_lead_user_id ?? null,
      assigned_engineer_id: task.assigned_engineer_id ?? null,
      estimated_hours: task.estimated_hours ?? null,
      deliverable_status: task.deliverable_status || 'To Do',
      start_date: task.start_date || null,
      target_due_date: task.target_due_date || null,
      end_date: task.end_date || null,
      phase: task.phase || null,
      ...changes,
    };
    const resp = await apiFetch(`/api/wbs-nodes/${task.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
      throw new Error(detail || 'Could not save.');
    }
    await loadTasks();
  }

  // A subtask is one day of work: either date sets both. A task or a step keeps its own two dates.
  const dateChanges = (task, which, value) => {
    const day = value || null;
    if (task.depth === 2) return { start_date: day, end_date: day, target_due_date: day };
    return which === 'start' ? { start_date: day } : { end_date: day, target_due_date: day };
  };

  const engineerCell = (task) => (
    <InlineEditCell
      kind="select"
      label={`engineer of ${task.task_name}`}
      value={task.assigned_engineer_id != null ? String(task.assigned_engineer_id) : ''}
      display={task.assigned_engineer_name}
      placeholder="Assign…"
      options={engineerOptions(task)}
      locked={planLock(task)}
      onSave={(value) => saveInline(task, { assigned_engineer_id: value ? Number(value) : null })}
    />
  );
  const hoursCell = (task) =>
    task.depth === 2 ? (
      <InlineEditCell
        kind="number"
        min={1}
        max={8}
        label={`hours of ${task.task_name}`}
        value={task.estimated_hours != null ? String(task.estimated_hours) : ''}
        display={hours(task)}
        placeholder="Set hours"
        locked={planLock(task)}
        onSave={(value) => saveInline(task, { estimated_hours: value === '' ? null : Number(value) })}
      />
    ) : (
      <div className="wbs-readonly" title={task.depth === 1 ? 'From the dates: weekdays × 8 hours' : 'A sub-subtask has no hours'}>
        {hours(task) || '—'}
      </div>
    );
  const dateCell = (task, which) => {
    const value = which === 'start' ? task.start_date : task.target_due_date || task.end_date;
    return (
      <InlineEditCell
        kind="date"
        label={`${which} date of ${task.task_name}`}
        value={value || ''}
        display={value}
        placeholder="Set date"
        locked={planLock(task)}
        onSave={(day) => saveInline(task, dateChanges(task, which, day))}
      />
    );
  };

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

  // WBS node blueprints: "+" on a node card adds that node's standard tasks (what is already
  // there is skipped). The node cards are how a WBS is added: the Excel upload was removed (2026-10-15).
  const { data: blueprints = [] } = useQuery({ queryKey: ['wbs-blueprints'], queryFn: wbsBlueprintsApi.list, staleTime: Infinity });
  const blueprintFor = (phase) => blueprints.find((blueprint) => blueprint.phase === phase);
  // The WBS nodes (the sheets of the CD/SD/DD workbooks), then Others, in order: what a lead adds to.
  const addablePhases = useMemo(() => [...blueprints.map((blueprint) => blueprint.phase), OTHERS_NODE], [blueprints]);
  // The node cards, stage by stage (CD, SD, DD), folded into one bar until the lead opens them.
  const [nodesOpen, setNodesOpen] = useState(nodesOpenAtFirst);
  const toggleNodes = () => {
    setNodesOpen(!nodesOpen);
    rememberNodesOpen(!nodesOpen);
  };
  const stages = useMemo(() => blueprints.reduce((list, blueprint) => {
    const last = list[list.length - 1];
    if (last && last.stage === blueprint.stage) last.nodes.push(blueprint);
    else list.push({ stage: blueprint.stage, nodes: [blueprint] });
    return list;
  }, []), [blueprints]);
  // Sections in the table: the nodes in order, then the original phases, then anything else found.
  const phaseOrder = useMemo(
    () => [...new Set([...addablePhases, ...LEGACY_PHASES, ...tasks.map((task) => task.phase).filter(Boolean)])],
    [addablePhases, tasks],
  );
  const [pendingPhase, setPendingPhase] = useState(null); // the phase whose "+" was clicked
  // Rows a blueprint just added: highlighted, each with the line it repeats, until Keep or Undo.
  const [recent, setRecent] = useState(null); // { phase, ids: Set, sameAs: { id: code } }
  const [undoing, setUndoing] = useState(false);

  async function blueprintAdded(result) {
    setPendingPhase(null);
    setToast({ type: 'success', message: `${result.phase}: ${result.created} added${result.skipped ? `, ${result.skipped} already there` : ''}.` });
    setRecent(result.created ? { phase: result.phase, ids: new Set(result.created_ids), sameAs: result.same_as || {} } : null);
    await loadTasks();
  }

  async function undoRecent() {
    setUndoing(true);
    try {
      const resp = await apiFetch(`/api/projects/${selectedId}/wbs-nodes/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_ids: [...recent.ids] }),
      });
      if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || 'Could not undo.');
      setToast({ type: 'success', message: `The ${recent.ids.size} added items were removed.` });
      setRecent(null);
      await loadTasks();
    } catch (err) {
      setToast({ type: 'error', message: err.message });
    } finally {
      setUndoing(false);
    }
  }

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
      const resp = await apiFetch(`/api/wbs-nodes/${task.id}/duplicate`, { method: 'POST' });
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
      const resp = await apiFetch(`/api/projects/${selectedId}/wbs-nodes/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
    const phase = task.phase || '';
    setNodeForm({ ...EMPTY_NODE, parent_id: task.id, wbs_code: '', phase, assigned_engineer_id: task.assigned_engineer_id ?? null });
    setShowNodeForm(true);
  }

  const children = useMemo(() => tasks.reduce((map, task) => {
    (map[task.parent_id || 0] ||= []).push(task);
    return map;
  }, {}), [tasks]);

  const phaseAggregates = useMemo(() => phaseOrder.map((phase) => {
    const phaseTasks = tasks.filter((task) => task.phase === phase);
    const assignedLead = [...new Set(phaseTasks.map((task) => task.assigned_lead).filter(Boolean))];
    const assignedEngineers = [...new Set(phaseTasks.map((task) => task.assigned_engineer_name).filter(Boolean))];
    const totalHours = phaseTasks.reduce((sum, task) => sum + (Number(task.estimated_hours) || 0), 0);
    const statuses = [...new Set(phaseTasks.map((task) => task.deliverable_status).filter(Boolean))];
    const dueDates = phaseTasks.map((task) => task.target_due_date || task.end_date).filter(Boolean).sort();
    const startDates = phaseTasks.map((task) => task.start_date).filter(Boolean).sort();
    const actualStarts = phaseTasks.map((task) => formatDayIST(task.actual_start_datetime)).filter(Boolean).sort();
    const actualEnds = phaseTasks.map((task) => formatDayIST(task.actual_end_datetime)).filter(Boolean).sort();
    const phaseTaskRoots = phaseTasks.filter((task) => task.parent_id == null);
    const finished = phaseTaskRoots.length > 0 && phaseTaskRoots.every((task) => task.actual_end_datetime);
    return {
      phase,
      count: phaseTasks.length,
      assignedLead: assignedLead.length ? assignedLead.join(' / ') : '',
      assignedEngineers: assignedEngineers.length ? assignedEngineers.join(' / ') : '',
      totalHours,
      status: statuses.length === 1 ? statuses[0] : phaseTasks.length === 0 ? '' : 'Mixed',
      targetStartDate: startDates[0] || '', // the phase starts with its earliest item
      targetDueDate: dueDates.length ? dueDates[dueDates.length - 1] : '',
      actualStartDate: actualStarts[0] || '', // when its first item really started
      actualEndDate: finished ? actualEnds[actualEnds.length - 1] : '', // once every task in it is finished
    };
  }), [tasks, phaseOrder]);

  const visibleSections = useMemo(() => {
    const sections = [];
    phaseOrder.forEach((phase) => {
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
  }, [children, expanded, phaseFilters, phaseAggregates, loaded, phaseOrder]);

  const expandAll = () => {
    setPhaseFilters(Object.fromEntries(phaseOrder.map((phase) => [phase, true])));
    setExpanded(Object.fromEntries(tasks.map((task) => [task.id, true])));
  };

  const collapseAll = () => {
    setPhaseFilters(Object.fromEntries(phaseOrder.map((phase) => [phase, false])));
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
  const canAddChild = (task) => task.depth < 3 && (isLead || task.assigned_engineer_id === employeeId);
  const kind = (task) => ['task', 'subtask', 'sub-subtask'][task.depth - 1] || 'item';
  const rowActions = (task) => (
    <div className="wbs-cell-actions">
      {canAddChild(task) ? (
        <button className="wbs-icon-btn wbs-icon-add" type="button" title={task.depth === 1 ? 'Add a subtask' : 'Add a sub-subtask'} aria-label={`Add a ${task.depth === 1 ? 'subtask' : 'sub-subtask'} to ${task.task_name}`} onClick={(e) => { e.stopPropagation(); openSubtaskForm(task); }}><Plus size={14} /></button>
      ) : slot}
      {duplicable(task) ? (
        <button className="wbs-icon-btn wbs-icon-copy" type="button" title={task.depth === 1 ? 'Duplicate task and its subtasks' : `Duplicate ${kind(task)}`} aria-label={`Duplicate ${task.task_name}`} disabled={duplicating} onClick={(e) => { e.stopPropagation(); duplicateNode(task); }}><Copy size={14} /></button>
      ) : slot}
      {isLead ? (
        <button className="wbs-icon-btn wbs-icon-edit" type="button" title="Edit task" aria-label={`Edit ${task.task_name}`} onClick={(e) => { e.stopPropagation(); openEditForm(task); }}><Pencil size={14} /></button>
      ) : slot}
      {deletable(task) ? (
        <button className="wbs-icon-btn wbs-icon-delete" type="button" title={task.depth === 1 ? 'Delete task and its subtasks' : `Delete ${kind(task)}`} aria-label={`Delete ${task.task_name}`} disabled={deleting} onClick={(e) => { e.stopPropagation(); requestDelete([task.id]); }}><Trash2 size={14} /></button>
      ) : slot}
    </div>
  );

  const hours = (task) => (task.estimated_hours === null || task.estimated_hours === '' ? '' : `${task.estimated_hours} hrs`);

  const rowTask = (task, engineerView = false, buHeadView = false) => {
    const editable = isLead && !engineerView && !buHeadView; // the lead's own table
    return (
    // Everyone opens every row to view it; working on it (status, Login/Logout) stays its owner's.
    <tr key={task.id} className={['wbs-row-clickable', recent?.ids.has(task.id) && 'wbs-row-new'].filter(Boolean).join(' ')} onClick={() => navigate(`/task-details?nodeId=${task.id}&projectId=${selectedId}`)}>
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
          {recent?.ids.has(task.id) && (
            <em className="wbs-new-badge">New{recent.sameAs[task.id] ? ` · same as ${recent.sameAs[task.id]}` : ''}</em>
          )}
        </span>
      </td>
      <td>{editable ? engineerCell(task) : <div className="wbs-readonly">{task.assigned_engineer_name || ''}</div>}</td>
      <td><div className="wbs-readonly">{task.assigned_lead || '—'}</div></td>
      <td>{editable ? hoursCell(task) : <div className="wbs-readonly">{hours(task)}</div>}</td>
      <td><div className="wbs-readonly">{task.deliverable_status || ''}</div></td>
      <td>{editable ? dateCell(task, 'start') : <div className="wbs-readonly">{task.start_date || ''}</div>}</td>
      <td>{editable ? dateCell(task, 'end') : <div className="wbs-readonly">{task.target_due_date || task.end_date || ''}</div>}</td>
      <td><div className="wbs-readonly">{formatDayIST(task.actual_start_datetime)}</div></td>
      <td><div className="wbs-readonly">{formatDayIST(task.actual_end_datetime)}</div></td>
      <td>{buHeadView ? <div className="wbs-readonly">{'—'}</div> : rowActions(task)}</td>
    </tr>
    );
  };

  const phaseDeletableIds = (phase) => deletableIds.filter((id) => byId[id]?.phase === phase);

  const phaseRow = (agg, buHeadView = false) => (
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
      <td><div className="wbs-readonly">{agg.assignedLead}</div></td>
      <td><div className="wbs-readonly">{agg.totalHours ? `${agg.totalHours} hrs` : ''}</div></td>
      <td><div className="wbs-readonly">{agg.status}</div></td>
      <td><div className="wbs-readonly">{agg.targetStartDate}</div></td>
      <td><div className="wbs-readonly">{agg.targetDueDate}</div></td>
      <td><div className="wbs-readonly">{agg.actualStartDate}</div></td>
      <td><div className="wbs-readonly">{agg.actualEndDate}</div></td>
      <td><div className="wbs-readonly">{buHeadView ? '—' : ''}</div></td>
    </tr>
  );

  return (
    <main className="resource-page">
      {pendingPhase && (
        <BlueprintDialog
          projectId={selectedId}
          blueprintKey={blueprintFor(pendingPhase)?.key ?? pendingPhase.toLowerCase().replace(/ /g, '-')}
          phase={pendingPhase}
          onAdded={blueprintAdded}
          onCancel={() => setPendingPhase(null)}
        />
      )}

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
          <p>{isLead ? 'Decompose MEP scope into disciplined phases, assign engineers, and set milestone budget allocations.' : isBuHead ? 'Read-only visibility of WBS nodes and Engineer assignments.' : 'The whole WBS of the project and who has each item: open any to view it; you work on your own.'}</p>
        </div>
        <label className="project-switcher">
          <span>Project Name</span>
          <select value={selectedId} onChange={(e) => chooseProject(e.target.value)}>
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
              <h2>{nodeMode === 'edit' ? 'Edit WBS Node' : formIsStep ? 'Add WBS Sub-subtask' : nodeMode === 'subtask' ? 'Add WBS Subtask' : 'Add WBS Node'}</h2>
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
                {[...new Set([...addablePhases, nodeForm.phase].filter(Boolean))].map((phase) => <option key={phase} value={phase}>{phase}</option>)}
              </select>
            </label>
            <label className="wbs-field-sm">
              <span>Assign Engineer</span>
              <select disabled={planLocked} value={nodeForm.assigned_engineer_id || ''} onChange={(e) => {
                  const id = e.target.value ? Number(e.target.value) : null;
                  setNodeForm({ ...nodeForm, assigned_engineer_id: id });
                }}>
                <option value="">Select engineer</option>
                {assignableEngineers.map((engineer) => <option key={engineer.id} value={engineer.id}>{engineer.name}{engineer.role_title ? ` - ${engineer.role_title}` : ''}</option>)}
              </select>
            </label>
            <label className="wbs-field-sm">
              <span>Start Date</span>
              <input type="date" disabled={planLocked} value={nodeForm.start_date} onChange={(e) => setNodeForm({ ...nodeForm, start_date: e.target.value })} />
            </label>
            <label className="wbs-field-sm">
              <span>End Date</span>
              <input type="date" disabled={planLocked} value={nodeForm.end_date} onChange={(e) => setNodeForm({ ...nodeForm, end_date: e.target.value })} />
            </label>
            {planLocked && (
              <div className="wbs-hours-calc warn" role="note">
                {editStatus}: the engineer, hours and dates stay as they are. Set the status back to To Do and save, then change them.
              </div>
            )}
            {formIsStep ? (
              <div className="wbs-hours-calc">For reference: a step of the subtask, with no Login/Logout and no hours.</div>
            ) : nodeMode === 'subtask' || (nodeMode === 'edit' && nodeForm.parent_id) ? (
              <div className="wbs-subtask-fields">
                <label className="wbs-field-sm">
                  <span>Estimated Hours <em className="req">*</em></span>
                  <input
                    type="number"
                    min="1"
                    max="8"
                    step="1"
                    placeholder="1-8"
                    disabled={planLocked}
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
          {addablePhases.length > 0 && (
          <div className={`wbs-phase-toolbar${nodesOpen ? '' : ' wbs-phase-toolbar-folded'}`}>
            <button
              type="button"
              className="wbs-nodes-toggle"
              aria-expanded={nodesOpen}
              aria-controls="wbs-node-cards"
              title={nodesOpen ? 'Hide the WBS nodes' : 'Show the WBS nodes to add one'}
              onClick={toggleNodes}
            >
              {nodesOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              <span>WBS Nodes ({addablePhases.length})</span>
            </button>
            {nodesOpen && (
            <div className="wbs-phase-stages" id="wbs-node-cards">
              {stages.map(({ stage, nodes }) => (
                <div className="wbs-phase-stage" key={stage}>
                  <span className="wbs-phase-stage-name">{stage}</span>
                  <div className="wbs-phase-cards">
                    {nodes.map(({ phase }) => (
                      <div className="wbs-phase-card" key={phase}>
                        <button type="button" className="wbs-phase-card-node" onClick={() => openNodeForm(phase)}>{phase}</button>
                        <button type="button" className="wbs-phase-card-plus" aria-label={`Add the ${phase} blueprint`} title={`Add the standard ${phase} tasks`} onClick={() => setPendingPhase(phase)}>+</button>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              {/* Others, below DD: a node of the lead's own, to add any tasks to by hand (no standard tasks). */}
              <div className="wbs-phase-stage wbs-phase-stage-others">
                <span className="wbs-phase-stage-name" aria-hidden="true" />
                <div className="wbs-phase-cards">
                  <div className="wbs-phase-card">
                    <button type="button" className="wbs-phase-card-node" onClick={() => openNodeForm(OTHERS_NODE)}>{OTHERS_NODE}</button>
                    <button type="button" className="wbs-phase-card-plus" aria-label={`Add a task to ${OTHERS_NODE}`} title="Add a task of your own" onClick={() => openNodeForm(OTHERS_NODE)}>+</button>
                  </div>
                </div>
              </div>
            </div>
            )}
          </div>
          )}

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
                {addablePhases.length > 0 && (
                  <button className="button button-primary" type="button" onClick={() => openNodeForm()}>+ Add WBS Node</button>
                )}
              </div>
            </div>
            {recent && (
              <div className="wbs-recent-bar" role="status">
                <span>
                  <strong>{recent.ids.size} items added to {recent.phase}</strong>, highlighted below; a repeat says which line it
                  copies.
                </span>
                <button className="button button-primary" type="button" disabled={undoing} onClick={() => setRecent(null)}>Keep</button>
                <button className="button button-secondary" type="button" disabled={undoing} onClick={undoRecent}>{undoing ? 'Undoing…' : 'Undo'}</button>
              </div>
            )}
            <div className="resource-table-wrap">
              <table className="resource-table wbs-table wbs-lead-table">
                <thead>
                  <tr>
                    <th>{selectAllBox('Select all tasks and subtasks')} WBS CODE & TASK NAME</th>
                    <th>ASSIGNED ENGINEER</th>
                    <th>REPORTER</th>
                    <th>ESTIMATED HOURS</th>
                    <th>DELIVERABLE STATUS</th>
                    <th>TARGET START DATE</th>
                    <th>TARGET END DATE</th>
                    <th>ACTUAL START DATE</th>
                    <th>ACTUAL END DATE</th>
                    <th className="wbs-col-actions" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
{visibleSections.map(({ agg, rows }) => (
                      <Fragment key={agg.phase}>
                        {agg.count > 0 && phaseRow(agg)}
                        {rows.map((r) => rowTask(r, false))}
                      </Fragment>
                    ))}
                  {!loaded && <tr><td colSpan={10} className="timesheet-empty-cell">Loading…</td></tr>}
                  {loaded && tasks.length === 0 && (
                    <tr><td colSpan={10}>No WBS tasks yet. Open WBS Nodes above and press + on a node to add its tasks.</td></tr>
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
            <button className="button button-secondary" type="button" onClick={() => { setPhaseFilters(Object.fromEntries(phaseOrder.map((phase) => [phase, true]))); loadTasks().catch((err) => setError(err.message)); }}>Expand All</button>
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
                  <th>ACTUAL START DATE</th>
                  <th>ACTUAL END DATE</th>
                  <th className="wbs-col-actions" aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {visibleSections.map(({ agg, rows }) => (
                  <Fragment key={agg.phase}>
                    {agg.count > 0 && phaseRow(agg, true)}
                    {rows.map((r) => rowTask(r, false, true))}
                  </Fragment>
                ))}
                {!loaded && <tr><td colSpan={10} className="timesheet-empty-cell">Loading…</td></tr>}
                {loaded && tasks.length === 0 && (
                  <tr><td colSpan={10}>No WBS nodes available for this project.</td></tr>
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
                        <th>ACTUAL START DATE</th>
                        <th>ACTUAL END DATE</th>
                        <th className="wbs-col-actions" aria-label="Actions" />
                      </tr>
                    </thead>
                  <tbody>
                    {visibleSections.map(({ agg, rows }) => (
                      <Fragment key={agg.phase}>
                        {agg.count > 0 && phaseRow(agg)}
                        {/* The server sends the whole WBS: colleagues' rows open to view; only the engineer's own take work. */}
                        {rows.map((r) => rowTask(r, true))}
                      </Fragment>
                    ))}
                    {!loaded && <tr><td colSpan={10} className="timesheet-empty-cell">Loading…</td></tr>}
                    {loaded && tasks.length === 0 && (
                      <tr><td colSpan={10}>No WBS tasks in this project yet.</td></tr>
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