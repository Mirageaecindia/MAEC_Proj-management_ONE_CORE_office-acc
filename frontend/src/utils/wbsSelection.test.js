import { describe, expect, it } from 'vitest';
import { canDelete, describeCount, impliedSelection, summarizeSelection } from './wbsSelection';

const task = (id, engineer) => ({
  id,
  parent_id: null,
  wbs_code: `${id}.`,
  task_name: `Task ${id}`,
  assigned_engineer_id: engineer,
});
const sub = (id, parent, engineer) => ({
  id,
  parent_id: parent,
  wbs_code: `${parent}.${id}`,
  task_name: `Sub ${id}`,
  assigned_engineer_id: engineer,
});

const nodes = [task(1, 7), sub(11, 1, 7), sub(12, 1, 7), task(2, 9), sub(21, 2, 9), task(3, 7)];
const byId = Object.fromEntries(nodes.map((node) => [node.id, node]));

describe('canDelete', () => {
  it('lets a lead delete anything', () => {
    expect(nodes.every((node) => canDelete(node, byId, { isLead: true, employeeId: null }))).toBe(true);
  });

  it('lets an engineer delete only subtasks under their own tasks', () => {
    const me = { isLead: false, employeeId: 7 };
    expect(canDelete(byId[1], byId, me)).toBe(false); // a task, even their own
    expect(canDelete(byId[11], byId, me)).toBe(true);
    expect(canDelete(byId[21], byId, me)).toBe(false); // under someone else's task
    expect(canDelete(sub(99, 404, 7), byId, me)).toBe(false); // parent not loaded
  });
});

describe('selection', () => {
  it('a ticked task implies its subtasks', () => {
    expect([...impliedSelection([1], nodes)]).toEqual([1, 11, 12]);
    expect([...impliedSelection([12], nodes)]).toEqual([12]);
  });

  it('summarises what will be deleted', () => {
    expect(summarizeSelection([1, 21], nodes)).toEqual({
      ids: [1, 11, 12, 21],
      tasks: 1,
      subtasks: 3,
      names: ['1. Task 1', '1.11 Sub 11', '1.12 Sub 12', '2.21 Sub 21'],
    });
    expect(summarizeSelection([], nodes)).toEqual({ ids: [], tasks: 0, subtasks: 0, names: [] });
  });

  it('describes the count in words', () => {
    expect(describeCount({ tasks: 2, subtasks: 5 })).toBe('2 tasks and 5 subtasks');
    expect(describeCount({ tasks: 1, subtasks: 0 })).toBe('1 task');
    expect(describeCount({ tasks: 0, subtasks: 1 })).toBe('1 subtask');
    expect(describeCount({ tasks: 0, subtasks: 0 })).toBe('nothing');
  });
});
