"""The gate: on every request, ask MAEC One Core who this browser is.

Adapted from Engineering Tools (backend/maec_auth/gate.py). Project Management signs nobody
in. Core's session cookie (maec_one_session) is set for the parent domain, so the browser
sends it here too; it is only a random id, and the session it names lives in Core's
database. So this layer forwards the browser's Cookie header to Core's /api/gate/check, with
this app's key and secret, and acts on the answer:

    200   who the person is and what they may do -> request.state.maec
    401   not signed in -> 401 + Core's {reason, login_url}: the frontend sends the window there
    403   no access, or a request from a foreign Origin -> 403 + Core's {reason, login_url}
    anything else, or no answer within 3 s -> 503 "MAEC One is unavailable". Never a pass.

Nothing is cached: a revoked seat or a sign-out at Core bites on the very next request.
Who the person is in THIS app (their users row, role, projects) is decided afterwards, from
Core's answer, by app/services/identity.py.

The backend serves only the API (the frontend container serves the pages), so every refusal
is JSON. Only /health, the container's health probe, is answered without asking Core.
"""

import asyncio
import logging

import httpx
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import GateConfigError, get_settings, require_gate_settings

log = logging.getLogger("maec.gate")

TIMEOUT_SECONDS = 3.0
EXEMPT = frozenset({"/health"})  # must keep answering when Core is down
UNAVAILABLE = "MAEC One is unavailable"
NO_STORE = {"Cache-Control": "no-store"}

# What a refusal's reason means to a person.
REASONS = {
    "not_signed_in": "You are not signed in to MAEC One.",
    "password_change": "Set a new password at MAEC One first.",
    "no_access": "Your account does not have access to Project Management.",
    "org_suspended": "Your organisation's access to MAEC One is suspended.",
    "bad_origin": "This request did not come from Project Management itself.",
    "bad_app": "Project Management is not set up correctly with MAEC One.",
}

# Tests swap this for an httpx.MockTransport: Core faked in-process.
transport: httpx.AsyncBaseTransport | None = None

# One pooled client per event loop: uvicorn runs one loop per process, so in practice one
# client; the loop check only matters where loops come and go (the test client).
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def exempt(path: str) -> bool:
    return path in EXEMPT


def _http() -> httpx.AsyncClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient(transport=transport, timeout=TIMEOUT_SECONDS)
        _client_loop = loop
    return _client


def reset_client() -> None:
    """Forget the pooled client, so the next call builds one with the current transport. For tests."""
    global _client, _client_loop
    _client, _client_loop = None, None


async def ask_core(request: Request) -> httpx.Response:
    """Forward this request's credentials to Core. Raises on no answer.

    X-Original-URL is request.url: the address the browser used, once app/api/proxy.py has
    applied a trusted proxy's X-Forwarded-Proto and -Host (and ignored anyone else's)."""
    settings = get_settings()
    require_gate_settings(settings)
    headers = {
        "X-MAEC-App": settings.maec_app_key,
        "X-MAEC-Gate-Secret": settings.maec_gate_secret,
        "X-Original-URL": str(request.url),
        "X-Original-Method": request.method,
    }
    if cookie := request.headers.get("cookie"):
        headers["Cookie"] = cookie
    if origin := request.headers.get("origin"):
        headers["X-Original-Origin"] = origin  # Core refuses a change from any page but this app's
    return await _http().get(f"{settings.core_url.rstrip('/')}/api/gate/check", headers=headers)


def unavailable() -> JSONResponse:
    return JSONResponse({"detail": UNAVAILABLE}, status_code=503, headers=NO_STORE)


def refused(status: int, body: dict) -> JSONResponse:
    reason = str(body.get("reason", ""))
    login_url = str(body.get("login_url", ""))
    detail = REASONS.get(reason, f"MAEC One refused access ({reason}).")
    return JSONResponse(
        {"detail": detail, "reason": reason, "login_url": login_url}, status_code=status, headers=NO_STORE
    )


async def inspect(request: Request) -> JSONResponse | None:
    """A response to send instead, or None to let the request through with request.state.maec."""
    try:
        answer = await ask_core(request)
    except GateConfigError as exc:
        log.error("gate is not configured: %s", exc)
        return unavailable()
    except httpx.HTTPError as exc:
        log.warning("MAEC One did not answer the gate check: %r", exc)
        return unavailable()

    if answer.status_code in (401, 403):
        try:
            body = answer.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if body.get("reason") == "bad_app":  # our own key or secret is wrong: a deployment fault
            log.error("MAEC One rejected this app's key or gate secret")
        return refused(answer.status_code, body)

    if answer.status_code != 200:
        log.warning("gate check answered %s", answer.status_code)
        return unavailable()
    try:
        maec = answer.json()
    except ValueError:
        log.warning("gate check answered 200 with no JSON")
        return unavailable()
    user = maec.get("user") if isinstance(maec, dict) else None
    if not isinstance(user, dict) or not user.get("id") or not user.get("email"):
        log.warning("gate check answered 200 without a user")
        return unavailable()
    request.state.maec = maec
    return None


class GateMiddleware(BaseHTTPMiddleware):
    """Refuse anything from a browser MAEC One has not vouched for."""

    async def dispatch(self, request: Request, call_next):
        if exempt(request.url.path):
            return await call_next(request)
        refusal = await inspect(request)
        response = refusal if refusal is not None else await call_next(request)
        # The answer depended on the cookie: a cache keyed only on the URL must not serve one
        # person's answer to another.
        response.headers.add_vary_header("Cookie")
        return response
