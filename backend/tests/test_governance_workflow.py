"""Governance workflow: threshold alerts, auto-lock at 100%, resume.

Rules (agreed with the BU Head owner):
- baseline = BU Head target effort hours + approved extension hours, per project;
- usage counts APPROVED hours only (a row approved by the Lead, or a row in a
  week the Lead approved); pending and rejected hours never count;
- reaching the alert threshold notifies the BU Head and the project's Leads once;
- reaching 100% of the baseline locks timesheets automatically and notifies them;
- approving an extension raises the baseline and lifts an automatic or manual lock;
- the BU Head can also resume manually; the next approval does not re-lock.

Scenario (`governed`): target 100h, threshold 80%, 30h approved + 20h pending.
"""

from datetime import date

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
from app.domain.timesheets import APPROVED, PENDING_REVIEW, REJECTED, effective_status
from app.repositories.work import WorkRepository

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
        approved_hours=500, target_effort_hours=None, extension_approved_hours=None, threshold_pct=80
    )

    assert reading.configured is False
    assert reading.level == NORMAL
    assert reading.consumption_pct == 0


def test_reading_adds_approved_extensions_to_the_target():
    reading = read_governance(approved_hours=90, target_effort_hours=100, extension_approved_hours=50, threshold_pct=80)

    assert reading.baseline_hours == 150
    assert reading.consumption_pct == 60.0
    assert reading.level == NORMAL


def test_monthly_split_uses_cumulative_hours():
    split = split_monthly_consumption({"2026-08": 50, "2026-09": 50, "2026-10": 20}, alert_hours=80)

    assert split == {"2026-08": (50, 0), "2026-09": (30, 20), "2026-10": (0, 20)}


@pytest.mark.parametrize(
    ("entry_status", "week_status", "expected"),
    [
        (PENDING_REVIEW, None, PENDING_REVIEW),
        (PENDING_REVIEW, "submitted", PENDING_REVIEW),
        (PENDING_REVIEW, APPROVED, APPROVED),  # the Lead approved the whole week
        (PENDING_REVIEW, REJECTED, REJECTED),
        (APPROVED, REJECTED, APPROVED),  # a row approval wins
        (REJECTED, None, REJECTED),
        (None, None, PENDING_REVIEW),
    ],
)
def test_effective_status_combines_row_and_week_approval(entry_status, week_status, expected):
    assert effective_status(entry_status, week_status) == expected


# --- Workflow through the API ---------------------------------------------------------------


def _log(client, world, node, week, **days):
    response = client.post(
        f"/api/projects/{node.project_id}/timesheet-entries",
        json={"task_id": node.id, "week_start_date": week, **days},
        headers=world.eng_h,
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _approve(client, world, entry_id):
    return client.post(f"/api/time-log-entries/{entry_id}/approve", headers=world.lead_h)


def _log_and_approve(client, world, node, week, **days):
    response = _approve(client, world, _log(client, world, node, week, **days))
    assert response.status_code == 200, response.text


def _reach_baseline(client, world, node):
    """30h already approved + 70h approved now = 100% of the 100h baseline."""
    _log_and_approve(client, world, node, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=20, thu_hours=10)


def _notifications(client, headers, project_id, kind):
    response = client.get("/api/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return [n for n in response.json() if n["project_id"] == project_id and n["notification_type"] == kind]


def _dashboard(client, world, project_id):
    response = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.bu_h)
    assert response.status_code == 200, response.text
    return response.json()


def _project(db, project_id):
    db.expire_all()
    return db.get(models.Project, project_id)


def test_pending_hours_do_not_count_until_the_lead_approves(client, db, world, governed):
    project_id, node_a, *_ = governed

    entry_id = _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=20, thu_hours=10)

    assert _project(db, project_id).timesheets_soft_locked is False  # 120h logged, only 30h approved
    assert _dashboard(client, world, project_id)["governance_status"]["consumption_pct"] == 30.0

    assert _approve(client, world, entry_id).status_code == 200

    assert _project(db, project_id).timesheets_soft_locked is True


def test_rejected_hours_do_not_count(client, db, world, governed):
    project_id, node_a, *_ = governed
    entry_id = _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=20, thu_hours=10)

    assert client.post(f"/api/time-log-entries/{entry_id}/reject", headers=world.lead_h).status_code == 200

    dashboard = _dashboard(client, world, project_id)
    assert dashboard["governance_status"]["consumption_pct"] == 30.0
    assert dashboard["summary"]["rejected_hours"] == 70.0
    assert _project(db, project_id).timesheets_soft_locked is False


def test_approving_a_whole_week_counts_its_hours(client, db, world, governed):
    project_id, node_a, *_ = governed
    _log(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=20, thu_hours=10)
    week = {"week_start_date": "2026-09-14"}
    submitted = client.post(f"/api/projects/{project_id}/weekly-hours/submit", json=week, headers=world.eng_h)
    assert submitted.status_code == 200, submitted.text
    assert _project(db, project_id).timesheets_soft_locked is False

    approved = client.post(
        f"/api/projects/{project_id}/weekly-hours/approve",
        json={**week, "employee_id": world.emp1.id},
        headers=world.lead_h,
    )

    assert approved.status_code == 200, approved.text
    project = _project(db, project_id)
    assert project.timesheets_soft_locked is True
    assert project.lock_reason == "auto"


def test_sql_and_dashboard_agree_on_approved_hours(client, db, make, world, governed):
    project_id, node_a, node_b, _ = governed
    make.time_entry(project_id, node_b, world.emp1, 7, status="rejected", week=date(2026, 9, 14))
    make.time_entry(project_id, node_a, world.emp2, 9, status="pending_review", week=date(2026, 9, 21))
    make._save(
        models.WeeklyHoursSubmission(
            project_id=project_id, employee_id=world.emp2.id, week_start_date=date(2026, 9, 21), status="approved"
        )
    )

    dashboard = _dashboard(client, world, project_id)

    # 30 row-approved + 9 in an approved week; 20 pending and 7 rejected excluded.
    assert WorkRepository(db).approved_hours(project_id) == dashboard["summary"]["approved_hours"] == 39.0


def test_reaching_the_threshold_alerts_bu_head_and_project_leads_once(client, db, world, governed):
    project_id, node_a, *_ = governed

    _log_and_approve(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=10)

    assert _project(db, project_id).governance_alert_level == WARNING  # 80 of 100 approved
    assert _project(db, project_id).timesheets_soft_locked is False
    assert len(_notifications(client, world.bu_h, project_id, "threshold_warning")) == 1
    assert len(_notifications(client, world.lead_h, project_id, "threshold_warning")) == 1
    assert _notifications(client, world.other_lead_h, project_id, "threshold_warning") == []

    # Still in the warning band: no repeat alert.
    _log_and_approve(client, world, node_a, "2026-09-21", mon_hours=5)
    assert len(_notifications(client, world.bu_h, project_id, "threshold_warning")) == 1


def test_reaching_the_baseline_locks_timesheets_automatically(client, db, world, governed):
    project_id, node_a, *_ = governed

    _reach_baseline(client, world, node_a)  # the approval that crosses 100% is kept

    project = _project(db, project_id)
    assert project.timesheets_soft_locked is True
    assert project.lock_reason == "auto"
    assert project.governance_alert_level == HARD_STOP
    assert len(_notifications(client, world.bu_h, project_id, "execution_locked")) == 1
    assert len(_notifications(client, world.lead_h, project_id, "execution_locked")) == 1
    audit = db.query(models.GovernanceAction).filter_by(project_id=project_id, action="auto_lock").one()
    assert audit.created_by == "System"
    assert audit.consumption_pct == 100.0
    assert audit.consumption_hours == 100.0

    blocked = client.post(
        f"/api/projects/{project_id}/timesheet-entries",
        json={"task_id": node_a.id, "week_start_date": "2026-09-21", "mon_hours": 1},
        headers=world.eng_h,
    )
    assert blocked.status_code == 409
    governance = _dashboard(client, world, project_id)["governance_status"]
    assert governance["level"] == HARD_STOP
    assert governance["soft_locked"] is True
    assert governance["lock_reason"] == "auto"


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
    _reach_baseline(client, world, node_a)
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
    _log(client, world, node_a, "2026-09-21", mon_hours=2)


def test_rejected_extension_keeps_the_lock(client, db, world, governed):
    project_id, node_a, *_ = governed
    _reach_baseline(client, world, node_a)
    request_id = client.post(
        f"/api/projects/{project_id}/extension-requests", json={"requested_hours": 50}, headers=world.lead_h
    ).json()["id"]

    client.post(
        f"/api/projects/{project_id}/extension-requests/{request_id}/decision",
        json={"decision": "reject"},
        headers=world.bu_h,
    )

    assert _project(db, project_id).timesheets_soft_locked is True


def test_manual_resume_over_the_baseline_is_not_relocked_by_the_next_approval(client, db, world, governed):
    project_id, node_a, *_ = governed
    _reach_baseline(client, world, node_a)

    resumed = client.post(
        f"/api/projects/{project_id}/governance/resume-execution",
        json={"comments": "Finish the issue for construction"},
        headers=world.bu_h,
    )

    assert resumed.status_code == 200
    _log_and_approve(client, world, node_a, "2026-09-21", mon_hours=4)
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
    _reach_baseline(client, world, node_a)
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


def test_extension_too_small_to_get_below_the_baseline_keeps_the_lock(client, db, world, governed):
    # TODO N14(d): otherwise the unlock would stick, and because the level stays
    # hard_stop, later approvals would never lock the project again.
    project_id, node_a, *_ = governed
    _log_and_approve(client, world, node_a, "2026-09-14", mon_hours=20, tue_hours=20, wed_hours=20, thu_hours=20)
    assert _project(db, project_id).timesheets_soft_locked is True  # 110 of 100 approved

    def approve_extension(hours):
        request_id = client.post(
            f"/api/projects/{project_id}/extension-requests", json={"requested_hours": hours}, headers=world.lead_h
        ).json()["id"]
        decided = client.post(
            f"/api/projects/{project_id}/extension-requests/{request_id}/decision",
            json={"decision": "approve"},
            headers=world.bu_h,
        )
        assert decided.status_code == 200, decided.text

    approve_extension(5)  # 110 of 105 = 104.8%

    project = _project(db, project_id)
    assert project.timesheets_soft_locked is True
    assert project.lock_reason == "auto"
    decided = _notifications(client, world.lead_h, project_id, "extension_decided")
    assert "Timesheets stay locked" in decided[0]["message"]
    assert _notifications(client, world.lead_h, project_id, "execution_resumed") == []

    approve_extension(20)  # 110 of 125 = 88%: below 100%, so it resumes

    assert _project(db, project_id).timesheets_soft_locked is False
