"""The audit log (app/services/audit.py, app/api/middleware.py).

Every change request is one entry, naming the person MAEC One vouched for; each person reads
their own, the BU Head everyone's; entries older than the retention window are deleted.
"""

from datetime import UTC, datetime, timedelta

import main
import models
from app.domain.audit import CATALOG, NOT_AUDITED
from app.services.audit import purge_old

MINE, EVERYONE = "/api/audit/mine", "/api/audit"
CHANGES = ("post", "put", "patch", "delete")


def _summaries(client, headers, url=MINE, **params):
    return [e["summary"] for e in client.get(url, params=params, headers=headers).json()["events"]]


def test_every_change_endpoint_is_in_the_log_or_deliberately_not():
    paths = main.app.openapi()["paths"]
    endpoints = {(method.upper(), path) for path, ops in paths.items() for method in ops if method in CHANGES}

    missing = endpoints - set(CATALOG) - NOT_AUDITED
    assert not missing, f"Add these to app/domain/audit.CATALOG (or NOT_AUDITED): {sorted(missing)}"


def test_the_actor_is_the_person_maec_one_vouched_for(client, db, world):
    """The gate's identity, mapped to the users row (app/core/identity.py), is who the entry
    names, even on the person's very first request, the one that links their profile."""
    assert world.bu.core_user_id is None  # not linked yet: this is their first request

    response = client.post("/api/projects", json=world.project_payload(), headers=world.bu_h)

    assert response.status_code == 201, response.text
    rows = db.query(models.AuditEvent).all()
    assert [(row.user_id, row.user_name, row.user_role, row.category) for row in rows] == [
        (world.bu.id, "Test BU Head", "bu_head", "project")
    ]
    db.refresh(world.bu)
    assert world.bu.core_user_id == f"core-user-{world.bu.id}"


def test_a_request_from_someone_without_a_profile_is_refused_and_not_logged(client, db, core):
    stranger = core.headers(core.sign_in("new.joiner@mirageaec.com", "New Joiner"))

    response = client.post("/api/projects", json={}, headers=stranger)

    assert response.status_code == 403 and response.headers["X-Error-Code"] == "PROFILE_NOT_SET_UP"
    assert db.query(models.AuditEvent).count() == 0


def test_work_is_described_in_words_with_its_project(client, make, world, governed):
    project_id, node_a, *_ = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, wbs_code="9.1")
    subtask_name = f"9.1 {subtask.task_name}"

    client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h)  # starts it too
    client.post("/api/subtask-tracking/heartbeat", headers=world.eng_h)
    client.post("/api/subtask-tracking/logout", headers=world.eng_h)
    client.post(f"/api/wbs-nodes/{subtask.id}/advance-status", json={"new_status": "Done"}, headers=world.eng_h)

    events = client.get(MINE, headers=world.eng_h).json()["events"]
    summaries = [e["summary"] for e in events]
    assert summaries[:3] == [
        f"Changed the status of {subtask_name} (to Done)",
        f"Logged out of {subtask_name}",
        f"Logged in to {subtask_name}",
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
    project_id, node_a, *_ = governed
    comment = {"comment": "Started the riser layout"}
    assert client.post(f"/api/wbs-nodes/{node_a.id}/comments", json=comment, headers=world.eng_h).status_code == 200

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
