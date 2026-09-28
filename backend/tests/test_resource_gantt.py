"""Engineer assignment timeline on the Resource Booking page: the selected project's engineers only."""


def _book(client, world, project_id, employee):
    response = client.post(
        f"/api/projects/{project_id}/resource-bookings",
        json={
            "employee_id": employee.id,
            "utilization_rate": 40,
            "start_date": "2026-10-01",
            "end_date": "2026-10-15",
        },
        headers=world.lead_h,
    )
    assert response.status_code == 200, response.text


def _engineers(client, headers, **params):
    response = client.get("/api/resource-bookings/gantt", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return {engineer["employee_id"] for engineer in response.json()["engineers"]}


def test_timeline_shows_only_the_selected_projects_people(client, world):
    tower = world.create_project()["id"]
    mall = world.create_project()["id"]  # same leads
    _book(client, world, tower, world.emp1)
    _book(client, world, mall, world.emp2)
    leads = {world.lead_e.employee_id, world.lead_m.employee_id, world.lead_b.employee_id}  # hold capacity too

    assert _engineers(client, world.lead_h, project_id=tower) == {world.emp1.id} | leads
    assert _engineers(client, world.lead_h, project_id=mall) == {world.emp2.id} | leads
    assert _engineers(client, world.lead_h) == {world.emp1.id, world.emp2.id} | leads  # without a project: all


def test_selected_project_keeps_each_engineers_other_commitments(client, world):
    tower = world.create_project()["id"]
    mall = world.create_project()["id"]
    _book(client, world, tower, world.emp1)
    _book(client, world, mall, world.emp1)

    response = client.get("/api/resource-bookings/gantt", params={"project_id": tower}, headers=world.lead_h)

    arjun = next(row for row in response.json()["engineers"] if row["employee_id"] == world.emp1.id)
    assert {a["project_id"] for a in arjun["assignments"]} == {tower, mall}  # concurrent work stays visible


def test_timeline_of_someone_elses_project_is_refused(client, world):
    tower = world.create_project()["id"]

    response = client.get("/api/resource-bookings/gantt", params={"project_id": tower}, headers=world.other_lead_h)

    assert response.status_code == 403
