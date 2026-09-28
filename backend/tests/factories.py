"""Test data builders shared by the BU Head characterization suite.

Imported only after conftest.py has isolated the environment.
"""

from datetime import date
from itertools import count

import models
from auth import hash_password

PASSWORD = "Passw0rd!"
# Hash once: PBKDF2 is deliberately slow and every test creates several users.
_PASSWORD_HASH = hash_password(PASSWORD)
WEEK = date(2026, 9, 7)


class Factory:
    """Builds rows directly in the database and logs users in via the API."""

    def __init__(self, db, client):
        self.db = db
        self.client = client
        self._seq = count(1)

    def next_seq(self):
        return next(self._seq)

    def _save(self, row):
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def user(self, username, role, full_name=None, discipline=None, employee_id=None):
        return self._save(
            models.User(
                username=username,
                password_hash=_PASSWORD_HASH,
                full_name=full_name,
                role=role,
                discipline=discipline,
                employee_id=employee_id,
            )
        )

    def lead(self, username, full_name, discipline):
        """A lead account with its employee record (everyone the BU Head can pick has one)."""
        employee = self.employee(full_name, discipline=f"{discipline} Lead")
        return self.user(username, "lead", full_name, discipline=discipline, employee_id=employee.id)

    def employee(self, name, discipline="Mechanical Engineer"):
        n = next(self._seq)
        return self._save(
            models.Employee(employee_code=f"E{n:04d}", name=name, role_title=discipline, discipline=discipline)
        )

    def headers(self, user):
        response = self.client.post("/api/auth/login", json={"username": user.username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['token']}"}

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

    def time_entry(self, project_id, node, employee, hours=0, status="pending_review", week=WEEK, **day_hours):
        return self._save(
            models.TimeLogEntry(
                project_id=project_id,
                task_id=node.id,
                employee_id=employee.id,
                week_start_date=week,
                mon_hours=hours,
                approval_status=status,
                **day_hours,
            )
        )
