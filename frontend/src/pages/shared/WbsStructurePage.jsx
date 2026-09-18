import { Eye, X, ChevronRight, ChevronDown, ChevronLeft } from 'lucide-react';
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../AuthContext';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const STATUSES = ['Not Started', 'In Progress', 'Completed', 'Blocked'];
const PHASES = ['Space Planning', 'STR Coordination', 'ID Coordination', 'BoH Area RCP Coordination', 'Submission'];

const EMPTY_NODE = {
  wbs_code: '',
  task_name: '',
  parent_id: null,
  assigned_lead: '',
  estimated_hours: null,
  deliverable_status: 'Not Started',
  start_date: '',
  target_due_date: '',
  end_date: '',
  subtask: '',
  phase: '',
};

export function WbsStructurePage() {
  const navigate = useNavigate();
  const { user, role, authHeaders } = useAuth();
  const isLead = role === 'lead';
  const isBuHead = role === 'bu_head';
  const isEngineer = role === 'engineer';
  const employeeId = user?.employee_id;
  const engineerFullName = user?.full_name || '';
  const isAssignedToMe = (task) => task.assigned_engineer_id === employeeId || task.assigned_lead === engineerFullName;

  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [tasks, setTasks] = useState([]);
  const [leads, setLeads] = useState([]);
  const [error, setError] = useState('');
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [loadingTasks, setLoadingTasks] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [phaseFilters, setPhaseFilters] = useState({});
  const [nodeForm, setNodeForm] = useState(EMPTY_NODE);
  const [nodeMode, setNodeMode] = useState('node');
  const [showNodeForm, setShowNodeForm] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [toast, setToast] = useState(null);
  const [uploadPhase, setUploadPhase] = useState('');
  const [viewTask, setViewTask] = useState(null);
  const fileInputRef = useRef(null);

  const loadTasks = useCallback(async (projectId = selectedId) => {
    if (!projectId) {
      setTasks([]);
      setLoadingTasks(false);
      return;
    }
    setLoadingTasks(true);
    setError('');
    const ancestorParam = isEngineer ? '?include_ancestors=true' : '';
    try {
      const resp = await fetch(`${API_BASE_URL}/api/projects/${projectId}/wbs-structure${ancestorParam}`, { headers: authHeaders() });
      if (!resp.ok) throw new Error('Could not load WBS tasks.');
      const data = await resp.json();
      setTasks(Array.isArray(data) ? data : []);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingTasks(false);
    }
  }, [selectedId, authHeaders, isEngineer]);

  useEffect(() => {
    let active = true;
    setLoadingProjects(true);
    setError('');
    Promise.all([
      fetch(`${API_BASE_URL}/api/projects`, { headers: authHeaders() }),
      isLead ? fetch(`${API_BASE_URL}/api/project-leads`, { headers: authHeaders() }) : Promise.resolve(null),
    ]).then(async ([projectsResp, leadsResp]) => {
      if (!projectsResp.ok) throw new Error('Could not load projects.');
      const [projs, leadList] = await Promise.all([
        projectsResp.json(),
        leadsResp ? (leadsResp.ok ? leadsResp.json() : []) : [],
      ]);
      if (!active) return;
      const projectList = Array.isArray(projs) ? projs : [];
      setProjects(projectList);
      setLeads(Array.isArray(leadList) ? leadList : []);
      setSelectedId((current) => {
        if (projectList.some((project) => String(project.id) === String(current))) return current;
        return projectList[0] ? String(projectList[0].id) : '';
      });
    }).catch((err) => {
      if (active) setError(err.message);
    }).finally(() => {
      if (active) setLoadingProjects(false);
    });
    return () => { active = false; };
  }, [isBuHead, isEngineer, isLead, authHeaders]);

  useEffect(() => {
    if (!selectedId) {
      setTasks([]);
      setLoadingTasks(false);
      return undefined;
    }
    let active = true;
    loadTasks().catch((err) => {
      if (active) setError(err.message);
    });
    const timer = setInterval(() => {
      if (active) loadTasks().catch(() => {});
    }, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selectedId, loadTasks]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  async function saveTask(task) {
    setSavingId(task.id);
    setError('');
    try {
      const resp = await fetch(`${API_BASE_URL}/api/wbs-nodes/${task.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          wbs_code: task.wbs_code ? String(task.wbs_code).trim() : null,
          task_name: task.task_name,
          parent_id: task.parent_id,
          assigned_lead: task.assigned_lead || null,
          assigned_engineer_id: task.assigned_engineer_id || null,
          estimated_hours: task.estimated_hours === '' || task.estimated_hours === null ? null : Number(task.estimated_hours || 0),
          deliverable_status: task.deliverable_status,
          start_date: task.start_date || null,
          target_due_date: task.target_due_date || null,
          end_date: task.end_date || null,
          phase: task.phase || null,
        }),
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || 'Could not save WBS task.');
      await loadTasks();
      setToast({ type: 'success', message: 'Task saved successfully.' });
    } catch (err) {
      setError(err.message);
      setToast({ type: 'error', message: err.message });
    } finally {
      setSavingId(null);
    }
  }

  function updateTask(id, field, value) {
    setTasks((rows) => rows.map((row) => row.id === id ? { ...row, [field]: value } : row));
  }

  async function addNode(event) {
    event.preventDefault();
    setError('');
    try {
      if (!nodeForm.task_name.trim()) {
        setError('Task Name is required.');
        return;
      }
      const hours = nodeForm.estimated_hours === '' || nodeForm.estimated_hours === null ? null : Number(nodeForm.estimated_hours);
      if (hours !== null && Number.isNaN(hours)) {
        setError('Estimated Hours must be a number.');
        return;
      }
      const resp = await fetch(`${API_BASE_URL}/api/projects/${selectedId}/wbs-nodes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          wbs_code: nodeForm.wbs_code ? String(nodeForm.wbs_code).trim() : null,
          task_name: nodeForm.task_name.trim(),
          parent_id: nodeForm.parent_id ? Number(nodeForm.parent_id) : null,
          assigned_lead: nodeForm.assigned_lead ? String(nodeForm.assigned_lead).trim() : null,
          estimated_hours: hours,
          deliverable_status: nodeForm.deliverable_status || 'Not Started',
          start_date: nodeForm.start_date || null,
          target_due_date: nodeForm.target_due_date || null,
          end_date: nodeForm.end_date || null,
          subtask: nodeForm.subtask ? String(nodeForm.subtask).trim() : null,
          phase: nodeForm.phase || null,
        }),
      });
      if (!resp.ok) throw new Error((await resp.json()).detail || 'Could not add WBS node.');
      setNodeForm(EMPTY_NODE);
      setShowNodeForm(false);
      await loadTasks();
      setToast({ type: 'success', message: nodeMode === 'subtask' ? 'Subtask created successfully.' : 'WBS node created successfully.' });
    } catch (err) {
      setError(err.message);
      setToast({ type: 'error', message: err.message });
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
        if (uploadPhase) form.append('phase', uploadPhase);
        const resp = await fetch(`${API_BASE_URL}/api/projects/${selectedId}/wbs-upload`, {
          method: 'POST',
          headers: authHeaders(),
          body: form,
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || 'Could not upload WBS file.');
        const result = await resp.json();
        const suffix = uploadPhase ? ` to ${uploadPhase}` : '';
        setToast({ type: 'success', message: `Uploaded${suffix}: ${result.created} created, ${result.updated} updated.` });
        await loadTasks();
      } catch (err) {
        setError(err.message);
        setToast({ type: 'error', message: `Upload failed: ${err.message}` });
      } finally {
        setShowUpload(false);
        setUploadPhase('');
        event.target.value = '';
      }
    }
  }

  function triggerPhaseUpload(phase) {
    setUploadPhase(phase);
    if (fileInputRef.current) fileInputRef.current.click();
  }

  function openNodeForm(phase) {
    setError('');
    setNodeMode('node');
    setNodeForm({ ...EMPTY_NODE, phase });
    setShowNodeForm(true);
  }

  function openSubtaskForm(task) {
    setError('');
    setNodeMode('subtask');
    const phase = task.phase || PHASES[0];
    setNodeForm({ ...EMPTY_NODE, parent_id: task.id, wbs_code: `${task.wbs_code}.`, phase, assigned_lead: task.assigned_lead || '' });
    setShowNodeForm(true);
  }

  function downloadTemplate(event) {
    event.preventDefault();
    const url = URL.createObjectURL(new Blob([`WBS Code,Task Name,Parent WBS Code,Assigned Lead,Estimated Hours,Deliverable Status,Target Due Date,Phase\n`], { type: 'text/csv' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'wbs-upload-template.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  const children = useMemo(() => tasks.reduce((map, task) => {
    (map[task.parent_id || 0] ||= []).push(task);
    return map;
  }, {}), [tasks]);

  const phaseAggregates = useMemo(() => PHASES.map((phase) => {
    const phaseTasks = tasks.filter((task) => task.phase === phase);
    const assignedLead = [...new Set(phaseTasks.map((task) => task.assigned_lead).filter(Boolean))];
    const totalHours = phaseTasks.reduce((sum, task) => sum + (Number(task.estimated_hours) || 0), 0);
    const statuses = [...new Set(phaseTasks.map((task) => task.deliverable_status).filter(Boolean))];
    const dueDates = phaseTasks.map((task) => task.target_due_date || task.end_date).filter(Boolean).sort();
    return {
      phase,
      count: phaseTasks.length,
      assignedLead: assignedLead.length ? assignedLead.join(' / ') : '',
      totalHours,
      status: statuses.length === 1 ? statuses[0] : phaseTasks.length === 0 ? '' : 'Mixed',
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
    return sections;
  }, [children, expanded, phaseFilters, phaseAggregates]);

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

  const rowTask = (task, engineerView = false) => (
    <tr key={task.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/task-details?nodeId=${task.id}&projectId=${selectedId}`)}>
      <td>
        <button className="wbs-expand" type="button" onClick={(e) => { e.stopPropagation(); setExpanded((prev) => ({ ...prev, [task.id]: prev[task.id] === false })); }}>
          {children[task.id]?.length ? (expanded[task.id] === false ? '+' : '-') : '\u00b7'}
        </button>
        <span style={{ paddingLeft: `${(task.depth - 1) * 24}px` }}>
          <strong>{task.wbs_code}</strong> {task.task_name}
        </span>
        {engineerView && (
          <button className="wbs-eye" type="button" aria-label={`View ${task.task_name}`} onClick={(e) => { e.stopPropagation(); setViewTask(task); }}>
            <Eye size={14} />
          </button>
        )}
      </td>
{engineerView ? (
          <>
            <td><div className="wbs-readonly">{task.assigned_lead || '\u2014'}</div></td>
            <td><div className="wbs-readonly">{task.estimated_hours === null || task.estimated_hours === '' ? '\u2014' : task.estimated_hours}</div></td>
            <td><div className="wbs-readonly">{task.deliverable_status || '\u2014'}</div></td>
            <td><div className="wbs-readonly">{task.target_due_date || task.end_date || '\u2014'}</div></td>
            <td>
              <button className="wbs-eye" type="button" aria-label={`View ${task.task_name}`} onClick={(e) => { e.stopPropagation(); setViewTask(task); }}>
                <Eye size={14} />
              </button>
            </td>
          </>
        ) : (
        <>
          <td><div className="wbs-readonly">{task.assigned_lead || ''}</div></td>
          <td><div className="wbs-readonly">{task.estimated_hours === null || task.estimated_hours === '' ? '' : task.estimated_hours}</div></td>
          <td><div className="wbs-readonly">{task.deliverable_status || ''}</div></td>
          <td><div className="wbs-readonly">{task.target_due_date || task.end_date || ''}</div></td>
          <td>
            {task.depth === 1 && (
              <button className="button button-secondary" type="button" onClick={(e) => { e.stopPropagation(); openSubtaskForm(task); }}>+ Subtask</button>
            )}
            <button className="button button-primary" type="button" disabled={savingId === task.id} onClick={(e) => { e.stopPropagation(); saveTask(task); }}>{savingId === task.id ? 'Saving...' : 'Save'}</button>
          </td>
        </>
      )}
    </tr>
  );

  const phaseRow = (agg, engineerView = false) => (
    <tr className="wbs-phase-row" key={agg.phase}>
      <td>
        <button className="wbs-expand" type="button" aria-label={`${phaseFilters[agg.phase] === false ? 'Expand' : 'Collapse'} ${agg.phase}`} onClick={() => togglePhase(agg.phase)}>
          {phaseFilters[agg.phase] === false ? '+' : '-'}
        </button>
        <strong className="wbs-phase-name">{agg.phase}</strong>
      </td>
{engineerView ? (
          <>
            <td><div className="wbs-readonly">{agg.assignedLead}</div></td>
            <td><div className="wbs-readonly">{agg.totalHours}</div></td>
            <td><div className="wbs-readonly">{agg.status}</div></td>
            <td><div className="wbs-readonly">{agg.targetDueDate}</div></td>
            <td><div className="wbs-readonly"></div></td>
          </>
        ) : (
        <>
          <td><div className="wbs-readonly">{agg.assignedLead}</div></td>
          <td><div className="wbs-readonly">{agg.totalHours}</div></td>
          <td><div className="wbs-readonly">{agg.status}</div></td>
          <td><div className="wbs-readonly">{agg.targetDueDate}</div></td>
          <td><div className="wbs-readonly"></div></td>
        </>
      )}
    </tr>
  );

  return (
    <main className="resource-page">
      <div className="resource-heading-row">
        <div>
          <div className="breadcrumb">
            <span>Project Controls</span><i>/</i><strong>WBS Structure</strong>
          </div>
          <h1>WBS Structure</h1>
          <p>{isLead ? 'Decompose MEP scope into disciplined phases, assign lead engineers, and set milestone budget allocations.' : isBuHead ? 'Read-only visibility of WBS nodes and Engineer assignments.' : 'Only WBS nodes assigned to you are shown.'}</p>
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
              <h2>{nodeMode === 'subtask' ? 'Add WBS Subtask' : 'Add WBS Node'}</h2>
              <button className="modal-close" type="button" aria-label="Close" onClick={() => { setShowNodeForm(false); setNodeForm(EMPTY_NODE); setError(''); }}>X</button>
            </div>
            {error && <div className="modal-error" role="alert">{error}</div>}
            <input placeholder="WBS Code" value={nodeForm.wbs_code} onChange={(e) => setNodeForm({ ...nodeForm, wbs_code: e.target.value })} />
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
            <select value={nodeForm.assigned_lead || ''} onChange={(e) => setNodeForm({ ...nodeForm, assigned_lead: e.target.value })}>
              <option value="">Assign Lead</option>
              {leads.map((lead) => <option key={lead.id} value={lead.name}>{lead.name}{lead.title ? ` - ${lead.title}` : ''}</option>)}
            </select>
            <input type="number" min="0" placeholder="Estimated Hours" value={nodeForm.estimated_hours} onChange={(e) => setNodeForm({ ...nodeForm, estimated_hours: e.target.value })} />
            <input type="date" aria-label="Start Date" value={nodeForm.start_date} onChange={(e) => setNodeForm({ ...nodeForm, start_date: e.target.value })} />
            <input type="date" aria-label="End Date" value={nodeForm.end_date} onChange={(e) => setNodeForm({ ...nodeForm, end_date: e.target.value })} />
            <label className="wbs-field">
              <span>Subtask</span>
              <input placeholder="Subtask name or description (saved as a child node)" value={nodeForm.subtask} onChange={(e) => setNodeForm({ ...nodeForm, subtask: e.target.value })} />
            </label>
            <div className="modal-actions">
              <button className="button button-secondary" type="button" onClick={() => { setShowNodeForm(false); setNodeForm(EMPTY_NODE); setError(''); }}>Cancel</button>
              <button className="button button-primary" type="submit" disabled={!nodeForm.task_name.trim()}>Save Node</button>
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
                  <button type="button" className="wbs-phase-card-plus" aria-label={`Upload to ${phase}`} title={`Upload to ${phase}`} onClick={() => triggerPhaseUpload(phase)}>+</button>
                </div>
              ))}
            </div>
            <div className="wbs-upload-tools">
              <button className="button button-secondary" type="button" onClick={() => { setUploadPhase(''); fileInputRef.current?.click(); }} disabled={showUpload}>{showUpload ? 'Uploading...' : 'Upload CSV'}</button>
              <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls" hidden onChange={handleUpload} />
              <a href="/wbs-upload-template.csv" onClick={downloadTemplate}>Click Here to Download Template</a>
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
                <button className="button button-primary" type="button" onClick={() => { setNodeMode('node'); setNodeForm(EMPTY_NODE); setShowNodeForm(true); }}>+ Add WBS Node</button>
              </div>
            </div>
            <div className="resource-table-wrap">
              <table className="resource-table wbs-table">
                <thead>
                  <tr>
                    <th>WBS CODE & TASK NAME</th>
                    <th>ASSIGNED LEAD</th>
                    <th>ESTIMATED HOURS</th>
                    <th>DELIVERABLE STATUS</th>
                    <th>TARGET DUE DATE</th>
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
{visibleSections.map(({ agg, rows }) => (
                      <Fragment key={agg.phase}>
                        {phaseRow(agg, false)}
                        {rows.map((r) => rowTask(r, false))}
                      </Fragment>
                    ))}
                  {tasks.length === 0 && (
                    <tr><td colSpan={6}>No WBS nodes uploaded or created for this project.</td></tr>
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
            <table className="resource-table">
              <thead>
                <tr>
                  <th>WBS CODE</th>
                  <th>TASK NAME</th>
                  <th>ASSIGNED ENGINEER</th>
                  <th>STATUS</th>
                  <th>ESTIMATED HOURS</th>
                  <th>TARGET DUE DATE</th>
                  <th>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {visibleSections.map(({ agg, rows }) => (
                  <Fragment key={agg.phase}>
                    <tr className="wbs-phase-row">
                      <td colSpan={2}>
                        <button className="wbs-expand" type="button" onClick={() => togglePhase(agg.phase)}>{phaseFilters[agg.phase] === false ? '+' : '-'}</button>
                        <strong className="wbs-phase-name">{agg.phase}</strong>
                      </td>
                      <td><div className="wbs-readonly">{agg.assignedLead}</div></td>
                      <td><div className="wbs-readonly">{agg.status}</div></td>
                      <td><div className="wbs-readonly">{agg.totalHours}</div></td>
                      <td><div className="wbs-readonly">{agg.targetDueDate}</div></td>
                      <td><div className="wbs-readonly">{'\u2014'}</div></td>
                    </tr>
                    {rows.map((task) => (
                      <tr key={task.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/task-details?nodeId=${task.id}&projectId=${selectedId}`)}>
                        <td>{task.wbs_code}</td>
                        <td style={{ paddingLeft: `${(task.depth - 1) * 24}px` }}>{task.task_name}</td>
                        <td>{task.assigned_engineer_name || 'Unassigned'}</td>
                        <td>{task.deliverable_status}</td>
                        <td>{task.estimated_hours}</td>
                        <td>{task.target_due_date || '\u2014'}</td>
                        <td>{task.assigned_engineer_id ? task.assigned_engineer_name || 'Assigned' : '\u2014'}</td>
                      </tr>
                    ))}
                  </Fragment>
                ))}
                {tasks.length === 0 && (
                  <tr><td colSpan={7}>No WBS nodes available for this project.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
          <>
            {toast && <div className={`upload-toast ${toast.type}`} role="status" onClick={() => setToast(null)}>{toast.message}</div>}

            {viewTask && (
              <div className="modal-backdrop" role="presentation" onClick={() => setViewTask(null)}>
                <div className="booking-modal wbs-view-modal" onClick={(e) => e.stopPropagation()}>
                  <div className="modal-heading">
                    <h2>{viewTask.wbs_code} — {viewTask.task_name}</h2>
                    <button className="modal-close" type="button" aria-label="Close" onClick={() => setViewTask(null)}>X</button>
                  </div>
                  <div className="wbs-view-fields">
                    <div className="wbs-view-row"><span>Phase</span><strong>{viewTask.phase || '\u2014'}</strong></div>
                    <div className="wbs-view-row"><span>Assigned Lead</span><strong>{viewTask.assigned_lead || '\u2014'}</strong></div>
                    <div className="wbs-view-row"><span>Status</span><strong>{viewTask.deliverable_status || '\u2014'}</strong></div>
                    <div className="wbs-view-row"><span>Assigned Hours</span><strong>{viewTask.estimated_hours !== null && viewTask.estimated_hours !== undefined ? viewTask.estimated_hours : '\u2014'}</strong></div>
                    <div className="wbs-view-row"><span>Target Due</span><strong>{viewTask.target_due_date || viewTask.end_date || '\u2014'}</strong></div>
                    <div className="wbs-view-row"><span>Start Date</span><strong>{viewTask.start_date || '\u2014'}</strong></div>
                    <div className="wbs-view-row"><span>End Date</span><strong>{viewTask.end_date || '\u2014'}</strong></div>
                  </div>
                </div>
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
                  <button className="button button-secondary" type="button" onClick={() => loadTasks().catch((err) => setError(err.message))}>Refresh</button>
                </div>
              </div>
              <div className="resource-table-wrap">
                <table className="resource-table wbs-table">
<thead>
                      <tr>
                        <th>WBS CODE & TASK NAME</th>
                        <th>ASSIGNED LEAD</th>
                        <th>EST. HOURS</th>
                        <th>DELIVERABLE STATUS</th>
                        <th>TARGET DUE DATE</th>
                        <th>ACTIONS</th>
                      </tr>
                    </thead>
                  <tbody>
                    {visibleSections.map(({ agg, rows }) => (
                      <Fragment key={agg.phase}>
                        {agg.count > 0 && phaseRow(agg, true)}
                        {rows
                          .filter((r) => isAssignedToMe(r))
                          .map((r) => rowTask(r, true))}
                      </Fragment>
                    ))}
                    {tasks.length === 0 && (
                      <tr><td colSpan={6}>No WBS nodes loaded for this project.</td></tr>
                    )}
                    {tasks.length > 0 && visibleSections.every(({ rows }) => rows.filter((r) => isAssignedToMe(r)).length === 0) && (
                      <tr><td colSpan={6}>No WBS nodes assigned to you in this project.</td></tr>
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