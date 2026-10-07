"""Money is the BU Head's (app/domain/commercial.py): leads and engineers get hours, never money."""


def test_the_bu_head_sees_the_money(client, world, governed):
    project_id, *_ = governed

    project = client.get(f"/api/projects/{project_id}", headers=world.bu_h).json()
    dashboard = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.bu_h).json()
    summary = client.get(f"/api/projects/{project_id}/resource-summary", headers=world.bu_h).json()

    assert (project["contract_value"], project["contract_currency"]) == (100000, "USD")
    assert dashboard["commercial_budget_burn"]["total"] == 100000
    assert dashboard["project"]["contract_value"] == 100000
    assert summary["contract_value"] == 100000


def test_a_lead_gets_no_money_anywhere(client, world, governed):
    project_id, *_ = governed

    listed = client.get("/api/projects", headers=world.lead_h).json()
    project = client.get(f"/api/projects/{project_id}", headers=world.lead_h).json()
    dashboard = client.get(f"/api/projects/{project_id}/executive-dashboard", headers=world.lead_h).json()
    summary = client.get(f"/api/projects/{project_id}/resource-summary", headers=world.lead_h).json()

    for record in (*listed, project, dashboard["project"], summary):
        assert record["contract_value"] is None and record["contract_currency"] is None
    assert "commercial_budget_burn" not in dashboard
    assert dashboard["hours_consumption"]["approved"] == 30  # the hours are all there


def test_an_engineer_gets_no_money_anywhere(client, world, governed):
    project_id, *_ = governed

    listed = client.get("/api/projects", headers=world.eng_h).json()
    mine = client.get(f"/api/engineer-performance-dashboard?project_id={project_id}", headers=world.eng_h).json()
    overview = client.get("/api/engineer-performance", headers=world.eng_h).json()

    for record in (*listed, *mine["projects"], *overview["projects"]):
        assert record.get("contract_value") is None and record.get("contract_currency") is None  # empty or absent
