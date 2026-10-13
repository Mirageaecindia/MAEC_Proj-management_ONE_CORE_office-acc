"""Test data builders shared by the BU Head characterization suite.

Imported only after conftest.py has isolated the environment.
"""

from datetime import date
from itertools import count

import models
from app.core.security import NO_PASSWORD

WEEK = date(2026, 9, 7)


class Factory:
    """Builds rows directly in the database, and signs people in at the fake MAEC One Core."""

    def __init__(self, db, client, core):
        self.db = db
        self.client = client
        self.core = core
        self._seq = count(1)

    def next_seq(self):
        return next(self._seq)

    def _save(self, row):
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def user(self, username, role, full_name=None, employee_id=None):
        return self._save(
            models.User(
                username=username,
                password_hash=NO_PASSWORD,
                full_name=full_name,
                role=role,
                employee_id=employee_id,
            )
        )

    def lead(self, username, full_name, discipline):
        """An engineer account the BU Head picks as a project lead: the designation names the discipline."""
        employee = self.employee(full_name, discipline=f"{discipline} Lead")
        return self.user(username, "engineer", full_name, employee_id=employee.id)

    def employee(self, name, discipline="Mechanical Engineer"):
        n = next(self._seq)
        return self._save(
            models.Employee(employee_code=f"E{n:04d}", name=name, role_title=discipline, discipline=discipline)
        )

    def headers(self, user, core_id=None):
        """Sign the person in at (fake) MAEC One, by the email their profile carries: the
        browser's cookie and Origin for every request after. Their profile is linked to the
        Core identity at the first request, as in production (app/core/identity.py)."""
        token = self.core.sign_in(user.username, user.full_name or "", core_id=core_id or f"core-user-{user.id}")
        return self.core.headers(token)

    def wbs_node(self, project_id, lead, engineer=None, **fields):
        n = next(self._seq)
        values = {
            "project_id": project_id,
            "wbs_code": f"{n}.",
            "task_name": f"Task {n}",
            "phase": "Space Planning",
            "estimated_hours": 40,
            "deliverable_status": "To Do",
            "assigned_lead": lead.full_name,
            "assigned_lead_user_id": lead.id,
            "assigned_engineer_id": engineer.id if engineer else None,
            "start_date": date(2026, 9, 1),
            "target_due_date": date(2026, 9, 30),
        }
        values.update(fields)
        return self._save(models.WbsNode(**values))

    def time_entry(self, project_id, node, employee, hours, status="pending_review", day=WEEK):
        """One day's hours on a node, as Logout banks them (a Monday in the past by default)."""
        return self._save(
            models.TimeLogEntry(
                project_id=project_id,
                task_id=node.id,
                employee_id=employee.id,
                work_date=day,
                hours=hours,
                approval_status=status,
            )
        )
