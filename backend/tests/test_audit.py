"""The audit log (app/services/audit.py, app/api/middleware.py).

Every change request is one entry; each person reads their own, the BU Head everyone's;
passwords are never stored; entries older than the retention window are deleted.
"""

from datetime import UTC, datetime, timedelta

import main
import models
from app.domain.audit import CATALOG, FAILED_SIGN_IN, NOT_AUDITED
from app.services.audit import purge_old
from tests.factories import PASSWORD

MINE, EVERYONE = "/api/audit/mine", "/api/audit"
CHANGES = ("post", "put", "patch", "delete")


def _summaries(client, headers, url=MINE, **params):
    return [e["summary"] for e in client.get(url, params=params, headers=headers).json()["events"]]


def test_every_change_endpoint_is_in_the_log_or_deliberately_not():
    paths = main.app.openapi()["paths"]
    endpoints = {(method.upper(), path) for path, ops in paths.items() for method in ops if method in CHANGES}

    missing = endpoints - set(CATALOG) - NOT_AUDITED
    assert not missing, f"Add these to app/domain/audit.CATALOG (or NOT_AUDITED): {sorted(missing)}"


def test_sign_ins_are_logged_and_a_failed_one_too(client, world):
    client.post("/api/auth/login", json={"username": world.engineer.username, "password": "wrong"})

    mine = _summaries(client, world.eng_h)

    assert mine[0] == FAILED_SIGN_IN
    assert "Signed in" in mine


def test_a_password_is_never_written_to_the_log(client, db, world):
    new = "N3w-password-123"
    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": new},
        headers=world.eng_h,
    )
    assert response.status_code == 200, response.text

    rows = db.query(models.AuditEvent).all()
    assert "Changed their password" in [r.summary for r in rows]
    assert not any(PASSWORD in (r.summary or "") or new in (r.summary or "") for r in rows)


def test_work_is_described_in_words_with_its_project(client, make, world, governed):
    project_id, node_a, *_ = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, wbs_code="9.1")
    subtask_name = f"9.1 {subtask.task_name}"

    client.post(f"/api/wbs-nodes/{subtask.id}/advance-status", json={"new_status": "In-Progress"}, headers=world.eng_h)
    client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h)
    client.post("/api/subtask-tracking/heartbeat", headers=world.eng_h)
    client.post("/api/subtask-tracking/logout", headers=world.eng_h)

    events = client.get(MINE, headers=world.eng_h).json()["events"]
    summaries = [e["summary"] for e in events]
    assert summaries[:3] == [
        f"Logged out of {subtask_name}",
        f"Logged in to {subtask_name}",
        f"Changed the status of {subtask_name} (to In-Progress)",
    ]  # the heartbeat is not an action
    assert {e["project_id"] for e in events[:3]} == {project_id}


def test_reviewing_hours_names_the_engineer_and_the_day(client, make, world, governed):
    project_id, node_a, _, pending = governed

    response = client.post(
        f"/api/time-log-entries/{pending.id}/reject", json={"reason": "Wrong subtask"}, headers=world.lead_h
    )
    assert response.status_code == 200, response.text

    latest = _summaries(client, world.lead_h)[0]
    assert latest.startswith(f"Rejected the hours of Arjun Mehta on {pending.work_date.isoformat()}")
    assert latest.endswith("(reason: Wrong subtask)")


def test_each_person_sees_only_their_own_and_only_the_bu_head_sees_everyone(client, world, governed):
    project_id, *_ = governed

    engineer = client.get(MINE, headers=world.eng_h).json()["events"]
    assert {e["user_id"] for e in engineer} == {world.engineer.id}
    assert client.get(EVERYONE, headers=world.lead_h).status_code == 403
    assert client.get(EVERYONE, headers=world.eng_h).status_code == 403
    assert client.get("/api/audit/export", headers=world.lead_h).status_code == 403

    everyone = client.get(EVERYONE, headers=world.bu_h).json()
    assert {world.bu.id, world.lead_e.id, world.engineer.id} <= {e["user_id"] for e in everyone["events"]}
    just_the_lead = client.get(EVERYONE, params={"user_id": world.lead_e.id}, headers=world.bu_h).json()
    assert {e["user_id"] for e in just_the_lead["events"]} == {world.lead_e.id}
    projects = client.get(EVERYONE, params={"category": "project"}, headers=world.bu_h).json()["events"]
    assert projects and all(e["category"] == "project" for e in projects)

    csv = client.get("/api/audit/export", params={"user_id": world.lead_e.id}, headers=world.bu_h)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0] == "When (UTC),Person,Role,Category,Action,Project"


def test_entries_past_the_retention_window_are_deleted(db, world):
    now = datetime.now(UTC)
    for age_days in (31, 29):
        db.add(
            models.AuditEvent(
                at=now - timedelta(days=age_days),
                user_id=world.engineer.id,
                user_name="Arjun Mehta",
                user_role="engineer",
                category="account",
                action="test",
                summary=f"{age_days} days ago",
            )
        )
    db.commit()

    assert purge_old(db, now, days=30) >= 1

    left = {e.summary for e in db.query(models.AuditEvent)}
    assert "29 days ago" in left and "31 days ago" not in left
