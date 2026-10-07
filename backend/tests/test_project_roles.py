"""Lead and engineer are roles on a project, not account types (app/services/access.py).

The same person can lead one project and work as an engineer on another.
"""

import models

WEEK = "2026-09-07"


def _approve_booking(client, world, project_id, employee, lead_headers):
    booked = client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={"employee_id": employee.id, "utilization_rate": 40, "start_date": "2026-09-01", "end_date": "2026-12-31"},
        headers=lead_headers,
    )
    assert booked.status_code == 200, booked.text
    assert client.post(f"/api/projects/{project_id}/resource-bookings/submit", headers=lead_headers).status_code == 200
    assert client.post(f"/api/projects/{project_id}/resource-bookings/approve", headers=world.bu_h).status_code == 200


def _make_lead(db, project_id, user):
    project = db.get(models.Project, project_id)
    project.project_lead_mechanical, project.project_lead_mechanical_user_id = user.full_name, user.id
    db.commit()


def _give_employee_record(db, make, user):
    employee = make.employee(user.full_name, discipline="Electrical Engineer")
    user.employee_id = employee.id
    db.commit()
    return employee


def test_engineer_chosen_as_lead_has_lead_powers_on_that_project_only(client, db, world):
    leads = world.create_project()["id"]
    works_on = world.create_project()["id"]
    _make_lead(db, leads, world.engineer)
    _approve_booking(client, world, works_on, world.emp1, world.lead_h)
    eng = world.eng_h

    assert {p["id"] for p in client.get("/api/projects", headers=eng).json()} == {leads, works_on}
    booking = {"employee_id": world.emp2.id, "utilization_rate": 20}
    assert client.post(f"/api/projects/{leads}/resource-bookings", json=booking, headers=eng).status_code == 200
    assert client.post(f"/api/projects/{works_on}/resource-bookings", json=booking, headers=eng).status_code == 403
    node = {"task_name": "Design", "phase": "Space Planning"}
    assert client.post(f"/api/projects/{leads}/wbs-nodes", json=node, headers=eng).status_code == 201
    assert client.post(f"/api/projects/{works_on}/wbs-nodes", json=node, headers=eng).status_code == 403
    assert client.get(f"/api/projects/{leads}/executive-dashboard", headers=eng).status_code == 200
    assert client.get(f"/api/projects/{works_on}/executive-dashboard", headers=eng).status_code == 403
    assert client.get(f"/api/projects/{leads}/resource-summary", headers=eng).status_code == 200
    assert client.get(f"/api/projects/{works_on}/resource-summary", headers=eng).status_code == 403
    assert client.get("/api/employees", headers=eng).status_code == 200  # the booking dropdown


def test_lead_booked_on_another_project_works_there_as_an_engineer(client, db, make, world):
    other = world.create_project(
        project_lead_electrical=world.other_lead.full_name, project_lead_electrical_user_id=world.other_lead.id
    )["id"]
    task = make.wbs_node(other, world.other_lead)
    subtask = make.wbs_node(other, world.other_lead, parent_id=task.id, estimated_hours=4)
    lead = world.lead_h

    # Without an employee record there is no engineer work to do.
    assert client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=lead).status_code == 403
    employee = _give_employee_record(db, make, world.lead_e)
    for node in (task, subtask):
        node.assigned_engineer_id = employee.id
    db.commit()
    _approve_booking(client, world, other, employee, world.other_lead_h)

    assert other in {p["id"] for p in client.get("/api/projects", headers=lead).json()}
    assert (
        client.post(f"/api/projects/{other}/resource-bookings", json={"employee_id": 1}, headers=lead).status_code
        == 403
    )
    assert client.get(f"/api/projects/{other}/executive-dashboard", headers=lead).status_code == 403
    assert client.post("/api/subtask-tracking/start", json={"subtask_id": subtask.id}, headers=lead).status_code == 201
    assert client.post("/api/subtask-tracking/logout", headers=lead).status_code == 200
    mine = client.get(f"/api/projects/{other}/wbs-structure", headers=lead).json()
    assert {n["id"] for n in mine} == {task.id, subtask.id}  # an engineer's view: own nodes only
    assert client.get("/api/engineer-performance", headers=lead).status_code == 200


def test_lead_does_a_subtask_on_their_own_project(client, db, make, world):
    project_id = world.create_project()["id"]
    employee = _give_employee_record(db, make, world.lead_e)
    task = make.wbs_node(project_id, world.lead_e, engineer=employee)
    subtask = make.wbs_node(project_id, world.lead_e, engineer=employee, parent_id=task.id, estimated_hours=4)
    lead = world.lead_h

    assert client.get(f"/api/wbs-nodes/{subtask.id}", headers=lead).status_code == 200
    advanced = client.post(
        f"/api/wbs-nodes/{subtask.id}/advance-status", json={"new_status": "In-Progress"}, headers=lead
    )
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["tracking_started"] is True  # starting their own subtask logged them in
    assert client.post("/api/subtask-tracking/logout", headers=lead).status_code == 200
    # Still the lead there: the whole WBS, not just their own nodes.
    make.wbs_node(project_id, world.lead_e, engineer=world.emp1)
    assert len(client.get(f"/api/projects/{project_id}/wbs-structure", headers=lead).json()) == 3


def test_login_and_me_say_whether_the_person_leads_a_project(client, db, world):
    engineer = client.post("/api/auth/login", json={"username": "eng.arjun", "password": "Passw0rd!"}).json()
    assert engineer["leads_projects"] is False
    assert client.get("/api/auth/me", headers=world.lead_h).json()["leads_projects"] is False  # no project yet

    leads = world.create_project()["id"]
    _make_lead(db, leads, world.engineer)

    assert client.get("/api/auth/me", headers=world.eng_h).json()["leads_projects"] is True
    assert client.post("/api/auth/login", json={"username": "lead.e", "password": "Passw0rd!"}).json()["leads_projects"]


def test_each_project_tells_the_caller_their_role_on_it(client, db, world):
    leads = world.create_project()["id"]
    works_on = world.create_project()["id"]
    _make_lead(db, leads, world.engineer)
    _approve_booking(client, world, works_on, world.emp1, world.lead_h)

    mine = {p["id"]: p["my_role"] for p in client.get("/api/projects", headers=world.eng_h).json()}
    assert mine == {leads: "lead", works_on: "engineer"}
    assert client.get(f"/api/projects/{works_on}", headers=world.eng_h).json()["my_role"] == "engineer"
    assert client.get(f"/api/projects/{works_on}", headers=world.bu_h).json()["my_role"] == "bu_head"
