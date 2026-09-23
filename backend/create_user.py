"""Create a MAEC login account. Run from the backend directory:

    Scripts\\python.exe create_user.py

It prompts for username, password, full name, role (bu_head/lead/engineer)
and, for engineers, an employee id from the employees table. Accounts are
NOT seeded at startup on purpose — real credentials are created manually.

Example:
    Scripts\\python.exe create_user.py --username lead.anita --role lead --full-name "Anita Kumar"

For an engineer, link the account to an employee so WBS/timesheet data is
scoped to that engineer:
    Scripts\\python.exe create_user.py --username eng.arjun --role engineer --employee-id 1
"""

import argparse
import getpass

from sqlalchemy.orm import Session

import models
from auth import hash_password
from database import Base, SessionLocal, engine

ROLES = ("bu_head", "lead", "engineer")


def create_user(
    db: Session,
    username: str,
    password: str,
    full_name: str,
    role: str,
    employee_id: int | None,
) -> models.User:
    if role not in ROLES:
        raise SystemExit(f"Invalid role '{role}'. Choose one of: {', '.join(ROLES)}.")
    if not username.strip():
        raise SystemExit("Username cannot be empty.")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if db.query(models.User).filter_by(username=username.strip()).first():
        raise SystemExit(f"User '{username}' already exists.")

    if role == "engineer":
        if not employee_id:
            raise SystemExit("Engineer accounts must be linked to an employee (--employee-id).")
        if not db.query(models.Employee).filter_by(id=employee_id).first():
            raise SystemExit(f"No employee with id {employee_id} in the employees table.")
    elif employee_id is not None:
        if not db.query(models.Employee).filter_by(id=employee_id).first():
            raise SystemExit(f"No employee with id {employee_id} in the employees table.")

    user = models.User(
        username=username.strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip() or None,
        role=role,
        employee_id=employee_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a MAEC login account.")
    parser.add_argument("--username", help="Login username (unique).")
    parser.add_argument("--role", choices=ROLES, help="bu_head | lead | engineer")
    parser.add_argument("--full-name", help="Display name (used as lead identity for leads).")
    parser.add_argument("--employee-id", type=int, help="Employee id to link (required for engineers).")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)

    username = args.username or input("Username: ").strip()
    role = args.role or input(f"Role ({'/'.join(ROLES)}): ").strip()
    full_name = args.full_name or input("Full name (optional): ").strip()
    if role == "engineer":
        employee_id = args.employee_id
        if employee_id is None:
            raw = input("Employee id (from employees table): ").strip()
            employee_id = int(raw) if raw else None
    else:
        employee_id = args.employee_id

    password = getpass.getpass("Password: ")

    db = SessionLocal()
    try:
        user = create_user(db, username, password, full_name, role, employee_id)
    finally:
        db.close()
    print(f"Created user '{user.username}' (role={user.role}, employee_id={user.employee_id or '—'}).")


if __name__ == "__main__":
    main()
