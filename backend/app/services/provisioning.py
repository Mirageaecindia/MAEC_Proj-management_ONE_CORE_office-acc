"""Bringing people into the app: employee records and their engineer accounts.

Today the BU Head feeds it a CSV exported from HR (decided 2026-10-03). When the
company's global admin application exists, it becomes the caller instead, and the
temporary passwords go away with this app's own login. So the rules live here, not
in the upload screen:

- the username is the work email (lowercase); the profile name is the full name;
- the employee code is the HR employee id; the job role is stored as given;
- nothing else is read from the file (no phone numbers, no personal data);
- a person who already has an account, or appears twice in the file, is skipped
  with the reason; an existing employee record without an account gets one;
- each new account has its own random temporary password, returned once and never
  stored readable, and must be changed at the first login.

The BU Head also sees everyone with an account, corrects an engineer's name, work email
or job role, and deactivates a leaver (they can't sign in; their bookings and hours stay,
since pay is calculated from them). Only an account with no history at all (created by
mistake) is deleted outright. BU Head accounts are listed but not changed here.

A BU Head may make an engineer a BU Head (decided 2026-10-04): confirmed with their own
password, and only when the engineer is on no live project (not a lead, not booked, no
tasks on a project that isn't archived), since a BU Head doesn't lead, get booked or log
hours. The role can be taken back from a promoted BU Head, never from the last one or
from oneself. The other BU Heads are notified either way.
"""

import csv
import io
import re
import secrets
from dataclasses import asdict, dataclass

from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.core.security import hash_password, verify_password
from app.services import notifications as notify

# Header of the HR export -> the field it fills. Matched without regard to case or spacing.
COLUMNS = {"employee id": "code", "full name": "name", "work email": "email", "job role": "role_title"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# No 0/O, 1/l/I: the password is read off a list and typed in by hand.
PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 12

MISSING_COLUMNS = "The file needs the columns {}. Found: {}."
NOT_A_STAFF_ACCOUNT = "Only engineer accounts are reset here."
NO_SUCH_ACCOUNT = "No engineer account with that username."
NOT_FOUND = "No such account."
ONLY_ENGINEERS = "BU Head accounts are not changed here."
USERNAME_TAKEN = "Another account already signs in with {}."
BAD_USERNAME = "Give a work email (or a username without spaces)."
NAME_NEEDED = "The name can't be empty."
WRONG_PASSWORD = "Your password is not correct."
NOT_YOURSELF = "You can't change your own role."
NOT_ACTIVE = "Reactivate the account first."
ON_PROJECTS = "{name} is assigned to {projects}. Remove them from these projects before making them a BU Head."
NOT_A_BU_HEAD = "This account is not a BU Head."
LAST_BU_HEAD = "There must always be at least one BU Head."
NO_EMPLOYEE_RECORD = (
    "This BU Head has no employee record, so they can't work as an engineer. Deactivate the account instead."
)
HAS_HISTORY = "{} has work on record (bookings, hours, tasks or a project lead role). Deactivate the account instead."
# Projects keep their leads' names next to the ids, for display: renaming updates these copies too.
LEAD_NAME_COLUMNS = (
    (models.Project.project_lead_electrical, models.Project.project_lead_electrical_user_id),
    (models.Project.project_lead_mechanical, models.Project.project_lead_mechanical_user_id),
    (models.Project.project_lead_bim, models.Project.project_lead_bim_user_id),
)


@dataclass(frozen=True)
class Person:
    row: int  # line in the file, for messages
    code: str
    name: str
    email: str
    role_title: str


@dataclass(frozen=True)
class Created:
    username: str
    full_name: str
    employee_code: str
    temporary_password: str


@dataclass(frozen=True)
class Skipped:
    row: int
    name: str
    email: str
    reason: str


def temporary_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def _clean(value: str | None) -> str:
    """Excel exports carry non-breaking and doubled spaces: one plain space between words."""
    return " ".join((value or "").replace("\xa0", " ").split())


def _decode(content: bytes) -> str:
    """Excel saves CSV as UTF-8 or in the Windows encoding, depending on the version."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252")


def read_people(content: bytes) -> list[Person]:
    """The people in an HR export, with only the four columns the app uses."""
    reader = csv.DictReader(io.StringIO(_decode(content)))
    headers = {_clean(header).lower(): header for header in reader.fieldnames or []}
    missing = [column for column in COLUMNS if column not in headers]
    if missing:
        wanted = ", ".join(f'"{column.title()}"' for column in COLUMNS)
        found = ", ".join(f'"{_clean(header)}"' for header in reader.fieldnames or []) or "no header row"
        raise BadRequestError(MISSING_COLUMNS.format(wanted, found))
    people = []
    for number, raw in enumerate(reader, start=2):  # line 1 is the header
        fields = {COLUMNS[column]: _clean(raw.get(headers[column])) for column in COLUMNS}
        if not any(fields.values()):
            continue  # a blank line
        people.append(Person(row=number, **{**fields, "email": fields["email"].lower()}))
    return people


class Provisioning:
    def __init__(self, db: Session):
        self.db = db

    def import_people(self, people: list[Person]) -> dict:
        """Create employee records and engineer accounts, all in one transaction."""
        usernames = {name.lower() for (name,) in self.db.query(models.User.username)}
        employees = {employee.employee_code: employee for employee in self.db.query(models.Employee)}
        linked = {employee_id for (employee_id,) in self.db.query(models.User.employee_id) if employee_id}
        created: list[Created] = []
        skipped: list[Skipped] = []
        seen_emails: set[str] = set()
        seen_codes: set[str] = set()

        def skip(person: Person, reason: str) -> None:
            skipped.append(Skipped(person.row, person.name, person.email, reason))

        for person in people:
            if not (person.code and person.name and person.email):
                skip(person, "Employee Id, Full Name and Work Email are all needed.")
            elif not EMAIL.match(person.email):
                skip(person, "The work email is not a valid address.")
            elif person.email in seen_emails or person.code in seen_codes:
                skip(person, "Appears earlier in the file.")
            elif person.email in usernames:
                skip(person, "Already has an account.")
            elif person.code in employees and employees[person.code].id in linked:
                skip(person, f"Employee {person.code} already has an account.")
            else:
                created.append(self._create(person, employees.get(person.code)))
            seen_emails.add(person.email)
            seen_codes.add(person.code)
        self.db.commit()
        return {
            "created": [asdict(row) for row in created],
            "skipped": [asdict(row) for row in skipped],
        }

    def reset_password(self, username: str) -> dict:
        """A new temporary password for an engineer, to be changed at their next login. Every
        session of theirs ends, so whoever had the old password is out."""
        user = self.db.query(models.User).filter(func.lower(models.User.username) == username.strip().lower()).first()
        if user is None:
            raise NotFoundError(NO_SUCH_ACCOUNT)
        if user.role != Role.ENGINEER:
            raise ForbiddenError(NOT_A_STAFF_ACCOUNT)
        password = temporary_password()
        user.password_hash, user.must_change_password = hash_password(password), True
        self.db.query(models.LoginSession).filter_by(user_id=user.id).delete(synchronize_session=False)
        self.db.commit()
        return {"username": user.username, "full_name": user.full_name, "temporary_password": password}

    # -- the people already in the app ------------------------------------------------------

    def list_people(self) -> list[dict]:
        """Everyone with an account, by name: no passwords. A fixed number of queries."""
        rows = (
            self.db.query(models.User, models.Employee)
            .outerjoin(models.Employee, models.Employee.id == models.User.employee_id)
            .order_by(func.lower(func.coalesce(models.User.full_name, models.User.username)))
            .all()
        )
        busy_users, busy_employees = self._with_history()
        bu_heads = self._active_bu_heads()
        out = []
        for user, employee in rows:
            engineer = user.role == Role.ENGINEER
            out.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": user.role,
                    "employee_code": employee.employee_code if employee else None,
                    "job_role": employee.role_title if employee else None,
                    "is_active": user.is_active,
                    "must_change_password": user.must_change_password,
                    "can_edit": engineer,
                    "can_delete": engineer
                    and user.id not in busy_users
                    and (employee is None or employee.id not in busy_employees),
                    "can_make_bu_head": engineer and user.is_active,
                    # Only a promoted BU Head (they have an employee record) goes back to engineer.
                    "can_remove_bu_head": not engineer and employee is not None and bu_heads > 1,
                }
            )
        return out

    def update_person(self, user_id: int, full_name: str | None, username: str | None, job_role: str | None) -> dict:
        """Correct an engineer's name, work email (their username) or job role."""
        user, employee = self._engineer(user_id)
        if full_name is not None:
            name = _clean(full_name)
            if not name:
                raise BadRequestError(NAME_NEEDED)
            user.full_name = name
            if employee is not None:
                employee.name = name
            for name_column, id_column in LEAD_NAME_COLUMNS:
                self.db.execute(update(models.Project).where(id_column == user.id).values({name_column: name}))
            self.db.execute(
                update(models.WbsNode).where(models.WbsNode.assigned_lead_user_id == user.id).values(assigned_lead=name)
            )
        if username is not None:
            new = username.strip().lower()
            if not new or " " in new:
                raise BadRequestError(BAD_USERNAME)
            taken = (
                self.db.query(models.User.id)
                .filter(func.lower(models.User.username) == new, models.User.id != user.id)
                .first()
            )
            if taken:
                raise ConflictError(USERNAME_TAKEN.format(new))
            user.username = new
        if job_role is not None and employee is not None:
            employee.role_title = employee.discipline = _clean(job_role)
        self.db.commit()
        return self._one(user.id)

    def set_active(self, user_id: int, active: bool) -> dict:
        """Deactivate a leaver (signed out everywhere, kept on record) or bring them back."""
        user, _ = self._engineer(user_id)
        user.is_active = active
        if not active:
            self.db.query(models.LoginSession).filter_by(user_id=user.id).delete(synchronize_session=False)
        self.db.commit()
        return self._one(user.id)

    def delete_person(self, user_id: int) -> None:
        """Remove an account created by mistake, and its employee record, only if neither has any
        work on record. Anything else is deactivated, so hours and approvals stay intact."""
        user, employee = self._engineer(user_id)
        busy_users, busy_employees = self._with_history()
        if user.id in busy_users or (employee is not None and employee.id in busy_employees):
            raise ConflictError(HAS_HISTORY.format(user.full_name or user.username))
        self.db.query(models.LoginSession).filter_by(user_id=user.id).delete(synchronize_session=False)
        self.db.query(models.Notification).filter_by(recipient_user_id=user.id).delete(synchronize_session=False)
        self.db.delete(user)
        if employee is not None:
            self.db.delete(employee)
        self.db.commit()

    # -- the BU Head role -------------------------------------------------------------------

    def make_bu_head(self, actor: models.User, user_id: int, password: str) -> dict:
        """Promote an engineer who is on no live project. Signs them out, so they come back as BU Head."""
        self._confirm(actor, password, user_id)
        user, employee = self._engineer(user_id)
        if not user.is_active:
            raise ConflictError(NOT_ACTIVE)
        projects = self._live_assignments(user, employee)
        if projects:
            listed = " and ".join(f"{name} as {role}" for name, role in projects)
            raise ConflictError(ON_PROJECTS.format(name=user.full_name or user.username, projects=listed))
        user.role = Role.BU_HEAD
        self._changed_role(actor, user, notify.BU_HEAD_APPOINTED, "New BU Head", "made {} a BU Head.")
        return self._one(user.id)

    def remove_bu_head(self, actor: models.User, user_id: int, password: str) -> dict:
        """Take the BU Head role back: they become an engineer again. Never the last BU Head."""
        self._confirm(actor, password, user_id)
        user = self.db.get(models.User, user_id)
        if user is None:
            raise NotFoundError(NOT_FOUND)
        if user.role != Role.BU_HEAD:
            raise ConflictError(NOT_A_BU_HEAD)
        if user.employee_id is None:
            raise ConflictError(NO_EMPLOYEE_RECORD)
        if self._active_bu_heads() <= 1:
            raise ConflictError(LAST_BU_HEAD)
        user.role = Role.ENGINEER
        self._changed_role(
            actor, user, notify.BU_HEAD_REMOVED, "BU Head role removed", "removed the BU Head role from {}."
        )
        return self._one(user.id)

    def _confirm(self, actor: models.User, password: str, user_id: int) -> None:
        if actor.id == user_id:
            raise ForbiddenError(NOT_YOURSELF)
        if not verify_password(password or "", actor.password_hash):
            raise ForbiddenError(WRONG_PASSWORD)

    def _changed_role(self, actor: models.User, user: models.User, kind: str, title: str, message: str) -> None:
        """Sign the person out everywhere (their pages follow the new role) and tell the BU Heads."""
        self.db.query(models.LoginSession).filter_by(user_id=user.id).delete(synchronize_session=False)
        actor_name = actor.full_name or actor.username
        text = f"{actor_name} " + message.format(user.full_name or user.username)
        notify.notify_role(self.db, Role.BU_HEAD, kind, title, text, None, actor_name)
        self.db.commit()

    def _active_bu_heads(self) -> int:
        return (
            self.db.query(models.User).filter(models.User.role == Role.BU_HEAD, models.User.is_active.is_(True)).count()
        )

    def _live_assignments(self, user: models.User, employee: models.Employee | None) -> list[tuple[str, str]]:
        """(project name, "lead" | "engineer") for every project that isn't archived where the
        person leads, is booked, or has WBS tasks assigned."""
        project = models.Project
        live = project.archived_at.is_(None)
        roles: dict[int, tuple[str, set[str]]] = {}

        def add(rows, role: str) -> None:
            for project_id, name in rows:
                roles.setdefault(project_id, (name, set()))[1].add(role)

        add(
            self.db.query(project.id, project.project_name).filter(
                live, or_(*(id_column == user.id for _, id_column in LEAD_NAME_COLUMNS))
            ),
            "lead",
        )
        if employee is not None:
            booking, node = models.ResourceBooking, models.WbsNode
            add(
                self.db.query(project.id, project.project_name)
                .join(booking, booking.project_id == project.id)
                .filter(live, booking.employee_id == employee.id, booking.role != "lead")
                .distinct(),
                "engineer",
            )
            add(
                self.db.query(project.id, project.project_name)
                .join(node, node.project_id == project.id)
                .filter(live, node.assigned_engineer_id == employee.id)
                .distinct(),
                "engineer",
            )
        return [
            (name, " and ".join(sorted(kinds)))
            for name, kinds in sorted(roles.values(), key=lambda item: (item[0] or "").lower())
        ]

    def _engineer(self, user_id: int) -> tuple[models.User, models.Employee | None]:
        user = self.db.get(models.User, user_id)
        if user is None:
            raise NotFoundError(NOT_FOUND)
        if user.role != Role.ENGINEER:
            raise ForbiddenError(ONLY_ENGINEERS)
        return user, self.db.get(models.Employee, user.employee_id) if user.employee_id else None

    def _one(self, user_id: int) -> dict:
        return next(person for person in self.list_people() if person["id"] == user_id)

    def _with_history(self) -> tuple[set[int], set[int]]:
        """(user ids, employee ids) that have any work on record: what makes deleting unsafe."""
        employees: set[int] = set()
        for column in (
            models.ResourceBooking.employee_id,
            models.TimeLogEntry.employee_id,
            models.TimeSession.employee_id,
            models.WbsNode.assigned_engineer_id,
            models.GanttTask.assigned_engineer_id,
        ):
            employees.update(value for (value,) in self.db.query(column).distinct() if value is not None)
        users: set[int] = set()
        for column in (
            models.WbsNode.assigned_lead_user_id,
            models.WbsNode.created_by_user_id,
            models.WbsNodeHistory.user_id,
            models.TimeLogEntry.reviewed_by_user_id,
            models.TimeLogEntry.task_lead_user_id,
        ):
            users.update(value for (value,) in self.db.query(column).distinct() if value is not None)
        leads = self.db.query(*(id_column for _, id_column in LEAD_NAME_COLUMNS)).filter(
            or_(*(id_column.is_not(None) for _, id_column in LEAD_NAME_COLUMNS))
        )
        users.update(value for row in leads for value in row if value is not None)
        return users, employees

    def _create(self, person: Person, employee: models.Employee | None) -> Created:
        if employee is None:
            employee = models.Employee(
                employee_code=person.code, name=person.name, role_title=person.role_title, discipline=person.role_title
            )
            self.db.add(employee)
            self.db.flush()
        password = temporary_password()
        self.db.add(
            models.User(
                username=person.email,
                password_hash=hash_password(password),
                full_name=person.name,
                role=Role.ENGINEER,
                employee_id=employee.id,
                must_change_password=True,
            )
        )
        return Created(person.email, person.name, person.code, password)
