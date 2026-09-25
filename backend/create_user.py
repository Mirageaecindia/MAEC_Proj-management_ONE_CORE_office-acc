"""Create a MAEC login account. Run from the backend directory.

Interactive (prompts for anything not given):
    .venv\\Scripts\\python.exe create_user.py

Leads need a discipline (Electrical, Mechanical or BIM); it decides which
Create Project dropdown they appear in:
    .venv\\Scripts\\python.exe create_user.py --username lead.anita --role lead ^
        --full-name "Anita Kumar" --discipline Electrical

Engineers are linked to an employee so WBS/timesheet data is scoped to them:
    .venv\\Scripts\\python.exe create_user.py --username eng.arjun --role engineer --employee-id 1

Set the discipline of an existing lead (no password prompt):
    .venv\\Scripts\\python.exe create_user.py --username lead --set-discipline Mechanical

Deactivate a leaver (logged out at once, can't log in again) or reactivate:
    .venv\\Scripts\\python.exe create_user.py --username eng.arjun --deactivate
    .venv\\Scripts\\python.exe create_user.py --username eng.arjun --activate

Accounts are NOT seeded at startup on purpose: real credentials are created manually.
"""

import argparse
import getpass

from sqlalchemy.orm import Session

import models
from app.core.migrations import migrate
from auth import hash_password
from database import SessionLocal, engine

ROLES = ("bu_head", "lead", "engineer")
LEAD_DISCIPLINES = ("Electrical", "Mechanical", "BIM")


def normalize_discipline(value: str | None) -> str | None:
    """'electrical' / 'ELECTRICAL' -> 'Electrical'; None stays None; anything else is rejected."""
    if value is None or not value.strip():
        return None
    for discipline in LEAD_DISCIPLINES:
        if discipline.lower() == value.strip().lower():
            return discipline
    raise SystemExit(f"Invalid discipline '{value}'. Choose one of: {', '.join(LEAD_DISCIPLINES)}.")


def create_user(
    db: Session,
    username: str,
    password: str,
    full_name: str,
    role: str,
    employee_id: int | None,
    discipline: str | None = None,
) -> models.User:
    if role not in ROLES:
        raise SystemExit(f"Invalid role '{role}'. Choose one of: {', '.join(ROLES)}.")
    if not username.strip():
        raise SystemExit("Username cannot be empty.")
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    if db.query(models.User).filter_by(username=username.strip()).first():
        raise SystemExit(f"User '{username}' already exists.")

    discipline = normalize_discipline(discipline)
    if role == "lead" and discipline is None:
        raise SystemExit(f"Lead accounts need a discipline (--discipline {'|'.join(LEAD_DISCIPLINES)}).")
    if role != "lead" and discipline is not None:
        raise SystemExit("Only lead accounts have a discipline.")

    if role == "engineer" and not employee_id:
        raise SystemExit("Engineer accounts must be linked to an employee (--employee-id).")
    if employee_id is not None and not db.get(models.Employee, employee_id):
        raise SystemExit(f"No employee with id {employee_id} in the employees table.")

    user = models.User(
        username=username.strip(),
        password_hash=hash_password(password),
        full_name=full_name.strip() or None,
        role=role,
        discipline=discipline,
        employee_id=employee_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_lead_discipline(db: Session, username: str, discipline: str) -> models.User:
    """Assign a discipline to an existing lead account."""
    user = db.query(models.User).filter_by(username=username.strip()).first()
    if not user:
        raise SystemExit(f"User '{username}' does not exist.")
    if user.role != "lead":
        raise SystemExit(f"User '{username}' is a {user.role}; only lead accounts have a discipline.")
    user.discipline = normalize_discipline(discipline)
    if user.discipline is None:
        raise SystemExit(f"Give a discipline: {', '.join(LEAD_DISCIPLINES)}.")
    db.commit()
    db.refresh(user)
    return user


def set_active(db: Session, username: str, active: bool) -> models.User:
    """Activate or deactivate an account; deactivating also ends its sessions."""
    user = db.query(models.User).filter_by(username=username.strip()).first()
    if not user:
        raise SystemExit(f"User '{username}' does not exist.")
    user.is_active = active
    if not active:
        db.query(models.LoginSession).filter_by(user_id=user.id).delete(synchronize_session=False)
    db.commit()
    db.refresh(user)
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a MAEC login account.")
    parser.add_argument("--username", help="Login username (unique).")
    parser.add_argument("--role", choices=ROLES, help="bu_head | lead | engineer")
    parser.add_argument("--full-name", help="Display name (used as lead identity for leads).")
    parser.add_argument("--employee-id", type=int, help="Employee id to link (required for engineers).")
    parser.add_argument("--discipline", help="Lead discipline: Electrical | Mechanical | BIM (required for leads).")
    parser.add_argument(
        "--set-discipline",
        metavar="DISCIPLINE",
        help="Only update the discipline of the existing lead given by --username.",
    )
    status = parser.add_mutually_exclusive_group()
    status.add_argument("--deactivate", action="store_true", help="Deactivate the account given by --username.")
    status.add_argument("--activate", action="store_true", help="Reactivate the account given by --username.")
    args = parser.parse_args()

    migrate(engine)  # same schema as the server, even if it hasn't started yet
    db = SessionLocal()
    try:
        if args.deactivate or args.activate:
            if not args.username:
                raise SystemExit("--deactivate/--activate need --username.")
            user = set_active(db, args.username, active=args.activate)
            print(f"User '{user.username}' is now {'active' if user.is_active else 'deactivated'}.")
            return

        if args.set_discipline:
            if not args.username:
                raise SystemExit("--set-discipline needs --username.")
            user = set_lead_discipline(db, args.username, args.set_discipline)
            print(f"Lead '{user.username}' ({user.full_name or '—'}) is now in discipline {user.discipline}.")
            return

        username = args.username or input("Username: ").strip()
        role = args.role or input(f"Role ({'/'.join(ROLES)}): ").strip()
        full_name = args.full_name or input("Full name (optional): ").strip()
        employee_id = args.employee_id
        if role == "engineer" and employee_id is None:
            raw = input("Employee id (from employees table): ").strip()
            employee_id = int(raw) if raw else None
        discipline = args.discipline
        if role == "lead" and not discipline:
            discipline = input(f"Discipline ({'/'.join(LEAD_DISCIPLINES)}): ").strip()
        password = getpass.getpass("Password: ")

        user = create_user(db, username, password, full_name, role, employee_id, discipline)
    finally:
        db.close()
    details = f"discipline={user.discipline}" if user.role == "lead" else f"employee_id={user.employee_id or '—'}"
    print(f"Created user '{user.username}' (role={user.role}, {details}).")


if __name__ == "__main__":
    main()
