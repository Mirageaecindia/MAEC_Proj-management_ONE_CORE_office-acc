"""Session handling the BU Head relies on (login, restore, logout)."""

from factories import PASSWORD


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
