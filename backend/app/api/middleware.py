"""HTTP middleware: the audit log entry for every change request (app/services/audit.py).

One place logs every create, edit, delete, approval, Login/Logout and sign-in, so no
endpoint has to remember to. Reading pages is not logged. Only the request fields named
in app/domain/audit.DETAIL_FIELDS are ever read into the log, never a password, and a
failure to write an entry never fails the request itself.
"""

import json
import logging

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.database import SessionLocal
from app.core.security import bearer_token
from app.services import audit

log = logging.getLogger(__name__)

CHANGES = frozenset({"POST", "PUT", "PATCH", "DELETE"})
JSON_BODY_LIMIT = 64 * 1024  # the log quotes a few short fields; nothing larger is read


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")  # behind the reverse proxy
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _json_body(request: Request) -> dict:
    if "application/json" not in request.headers.get("content-type", ""):
        return {}  # file uploads and forms are never read
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > JSON_BODY_LIMIT:
        return {}
    try:
        data = json.loads(await request.body() or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _before(method: str, path: str, token: str | None) -> audit.Before:
    with SessionLocal() as db:
        before = audit.before_request(db, method, path, token)
        db.expunge_all()  # used after this session closes
        return before


def _template(route) -> str | None:
    """The matched route's path template, e.g. /api/wbs-nodes/{node_id}. Routes included
    through the app's /api router report their path without that prefix."""
    path = getattr(route, "path", None)
    if path is None:
        return None
    return path if path.startswith("/api/") or path == "/api" else f"/api{path}"


def _record(**kwargs) -> None:
    with SessionLocal() as db:
        audit.record(db, **kwargs)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method not in CHANGES or not request.url.path.startswith("/api/"):
            return await call_next(request)
        try:
            body = await _json_body(request)
            token = bearer_token(request.headers.get("authorization"))
            before = await run_in_threadpool(_before, request.method, request.url.path, token)
        except Exception:
            log.exception("Audit log: could not read the request")
            return await call_next(request)

        response = await call_next(request)

        try:
            route = request.scope.get("route")
            await run_in_threadpool(
                _record,
                method=request.method,
                template=_template(route),
                route_name=getattr(route, "name", None),
                path_params=dict(request.scope.get("path_params") or {}),
                body=body,
                status=response.status_code,
                before=before,
                ip=_client_ip(request),
            )
        except Exception:
            log.exception("Audit log: could not write the entry for %s %s", request.method, request.url.path)
        return response
