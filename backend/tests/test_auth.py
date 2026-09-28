"""Session handling the BU Head relies on (login, restore, logout)."""

import models
from auth import hash_password
from factories import PASSWORD

# New accounts added alongside the pre-existing cast. Each test builds its own
# copies so the suite is self-contained and never depends on (or touches) the
# pre-existing accounts created by the `world` fixture.
NEW_LEAD_PASSWORD = "pass123"
NEW_LEADS = [
    ("kiran", NEW_LEAD_PASSWORD, "Kiran", "Electrical"),
    ("naveen", NEW_LEAD_PASSWORD, "Naveen", "Mechanical"),
    ("pallavi", NEW_LEAD_PASSWORD, "Pallavi", "BIM"),
]
NEW_ENGINEERS = [
    ("sanjana", NEW_LEAD_PASSWORD, "Sanjana"),
    ("vivek", NEW_LEAD_PASSWORD, "Vivek"),
    ("ritu", NEW_LEAD_PASSWORD, "Ritu"),
]


def _make_new_accounts(db, make):
    """Create the 3 new Leads and 3 new Engineers (with linked employees)."""
    rows = {}
    for username, password, full_name, discipline in NEW_LEADS:
        rows[username] = models.User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role="lead",
            discipline=discipline,
            employee_id=make.employee(full_name, discipline=f"{discipline} Lead").id,
        )
    for username, password, full_name in NEW_ENGINEERS:
        employee = make.employee(full_name)
        rows[username] = models.User(
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role="engineer",
            employee_id=employee.id,
        )
    for row in rows.values():
        db.add(row)
    db.commit()
    for row in rows.values():
        db.refresh(row)
    return rows


def _login(client, username, password=NEW_LEAD_PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _login_headers(client, username):
    response = _login(client, username)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_login_returns_token_and_role(client, world):
    response = client.post("/api/auth/login", json={"username": "buhead", "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "bu_head"
    assert body["full_name"] == "Test BU Head"
    assert body["engineer_id"] is None
    assert len(body["token"]) == 64


def test_login_rejects_wrong_password(client, world):
    response = client.post("/api/auth/login", json={"username": "buhead", "password": "wrong"})

    assert response.status_code == 401


def test_me_restores_session(client, world):
    response = client.get("/api/auth/me", headers=world.bu_h)

    assert response.status_code == 200
    assert response.json()["role"] == "bu_head"


def test_logout_invalidates_token(client, world):
    assert client.post("/api/auth/logout", headers=world.bu_h).status_code == 200

    assert client.get("/api/auth/me", headers=world.bu_h).status_code == 401


def test_protected_endpoints_require_token(client, world):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/projects", headers={"Authorization": "Bearer nope"}).status_code == 401


# --- New accounts (Leads: kiran / naveen / pallavi, Engineers: sanjana / vivek / ritu) ---


def test_new_leads_and_engineers_can_log_in(client, db, make):
    accounts = _make_new_accounts(db, make)

    for username, password, full_name, _discipline in NEW_LEADS:
        response = _login(client, username, password)
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "lead"
        assert body["full_name"] == full_name
        assert body["engineer_id"] is None

    for username, password, full_name in NEW_ENGINEERS:
        response = _login(client, username, password)
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "engineer"
        assert body["full_name"] == full_name
        assert body["engineer_id"] == accounts[username].employee_id

    assert _login(client, "kiran", "wrong-password").status_code == 401


def test_new_accounts_appear_in_the_lead_dropdown(client, db, make, world):
    _make_new_accounts(db, make)

    names = {lead["name"] for lead in client.get("/api/project-leads", headers=world.bu_h).json()}

    # Anyone with an employee record can lead a project, whatever their account role.
    assert {"Kiran", "Naveen", "Pallavi", "Sanjana", "Vivek", "Ritu", "Anita Kumar", "Arjun Mehta"} <= names


def test_new_engineers_appear_in_employee_dropdowns(client, db, make, world):
    _make_new_accounts(db, make)
    world.create_project()  # only someone leading a project books engineers
    world.create_project()  # only someone leading a project books engineers

    employees = {employee["name"] for employee in client.get("/api/employees", headers=world.lead_h).json()}
    engineers = {employee["name"] for employee in client.get("/api/engineers", headers=world.lead_h).json()}

    expected_new = {"Sanjana", "Vivek", "Ritu"}
    assert expected_new <= employees
    assert expected_new <= engineers
    assert {"Arjun Mehta", "Ravi Kumar"} <= employees


def test_project_scoped_to_new_lead_only(client, db, make, world):
    accounts = _make_new_accounts(db, make)
    kiran = accounts["kiran"]

    project = world.create_project(
        project_lead_electrical="Kiran",
        project_lead_electrical_user_id=kiran.id,
    )

    kiran_sees = {p["id"] for p in client.get("/api/projects", headers=_login_headers(client, "kiran")).json()}
    assert project["id"] in kiran_sees

    for other in ("naveen", "pallavi"):
        other_ids = {p["id"] for p in client.get("/api/projects", headers=_login_headers(client, other)).json()}
        assert project["id"] not in other_ids
        assert client.get(f"/api/projects/{project['id']}", headers=_login_headers(client, other)).status_code == 403

    # existing lead accounts are not affected by the new lead assignment
    assert client.get("/api/projects", headers=world.other_lead_h).json() == []


def test_engineer_assignment_scopes_project_to_that_engineer_only(client, db, make, world):
    accounts = _make_new_accounts(db, make)
    kiran = accounts["kiran"]

    project = world.create_project(
        project_lead_electrical="Kiran",
        project_lead_electrical_user_id=kiran.id,
    )

    kiran_h = _login_headers(client, "kiran")
    sanjana_employee_id = accounts["sanjana"].employee_id
    booking = client.post(
        f"/api/projects/{project['id']}/resource-bookings",
        json={"employee_id": sanjana_employee_id, "planned_hours": 40, "utilization_rate": 50},
        headers=kiran_h,
    )
    assert booking.status_code == 200, booking.text

    booked_names = {
        engineer["name"]
        for engineer in client.get(f"/api/projects/{project['id']}/booked-engineers", headers=kiran_h).json()
    }
    assert "Sanjana" in booked_names

    # Lead assignment (draft booking) alone grants NO project access — the
    # project must not appear for the engineer until the BU Head approves.
    assert client.get("/api/projects", headers=_login_headers(client, "sanjana")).json() == []

    submit = client.post(f"/api/projects/{project['id']}/resource-bookings/submit", headers=kiran_h)
    assert submit.status_code == 200
    assert client.get("/api/projects", headers=_login_headers(client, "sanjana")).json() == []

    approve = client.post(f"/api/projects/{project['id']}/resource-bookings/approve", headers=world.bu_h)
    assert approve.status_code == 200

    sanjana_ids = {p["id"] for p in client.get("/api/projects", headers=_login_headers(client, "sanjana")).json()}
    assert project["id"] in sanjana_ids

    for other in ("vivek", "ritu"):
        other_ids = {p["id"] for p in client.get("/api/projects", headers=_login_headers(client, other)).json()}
        assert project["id"] not in other_ids


def test_status_change_endpoints_reject_missing_and_invalid_sessions(client, make, world):
    """The Engineer's task status-change actions (advance, subtask Done,
    approve) must reject missing / stale / invalid sessions with 401 and the
    re-login message, and accept a real Engineer session via /api/auth/login."""
    project = world.create_project()
    node = make.wbs_node(project["id"], world.lead_e, engineer=world.emp1)

    advance_url = f"/api/wbs-nodes/{node.id}/advance-status"
    approve_url = f"/api/wbs-nodes/{node.id}/approve"
    status_payload = {"new_status": "In-Progress"}

    # Missing session
    for url, payload in ((advance_url, status_payload), (approve_url, status_payload)):
        response = client.post(url, json=payload)
        assert response.status_code == 401
        assert "Session expired or invalid" in response.json()["detail"]

    # Client-side stale / fabricated session
    bad_headers = {"Authorization": "Bearer deadbeefcafe"}
    for url, payload in ((advance_url, status_payload), (approve_url, status_payload)):
        response = client.post(url, json=payload, headers=bad_headers)
        assert response.status_code == 401

    # Session that was valid but has since logged out server-side
    assert client.post("/api/auth/logout", headers=world.eng_h).status_code == 200
    assert client.post(advance_url, json=status_payload, headers=world.eng_h).status_code == 401

    # A real Engineer session (fresh login through the auth API) succeeds
    login = client.post("/api/auth/login", json={"username": "eng.arjun", "password": PASSWORD})
    assert login.status_code == 200
    engineer_h = {"Authorization": f"Bearer {login.json()['token']}"}

    advanced = client.post(advance_url, json=status_payload, headers=engineer_h)
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["ok"] is True
