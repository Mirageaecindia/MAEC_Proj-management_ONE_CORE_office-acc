"""create_user.py: account creation rules."""

import pytest

from create_user import create_user

PASSWORD = "Longenough1"


def test_new_engineer_appears_in_the_project_lead_dropdown(client, db, make, world):
    employee = make.employee("New Person", discipline="Mechanical Engineer")
    create_user(db, "eng.new", PASSWORD, "New Person", "engineer", employee.id)

    names = {row["name"] for row in client.get("/api/project-leads", headers=world.bu_h).json()}
    assert "New Person" in names


def test_only_bu_head_and_engineer_accounts_exist(db):
    with pytest.raises(SystemExit, match="Invalid role"):
        create_user(db, "someone", PASSWORD, "Someone", "lead", None)


def test_engineer_must_link_to_an_existing_employee(db, make):
    with pytest.raises(SystemExit, match="must be linked"):
        create_user(db, "eng.x", PASSWORD, "Eng", "engineer", None)
    with pytest.raises(SystemExit, match="No employee"):
        create_user(db, "eng.x", PASSWORD, "Eng", "engineer", 999999)

    employee = make.employee("Real Person")
    assert create_user(db, "eng.x", PASSWORD, "Eng", "engineer", employee.id).employee_id == employee.id


def test_short_password_and_duplicate_username_are_rejected(db, make):
    make.user("taken", "bu_head", "Taken")
    with pytest.raises(SystemExit, match="at least 8"):
        create_user(db, "new", "short", "X", "bu_head", None)
    with pytest.raises(SystemExit, match="already exists"):
        create_user(db, "taken", PASSWORD, "X", "bu_head", None)
