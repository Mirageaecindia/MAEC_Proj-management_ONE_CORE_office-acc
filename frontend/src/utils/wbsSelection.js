/**
 * Selecting WBS tasks and subtasks for deletion (decided 2026-09-29).
 *
 * A project lead may delete any task or subtask; an engineer only subtasks
 * they created themselves. Deleting a task takes its subtasks with it (and a subtask
 * its sub-subtasks), so a ticked item implies everything under it.
 */

/** Whether this viewer may delete the node. */
export function canDelete(node, { isLead, userId }) {
  if (isLead) return true;
  return node.parent_id != null && userId != null && node.created_by_user_id === userId;
}

/** Ids the user ticked plus everything under them (a task's subtasks, a subtask's sub-subtasks). */
export function impliedSelection(selectedIds, nodes) {
  const implied = new Set(selectedIds);
  let grew = true;
  while (grew) {
    grew = false;
    for (const node of nodes) {
      if (node.parent_id != null && implied.has(node.parent_id) && !implied.has(node.id)) {
        implied.add(node.id);
        grew = true;
      }
    }
  }
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
