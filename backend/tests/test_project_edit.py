"""Editing a project (TODO C2).

Every changed field is audited (before -> after); the lock is re-checked both
ways; a currency change needs confirmation; a replaced Lead's WBS nodes move to
their successor; project codes stay unique; archived projects can't be edited.
Scenario (`governed`): target 100h, threshold 80%, contract 100,000 USD, 30h approved.
"""

from datetime import date

import models
from app.services.governance_monitor import enforce_governance
from app.services.projects import CURRENCY_CHANGE


def _payload(client, world, project_id, **changes):
    """The project's current values in update form, with `changes` applied."""
    project = client.get(f"/api/projects/{project_id}", headers=world.bu_h).json()
    payload = {
        "project_name": project["project_name"],
        "project_code": project["project_code"],
        "client_customer": project["client_organization"],
        "target_start_date": project["start_date"],
        "total_contract_value": project["contract_value"],
        "contract_currency": project["contract_currency"],
        "target_effort_hours": project["target_effort_hours"],
        "alert_override_threshold_pct": project["governance_threshold_pct"],
    }
    for discipline in ("electrical", "mechanical", "bim"):
        payload[f"project_lead_{discipline}"] = project[f"project_lead_{discipline}"]
        payload[f"project_lead_{discipline}_user_id"] = project[f"project_lead_{discipline}_user_id"]
        for field in ("start_date", "end_date", "utilization_pct"):
            payload[f"project_lead_{discipline}_{field}"] = project[f"project_lead_{discipline}_{field}"]
    return {**payload, **changes}


def _edit(client, world, project_id, headers=None, **changes):
    return client.put(
        f"/api/projects/{project_id}",
        json=_payload(client, world, project_id, **changes),
        headers=headers or world.bu_h,
    )


def _audit(db, project_id, action):
    return [a.comments for a in db.query(models.GovernanceAction).filter_by(project_id=project_id, action=action)]


def _project(db, project_id):
    db.expire_all()
    return db.get(models.Project, project_id)


def test_changed_fields_are_audited_before_and_after(client, db, world, governed):
    project_id, *_ = governed

    edited = _edit(
        client, world, project_id, target_effort_hours=120, alert_override_threshold_pct=90, total_contract_value=120000
    )

    assert edited.status_code == 200, edited.text
    (comments,) = _audit(db, project_id, "edit_project")
    assert "Target effort hours: 100 -> 120" in comments
    assert "Alert threshold %: 80 -> 90" in comments
    assert "Contract value: 100000 -> 120000" in comments
    assert "Project name" not in comments  # unchanged fields are not listed
    assert _edit(client, world, project_id).status_code == 200  # no changes: no audit entry
    assert len(_audit(db, project_id, "edit_project")) == 1


def test_only_the_bu_head_edits(client, world, governed):
    project_id, *_ = governed

    assert _edit(client, world, project_id, headers=world.lead_h).status_code == 403
    assert (
        client.put("/api/projects/999999", json=_payload(client, world, project_id), headers=world.bu_h).status_code
        == 404
    )


def test_project_code_stays_unique(client, world, governed):
    project_id, *_ = governed
    other_code = world.create_project()["project_code"]

    assert _edit(client, world, project_id, project_code=other_code).status_code == 409
    assert _edit(client, world, project_id, project_code="NEW-CODE").json()["project_code"] == "NEW-CODE"


def test_currency_change_needs_confirmation(client, db, world, governed):
    project_id, *_ = governed

    refused = _edit(client, world, project_id, contract_currency="INR")
    assert (refused.status_code, refused.json()["detail"]) == (409, CURRENCY_CHANGE)
    assert _project(db, project_id).contract_currency == "USD"

    confirmed = _edit(client, world, project_id, contract_currency="INR", confirm_currency_change=True)
    assert confirmed.status_code == 200, confirmed.text
    assert "Currency: USD -> INR" in _audit(db, project_id, "edit_project")[0]


def _reach_auto_lock(db, make, world, project_id, node):
    make.time_entry(project_id, node, world.emp1, 70, status="approved", day=date(2026, 9, 14))  # 100 of 100
    enforce_governance(db, project_id)
    project = _project(db, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (True, "auto")


def test_raising_the_target_lifts_an_automatic_lock(client, db, make, world, governed):
    project_id, node_a, *_ = governed
    _reach_auto_lock(db, make, world, project_id, node_a)

    assert _edit(client, world, project_id, target_effort_hours=150).status_code == 200

    project = _project(db, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (False, None)
    reopened = db.query(models.GovernanceAction).filter_by(project_id=project_id, action="resume_execution").one()
    assert reopened.created_by == "System"
    kinds = {n.notification_type for n in db.query(models.Notification).filter_by(recipient_user_id=world.lead_e.id)}
    assert "execution_resumed" in kinds


def test_raising_the_target_keeps_a_manual_stop(client, db, make, world, governed):
    # At 100% the BU Head resumes, then stops manually: raising the target must not lift that stop.
    project_id, node_a, *_ = governed
    _reach_auto_lock(db, make, world, project_id, node_a)
    governance = f"/api/projects/{project_id}/governance"
    assert client.post(f"{governance}/resume-execution", json={}, headers=world.bu_h).status_code == 200
    assert (
        client.post(f"{governance}/stop-execution", json={"comments": "Audit"}, headers=world.bu_h).status_code == 200
    )

    _edit(client, world, project_id, target_effort_hours=150)

    project = _project(db, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (True, "manual")


def test_lowering_the_target_past_the_baseline_locks(client, db, world, governed):
    project_id, *_ = governed  # 30 approved hours

    assert _edit(client, world, project_id, target_effort_hours=25).status_code == 200  # 120%

    project = _project(db, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (True, "auto")
    assert len(_audit(db, project_id, "auto_lock")) == 1


def test_replacing_a_lead_moves_their_nodes_and_access(client, db, world, governed):
    project_id, node_a, node_b, _ = governed  # both nodes assigned to Anita (electrical)

    edited = _edit(
        client,
        world,
        project_id,
        project_lead_electrical=world.other_lead.full_name,
        project_lead_electrical_user_id=world.other_lead.id,
    )

    assert edited.status_code == 200, edited.text
    assert edited.json()["reassigned_nodes"] == 2
    db.expire_all()
    assert {db.get(models.WbsNode, n.id).assigned_lead_user_id for n in (node_a, node_b)} == {world.other_lead.id}
    visible = lambda headers: {p["id"] for p in client.get("/api/projects", headers=headers).json()}  # noqa: E731
    assert project_id not in visible(world.lead_h)
    assert project_id in visible(world.other_lead_h)
    comments = _audit(db, project_id, "edit_project")[0]
    assert "Electrical lead: Anita Kumar -> Unassigned Lead" in comments
    assert "2 WBS node(s) moved to the new lead" in comments

    def kinds(user):
        return {n.notification_type for n in db.query(models.Notification).filter_by(recipient_user_id=user.id)}

    assert "project_lead_removed" in kinds(world.lead_e)
    assert "project_lead_assigned" in kinds(world.other_lead)


def test_an_archived_project_cannot_be_edited(client, world, governed):
    project_id, *_ = governed
    client.post(f"/api/projects/{project_id}/archive", json={}, headers=world.bu_h)

    assert _edit(client, world, project_id, target_effort_hours=150).status_code == 409


def test_fewer_approved_hours_never_reopen_an_automatic_lock(db, make, world, governed):
    # A Lead rejecting approved rows must not reopen the project: only the BU Head's
    # baseline changes do (an approved extension or a target edit).
    project_id, node_a, *_ = governed
    _reach_auto_lock(db, make, world, project_id, node_a)
    for entry in db.query(models.TimeLogEntry).filter_by(project_id=project_id, approval_status="approved"):
        entry.approval_status = "rejected"  # the lock blocks this today; D8 plans to allow rejects while locked
    db.commit()

    enforce_governance(db, project_id)

    project = _project(db, project_id)
    assert (project.timesheets_soft_locked, project.lock_reason) == (True, "auto")
