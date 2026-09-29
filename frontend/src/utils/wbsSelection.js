/**
 * Selecting WBS tasks and subtasks for deletion (decided 2026-09-29).
 *
 * A project lead may delete any task or subtask; an engineer only subtasks
 * under tasks assigned to them. Deleting a task takes its subtasks with it, so
 * a ticked task implies its subtasks and they cannot be unticked on their own.
 */

/** Whether this viewer may delete the node. `byId` maps node id → node. */
export function canDelete(node, byId, { isLead, employeeId }) {
  if (isLead) return true;
  if (node.parent_id == null) return false;
  const parent = byId[node.parent_id];
  return Boolean(parent && employeeId && parent.assigned_engineer_id === employeeId);
}

/** Ids the user ticked plus the subtasks of every ticked task. */
export function impliedSelection(selectedIds, nodes) {
  const implied = new Set(selectedIds);
  for (const node of nodes) if (node.parent_id != null && implied.has(node.parent_id)) implied.add(node.id);
  return implied;
}

/** What a selection deletes, for the button, the dialog and the toast. */
export function summarizeSelection(selectedIds, nodes) {
  const implied = impliedSelection(selectedIds, nodes);
  const picked = nodes.filter((node) => implied.has(node.id));
  const tasks = picked.filter((node) => node.parent_id == null);
  const subtasks = picked.filter((node) => node.parent_id != null);
  return {
    ids: picked.map((node) => node.id),
    tasks: tasks.length,
    subtasks: subtasks.length,
    names: picked.map(label),
  };
}

/** "2 tasks and 5 subtasks", "1 subtask", … */
export function describeCount({ tasks, subtasks }) {
  const parts = [];
  if (tasks) parts.push(`${tasks} ${tasks === 1 ? 'task' : 'tasks'}`);
  if (subtasks) parts.push(`${subtasks} ${subtasks === 1 ? 'subtask' : 'subtasks'}`);
  return parts.join(' and ') || 'nothing';
}

function label(node) {
  return [node.wbs_code, node.task_name].filter(Boolean).join(' ');
}
