"""Characterization: project creation, listing, retrieval and deletion (BU Head).

Assertions marked KNOWN record today's behaviour for issues scheduled in the
roadmap; update them deliberately when that step lands.
"""

from datetime import date, datetime

import pytest

import models
from app.integrations.sharepoint import SharePointError

# --- Lead dropdowns ------------------------------------------------------------


def test_project_leads_filters_by_discipline(client, world):
    response = client.get("/api/project-leads", params={"discipline": "electrical"}, headers=world.bu_h)

    assert response.status_code == 200
    assert {lead["name"] for lead in response.json()} == {"Anita Kumar", "Unassigned Lead"}
    assert all(lead["title"] == "Electrical" for lead in response.json())


def test_project_leads_without_discipline_are_hidden_from_filtered_dropdowns(client, make, world):
    # By design: a lead without a discipline appears only in the unfiltered list.
    # create_user.py now requires a discipline for new leads (roadmap 4.1).
    make.user("lead.nodisc", "lead", "No Discipline Lead")

    filtered = client.get("/api/project-leads", params={"discipline": "electrical"}, headers=world.bu_h).json()
    unfiltered = client.get("/api/project-leads", headers=world.bu_h).json()

    assert "No Discipline Lead" not in {lead["name"] for lead in filtered}
    assert "No Discipline Lead" in {lead["name"] for lead in unfiltered}


# --- Create ----------------------------------------------------------------------


def test_create_project_maps_form_fields_onto_project(client, db, world):
    body = world.create_project(project_name="Hotel Tower", project_code="MAEC-001", total_contract_value=250000)

    assert body["sharepoint_status"] == "not_requested"
    assert body["sharepoint_site_url"] is None
    project = db.get(models.Project, body["id"])
    assert project.project_name == "Hotel Tower"
    assert project.client_organization == "Acme Developments"
    assert project.project_lead == "Anita Kumar"  # primary lead = electrical
    assert project.project_lead_electrical_user_id == world.lead_e.id
    assert project.project_lead_mechanical_user_id == world.lead_m.id
    assert project.project_lead_bim_user_id == world.lead_b.id
    assert project.start_date == date(2026, 9, 1)
    assert project.contract_value == 250000
    assert project.contract_currency == "USD"
    assert project.governance_threshold_pct == 80
    assert project.target_effort_hours == 500
    assert project.sharepoint_disciplines is None  # empty list is not stored
    assert project.timesheets_soft_locked is False


def test_create_project_takes_lead_name_from_account_not_payload(client, db, world):
    payload = world.project_payload(project_lead_electrical="Spoofed Name")

    body = client.post("/api/projects", json=payload, headers=world.bu_h).json()

    assert db.get(models.Project, body["id"]).project_lead_electrical == "Anita Kumar"


def test_create_project_accepts_legacy_name_only_leads(client, db, world):
    payload = world.project_payload(project_lead_electrical_user_id=None, project_lead_electrical="Legacy Lead")

    body = client.post("/api/projects", json=payload, headers=world.bu_h).json()

    project = db.get(models.Project, body["id"])
    assert project.project_lead_electrical == "Legacy Lead"
    assert project.project_lead_electrical_user_id is None


def test_create_project_rejects_non_lead_account_as_lead(client, world):
    payload = world.project_payload(project_lead_bim_user_id=world.engineer.id)

    response = client.post("/api/projects", json=payload, headers=world.bu_h)

    assert response.status_code == 400


def test_create_project_rejects_duplicate_code(client, world):
    world.create_project(project_code="DUP-1")

    response = client.post("/api/projects", json=world.project_payload(project_code="DUP-1"), headers=world.bu_h)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "overrides",
    [
        {"project_name": "   "},
        {"client_customer": ""},
        {"alert_override_threshold_pct": 150},
        {"alert_override_threshold_pct": -1},
    ],
)
def test_create_project_validates_payload(client, world, overrides):
    response = client.post("/api/projects", json=world.project_payload(**overrides), headers=world.bu_h)

    assert response.status_code == 422


def test_create_project_clamps_negative_money_and_hours_to_zero(client, db, world):
    body = world.create_project(total_contract_value=-5, target_effort_hours=-10)

    project = db.get(models.Project, body["id"])
    assert project.contract_value == 0
    assert project.target_effort_hours == 0


@pytest.mark.parametrize("role_headers", ["lead_h", "eng_h"])
def test_only_bu_head_can_create_projects(client, world, role_headers):
    response = client.post("/api/projects", json=world.project_payload(), headers=getattr(world, role_headers))

    assert response.status_code == 403


# --- Create: SharePoint provisioning outcome --------------------------------------


def test_create_project_records_provisioned_sharepoint_url(client, db, world, storage):
    storage.provision_url = "https://example.sharepoint.com/sites/Automation/Project/Hotel%20Tower"

    body = world.create_project(sharepoint_disciplines=["HVAC Discipline", "Plumbing"])

    assert body["sharepoint_status"] == "provisioned"
    assert body["sharepoint_site_url"] == storage.provision_url
    assert storage.provisioned == [["HVAC Discipline", "Plumbing"]]
    assert db.get(models.Project, body["id"]).sharepoint_site_url == storage.provision_url


def test_create_project_still_succeeds_when_sharepoint_fails(client, db, world, storage):
    storage.provision_error = SharePointError("403 Forbidden")

    body = world.create_project(sharepoint_disciplines=["Plumbing"])

    assert body["sharepoint_status"] == "failed"
    assert body["sharepoint_error"] == "403 Forbidden"
    assert db.get(models.Project, body["id"]).sharepoint_site_url is None


def test_create_project_reports_unexpected_sharepoint_errors(client, world, storage):
    storage.provision_error = RuntimeError("boom")

    body = world.create_project(sharepoint_disciplines=["Plumbing"])

    assert body["sharepoint_status"] == "error"
    assert body["sharepoint_error"] == "Unexpected error: boom"


def test_create_project_skips_sharepoint_when_no_disciplines(client, world, storage):
    body = world.create_project(sharepoint_disciplines=[])

    assert body["sharepoint_status"] == "not_requested"
    assert storage.provisioned == []


def test_create_project_without_azure_config_fails_fast_without_network(client, world):
    # The suite blanks the Azure settings; the real client must refuse to start.
    body = world.create_project(sharepoint_disciplines=["Plumbing"])

    assert body["sharepoint_status"] == "failed"
    assert "Missing required Azure AD" in body["sharepoint_error"]


# --- List / get --------------------------------------------------------------------


def test_bu_head_lists_every_project(client, world):
    ids = {world.create_project()["id"] for _ in range(3)}

    response = client.get("/api/projects", headers=world.bu_h)

    assert response.status_code == 200
    assert {project["id"] for project in response.json()} == ids


def test_lead_and_engineer_project_lists_are_scoped(client, make, world):
    visible = world.create_project()
    world.create_project(
        project_lead_electrical_user_id=world.other_lead.id,
        project_lead_electrical=world.other_lead.full_name,
    )
    make.wbs_node(visible["id"], world.lead_e, engineer=world.emp1)

    lead_ids = {p["id"] for p in client.get("/api/projects", headers=world.lead_h).json()}
    assert visible["id"] in lead_ids

    # A Lead assignment (WBS task + draft booking) alone grants the engineer NO
    # project access — BU Head approval is the only grant.
    booking = client.post(
        f"/api/projects/{visible['id']}/resource-bookings",
        json={"employee_id": world.emp1.id, "planned_hours": 80, "utilization_rate": 50},
        headers=world.lead_h,
    )
    assert booking.status_code == 200, booking.text
    assert client.get("/api/projects", headers=world.eng_h).json() == []

    client.post(f"/api/projects/{visible['id']}/resource-bookings/submit", headers=world.lead_h)
    assert client.get("/api/projects", headers=world.eng_h).json() == []

    client.post(f"/api/projects/{visible['id']}/resource-bookings/approve", headers=world.bu_h)
    eng_ids = {p["id"] for p in client.get("/api/projects", headers=world.eng_h).json()}
    assert eng_ids == {visible["id"]}


def test_get_project(client, world):
    project = world.create_project()

    assert client.get(f"/api/projects/{project['id']}", headers=world.bu_h).status_code == 200
    assert client.get("/api/projects/999999", headers=world.bu_h).status_code == 404
    assert client.get(f"/api/projects/{project['id']}", headers=world.other_lead_h).status_code == 403


# --- Delete --------------------------------------------------------------------------


def test_project_with_history_is_not_deleted(client, db, make, world):
    # TODO C1: deleting wiped the governance audit log; a project with any history is archived instead.
    project_id = world.create_project()["id"]
    node = make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    make.time_entry(project_id, node, world.emp1, 5)
    db.add_all(
        [
            models.ResourceBooking(project_id=project_id, employee_id=world.emp1.id, planned_hours=8),
            models.WbsNodeHistory(
                node_id=node.id,
                project_id=project_id,
                user_id=world.bu.id,
                user_name="x",
                action="comment",
                new_status="To Do",
            ),
            models.GovernanceAction(project_id=project_id, action="stop_execution"),
            models.ExtensionRequest(project_id=project_id, requested_by="x", requested_by_user_id=1, requested_hours=5),
            models.Notification(recipient_role="bu_head", notification_type="t", title="t", project_id=project_id),
            models.TimeSession(
                project_id=project_id,
                task_id=node.id,
                subtask_id=node.id,
                employee_id=world.emp1.id,
                login_at=datetime(2026, 9, 7, 9, 0),
            ),
        ]
    )
    db.commit()

    response = client.delete(f"/api/projects/{project_id}", headers=world.bu_h)

    assert response.status_code == 409
    assert "Archive it instead" in response.json()["detail"]
    db.expire_all()
    assert db.get(models.Project, project_id) is not None
    assert db.query(models.GovernanceAction).filter_by(project_id=project_id).count() == 1


def test_project_without_history_is_deleted_with_its_notifications(client, db, world):
    project_id = world.create_project()["id"]
    db.add(models.Notification(recipient_role="bu_head", notification_type="t", title="t", project_id=project_id))
    db.commit()

    response = client.delete(f"/api/projects/{project_id}", headers=world.bu_h)

    assert response.status_code == 200
    db.expire_all()
    assert db.get(models.Project, project_id) is None
    assert db.query(models.Notification).filter_by(project_id=project_id).count() == 0


def test_delete_project_guards(client, world):
    project_id = world.create_project()["id"]

    assert client.delete(f"/api/projects/{project_id}", headers=world.lead_h).status_code == 403
    assert client.delete("/api/projects/999999", headers=world.bu_h).status_code == 404
