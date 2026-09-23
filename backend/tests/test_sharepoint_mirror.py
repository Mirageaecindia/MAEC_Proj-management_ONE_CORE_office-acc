"""Characterization: GET /api/projects/{id}/sharepoint-mirror."""

import main
import models
import sharepoint_service

FAKE_MIRROR = {
    "provisioned": True,
    "error": None,
    "folder_hierarchy": [{"id": "f1", "name": "01_HVAC Discipline", "children": []}],
    "files": [],
    "stats": {"total_files": 0, "total_size_bytes": 0, "total_size_formatted": "0.00 B"},
    "connection": {"connected": True, "status": "Connected", "error": None},
    "target_location": "https://example.sharepoint.com/x",
}


def _provisioned_project(db, world):
    project_id = world.create_project()["id"]
    project = db.get(models.Project, project_id)
    project.sharepoint_site_url = "https://example.sharepoint.com/sites/Automation/Project/Project%201"
    db.commit()
    return project_id


def test_unprovisioned_project_reports_not_provisioned_without_calling_graph(client, world):
    project_id = world.create_project()["id"]

    response = client.get(f"/api/projects/{project_id}/sharepoint-mirror", headers=world.bu_h)

    assert response.status_code == 200
    body = response.json()
    assert body["provisioned"] is False
    assert body["connection"]["status"] == "Not Provisioned"
    assert body["target_location"] is None


def test_provisioned_project_returns_mirror_payload(client, db, world, monkeypatch):
    project_id = _provisioned_project(db, world)

    async def fake_mirror(project):
        assert project.id == project_id
        return FAKE_MIRROR

    monkeypatch.setattr(main, "get_sharepoint_mirror_data", fake_mirror)

    response = client.get(f"/api/projects/{project_id}/sharepoint-mirror", headers=world.bu_h)

    assert response.status_code == 200
    assert response.json() == FAKE_MIRROR


def test_graph_errors_map_to_502(client, db, world, monkeypatch):
    project_id = _provisioned_project(db, world)

    async def failing_mirror(project):
        raise sharepoint_service.SharePointError("throttled")

    monkeypatch.setattr(main, "get_sharepoint_mirror_data", failing_mirror)

    response = client.get(f"/api/projects/{project_id}/sharepoint-mirror", headers=world.bu_h)

    assert response.status_code == 502
    assert response.json()["detail"] == "SharePoint error: throttled"


def test_unexpected_errors_map_to_500(client, db, world, monkeypatch):
    project_id = _provisioned_project(db, world)

    async def broken_mirror(project):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "get_sharepoint_mirror_data", broken_mirror)

    response = client.get(f"/api/projects/{project_id}/sharepoint-mirror", headers=world.bu_h)

    assert response.status_code == 500


def test_missing_azure_config_surfaces_as_502(client, db, world):
    project_id = _provisioned_project(db, world)

    response = client.get(f"/api/projects/{project_id}/sharepoint-mirror", headers=world.bu_h)

    assert response.status_code == 502
    assert "Missing required Azure AD" in response.json()["detail"]


def test_mirror_access_is_scoped(client, world):
    project_id = world.create_project()["id"]

    assert client.get(f"/api/projects/{project_id}/sharepoint-mirror", headers=world.other_lead_h).status_code == 403
    assert client.get("/api/projects/999999/sharepoint-mirror", headers=world.bu_h).status_code == 404
