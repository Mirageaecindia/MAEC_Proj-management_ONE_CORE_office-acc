"""WBS node statuses: the only values stored in wbs_nodes.deliverable_status.

Tasks:    To Do -> In-Progress -> Submitted for Approval -> Approved
Subtasks: To Do -> In-Progress -> Done

Older code and the Excel upload used other names ("Not Started",
"In Progress", "Completed", ...). `normalize_status` maps them on every write
(see models.WbsNode) and migration 0002 converted existing rows.
"""

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
