"""Archiving a project (TODO C1).

Archived = read-only for everyone, hidden from Leads and Engineers, out of the
allocation cap and governance; the BU Head keeps its history behind a filter.
Unarchiving restores the project exactly as it was, lock included.
"""

from datetime import UTC, date, datetime, timedelta

import models
from app.repositories.work import WorkRepository
from app.services.archive_guard import ARCHIVED_READ_ONLY
from app.services.governance_monitor import GovernanceMonitor


def _archive(client, headers, project_id, comments="Handed over"):
    return client.post(f"/api/projects/{project_id}/archive", json={"comments": comments}, headers=headers)


def _unarchive(client, headers, project_id):
    return client.post(f"/api/projects/{project_id}/unarchive", json={}, headers=headers)


def _project_ids(client, headers, **params):
    response = client.get("/api/projects", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return {project["id"] for project in response.json()}


def test_only_the_bu_head_archives_and_each_step_happens_once(client, world, governed):
    project_id, *_ = governed

    assert _archive(client, world.lead_h, project_id).status_code == 403
    archived = _archive(client, world.bu_h, project_id)
    assert archived.status_code == 200, archived.text
    assert archived.json()["archived_at"] is not None
    assert _archive(client, world.bu_h, project_id).status_code == 409
    assert _unarchive(client, world.bu_h, project_id).json()["archived_at"] is None
    assert _unarchive(client, world.bu_h, project_id).status_code == 409


def test_archive_ends_tracking_cancels_the_pending_extension_and_is_audited(client, db, make, world, governed):
    project_id, node_a, *_ = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    session_id = client.post(
        "/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h
    ).json()["id"]
    session = db.get(models.TimeSession, session_id)
    session.login_at = datetime.now(UTC) - timedelta(minutes=30)
    db.commit()
    client.post(f"/api/subtask-tracking/{session_id}/sync", json={"active_seconds": 1800}, headers=world.eng_h)
    request_id = client.post(
        f"/api/projects/{project_id}/extension-requests", json={"requested_hours": 20}, headers=world.lead_h
    ).json()["id"]

    assert _archive(client, world.bu_h, project_id).status_code == 200

    db.expire_all()
    session = db.get(models.TimeSession, session_id)
    assert session.status == "ended"
    banked = db.query(models.TimeLogEntry).filter_by(task_id=subtask.id).one()
    assert sum(getattr(banked, field) for field in models.DAY_FIELDS) == 0.5  # 30 minutes kept
    assert db.get(models.ExtensionRequest, request_id).status == "cancelled"
    assert db.get(models.Project, project_id).extension_status == "cancelled"
    audit = db.query(models.GovernanceAction).filter_by(project_id=project_id, action="archive").one()
    assert (audit.created_by, audit.comments) == ("Test BU Head", "Handed over")
    kinds = {n.notification_type for n in db.query(models.Notification).filter_by(recipient_user_id=world.lead_e.id)}
    assert "project_archived" in kinds


def test_archived_project_is_read_only_for_everyone(client, db, make, world, governed):
    project_id, node_a, _, pending_entry = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=4)
    _archive(client, world.bu_h, project_id)

    # Leads and Engineers lose access to the project altogether.
    log = client.post(
        f"/api/projects/{project_id}/timesheet-entries",
        json={"task_id": node_a.id, "week_start_date": "2026-09-21", "mon_hours": 2},
        headers=world.eng_h,
    )
    assert log.status_code == 403
    wbs = client.post(
        f"/api/projects/{project_id}/wbs-nodes",
        json={"task_name": "New", "phase": "Space Planning"},
        headers=world.lead_h,
    )
    assert wbs.status_code == 403
    # Paths scoped by node or session instead of project access hit the read-only guard.
    approve = client.post(f"/api/time-log-entries/{pending_entry.id}/approve", headers=world.lead_h)
    assert (approve.status_code, approve.json()["detail"]) == (409, ARCHIVED_READ_ONLY)
    tracking = client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h)
    assert tracking.status_code == 409
    # The BU Head can't act on it either (unarchive first).
    stop = client.post(
        f"/api/projects/{project_id}/governance/stop-execution", json={"comments": "x"}, headers=world.bu_h
    )
    assert (stop.status_code, stop.json()["detail"]) == (409, ARCHIVED_READ_ONLY)
    assert client.delete(f"/api/projects/{project_id}", headers=world.bu_h).status_code == 409
    db.expire_all()
    assert db.get(models.TimeLogEntry, pending_entry.id).approval_status == "pending_review"
    assert db.query(models.TimeSession).filter_by(project_id=project_id).count() == 0


def test_archived_project_is_hidden_except_for_the_bu_head_on_request(client, world, governed):
    project_id, *_ = governed
    _archive(client, world.bu_h, project_id)

    assert project_id not in _project_ids(client, world.eng_h)
    assert project_id not in _project_ids(client, world.lead_h, include_archived="true")
    assert project_id not in _project_ids(client, world.bu_h)
    assert project_id in _project_ids(client, world.bu_h, include_archived="true")
    dashboard = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.bu_h)
    assert dashboard.status_code == 200
    assert dashboard.json()["project"]["archived_at"] is not None
    assert client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.lead_h).status_code == 403


def test_archived_project_frees_the_allocation_cap(client, world, governed):
    project_id, *_ = governed  # Arjun is booked at 50% there
    other_id = world.create_project()["id"]
    booking = {
        "employee_id": world.emp1.id,
        "planned_hours": 40,
        "utilization_rate": 60,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
    }
    url = f"/api/projects/{other_id}/resource-bookings"

    assert client.post(url, json=booking, headers=world.lead_h).status_code == 400  # 50% + 60% > 100%
    _archive(client, world.bu_h, project_id)
    assert client.post(url, json=booking, headers=world.lead_h).status_code == 200


def test_unarchive_restores_the_lock(client, db, world, governed):
    project_id, *_ = governed
    client.post(f"/api/projects/{project_id}/governance/stop-execution", json={"comments": "Audit"}, headers=world.bu_h)

    _archive(client, world.bu_h, project_id)
    _unarchive(client, world.bu_h, project_id)

    db.expire_all()
    project = db.get(models.Project, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (True, "manual")
    assert project_id in _project_ids(client, world.lead_h)
    actions = [a.action for a in db.query(models.GovernanceAction).filter_by(project_id=project_id)]
    assert actions[-2:] == ["archive", "unarchive"]


def test_governance_skips_archived_projects(client, db, make, world, governed):
    project_id, node_a, *_ = governed
    make.time_entry(project_id, node_a, world.emp1, 90, status="approved", week=date(2026, 9, 14))  # 120 of 100
    _archive(client, world.bu_h, project_id)

    db.expire_all()
    project = db.get(models.Project, project_id)
    GovernanceMonitor(db, WorkRepository(db)).evaluate(project)

    assert project.timesheets_soft_locked is False
    assert project.governance_alert_level is None


def test_archived_project_leaves_engineer_dashboards_and_lead_gantt(client, world, governed):
    project_id, *_ = governed

    def dashboard_projects():
        response = client.get("/api/engineer-performance-dashboard", headers=world.eng_h)
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()["projects"]}

    def gantt_projects():
        response = client.get("/api/resource-bookings/gantt", headers=world.lead_h)
        assert response.status_code == 200, response.text
        return {a["project_id"] for engineer in response.json()["engineers"] for a in engineer["assignments"]}

    assert project_id in dashboard_projects() and project_id in gantt_projects()
    _archive(client, world.bu_h, project_id)
    assert project_id not in dashboard_projects()
    assert project_id not in gantt_projects()
