"""Test doubles for external systems."""

import json
from urllib.parse import quote

import httpx


class FakeDocumentStorage:
    """In-memory DocumentStorage: records calls and returns (or raises) what the test set."""

    def __init__(self):
        self.provision_url = "https://example.sharepoint.com/sites/Automation/Project/Fake%20Project"
        self.provision_error: Exception | None = None
        self.mirror_data: dict = {}
        self.mirror_error: Exception | None = None
        self.provisioned: list[list[str]] = []
        self.mirrored: list[int] = []

    async def provision_project(self, project) -> str:
        self.provisioned.append(json.loads(project.sharepoint_disciplines))
        if self.provision_error:
            raise self.provision_error
        return self.provision_url

    async def get_mirror(self, project) -> dict:
        self.mirrored.append(project.id)
        if self.mirror_error:
            raise self.mirror_error
        return self.mirror_data


class FakeCore:
    """MAEC One Core's /api/gate/check, faked in-process for the gate (app/api/gate.py).

    It answers in the real check's order (maec-one-core, backend/identity/router_gate.py):
    a wrong key or secret is 403 bad_app; a change whose Origin isn't the app's own is
    403 bad_origin; a cookie that names no session is 401 not_signed_in; no seat on the app
    is 403 no_access; otherwise 200 with who the person is. `down` makes it unreachable.
    """

    APP_URL = "http://testserver"  # the app's base_url in Core: the test client's address
    APP_KEY = "projects"
    COOKIE = "maec_one_session"
    SAFE = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, secret: str, public_url: str):
        self.secret = secret
        self.public_url = public_url
        self.sessions: dict[str, dict] = {}  # cookie value -> {"id", "email", "name"}
        self.seats: set[str] = set()  # Core user ids with a seat on Project Management
        self.down = False
        self.calls: list[dict] = []  # the headers of every check the gate made
        self._next = 0

    def sign_in(self, email: str, name: str = "", core_id: str | None = None, seat: bool = True) -> str:
        """A session for this person, as Core's sign-in makes; returns the cookie's value."""
        self._next += 1
        core_id = core_id or f"core-{self._next}"
        token = f"session-{self._next}"
        self.sessions[token] = {"id": core_id, "email": email, "name": name}
        if seat:
            self.seats.add(core_id)
        return token

    def sign_out(self, token: str) -> None:
        self.sessions.pop(token, None)

    def headers(self, token: str, origin: str | None = APP_URL) -> dict:
        """What the browser sends: Core's cookie, and the page's Origin on a change."""
        return {"Cookie": f"{self.COOKIE}={token}", **({"Origin": origin} if origin else {})}

    def _refuse(self, status: int, reason: str, url: str):
        login_url = f"{self.public_url}/?next={quote(url, safe='')}"
        return httpx.Response(status, json={"reason": reason, "login_url": login_url})

    def handler(self, request):
        if self.down:
            raise httpx.ConnectError("Core is down", request=request)
        headers = request.headers
        self.calls.append(dict(headers))
        url = headers.get("x-original-url", "")
        if headers.get("x-maec-app") != self.APP_KEY or headers.get("x-maec-gate-secret") != self.secret:
            return self._refuse(403, "bad_app", url)
        method = headers.get("x-original-method", "GET").upper()
        if method not in self.SAFE and headers.get("x-original-origin", "") != self.APP_URL:
            return self._refuse(403, "bad_origin", url)
        cookies = dict(part.strip().split("=", 1) for part in headers.get("cookie", "").split(";") if "=" in part)
        person = self.sessions.get(cookies.get(self.COOKIE, ""))
        if person is None:
            return self._refuse(401, "not_signed_in", url)
        if person["id"] not in self.seats:
            return self._refuse(403, "no_access", url)
        return httpx.Response(
            200,
            json={"user": dict(person), "org_id": "org-1", "permissions": ["projects:app:use"], "nav_hidden": []},
        )
