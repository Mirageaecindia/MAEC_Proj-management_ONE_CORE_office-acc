"""Who approves which hours (decided 2026-09-28).

Hours are approved per timesheet row: one subtask, one engineer, one week.
1. A project lead's own hours: the BU Head.
2. Otherwise the lead of the row's task, while they lead the project and
   their lead period hasn't ended.
3. Otherwise (the task has no lead, its lead was replaced or their period is
   over, or the lead is the engineer themselves): the BU Head.
Nobody approves their own hours, and no hours are left without a reviewer.

"Approve week" approves only the caller's rows; the week becomes Approved once
every row is (see `week_status`). Usage counts each row as it is approved.
"""

from collections.abc import Iterable
from datetime import date

from sqlalchemy.orm import Session

import models
from app.core.roles import Role
from app.domain.timesheets import APPROVED, PENDING_REVIEW, REJECTED

BU_HEAD = None  # reviewer id meaning "the BU Head"
SUBMITTED = "submitted"


def week_status(row_statuses: Iterable[str]) -> str:
    """A submitted week's status, derived from its rows: waiting while any row is pending."""
    statuses = set(row_statuses)
    if PENDING_REVIEW in statuses or not statuses:
        return SUBMITTED
    return REJECTED if REJECTED in statuses else APPROVED


class HoursReview:
    """The reviewer rule for one project, loaded once (two small queries) and applied to any number of rows."""

    def __init__(self, db: Session, project: models.Project, today: date):
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


def sync_week_status(db: Session, project_id: int, employee_id: int, week: date) -> None:
    """Keep a submitted week's status in step with its rows (a no-op before the engineer submits)."""
    submission = (
        db.query(models.WeeklyHoursSubmission)
        .filter_by(project_id=project_id, employee_id=employee_id, week_start_date=week)
        .first()
    )
    if submission is None:
        return
    rows = db.query(models.TimeLogEntry.approval_status).filter_by(
        project_id=project_id, employee_id=employee_id, week_start_date=week
    )
    submission.status = week_status(status for (status,) in rows)


def tasks_by_id(db: Session, entries: Iterable[models.TimeLogEntry]) -> dict[int, models.WbsNode]:
    ids = {entry.task_id for entry in entries}
    return {node.id: node for node in db.query(models.WbsNode).filter(models.WbsNode.id.in_(ids))} if ids else {}


def review_summary(
    db: Session,
    project: models.Project,
    week: date,
    employee_ids: Iterable[int],
    user: models.User,
    today: date,
) -> dict[int, dict]:
    """Per engineer, for one week: whether `user` has rows to review, and how many reviewers have
    finished ("2 of 3 approved") with the names still pending. Four queries for the whole list."""
    employee_ids = set(employee_ids)
    if not employee_ids:
        return {}
    entries = (
        db.query(models.TimeLogEntry)
        .filter(
            models.TimeLogEntry.project_id == project.id,
            models.TimeLogEntry.week_start_date == week,
            models.TimeLogEntry.employee_id.in_(employee_ids),
        )
        .all()
    )
    tasks = tasks_by_id(db, entries)
    review = HoursReview(db, project, today)
    per_employee: dict[int, dict[int | None, bool]] = {}  # reviewer -> still has pending rows
    mine: set[int] = set()
    for entry in entries:
        task = tasks.get(entry.task_id)
        reviewer = review.reviewer(task, entry.employee_id)
        pending = entry.approval_status == PENDING_REVIEW
        reviewers = per_employee.setdefault(entry.employee_id, {})
        reviewers[reviewer] = reviewers.get(reviewer, False) or pending
        if pending and review.may_review(user, task, entry.employee_id):
            mine.add(entry.employee_id)
    lead_ids = {reviewer for reviewers in per_employee.values() for reviewer in reviewers} - {BU_HEAD}
    names = (
        dict(db.query(models.User.id, models.User.full_name).filter(models.User.id.in_(lead_ids))) if lead_ids else {}
    )
    summary = {}
    for employee_id in employee_ids:
        reviewers = per_employee.get(employee_id, {})
        waiting = [
            ("BU Head" if r is BU_HEAD else names.get(r) or "Lead") for r, pending in reviewers.items() if pending
        ]
        summary[employee_id] = {
            "can_review": employee_id in mine,
            "reviewers_total": len(reviewers),
            "reviewers_done": len(reviewers) - len(waiting),
            "waiting_on": sorted(waiting),
        }
    return summary
