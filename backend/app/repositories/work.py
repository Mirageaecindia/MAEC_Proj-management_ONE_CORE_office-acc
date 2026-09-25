"""Read access to a project's execution data (WBS nodes, timesheets, people)."""

from collections.abc import Collection

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import models
from app.domain.timesheets import APPROVED, HOUR_FIELDS


class WorkRepository:
    def __init__(self, db: Session):
        self.db = db

    def nodes_for_project(self, project_id: int, *, order_by_code: bool = False) -> list[models.WbsNode]:
        query = self.db.query(models.WbsNode).filter_by(project_id=project_id)
        if order_by_code:
            query = query.order_by(models.WbsNode.wbs_code)
        return query.all()

    def entries_for_project(self, project_id: int) -> list[models.TimeLogEntry]:
        return self.db.query(models.TimeLogEntry).filter_by(project_id=project_id).all()

    def week_statuses(self, project_id: int) -> dict[tuple[int, object], str]:
        """(employee_id, week_start_date) -> weekly submission status for a project."""
        rows = (
            self.db.query(
                models.WeeklyHoursSubmission.employee_id,
                models.WeeklyHoursSubmission.week_start_date,
                models.WeeklyHoursSubmission.status,
            )
            .filter(models.WeeklyHoursSubmission.project_id == project_id)
            .all()
        )
        return {(employee_id, week): status for employee_id, week, status in rows}

    def approved_hours(self, project_id: int) -> float:
        """Approved hours on a project (all seven days), in one SQL query. A row counts when
        it was approved itself or its engineer's week was approved (see effective_status)."""
        entry, week = models.TimeLogEntry, models.WeeklyHoursSubmission
        hours_sum = sum(func.coalesce(getattr(entry, field), 0) for field in HOUR_FIELDS)
        total = (
            self.db.query(func.sum(hours_sum))
            .select_from(entry)
            .outerjoin(
                week,
                and_(
                    week.project_id == entry.project_id,
                    week.employee_id == entry.employee_id,
                    week.week_start_date == entry.week_start_date,
                ),
            )
            .filter(entry.project_id == project_id, or_(entry.approval_status == APPROVED, week.status == APPROVED))
            .scalar()
        )
        return float(total or 0)

    def employees_by_ids(self, ids: Collection[int]) -> dict[int, models.Employee]:
        if not ids:
            return {}
        employees = self.db.query(models.Employee).filter(models.Employee.id.in_(ids)).all()
        return {employee.id: employee for employee in employees}

    def employee_count(self) -> int:
        return self.db.query(models.Employee).count()
