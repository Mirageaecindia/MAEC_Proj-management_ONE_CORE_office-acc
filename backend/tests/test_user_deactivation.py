"""Deactivated accounts can't log in or keep using a session (TODO S6)."""

from sqlalchemy import create_engine, inspect, text

import models
from app.core.schema_upgrades import upgrade_schema
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


def test_upgrade_adds_is_active_to_an_existing_users_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))")
        connection.exec_driver_sql("INSERT INTO users (username) VALUES ('old.user')")

    upgrade_schema(engine)
    upgrade_schema(engine)  # idempotent

    assert "is_active" in {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT is_active FROM users")).scalar() == 1
