"""WBS node statuses: the only values stored in wbs_nodes.deliverable_status.

Tasks:    To Do -> In-Progress -> Submitted for Approval -> Approved
Subtasks: To Do -> In-Progress -> Done

Older code and the Excel upload used other names ("Not Started",
"In Progress", "Completed", ...). `normalize_status` maps them on every write
(see models.WbsNode) and migration 0002 converted existing rows.
"""

import re
from collections.abc import Iterable

from app.domain.wbs_nodes import node_phases

# The five original phases, in order (WBS_PHASES in schemas, the outline workbook). No longer offered
# since 2026-10-15 (the WBS nodes of app/domain/wbs_nodes.py took their place); their tasks stay valid.
PHASES = ("Space Planning", "STR Coordination", "ID - RCP Coordination", "BoH Area RCP Coordination", "Submission")
# A renamed phase keeps its old name as an alias: old workbooks and old API calls still work.
RENAMED_PHASES = {"ID Coordination": "ID - RCP Coordination"}  # 2026-10-09


def current_phase(name) -> str | None:
    """The phase by its current name (an old name is taken too), or None when it is not a phase:
    a WBS node (a sheet of the stage workbooks) or one of the five original phases."""
    text = str(name or "").strip()
    text = RENAMED_PHASES.get(text, text)
    return text if text in PHASES or text in node_phases() else None


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


NO_DEEPER = "A sub-subtask can't have items of its own."


def code_order(node) -> tuple:
    """Sort key: WBS codes in number order (1, 2, ... 10; 1.2 before 1.10), not as text, where
    "10." would come before "2.". Items without a code come last, oldest first."""
    numbers = tuple(int(part) for part in re.findall(r"\d+", node.wbs_code or ""))
    return (0, numbers, node.id) if numbers else (1, (), node.id)


def by_code(nodes: Iterable) -> list:
    return sorted(nodes, key=code_order)


def is_sub_subtask(parent) -> bool:
    """A node whose parent is a subtask: a sub-subtask. Sub-subtasks are for reference:
    they split a subtask into smaller steps (To Do -> In-Progress -> Done) but take no
    Login/Logout, no hours and no estimate, and don't hold up their subtask."""
    return parent is not None and parent.parent_id is not None


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
