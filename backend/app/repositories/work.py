"""Read access to a project's execution data (WBS nodes, timesheets, people)."""

from collections.abc import Collection

from sqlalchemy.orm import Session

import models


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

    def employees_by_ids(self, ids: Collection[int]) -> dict[int, models.Employee]:
        if not ids:
            return {}
        employees = self.db.query(models.Employee).filter(models.Employee.id.in_(ids)).all()
        return {employee.id: employee for employee in employees}

    def employee_count(self) -> int:
        return self.db.query(models.Employee).count()
