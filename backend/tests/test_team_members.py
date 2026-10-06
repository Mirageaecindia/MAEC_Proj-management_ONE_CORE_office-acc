"""A lead's team on a project: the people Assign Engineer offers (app/services/team_members.py)."""

TEAM = "/api/projects/{}/team-members"


def test_a_lead_picks_their_team_and_changes_it(client, world):
    project_id = world.create_project()["id"]

    assert client.get(TEAM.format(project_id), headers=world.lead_h).json() == {"employee_ids": []}

    picked = client.put(
        TEAM.format(project_id), json={"employee_ids": [world.emp2.id, world.emp1.id]}, headers=world.lead_h
    )
    assert picked.status_code == 200, picked.text
    assert picked.json()["employee_ids"] == sorted([world.emp1.id, world.emp2.id])

    client.put(TEAM.format(project_id), json={"employee_ids": [world.emp2.id]}, headers=world.lead_h)
    assert client.get(TEAM.format(project_id), headers=world.lead_h).json() == {"employee_ids": [world.emp2.id]}


def test_each_lead_keeps_their_own_team(client, make, world):
    project_id = world.create_project()["id"]
    other_lead_h = make.headers(world.lead_m)  # the project's mechanical lead

    client.put(TEAM.format(project_id), json={"employee_ids": [world.emp1.id]}, headers=world.lead_h)

    assert client.get(TEAM.format(project_id), headers=other_lead_h).json() == {"employee_ids": []}


def test_only_the_projects_leads_have_a_team(client, world):
    project_id = world.create_project()["id"]

    for headers in (world.eng_h, world.other_lead_h, world.bu_h):
        assert client.get(TEAM.format(project_id), headers=headers).status_code == 403
        assert client.put(TEAM.format(project_id), json={"employee_ids": []}, headers=headers).status_code == 403


def test_unknown_people_are_refused_and_nothing_changes(client, world):
    project_id = world.create_project()["id"]
    client.put(TEAM.format(project_id), json={"employee_ids": [world.emp1.id]}, headers=world.lead_h)

    refused = client.put(TEAM.format(project_id), json={"employee_ids": [world.emp2.id, 99999]}, headers=world.lead_h)

    assert refused.status_code == 400
    assert client.get(TEAM.format(project_id), headers=world.lead_h).json() == {"employee_ids": [world.emp1.id]}
