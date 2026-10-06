"""WBS node statuses: the only values stored in wbs_nodes.deliverable_status.

Tasks:    To Do -> In-Progress -> Submitted for Approval -> Approved
Subtasks: To Do -> In-Progress -> Done

Older code and the Excel upload used other names ("Not Started",
"In Progress", "Completed", ...). `normalize_status` maps them on every write
(see models.WbsNode) and migration 0002 converted existing rows.
"""

from collections.abc import Callable, Iterable

TO_DO = "To Do"
IN_PROGRESS = "In-Progress"
SUBMITTED = "Submitted for Approval"
APPROVED = "Approved"
DONE = "Done"

TASK_STATUSES = (TO_DO, IN_PROGRESS, SUBMITTED, APPROVED)
SUBTASK_STATUSES = (TO_DO, IN_PROGRESS, DONE)
FINISHED = frozenset({APPROVED, DONE})  # a task is finished when Approved, a subtask when Done

LEGACY_COMPLETED = "Completed"
_LEGACY_NAMES = {
    "Not Started": TO_DO,
    "Blocked": TO_DO,
    "In Progress": IN_PROGRESS,
    "Submitted for Review": SUBMITTED,
}


def normalize_status(status: str | None, *, is_subtask: bool) -> str:
    """Canonical status for any current or legacy name; empty means To Do."""
    if not status:
        return TO_DO
    if status == LEGACY_COMPLETED:
        return DONE if is_subtask else APPROVED
    return _LEGACY_NAMES.get(status, status)


def is_finished(status: str | None) -> bool:
    return normalize_status(status, is_subtask=False) in FINISHED


def next_code(prefix: str, codes: Iterable[str | None]) -> str:
    """The next free WBS code at one level, after the highest number used there: tasks
    (prefix "") "3" -> "4", subtasks of task 1 (prefix "1.") "1.4" -> "1.5". Gaps left by
    deleted items stay gaps, so a new code never collides with an existing one."""
    trimmed = ((code or "").rstrip(".") for code in codes)
    numbers = (
        int(code[len(prefix) :]) for code in trimmed if code.startswith(prefix) and code[len(prefix) :].isdigit()
    )
    return f"{prefix}{max(numbers, default=0) + 1}"


def child_prefix(parent_code: str | None) -> str | None:
    """ "1" or "1." -> "1."; None when the task has no code (its subtasks then have none either)."""
    code = (parent_code or "").strip().rstrip(".")
    return f"{code}." if code else None


def whole_tasks(nodes: Iterable, involved: Callable[[object], bool]) -> list:
    """Every node of each task tree that has an `involved` node anywhere in it: the task,
    all its subtasks and their items. An engineer sees who else works on their tasks and
    which subtasks are still open, so they know whom to ask before the task can close."""
    nodes = list(nodes)
    parent_of = {node.id: node.parent_id for node in nodes}

    def root(node_id: int) -> int:
        while parent_of.get(node_id) is not None and parent_of[node_id] in parent_of:
            node_id = parent_of[node_id]
        return node_id

    roots = {root(node.id) for node in nodes if involved(node)}
    return [node for node in nodes if root(node.id) in roots]
