"""Governance workflow: threshold alerts, auto-lock at 100%, resume.

Rules (agreed with the BU Head owner):
- baseline = BU Head target effort hours + approved extension hours, per project;
- reaching the alert threshold notifies the BU Head and the project's Leads once;
- reaching 100% of the baseline locks timesheets automatically and notifies them;
- approving an extension raises the baseline and lifts an automatic or manual lock;
- the BU Head can also resume manually; the next logged hour does not re-lock.

Scenario (`governed`): target 100h, threshold 80%, 50h already logged.
"""

import pytest

import models
from app.domain.governance import (
    HARD_STOP,
    NORMAL,
    WARNING,
    governance_level,
    read_governance,
    split_monthly_consumption,
)

# --- Pure rules -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pct", "threshold", "expected"),
    [
        (0, 80, NORMAL),
        (79.9, 80, NORMAL),
        (80, 80, WARNING),
        (99.9, 80, WARNING),
        (100, 80, HARD_STOP),
        (150, None, HARD_STOP),
        (95, None, NORMAL),  # no alert threshold configured: only the hard stop applies
    ],
)
def test_governance_level_boundaries(pct, threshold, expected):
    assert governance_level(pct, threshold, baseline_hours=100) == expected


def test_no_baseline_means_no_governance():
    reading = read_governance(
        logged_hours=500, target_effort_hours=None, extension_approved_hours=None, threshold_pct=80
    )

    assert reading.configured is False
    assert reading.level == NORMAL
    assert reading.consumption_pct == 0


def test_reading_adds_approved_extensions_to_the_target():
    reading = read_governance(logged_hours=90, target_effort_hours=100, extension_approved_hours=50, threshold_pct=80)

    assert reading.baseline_hours == 150
    assert reading.consumption_pct == 60.0
    assert reading.level == NORMAL


def test_monthly_split_uses_cumulative_hours():
    split = split_monthly_consumption({"2026-08": 50, "2026-09": 50, "2026-10": 20}, alert_hours=80)

    assert split == {"2026-08": (50, 0), "2026-09": (30, 20), "2026-10": (0, 20)}


# --- Workflow through the API ---------------------------------------------------------------


def _log(client, world, node, week, **days):
    return client.post(
        f"/api/projects/{node.project_id}/timesheet-entries",
        json={"task_id": node.id, "week_start_date": week, **days},
        headers=world.eng_h,
    )


def _notifications(client, headers, project_id, kind):
    response = client.get("/api/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return [n for n in response.json() if n["project_id"] == project_id and n["notification_type"] == kind]


def _project(db, project_id):
    db.expire_all()
    return db.get(models.Project, project_id)


def test_reaching_the_threshold_alerts_bu_head_and_project_leads_once(client, db, world, governed):
    project_id, node_a, *_ = governed

    assert _log(client, world, node_a, "2026-09-14", mon_hours=10, tue_hours=10, wed_hours=10).status_code == 200

    assert _project(db, project_id).governance_alert_level == WARNING
    assert _project(db, project_id).timesheets_soft_locked is False
    assert len(_notifications(client, world.bu_h, project_id, "threshold_warning")) == 1
    assert len(_notifications(client, world.lead_h, project_id, "threshold_warning")) == 1
    assert _notifications(client, world.other_lead_h, project_id, "threshold_warning") == []

    # Still in the warning band: no repeat alert.
    assert _log(client, world, node_a, "2026-09-21", mon_hours=5).status_code == 200
    assert len(_notifications(client, world.bu_h, project_id, "threshold_warning")) == 1


def test_reaching_the_baseline_locks_timesheets_automatically(client, db, world, governed):
    project_id, node_a, *_ = governed

    logged = _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=10)

    assert logged.status_code == 200  # the entry that crosses 100% is kept
    project = _project(db, project_id)
    assert project.timesheets_soft_locked is True
    assert project.lock_reason == "auto"
    assert project.governance_alert_level == HARD_STOP
    assert len(_notifications(client, world.bu_h, project_id, "execution_locked")) == 1
    assert len(_notifications(client, world.lead_h, project_id, "execution_locked")) == 1
    audit = db.query(models.GovernanceAction).filter_by(project_id=project_id, action="auto_lock").one()
    assert audit.created_by == "System"
    assert audit.consumption_pct == 100.0

    blocked = _log(client, world, node_a, "2026-09-21", mon_hours=1)
    assert blocked.status_code == 409
    dashboard = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.bu_h).json()
    assert dashboard["governance_status"]["level"] == HARD_STOP
    assert dashboard["governance_status"]["soft_locked"] is True
    assert dashboard["governance_status"]["lock_reason"] == "auto"


def test_subtask_tracking_cannot_start_while_locked(client, db, make, world, governed):
    project_id, node_a, *_ = governed
    subtask = make.wbs_node(project_id, world.lead_e, engineer=world.emp1, parent_id=node_a.id, estimated_hours=5)
    project = _project(db, project_id)
    project.timesheets_soft_locked = True
    db.commit()

    response = client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=world.eng_h)

    assert response.status_code == 409
    assert "soft-locked" in response.json()["detail"]


def test_approved_extension_lifts_the_automatic_lock(client, db, world, governed):
    project_id, node_a, *_ = governed
    _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=10)
    assert _project(db, project_id).timesheets_soft_locked is True
    request = client.post(
        f"/api/projects/{project_id}/extension-requests",
        json={"requested_hours": 50, "justification": "Client added a floor"},
        headers=world.lead_h,
    )
    assert request.status_code == 201
    assert len(_notifications(client, world.bu_h, project_id, "extension_requested")) == 1

    decided = client.post(
        f"/api/projects/{project_id}/extension-requests/{request.json()['id']}/decision",
        json={"decision": "approve", "comments": "Agreed with client"},
        headers=world.bu_h,
    )

    assert decided.status_code == 200
    project = _project(db, project_id)
    assert project.timesheets_soft_locked is False
    assert project.lock_reason is None
    assert project.governance_alert_level == NORMAL  # 100 of 150 baseline hours = 66.7%
    assert len(_notifications(client, world.lead_h, project_id, "extension_decided")) == 1
    assert len(_notifications(client, world.lead_h, project_id, "execution_resumed")) == 1
    actions = [a.action for a in db.query(models.GovernanceAction).filter_by(project_id=project_id)]
    assert "resume_execution" in actions
    assert _log(client, world, node_a, "2026-09-21", mon_hours=2).status_code == 200


def test_rejected_extension_keeps_the_lock(client, db, world, governed):
    project_id, node_a, *_ = governed
    _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=10)
    request_id = client.post(
        f"/api/projects/{project_id}/extension-requests", json={"requested_hours": 50}, headers=world.lead_h
    ).json()["id"]

    client.post(
        f"/api/projects/{project_id}/extension-requests/{request_id}/decision",
        json={"decision": "reject"},
        headers=world.bu_h,
    )

    assert _project(db, project_id).timesheets_soft_locked is True


def test_manual_resume_over_the_baseline_is_not_relocked_by_the_next_entry(client, db, world, governed):
    project_id, node_a, *_ = governed
    _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=10)

    resumed = client.post(
        f"/api/projects/{project_id}/governance/resume-execution",
        json={"comments": "Finish the issue for construction"},
        headers=world.bu_h,
    )

    assert resumed.status_code == 200
    assert _log(client, world, node_a, "2026-09-21", mon_hours=4).status_code == 200
    project = _project(db, project_id)
    assert project.timesheets_soft_locked is False
    assert project.governance_alert_level == HARD_STOP
    assert len(_notifications(client, world.bu_h, project_id, "execution_locked")) == 1


def test_manual_stop_notifies_project_leads(client, world, governed):
    project_id, *_ = governed

    client.post(f"/api/projects/{project_id}/governance/stop-execution", json={"comments": "Audit"}, headers=world.bu_h)

    assert len(_notifications(client, world.lead_h, project_id, "execution_locked")) == 1
    assert _notifications(client, world.other_lead_h, project_id, "execution_locked") == []


def test_dropping_back_into_the_warning_band_does_not_alert_again(client, db, world, governed):
    project_id, node_a, *_ = governed
    _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=10)
    request_id = client.post(
        f"/api/projects/{project_id}/extension-requests", json={"requested_hours": 20}, headers=world.lead_h
    ).json()["id"]

    client.post(
        f"/api/projects/{project_id}/extension-requests/{request_id}/decision",
        json={"decision": "approve"},
        headers=world.bu_h,
    )

    project = _project(db, project_id)
    assert project.governance_alert_level == WARNING  # 100 of 120 baseline hours
    assert project.timesheets_soft_locked is False
    assert _notifications(client, world.bu_h, project_id, "threshold_warning") == []
