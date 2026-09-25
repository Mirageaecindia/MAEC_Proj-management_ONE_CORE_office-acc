"""Deactivated accounts can't log in or keep using a session (TODO S6)."""

import models
from create_user import set_active
from factories import PASSWORD


def _login(client, username):
    return client.post("/api/auth/login", json={"username": username, "password": PASSWORD})


def test_deactivation_ends_sessions_and_blocks_login(client, db, world):
    assert client.get("/api/projects", headers=world.bu_h).status_code == 200

    set_active(db, world.bu.username, active=False)

    assert client.get("/api/projects", headers=world.bu_h).status_code == 401
    refused = _login(client, world.bu.username)
    assert refused.status_code == 401
    assert refused.json()["detail"] == "Invalid username or password."  # no account-state leak

    set_active(db, world.bu.username, active=True)
    assert _login(client, world.bu.username).status_code == 200


def test_session_stops_working_when_flag_is_cleared_directly(client, db, world):
    user = db.get(models.User, world.bu.id)
    user.is_active = False
    db.commit()

    assert client.get("/api/projects", headers=world.bu_h).status_code == 401


def test_inactive_lead_is_not_offered_or_assignable(client, db, world):
    set_active(db, world.lead_m.username, active=False)

    leads = client.get("/api/project-leads?discipline=mechanical", headers=world.bu_h).json()
    assert world.lead_m.full_name not in {lead["name"] for lead in leads}
    created = client.post("/api/projects", json=world.project_payload(), headers=world.bu_h)
    assert created.status_code == 400, created.text
