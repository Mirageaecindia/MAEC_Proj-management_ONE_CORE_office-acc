"""Shared fixtures for the BU Head characterization suite.

Isolation rules, applied before the app is imported:
- DATABASE_URL points at a throwaway SQLite file, so the real database is
  never touched. TEST_DATABASE_URL overrides it to run the suite against an
  empty, throwaway Postgres (every table is wiped before each test).
- Azure/SharePoint settings are blanked, so any code path that is not
  explicitly faked fails fast with a SharePointError instead of calling
  Microsoft Graph. (python-dotenv never overrides variables already set.)
- MAEC One Core is faked in-process (fakes.FakeCore): the gate's settings are
  throwaway values, and the gate's HTTP client talks to the fake. People sign
  in through it (`make.headers`), never through this app.
"""

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TMP_DIR = tempfile.mkdtemp(prefix="maec-tests-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{Path(_TMP_DIR, 'test.db').as_posix()}"
for _key in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "SHAREPOINT_SITE_ID", "SHAREPOINT_DRIVE_ID"):
    os.environ[_key] = ""
# Throwaway gate settings: the fake Core below is the only thing they reach.
GATE_SECRET = "test-gate-secret-" + "x" * 32
os.environ.update(
    {
        "CORE_URL": "http://core.test",
        "CORE_PUBLIC_URL": "http://auth.test",
        "MAEC_APP_KEY": "projects",
        "MAEC_GATE_SECRET": GATE_SECRET,
        "TRUSTED_PROXIES": "",
    }
)

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from app.api import gate
from app.core.database import Base, SessionLocal, engine
from app.integrations.sharepoint import get_document_storage
from factories import Factory
from fakes import FakeCore, FakeDocumentStorage

# Every lead holds 20% of their time on a project for a year (see test_lead_assignments.py).
LEAD_PERIOD = {"start_date": "2026-09-01", "end_date": "2027-08-31", "utilization_pct": 20}


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_db():
    """Every test starts from empty tables (this also drops the CSV seed)."""
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture(autouse=True)
def core():
    """A fresh MAEC One Core for every test, answering the gate's checks in-process."""
    fake = FakeCore(secret=GATE_SECRET, public_url=os.environ["CORE_PUBLIC_URL"])
    gate.transport = httpx.MockTransport(fake.handler)
    gate.reset_client()
    yield fake
    gate.transport = None
    gate.reset_client()


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def storage():
    """Replace SharePoint with an in-memory fake for the duration of a test."""
    fake = FakeDocumentStorage()
    main.app.dependency_overrides[get_document_storage] = lambda: fake
    yield fake
    main.app.dependency_overrides.pop(get_document_storage, None)


@pytest.fixture
def make(db, client, core):
    return Factory(db, client, core)


@pytest.fixture
def world(make, client):
    """Standard cast: a BU Head, three discipline leads, an unassigned lead,
    two employees and an engineer account linked to the first employee."""
    w = SimpleNamespace()
    w.bu = make.user("buhead", "bu_head", "Test BU Head")
    w.lead_e = make.lead("lead.e", "Anita Kumar", "Electrical")
    w.lead_m = make.lead("lead.m", "Priya Nair", "Mechanical")
    w.lead_b = make.lead("lead.b", "Mohan Daniel", "BIM")
    w.other_lead = make.lead("lead.x", "Unassigned Lead", "Electrical")
    w.emp1 = make.employee("Arjun Mehta", discipline="Mechanical Engineer")
    w.emp2 = make.employee("Ravi Kumar", discipline="Electrical Engineer")
    w.engineer = make.user("eng.arjun", "engineer", "Arjun Mehta", employee_id=w.emp1.id)

    w.bu_h = make.headers(w.bu)
    w.lead_h = make.headers(w.lead_e)
    w.other_lead_h = make.headers(w.other_lead)
    w.eng_h = make.headers(w.engineer)

    def project_payload(**overrides):
        n = make.next_seq()
        payload = {
            "project_name": f"Project {n}",
            "project_code": f"PRJ-{n:03d}",
            "client_customer": "Acme Developments",
            "project_lead_electrical": w.lead_e.full_name,
            "project_lead_mechanical": w.lead_m.full_name,
            "project_lead_bim": w.lead_b.full_name,
            "project_lead_electrical_user_id": w.lead_e.id,
            "project_lead_mechanical_user_id": w.lead_m.id,
            "project_lead_bim_user_id": w.lead_b.id,
            **{
                f"project_lead_{slot}_{field}": value
                for slot in ("electrical", "mechanical", "bim")
                for field, value in LEAD_PERIOD.items()
            },
            "target_start_date": "2026-09-01",
            "sharepoint_disciplines": [],
            "total_contract_value": 100000,
            "contract_currency": "USD",
            "target_effort_hours": 500,
            "alert_override_threshold_pct": 80,
        }
        payload.update(overrides)
        return payload

    def create_project(**overrides):
        response = client.post("/api/projects", json=project_payload(**overrides), headers=w.bu_h)
        assert response.status_code == 201, response.text
        return response.json()

    w.project_payload = project_payload
    w.create_project = create_project
    return w


@pytest.fixture
def governed(client, make, world):
    """Governance reference scenario: target 100h, threshold 80%, 50h logged (30 approved + 20 pending).

    Returns (project_id, node_a, node_b, pending_entry). Engineer `world.engineer` is booked (approved)."""
    project = world.create_project(
        total_contract_value=100000, alert_override_threshold_pct=80, target_effort_hours=100
    )
    project_id = project["id"]
    # The engineer must be booked and the booking APPROVED before they can log
    # hours (access is only granted by BU Head approval of the assignment).
    booking = client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={
            "employee_id": world.emp1.id,
            "planned_hours": 100,
            "utilization_rate": 50,
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
        },
        headers=world.lead_h,
    )
    assert booking.status_code == 200, booking.text
    assert client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=world.lead_h).status_code == 200
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200
    node_a = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, estimated_hours=40)
    node_b = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, estimated_hours=60)
    make.time_entry(project_id, node_a, world.emp1, 30, status="approved")
    pending = make.time_entry(project_id, node_b, world.emp1, 20, status="pending_review")
    return project_id, node_a, node_b, pending
