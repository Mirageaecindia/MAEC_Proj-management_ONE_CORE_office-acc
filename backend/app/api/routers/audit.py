"""The audit log: each person's own activity, and everyone's for the BU Head (app/services/audit.py)."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

import models
from app.api.deps import get_audit_log
from app.core.security import get_current_user
from app.domain.audit import CATEGORIES
from app.services.audit import AuditFilter, AuditLog

router = APIRouter(tags=["audit"])


def filters(
    project_id: int | None = None,
    category: str | None = Query(default=None, pattern="^(" + "|".join(CATEGORIES) + ")$"),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditFilter:
    return AuditFilter(
        project_id=project_id,
        category=category,
        date_from=date_from,
        date_to=date_to,
        text=q,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/mine")
def my_activity(
    chosen: AuditFilter = Depends(filters),
    user: models.User = Depends(get_current_user),
    service: AuditLog = Depends(get_audit_log),
) -> dict:
    """The signed-in person's own actions, newest first."""
    return service.mine(user, chosen)


@router.get("/audit")
def everyones_activity(
    user_id: int | None = None,
    chosen: AuditFilter = Depends(filters),
    user: models.User = Depends(get_current_user),
    service: AuditLog = Depends(get_audit_log),
) -> dict:
    """Everyone's actions, newest first (BU Head only)."""
    chosen.user_id = user_id
    return service.everyone(user, chosen)


@router.get("/audit/export")
def export_activity(
    user_id: int | None = None,
    chosen: AuditFilter = Depends(filters),
    user: models.User = Depends(get_current_user),
    service: AuditLog = Depends(get_audit_log),
) -> Response:
    """The filtered entries as a CSV file (BU Head only)."""
    chosen.user_id = user_id
    return Response(
        content=service.export_csv(user, chosen),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="promanage-audit-log.csv"'},
    )
