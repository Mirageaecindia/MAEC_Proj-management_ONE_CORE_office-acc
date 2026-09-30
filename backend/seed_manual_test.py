"""Seed a SCRATCH database for walking through the timesheet flow by hand.

    .venv\\Scripts\\python.exe seed_manual_test.py --database manual_test.db

It builds a new SQLite file with four accounts, one project and the situations
that otherwise take days to reach: a session past 8 hours with an old last
visit, an unattended day, an overtime day, and rejections that are 6 and 8
days old. Then it prints the accounts and how to start the app on that file.

It never touches a real or development database:
- the target must be passed explicitly (`--database`), as a path to a `.db` file;
- it refuses the development database (DATABASE_URL from the environment or
  backend/.env, and the default promanage.db);
- it refuses a file that already exists, unless `--reset` is given and the file
  is a scratch database this script made (its only project is MANUAL-TEST).
"""

import argparse
import os
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DEV_DATABASE = BACKEND_DIR / "promanage.db"
MARKER_PROJECT_CODE = "MANUAL-TEST"
PASSWORD = "MaecTest@2026"  # scratch accounts only
NO_SHAREPOINT = (
    "AZURE_CLIENT_ID",
    "AZURE_CLIENT_SECRET",
    "AZURE_TENANT_ID",
    "SHAREPOINT_SITE_ID",
    "SHAREPOINT_DRIVE_ID",
)


class Refused(SystemExit):
    """The target is not a safe scratch database."""


def sqlite_path(url: str | None) -> Path | None:
    """The file behind a sqlite URL, or None for anything else."""
    if not url or not url.startswith("sqlite:///"):
        return None
    return Path(url.removeprefix("sqlite:///")).resolve()


def dev_database_paths(environ: dict[str, str], env_file: Path) -> set[Path]:
    """Every file that could be the development database: the default, DATABASE_URL in the
    environment, and DATABASE_URL in backend/.env. Only that one key of the file is read."""
    paths = {DEFAULT_DEV_DATABASE.resolve()}
    candidates = [environ.get("DATABASE_URL")]
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.strip().partition("=")
            if key.strip() == "DATABASE_URL":
                candidates.append(value.strip().strip("\"'"))
    paths.update(path for path in map(sqlite_path, candidates) if path is not None)
    return paths


def is_scratch(path: Path) -> bool:
    """An existing file this script made: a database whose only project is the marker project."""
    try:
        # closing(): sqlite3's own context manager only ends the transaction and would keep the
        # file open, so a --reset could not delete it on Windows.
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
            codes = [code for (code,) in connection.execute("SELECT project_code FROM projects")]
    except sqlite3.Error:
        return False
    return codes == [MARKER_PROJECT_CODE]


def safe_target(database: str | None, reset: bool, dev_paths: set[Path]) -> Path:
    """The scratch file to write, or Refused with the reason."""
    if not database:
        raise Refused("Pass the scratch database explicitly: --database manual_test.db")
    if "://" in database:
        raise Refused("Pass a path to a .db file, not a database URL. Only a SQLite scratch file is ever written.")
    target = Path(database).resolve()
    if target.suffix != ".db":
        raise Refused(f"{target.name}: the scratch database must be a .db file.")
    if target in dev_paths:
        raise Refused(f"{target} is the development database. This script only writes a scratch file.")
    if target.exists():
        if not reset:
            raise Refused(f"{target} already exists. Choose another name, or pass --reset to rebuild a scratch file.")
        if not is_scratch(target):
            raise Refused(f"{target} was not made by this script (its only project is not {MARKER_PROJECT_CODE}).")
    return target


def seed(target: Path) -> dict:
    """Build the scratch database. The app is imported only here, after DATABASE_URL points at it."""
    for leftover in (target, *(target.with_name(target.name + suffix) for suffix in ("-wal", "-shm", "-journal"))):
        leftover.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{target.as_posix()}"
    for key in NO_SHAREPOINT:  # a seed never calls Microsoft Graph
        os.environ[key] = ""

    from fastapi.testclient import TestClient

    import main  # runs the migrations against the scratch file
    import models
    from app.core.database import SessionLocal, engine
    from auth import hash_password

    assert sqlite_path(str(engine.url).replace("\\", "/")) == target, "the app did not open the scratch database"
    client = TestClient(main.app)
    db = SessionLocal()
    now = datetime.now(UTC)
    today = now.date()

    def person(username: str, name: str, role: str, title: str | None):
        employee = None
        if title:
            employee = models.Employee(employee_code=username.upper(), name=name, role_title=title, discipline=title)
            db.add(employee)
            db.flush()
        user = models.User(
            username=username,
            password_hash=hash_password(PASSWORD),
            full_name=name,
            role=role,
            employee_id=employee.id if employee else None,
        )
        db.add(user)
        db.commit()
        return user, employee

    def headers(username: str) -> dict:
        response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['token']}"}

    def ok(response, status=200):
        assert response.status_code == status, response.text
        return response.json()

    bu_head, _ = person("bu.test", "Test BU Head", "bu_head", None)
    lead_a, _ = person("lead.test", "Test Lead A", "engineer", "Electrical Lead")
    lead_b, _ = person("lead2.test", "Test Lead B", "engineer", "Mechanical Lead")
    lead_c, _ = person("lead3.test", "Test Lead C", "engineer", "BIM Lead")
    engineer, engineer_employee = person("eng.test", "Test Engineer", "engineer", "Electrical Engineer")
    bu_h, lead_h = headers("bu.test"), headers("lead.test")

    period = {
        "start_date": (today - timedelta(days=30)).isoformat(),
        "end_date": (today + timedelta(days=335)).isoformat(),
    }
    slots = {"electrical": lead_a, "mechanical": lead_b, "bim": lead_c}
    project = ok(
        client.post(
            "/api/projects",
            json={
                "project_name": "Manual test project",
                "project_code": MARKER_PROJECT_CODE,
                "client_customer": "Walk-through",
                **{f"project_lead_{slot}": user.full_name for slot, user in slots.items()},
                **{f"project_lead_{slot}_user_id": user.id for slot, user in slots.items()},
                **{f"project_lead_{slot}_{field}": value for slot in slots for field, value in period.items()},
                **{f"project_lead_{slot}_utilization_pct": 20 for slot in slots},
                "target_start_date": period["start_date"],
                "sharepoint_disciplines": [],
                "total_contract_value": 100000,
                "contract_currency": "USD",
                "target_effort_hours": 500,
                "alert_override_threshold_pct": 80,
            },
            headers=bu_h,
        ),
        201,
    )
    project_id = project["id"]
    ok(
        client.post(
            f"/api/projects/{project_id}/resource-bookings",
            json={"employee_id": engineer_employee.id, "utilization_rate": 50, **period},
            headers=lead_h,
        )
    )
    ok(client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=lead_h))
    ok(client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=bu_h))

    def node(code: str, name: str, parent=None, day: date | None = None):
        row = models.WbsNode(
            project_id=project_id,
            wbs_code=code,
            task_name=name,
            phase="Space Planning",
            parent_id=parent.id if parent else None,
            estimated_hours=8 if parent else 40,
            deliverable_status="In-Progress",
            assigned_lead=lead_a.full_name,
            assigned_lead_user_id=lead_a.id,
            assigned_engineer_id=engineer_employee.id,
            start_date=day or today - timedelta(days=10),
            target_due_date=day or today + timedelta(days=10),
        )
        db.add(row)
        db.commit()
        return row

    def at(day: date, hour: float) -> datetime:
        return datetime.combine(day, time.min, tzinfo=UTC) + timedelta(hours=hour)

    def worked_day(
        subtask, days_ago: int, start: float, end: float, last_visit: float | None = None, ended_by="engineer"
    ):
        """A closed session and the day's row it banked (hours in UTC: 04:00 is 09:30 in India)."""
        day = today - timedelta(days=days_ago)
        db.add(
            models.TimeSession(
                project_id=project_id,
                task_id=subtask.parent_id,
                subtask_id=subtask.id,
                employee_id=engineer_employee.id,
                login_at=at(day, start),
                last_seen_at=at(day, end),
                last_active_at=at(day, end if last_visit is None else last_visit),
                logout_at=at(day, end),
                active_seconds=int((end - start) * 3600),
                status="ended",
                ended_by=ended_by,
            )
        )
        entry = models.TimeLogEntry(
            project_id=project_id,
            task_id=subtask.id,
            employee_id=engineer_employee.id,
            work_date=day,
            hours=round(end - start, 2),
            approval_status="pending_review",
        )
        db.add(entry)
        db.commit()
        return entry

    def rejected(entry, days_ago: int, reason: str):
        entry.approval_status, entry.review_reason = "rejected", reason
        entry.reviewed_by, entry.reviewed_by_user_id = lead_a.full_name, lead_a.id
        entry.reviewed_at = now - timedelta(days=days_ago)
        db.commit()

    task = node("1.", "Electrical load estimate")
    running = node("1.1", "Running now: past 8 hours, last visit 50 minutes ago", task)
    unattended = node("1.2", "Unattended day: laptop left on", task)
    normal = node("1.3", "Normal day", task)
    overtime = node("1.4", "Overtime day: 9.5 hours", task)
    recent = node("1.5", "Rejected 6 days ago: one day left", task)
    final = node("1.6", "Rejected 8 days ago: final", task)
    node("1.7", "Free subtask: try Login and switching here", task, day=today)

    db.add(  # still open: opening the app as the engineer (or the 5-minute sweep) logs it out at the last visit
        models.TimeSession(
            project_id=project_id,
            task_id=task.id,
            subtask_id=running.id,
            employee_id=engineer_employee.id,
            login_at=now - timedelta(hours=9),
            last_seen_at=now - timedelta(minutes=45),
            last_active_at=now - timedelta(minutes=50),
            status="active",
        )
    )
    db.commit()
    worked_day(unattended, 2, start=4, end=12, last_visit=6, ended_by="laptop_off")  # 8 h, 6 of them unattended
    worked_day(normal, 3, start=4, end=10)  # 6 h
    worked_day(overtime, 4, start=4, end=13.5)  # 9.5 h
    rejected(worked_day(recent, 7, start=4, end=9), days_ago=6, reason="Idle time: no drawings issued that day")
    rejected(worked_day(final, 9, start=4, end=8), days_ago=8, reason="Not worked")
    db.close()
    engine.dispose()
    return {"project": project["project_name"], "accounts": [bu_head, lead_a, lead_b, lead_c, engineer]}


GUIDE = """
Scratch database written: {target}

Accounts (password for all: {password})
  bu.test     BU Head
  lead.test   Test Lead A: leads the project, assigned lead of the task, rejected the two days
  lead2.test  Test Lead B: another lead of the project (approves what Lead A rejected)
  lead3.test  Test Lead C: the third lead slot
  eng.test    Test Engineer

Start the backend on the scratch database (PowerShell, in backend\\):
  $env:DATABASE_URL = "sqlite:///{url_path}"
  .venv\\Scripts\\python.exe -m uvicorn main:app --port 8000
Close that window afterwards: DATABASE_URL is only set there, so the next start uses your normal database.
Start the frontend as usual (npm run dev in frontend\\).

What to look at
  1. eng.test: open WBS Structure, then subtask 1.1. You were logged out at your last visit (past 8 hours,
     more than 30 minutes away). Press Login again: the "Over 8 hours today" note shows.
  2. eng.test: with 1.1 running, open 1.7 and press Login: the switch dialog asks to log out of 1.1.
  3. lead.test: Timeline & Logs, this week and last week. "Approve all on my tasks" approves the normal day and
     leaves the overtime day (1.4) and the unattended day (1.2) for an individual look.
  4. lead.test: open the engineer's weekly log. 1.2 shows its session and "Approve up to last visit (2 h)".
  5. lead2.test: Timeline & Logs, Rejected hours panel. 1.5 has about 1 day left: approve it with a reason.
     1.6 is not listed: its rejection is 8 days old and final.
  6. lead.test: try to reject the hours Lead B just approved again: refused, only the BU Head decides now.
  7. bu.test: the dashboard's audit log shows "Rejected hours approved again" with both names.
"""


def main_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed a scratch database for the manual timesheet walk-through.")
    parser.add_argument("--database", help="path of the scratch .db file to create (never the development database)")
    parser.add_argument("--reset", action="store_true", help="rebuild a scratch file this script made earlier")
    args = parser.parse_args(argv)
    target = safe_target(args.database, args.reset, dev_database_paths(dict(os.environ), BACKEND_DIR / ".env"))
    seed(target)
    print(GUIDE.format(target=target, password=PASSWORD, url_path=target.as_posix()))


if __name__ == "__main__":
    sys.path.insert(0, str(BACKEND_DIR))
    main_cli()
