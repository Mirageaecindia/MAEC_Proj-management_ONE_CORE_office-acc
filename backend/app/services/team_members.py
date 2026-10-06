"""A lead's team on a project (decided 2026-10-07).

From everyone in the app the lead picks the people they work with on the project.
Resource Booking's Assign Engineer lists only those people, and stays off while the
team is empty. Each lead of a project keeps their own team; picking someone grants
nothing: access still comes from a booking the BU Head approves.
"""

from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError
from app.services.access import require_project_lead

UNKNOWN_PEOPLE = "Some of the chosen people are not in the app. Refresh the page and try again."


class TeamMembers:
    def __init__(self, db: Session):
        self.db = db

    def list(self, user: models.User, project_id: int) -> list[int]:
        """Employee ids in this lead's team for the project."""
        require_project_lead(self.db, user, project_id)
        return self._ids(user, project_id)

    def replace(self, user: models.User, project_id: int, employee_ids: list[int]) -> list[int]:
        """The team becomes exactly `employee_ids`. Commits."""
        require_project_lead(self.db, user, project_id)
        wanted = set(employee_ids)
        known = {i for (i,) in self.db.query(models.Employee.id).filter(models.Employee.id.in_(wanted))}
        if known != wanted:
            raise BadRequestError(UNKNOWN_PEOPLE)
        current = set(self._ids(user, project_id))
        member = models.TeamMember
        if current - wanted:
            self.db.query(member).filter(
                member.project_id == project_id,
                member.lead_user_id == user.id,
                member.employee_id.in_(current - wanted),
            ).delete(synchronize_session=False)
        self.db.add_all(
            member(project_id=project_id, lead_user_id=user.id, employee_id=employee_id)
            for employee_id in sorted(wanted - current)
        )
        self.db.commit()
        return sorted(wanted)

    def _ids(self, user: models.User, project_id: int) -> list[int]:
        member = models.TeamMember
        rows = self.db.query(member.employee_id).filter_by(project_id=project_id, lead_user_id=user.id)
        return sorted(employee_id for (employee_id,) in rows)
