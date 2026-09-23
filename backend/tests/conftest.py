"""Shared fixtures for the BU Head characterization suite.

Isolation rules, applied before the app is imported:
- DATABASE_URL points at a throwaway SQLite file, so the real database is
  never touched.
- Azure/SharePoint settings are blanked, so any code path that is not
  explicitly faked fails fast with a SharePointError instead of calling
  Microsoft Graph. (python-dotenv never overrides variables already set.)
"""

import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TMP_DIR = tempfile.mkdtemp(prefix="maec-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP_DIR, 'test.db').as_posix()}"
for _key in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "SHAREPOINT_SITE_ID", "SHAREPOINT_DRIVE_ID"):
    os.environ[_key] = ""

import pytest
from fastapi.testclient import TestClient

import main
from app.core import security
from app.core.database import Base, SessionLocal, engine
from app.integrations.sharepoint import get_document_storage
from fakes import FakeDocumentStorage

# PBKDF2 is intentionally slow (100k rounds). Tests log in hundreds of times,
# so use a cheap cost here; hashing and verification still go through the
# real code path. Must be set before factories computes its shared hash.
security.PBKDF2_ITERATIONS = 1_000

from factories import Factory


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_db():
    """Every test starts from empty tables (this also drops the CSV seed)."""
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


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
def make(db, client):
    return Factory(db, client)


@pytest.fixture
def world(make, client):
    """Standard cast: a BU Head, three discipline leads, an unassigned lead,
    two employees and an engineer account linked to the first employee."""
    w = SimpleNamespace()
    w.bu = make.user("buhead", "bu_head", "Test BU Head")
    w.lead_e = make.user("lead.e", "lead", "Anita Kumar", discipline="Electrical")
    w.lead_m = make.user("lead.m", "lead", "Priya Nair", discipline="Mechanical")
    w.lead_b = make.user("lead.b", "lead", "Mohan Daniel", discipline="BIM")
    w.other_lead = make.user("lead.x", "lead", "Unassigned Lead", discipline="Electrical")
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
