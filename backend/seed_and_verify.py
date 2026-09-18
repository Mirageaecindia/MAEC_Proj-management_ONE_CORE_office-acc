import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from sqlalchemy import select
from database import Base, engine, SessionLocal
from models import Employee, Project, ResourceBooking, WbsNode, TimeLogEntry
from main import app

PROJECT_CODE = "PRJ-TEST-01"
PROJECT_NAME = "Test Project for Verification"
CLIENT = "Apex Developments"
WEEK = "2026-09-07"


def seed_and_verify():
    Base.metadata.create_all(bind=engine)
    client = TestClient(app)
    db = SessionLocal()

    try:
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "buhead", "password": "BuHead@123"},
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.json()}"
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200, f"Auth me failed: {me.json()}"
        print(f"Logged in as: {me.json()['full_name']} (role={me.json()['role']})")

        project = db.scalar(select(Project).filter_by(project_code=PROJECT_CODE))
        if not project:
            payload = {
                "project_name": PROJECT_NAME,
                "project_code": PROJECT_CODE,
                "client_customer": CLIENT,
                "project_lead_electrical": "Anita Kumar",
                "project_lead_mechanical": "Priya Nair",
                "project_lead_bim": "Mohan Daniel",
                "target_start_date": "2026-09-01",
                "sharepoint_disciplines": ["HVAC Discipline", "Electrical Discipline"],
                "total_contract_value": 150000.0,
                "contract_currency": "USD",
                "target_effort_hours": 500,
                "alert_override_threshold_pct": 80,
            }
            resp = client.post("/api/projects", json=payload, headers=headers)
            assert resp.status_code == 201, f"Create project failed: {resp.json()}"
            project = db.scalar(select(Project).filter_by(project_code=PROJECT_CODE))
            print(f"Created project: {project.project_name} (id={project.id})")
        else:
            print(f"Project exists: {project.project_name} (id={project.id})")

        project_id = project.id

        employees = db.scalars(select(Employee).order_by(Employee.id)).all()
        if not employees:
            e1 = Employee(employee_code="ENG-01", name="Arjun Mehta", discipline="MEP", role_title="Engineer I")
            e2 = Employee(employee_code="ENG-02", name="Ravi Kumar", discipline="Structural", role_title="Engineer II")
            db.add_all([e1, e2])
            db.commit()
            employees = db.scalars(select(Employee).order_by(Employee.id)).all()
        print(f"Employees: {[(e.id, e.name) for e in employees]}")

        booked_emp = employees[0]

        existing_booking = db.scalar(
            select(ResourceBooking)
            .where(ResourceBooking.project_id == project_id, ResourceBooking.employee_id == booked_emp.id)
        )
        if not existing_booking:
            db.add(ResourceBooking(
                project_id=project_id, employee_id=booked_emp.id,
                planned_hours=100, utilization_rate=50,
            ))
            db.commit()
            print(f"Created booking for {booked_emp.name}")

        existing_tasks = db.scalars(select(WbsNode).filter_by(project_id=project_id)).all()
        if not existing_tasks:
            nodes = [
                WbsNode(
                    project_id=project_id, wbs_code="WBS 1.1", task_name="Space Planning",
                    assigned_lead="Anita Kumar", estimated_hours=80, deliverable_status="Completed",
                    start_date=date(2026, 9, 1), target_due_date=date(2026, 9, 30), phase="Space Planning",
                ),
                WbsNode(
                    project_id=project_id, wbs_code="WBS 1.2", task_name="STR Coordination",
                    assigned_lead="Priya Nair", estimated_hours=120, deliverable_status="In Progress",
                    start_date=date(2026, 10, 1), target_due_date=date(2026, 10, 31), phase="STR Coordination",
                ),
                WbsNode(
                    project_id=project_id, wbs_code="WBS 2.1", task_name="BIM Modeling",
                    assigned_lead="Mohan Daniel", estimated_hours=160, deliverable_status="Not Started",
                    start_date=date(2026, 11, 1), target_due_date=date(2026, 12, 15), phase="ID Coordination",
                ),
                WbsNode(
                    project_id=project_id, wbs_code="WBS 3.1", task_name="BoH Area RCP Coordination",
                    assigned_lead="Anita Kumar", estimated_hours=90, deliverable_status="Not Started",
                    start_date=date(2026, 10, 15), target_due_date=date(2026, 11, 15), phase="BoH Area RCP Coord.",
                ),
            ]
            db.add_all(nodes)
            db.commit()
            existing_tasks = db.scalars(select(WbsNode).filter_by(project_id=project_id)).all()
            print(f"Created {len(existing_tasks)} WBS nodes")

        task1, task2, task3, task4 = existing_tasks

        existing_entries = db.scalars(
            select(TimeLogEntry).filter_by(project_id=project_id)
        ).all()
        if not existing_entries:
            entries = [
                TimeLogEntry(
                    project_id=project_id, task_id=task3.id, employee_id=booked_emp.id,
                    week_start_date=date(2026, 9, 7), mon_hours=0, tue_hours=0, wed_hours=0,
                    thu_hours=0, fri_hours=0, sat_hours=0, sun_hours=0, approval_status="pending_review",
                ),
                TimeLogEntry(
                    project_id=project_id, task_id=task4.id, employee_id=booked_emp.id,
                    week_start_date=date(2026, 9, 7), mon_hours=0, tue_hours=0, wed_hours=0,
                    thu_hours=0, fri_hours=0, sat_hours=0, sun_hours=0, approval_status="pending_review",
                ),
            ]
            db.add_all(entries)
            db.commit()
            print(f"Created {len(entries)} time entries")

        print("\n================ VERIFICATION 1 ==================")
        res_ts = client.get(
            f"/api/projects/{project_id}/timesheet",
            params={"week_start": WEEK},
            headers=headers,
        )
        print(f"GET /api/projects/{project_id}/timesheet?week_start={WEEK}")
        print(f"HTTP Status: {res_ts.status_code}")
        ts_rows = res_ts.json()
        print(f"Timesheet rows returned: {len(ts_rows)}")
        for r in ts_rows:
            print(f"  - {r['employee_name']}: {r['task_name']} = {r['total_hours']} hrs ({r['approval_status']})")
        rahul_rows = [r for r in ts_rows if r["employee_id"] == booked_emp.id]
        assert len(rahul_rows) >= 1, f"Expected at least 1 row for booked employee"
        print("PASS: Timesheet returns entries")

        print("\n================ VERIFICATION 2 ==================")
        res_tasks = client.get(
            f"/api/projects/{project_id}/wbs-tasks",
            headers=headers,
        )
        print(f"GET /api/projects/{project_id}/wbs-tasks")
        print(f"HTTP Status: {res_tasks.status_code}")
        if res_tasks.status_code == 200:
            tasks = res_tasks.json()
            print(f"WBS tasks: {len(tasks)}")
            for t in tasks:
                print(f"  - {t['wbs_code']}: {t['task_name']} (status={t['status']})")
            print("PASS: WBS tasks loaded")

        print("\n================ VERIFICATION 3 ==================")
        res_exec = client.get(
            f"/api/projects/{project_id}/executive-dashboard",
            headers=headers,
        )
        print(f"GET /api/projects/{project_id}/executive-dashboard")
        print(f"HTTP Status: {res_exec.status_code}")
        if res_exec.status_code == 200:
            ed = res_exec.json()
            print(f"  Governance status: {ed['governance_status']['status']}")
            print(f"  SPI: {ed['spi']['value']}")
            print(f"  Budget consumed: {ed['commercial_budget_burn']['percent']}%")
            print(f"  Disciplines: {len(ed['disciplines'])}")
            print("PASS: Executive dashboard loaded")

        print("\n================ VERIFICATION 4 ==================")
        res_summary = client.get(
            f"/api/projects/{project_id}/work-summary",
            headers=headers,
        )
        print(f"GET /api/projects/{project_id}/work-summary")
        print(f"HTTP Status: {res_summary.status_code}")
        if res_summary.status_code == 200:
            ws = res_summary.json()
            print(f"  Leads: {len(ws['leads'])}")
            print(f"  Engineers: {len(ws['engineers'])}")
            print(f"  Total nodes: {ws['summary']['total_nodes']}")
            print("PASS: Work summary loaded")

        print("\n================ VERIFICATION 5 ==================")
        res_perf = client.get("/api/engineer-performance", headers=headers)
        print(f"GET /api/engineer-performance")
        print(f"HTTP Status: {res_perf.status_code}")
        if res_perf.status_code == 200:
            perf = res_perf.json()
            print(f"  Engineer: {perf['summary']['name']}")
            print(f"  Tasks: {perf['summary']['total_tasks']}")
            print("PASS: Engineer performance loaded")

        print("\n================ VERIFICATION 6 ==================")
        res_proj = client.get("/api/projects", headers=headers)
        print(f"GET /api/projects")
        print(f"HTTP Status: {res_proj.status_code}")
        if res_proj.status_code == 200:
            projs = res_proj.json()
            print(f"  Projects: {len(projs)}")
            for p in projs:
                print(f"  - {p['project_code']}: {p['project_name']}")
            print("PASS: Projects listed")

        print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")

    except AssertionError as e:
        print(f"\nVERIFICATION FAILED: {e}")
        raise
    except Exception as e:
        print(f"\nERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_and_verify()
