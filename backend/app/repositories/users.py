from collections.abc import Collection

from sqlalchemy.orm import Session

import models
from app.core.roles import Role


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_staff(self) -> list[tuple[models.User, models.Employee]]:
        """Every active account with an employee record (anyone the BU Head can make a project lead), by name."""
        return (
            self.db.query(models.User, models.Employee)
            .join(models.Employee, models.Employee.id == models.User.employee_id)
            .filter(models.User.role != Role.BU_HEAD, models.User.is_active.is_(True))
            .order_by(models.Employee.name)
            .all()
        )

    def staff_employee_ids(self) -> list[int]:
        """Employee ids of every active account that can be booked (not a BU Head)."""
        rows = (
            self.db.query(models.User.employee_id)
            .filter(
                models.User.role != Role.BU_HEAD,
                models.User.is_active.is_(True),
                models.User.employee_id.is_not(None),
            )
            .all()
        )
        return [employee_id for (employee_id,) in rows]

    def get_staff(self, user_id: int) -> models.User | None:
        """An active account with an employee record, or None."""
        return (
            self.db.query(models.User)
            .filter(
                models.User.id == user_id,
                models.User.role != Role.BU_HEAD,
                models.User.is_active.is_(True),
                models.User.employee_id.is_not(None),
            )
            .first()
        )

    def employee_ids(self, user_ids: Collection[int]) -> dict[int, int]:
        """user id -> employee id."""
        rows = self.db.query(models.User.id, models.User.employee_id).filter(models.User.id.in_(user_ids)).all()
        return {user_id: employee_id for user_id, employee_id in rows if employee_id}
