"""Characterization: Executive Dashboard figures and BU Head governance actions.

Reference scenario (see `governed`): two WBS nodes of 40h + 60h assigned to one
engineer whose discipline is "Mechanical Engineer"; 30h approved + 20h pending
logged. Contract 100,000 USD, threshold 80%, target effort 100h, so the
governance baseline is 100h (target + approved extensions) and usage, which
counts approved hours only, is 30%.
The alert/auto-lock workflow itself is covered in test_governance_workflow.py.
"""

from datetime import date

import models


def _dashboard(client, headers, project_id):
    response = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Dashboard figures ---------------------------------------------------------------


def test_dashboard_figures_for_reference_scenario(client, world, governed):
    project_id, *_ = governed

    data = _dashboard(client, world.bu_h, project_id)

    assert data["summary"] == {
        "scheduled_hours": 100,
        "baseline_hours": 100.0,
        "target_effort_hours": 100.0,
        "extension_approved_hours": 0.0,
        "approved_hours": 30.0,
        "logged_hours": 50.0,
        "pending_hours": 20.0,
        "pending_entries": 1,
        "rejected_hours": 0.0,
        "consumption_pct": 30.0,
    }
    assert data["commercial_budget_burn"] == {
        "currency": "USD",
        "total": 100000.0,
        "consumed": 30000.0,
        "remaining": 70000.0,
        "percent": 30.0,
    }
    assert data["spi"] == {"value": 0.3, "note": "Behind plan — 30 earned of 100 planned baseline hours."}
    assert data["governance_status"]["status"] == "normal"
    assert data["governance_status"]["level"] == "normal"
    assert data["governance_status"]["baseline_hours"] == 100.0
    assert data["governance_status"]["max_discipline"] == "Mechanical Engineer"
    assert data["governance_status"]["soft_locked"] is False
    assert data["exceptions"] == []
    assert data["monthly_data"] == [
        {
            "month": "2026-09",
            "month_label": "Sep 2026",
            "planned_baseline": 100.0,
            "normal_consumption": 30.0,  # approved hours only
            "exceeded_threshold": 0.0,
        }
    ]


def test_project_at_alert_threshold_reports_warning_and_splits_the_chart(client, make, world, governed):
    project_id, _, node_b, _ = governed
    make.time_entry(project_id, node_b, world.emp1, 60, status="approved", week=date(2026, 9, 14))

    data = _dashboard(client, world.bu_h, project_id)

    assert data["governance_status"]["status"] == "exceeded"  # at/above the alert threshold
    assert data["governance_status"]["level"] == "warning"
    assert data["governance_status"]["consumption_pct"] == 90.0
    # Monthly chart: hours after cumulative usage passed 80h (80% of 100h) count as exceeded.
    assert data["monthly_data"][0]["normal_consumption"] == 80.0
    assert data["monthly_data"][0]["exceeded_threshold"] == 10.0
    # The per-discipline breakdown stays informational.
    assert [e["discipline"] for e in data["exceptions"]] == ["Mechanical Engineer"]


def test_usage_counts_approved_hours_only(client, make, world, governed):
    project_id, node_a, node_b, _ = governed
    make.time_entry(project_id, node_a, world.emp1, 25, status="rejected", week=date(2026, 9, 14))
    # Approving the engineer's whole week approves its pending rows too (weekly route).
    week = models.WeeklyHoursSubmission(
        project_id=project_id, employee_id=world.emp1.id, week_start_date=date(2026, 9, 7), status="approved"
    )
    make._save(week)

    data = _dashboard(client, world.bu_h, project_id)

    assert data["summary"]["approved_hours"] == 50.0  # 30 row-approved + 20 week-approved
    assert data["summary"]["pending_hours"] == 0.0
    assert data["summary"]["rejected_hours"] == 25.0
    assert data["summary"]["logged_hours"] == 50.0  # rejected hours excluded
    assert data["summary"]["consumption_pct"] == 50.0


def test_baseline_is_bu_head_target_plus_approved_extensions(client, db, world, governed):
    # Roadmap 5.2 (fixed): the BU Head's target effort hours, not the WBS total.
    project_id, *_ = governed
    project = db.get(models.Project, project_id)
    project.target_effort_hours = 500
    project.extension_approved_hours = 100
    db.commit()

    data = _dashboard(client, world.bu_h, project_id)

    assert data["hours_consumption"]["scheduled"] == 600.0  # 500 target + 100 approved extensions
    assert data["hours_consumption"]["wbs_planned"] == 100
    assert data["hours_consumption"]["percent"] == 5.0  # 30 approved / 600
    assert data["governance_status"]["wbs_exceeds_target"] is False
    assert data["commercial_budget_burn"]["consumed"] == 6000.0  # contract x 30 approved / 500 target

    project.target_effort_hours = 80
    project.extension_approved_hours = None
    db.commit()
    assert _dashboard(client, world.bu_h, project_id)["governance_status"]["wbs_exceeds_target"] is True


def test_dashboard_access(client, world, governed):
    project_id, *_ = governed

    assert client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.eng_h).status_code == 403
    assert client.get("/api/projects/999999/executive-dashboard", headers=world.bu_h).status_code == 404
    # A lead not assigned to the project must not see its commercial data (P0 fix).
    assert client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.other_lead_h).status_code == 403
    assert client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.lead_h).status_code == 200


# --- Stop execution (soft lock) ---------------------------------------------------------


def test_stop_execution_requires_comment_and_bu_head(client, world, governed):
    project_id, *_ = governed
    url = f"/api/projects/{project_id}/governance/stop-execution"

    assert client.post(url, json={"comments": "   "}, headers=world.bu_h).status_code == 422
    assert client.post(url, json={"comments": "Halt"}, headers=world.lead_h).status_code == 403


def test_stop_execution_soft_locks_timesheets(client, db, world, governed):
    project_id, node_a, _, pending = governed

    response = client.post(
        f"/api/projects/{project_id}/governance/stop-execution", json={"comments": "Over budget"}, headers=world.bu_h
    )

    assert response.status_code == 200
    action = response.json()
    assert action["action"] == "stop_execution"
    assert action["discipline"] == "Mechanical Engineer"
    assert action["consumption_pct"] == 30.0
    assert action["threshold_pct"] == 80
    assert action["consumption_hours"] == 30.0
    assert action["comments"] == "Over budget"
    assert action["created_by"] == "Test BU Head"
    assert _dashboard(client, world.bu_h, project_id)["governance_status"]["soft_locked"] is True

    log_hours = client.post(
        f"/api/projects/{project_id}/timesheet-entries",
        json={"task_id": node_a.id, "week_start_date": "2026-09-21", "mon_hours": 2},
        headers=world.eng_h,
    )
    approve_hours = client.post(f"/api/time-log-entries/{pending.id}/approve", headers=world.lead_h)
    assert log_hours.status_code == 409
    assert approve_hours.status_code == 409


def test_stop_is_refused_when_already_stopped_and_resume_reopens(client, db, world, governed):
    # Roadmap 6.1 (fixed): stop is idempotent-safe and execution can be resumed.
    project_id, node_a, _, _ = governed
    stop_url = f"/api/projects/{project_id}/governance/stop-execution"
    resume_url = f"/api/projects/{project_id}/governance/resume-execution"

    assert client.post(resume_url, json={}, headers=world.bu_h).status_code == 409  # not stopped yet
    assert client.post(stop_url, json={"comments": "first"}, headers=world.bu_h).status_code == 200
    assert client.post(stop_url, json={"comments": "second"}, headers=world.bu_h).status_code == 409
    assert db.get(models.Project, project_id).lock_reason == "manual"

    assert client.post(resume_url, json={"comments": "Budget agreed"}, headers=world.lead_h).status_code == 403
    resumed = client.post(resume_url, json={"comments": "Budget agreed"}, headers=world.bu_h)

    assert resumed.status_code == 200
    assert resumed.json()["action"] == "resume_execution"
    assert resumed.json()["comments"] == "Budget agreed"
    db.expire_all()
    project = db.get(models.Project, project_id)
    assert project.timesheets_soft_locked is False
    assert project.lock_reason is None
    log_hours = client.post(
        f"/api/projects/{project_id}/timesheet-entries",
        json={"task_id": node_a.id, "week_start_date": "2026-09-21", "mon_hours": 2},
        headers=world.eng_h,
    )
    assert log_hours.status_code == 200


# --- Extension requests -----------------------------------------------------------------


def _request_extension(client, headers, project_id, hours=40, justification="Scope creep"):
    return client.post(
        f"/api/projects/{project_id}/extension-requests",
        json={"requested_hours": hours, "justification": justification},
        headers=headers,
    )


def test_extension_request_appears_in_bu_head_queue(client, world, governed):
    project_id, *_ = governed

    created = _request_extension(client, world.lead_h, project_id)

    assert created.status_code == 201
    request = created.json()
    assert request["status"] == "pending"
    assert request["status_label"] == "Pending BU Head Approval"
    assert request["requested_by"] == "Anita Kumar"
    data = _dashboard(client, world.bu_h, project_id)
    assert data["current_extension_request"]["id"] == request["id"]
    assert data["project"]["extension_status"] == "pending"
    assert data["governance_actions"][0]["action"] == "extension_request"
    assert data["governance_actions"][0]["requested_hours"] == 40
    assert _request_extension(client, world.lead_h, project_id).status_code == 409  # one pending at a time
    assert _request_extension(client, world.lead_h, project_id, hours=0).status_code == 422


def test_approving_extension_raises_the_baseline(client, db, world, governed):
    project_id, *_ = governed
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]
    url = f"/api/projects/{project_id}/extension-requests/{request_id}/decision"

    response = client.post(url, json={"decision": "approve", "comments": "OK"}, headers=world.bu_h)

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["decided_by"] == "Test BU Head"
    assert response.json()["decision_comments"] == "OK"
    project = db.get(models.Project, project_id)
    assert project.extension_status == "approved"
    assert project.extension_approved_hours == 40
    data = _dashboard(client, world.bu_h, project_id)
    assert data["current_extension_request"] is None
    assert [a["action"] for a in data["governance_actions"]] == ["approve_extension", "extension_request"]
    # Roadmap 5.2 / 6.3 (fixed): approved hours raise the baseline (100 + 40).
    assert data["summary"]["baseline_hours"] == 140.0
    assert data["summary"]["consumption_pct"] == 21.4  # 30 approved / 140
    assert client.post(url, json={"decision": "approve"}, headers=world.bu_h).status_code == 409


def test_rejecting_extension(client, db, world, governed):
    project_id, *_ = governed
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]

    response = client.post(
        f"/api/projects/{project_id}/extension-requests/{request_id}/decision",
        json={"decision": "reject"},
        headers=world.bu_h,
    )

    assert response.json()["status"] == "rejected"
    project = db.get(models.Project, project_id)
    assert project.extension_status == "rejected"
    assert project.extension_approved_hours is None


def test_extension_decision_guards(client, world, governed):
    project_id, *_ = governed
    request_id = _request_extension(client, world.lead_h, project_id).json()["id"]
    url = f"/api/projects/{project_id}/extension-requests/{request_id}/decision"

    assert client.post(url, json={"decision": "maybe"}, headers=world.bu_h).status_code == 422
    assert client.post(url, json={"decision": "approve"}, headers=world.lead_h).status_code == 403
    missing = f"/api/projects/{project_id}/extension-requests/999999/decision"
    assert client.post(missing, json={"decision": "approve"}, headers=world.bu_h).status_code == 404


def test_only_a_lead_allocated_to_the_project_can_request_an_extension(client, db, world, governed):
    project_id, *_ = governed

    unassigned = _request_extension(client, world.other_lead_h, project_id)
    legacy = client.post(
        f"/api/projects/{project_id}/governance/request-extension",
        json={"comments": "Please extend limit by 20 hours"},
        headers=world.other_lead_h,
    )

    assert unassigned.status_code == 403
    assert legacy.status_code == 403
    assert db.query(models.ExtensionRequest).filter_by(project_id=project_id).count() == 0
    assert _request_extension(client, world.lead_h, project_id).status_code == 201  # the allocated lead can


def test_legacy_bu_extension_endpoints_are_removed(client, world, governed):
    # Roadmap 1.6: the unused duplicates of the decision endpoint were deleted.
    project_id, *_ = governed
    _request_extension(client, world.lead_h, project_id)

    for action in ("approve-extension", "reject-extension"):
        response = client.post(
            f"/api/projects/{project_id}/governance/{action}", json={"comments": "x"}, headers=world.bu_h
        )
        assert response.status_code in (404, 405)
