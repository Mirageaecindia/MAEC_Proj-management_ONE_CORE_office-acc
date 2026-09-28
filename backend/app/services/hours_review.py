"""Who approves which hours, and the decisions themselves (decided 2026-09-28).

Hours are approved per day, per subtask, per engineer:
1. A project lead's own hours: the BU Head.
2. Otherwise the lead of the row's task, while they lead the project and
   their lead period hasn't ended.
3. Otherwise (the task has no lead, its lead was replaced or their period is
   over, or the lead is the engineer themselves): the BU Head.
Nobody approves their own hours, and no hours are left without a reviewer.

Only finished days are reviewed. Usage counts each day as it is approved; the
week is nothing more than the sum of its days.
"""

from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, ConflictError, ForbiddenError
from app.core.roles import Role
from app.domain.timesheets import APPROVED, PENDING_REVIEW, REASON_REQUIRED, review_transition, reviewable

BU_HEAD = None  # reviewer id meaning "the BU Head"
NOT_YOUR_HOURS = (
    "These hours are approved by the task's lead, or by the BU Head when the task has no active lead "
    "or they are a project lead's own."
)
DAY_NOT_OVER = "A day is reviewed once it is over (yesterday or earlier)."
HOURS_UNAPPROVED = "hours_unapproved"  # GovernanceAction.action: approved hours taken back, with the reason


def tasks_by_id(db: Session, entries: Iterable[models.TimeLogEntry]) -> dict[int, models.WbsNode]:
    ids = {entry.task_id for entry in entries}
    return {node.id: node for node in db.query(models.WbsNode).filter(models.WbsNode.id.in_(ids))} if ids else {}


class HoursReview:
    """The reviewer rule for one project, loaded once (two small queries) and applied to any number of rows."""

    def __init__(self, db: Session, project: models.Project, today: date):
        self.db = db
        self.project = project
        self.today = today
        lead_ids = {
            project.project_lead_electrical_user_id,
            project.project_lead_mechanical_user_id,
            project.project_lead_bim_user_id,
        } - {None}
        rows = db.query(models.User.id, models.User.employee_id).filter(models.User.id.in_(lead_ids)).all()
        self._employee_of_lead = {user_id: employee_id for user_id, employee_id in rows}
        self.lead_employee_ids = set(self._employee_of_lead.values()) - {None}
        ended = {
            employee_id
            for (employee_id,) in db.query(models.ResourceBooking.employee_id).filter(
                models.ResourceBooking.project_id == project.id,
                models.ResourceBooking.role == "lead",
                models.ResourceBooking.end_date < today,
            )
        }
        self._active_leads = {user_id for user_id, employee_id in rows if employee_id not in ended}

    def reviewer(self, task: models.WbsNode | None, employee_id: int) -> int | None:
        """The user id who approves this engineer's hours on this task, or BU_HEAD."""
        if employee_id in self.lead_employee_ids:
            return BU_HEAD
        lead = task.assigned_lead_user_id if task is not None else None
        if lead not in self._active_leads or self._employee_of_lead.get(lead) == employee_id:
            return BU_HEAD
        return lead

    def may_review(self, user: models.User, task: models.WbsNode | None, employee_id: int) -> bool:
        reviewer = self.reviewer(task, employee_id)
        return user.role == Role.BU_HEAD if reviewer is BU_HEAD else reviewer == user.id

    def review(
        self,
        user: models.User,
        entry: models.TimeLogEntry,
        task: models.WbsNode | None,
        action: str,
        reason: str | None,
        now: datetime,
    ) -> None:
        """One decision on one day's hours. The caller checks the project lock and commits."""
        if not self.may_review(user, task, entry.employee_id):
            raise ForbiddenError(NOT_YOUR_HOURS)
        if not reviewable(entry.work_date, self.today):
            raise ConflictError(DAY_NOT_OVER)
        problem = review_transition(entry.approval_status, action, reason)
        if problem == REASON_REQUIRED:
            raise BadRequestError(problem)
        if problem:
            raise ConflictError(problem)
        reviewer = user.full_name or user.username
        if entry.approval_status == APPROVED:  # taken back: audited, shown on the BU Head's dashboard
            task_name = task.task_name if task is not None else f"task #{entry.task_id}"
            self.db.add(
                models.GovernanceAction(
                    project_id=entry.project_id,
                    action=HOURS_UNAPPROVED,
                    comments=f"{entry.hours:g} h on {entry.work_date.isoformat()} ({task_name}) rejected: {reason}",
                    created_by=reviewer,
                )
            )
        entry.approval_status, entry.reviewed_by, entry.reviewed_at = action, reviewer, now
        entry.review_reason = (reason or "").strip() or None

    def review_pending(
        self,
        user: models.User,
        entries: Iterable[models.TimeLogEntry],
        tasks: dict[int, models.WbsNode],
        action: str,
        now: datetime,
    ) -> int:
        """Bulk: every pending, finished day among `entries` that `user` is responsible for.
        Returns how many were decided."""
        mine = [
            entry
            for entry in entries
            if entry.approval_status == PENDING_REVIEW
            and reviewable(entry.work_date, self.today)
            and self.may_review(user, tasks.get(entry.task_id), entry.employee_id)
        ]
        for entry in mine:
            self.review(user, entry, tasks.get(entry.task_id), action, None, now)
        return len(mine)
