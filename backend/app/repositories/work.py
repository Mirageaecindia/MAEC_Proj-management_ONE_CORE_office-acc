"""Read access to a project's execution data (WBS nodes, timesheets, people)."""

from collections.abc import Collection

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from app.domain.timesheets import APPROVED
from app.domain.wbs import by_code


class WorkRepository:
    def __init__(self, db: Session):
        self.db = db

    def nodes_for_project(self, project_id: int, *, order_by_code: bool = False) -> list[models.WbsNode]:
        nodes = self.db.query(models.WbsNode).filter_by(project_id=project_id).all()
        return by_code(nodes) if order_by_code else nodes

    def entries_for_project(self, project_id: int) -> list[models.TimeLogEntry]:
        return self.db.query(models.TimeLogEntry).filter_by(project_id=project_id).all()

    def approved_hours(self, project_id: int) -> float:
        """Approved hours on a project, in one SQL query."""
        entry = models.TimeLogEntry
        total = (
            self.db.query(func.sum(entry.hours))
            .filter(entry.project_id == project_id, entry.approval_status == APPROVED)
            .scalar()
        )
        return float(total or 0)

    def employees_by_ids(self, ids: Collection[int]) -> dict[int, models.Employee]:
        if not ids:
            return {}
        employees = self.db.query(models.Employee).filter(models.Employee.id.in_(ids)).all()
        return {employee.id: employee for employee in employees}
