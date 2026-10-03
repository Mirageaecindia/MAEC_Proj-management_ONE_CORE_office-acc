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
"""

import csv
import io
import re
import secrets
from dataclasses import asdict, dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from app.core.errors import BadRequestError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.core.security import hash_password

# Header of the HR export -> the field it fills. Matched without regard to case or spacing.
COLUMNS = {"employee id": "code", "full name": "name", "work email": "email", "job role": "role_title"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# No 0/O, 1/l/I: the password is read off a list and typed in by hand.
PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 12

MISSING_COLUMNS = "The file needs the columns {}. Found: {}."
NOT_A_STAFF_ACCOUNT = "Only engineer accounts are reset here."
NO_SUCH_ACCOUNT = "No engineer account with that username."


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
