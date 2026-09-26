"""Who may see which project.

- BU Head: every project.
- Lead: projects where their user id is one of the three project leads, or
  the assigned lead of any WBS node. Legacy rows without a user id fall back
  to matching the lead's full name.
- Engineer: only projects where their employee id has an APPROVED resource
  booking. BU Head approval of the Lead's assignment is the only event that
  grants access; a draft/pending booking or a WBS task alone grants none.
- Archived projects are closed to Leads and Engineers; only the BU Head sees
  them (read-only, see app/services/archive_guard.py).

Shared with the Lead/Engineer endpoints in main.py, which import these.
"""

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
from app.core.roles import Role


def engineer_wbs_condition(employee_id: int):
    """SQL condition: WBS node assigned to the engineer's employee id."""
    return models.WbsNode.assigned_engineer_id == employee_id


def engineer_wbs_ids(db: Session, employee_id: int) -> set[int]:
    """Projects where the engineer has a WBS node assigned."""
    rows = db.query(models.WbsNode.project_id).filter(engineer_wbs_condition(employee_id)).distinct().all()
    return {project_id for (project_id,) in rows}


def engineer_approved_project_ids(db: Session, employee_id: int) -> set[int]:
    """Projects where the engineer has an APPROVED resource booking (their only access grant)."""
    rows = (
        db.query(models.ResourceBooking.project_id)
        .join(models.Project, models.Project.id == models.ResourceBooking.project_id)
        .filter(
            models.ResourceBooking.employee_id == employee_id,
            models.ResourceBooking.approval_status == "approved",
            models.Project.archived_at.is_(None),
        )
        .distinct()
        .all()
    )
    return {project_id for (project_id,) in rows}


def lead_project_ids(db: Session, user: models.User) -> set[int]:
    """Projects assigned to this lead, matched by real user id (name fallback for legacy rows)."""
    if not user:
        return set()
    name = user.full_name
    P = models.Project

    project_condition = or_(
        P.project_lead_electrical_user_id == user.id,
        P.project_lead_mechanical_user_id == user.id,
        P.project_lead_bim_user_id == user.id,
    )
    if name:
        project_condition = or_(
            project_condition,
            and_(P.project_lead_electrical_user_id.is_(None), P.project_lead_electrical == name),
            and_(P.project_lead_mechanical_user_id.is_(None), P.project_lead_mechanical == name),
            and_(P.project_lead_bim_user_id.is_(None), P.project_lead_bim == name),
        )
    active = P.archived_at.is_(None)
    as_project_lead = {project_id for (project_id,) in db.query(P.id).filter(project_condition, active).all()}

    node_conditions = [models.WbsNode.assigned_lead_user_id == user.id]
    if name:
        node_conditions.append(
            and_(models.WbsNode.assigned_lead_user_id.is_(None), models.WbsNode.assigned_lead == name)
        )
    rows = (
        db.query(models.WbsNode.project_id)
        .join(P, P.id == models.WbsNode.project_id)
        .filter(or_(*node_conditions), active)
        .distinct()
        .all()
    )
    return as_project_lead | {project_id for (project_id,) in rows}


def visible_project_ids(db: Session, user: models.User) -> set[int] | None:
    """Project ids the user may see, or None when they may see every project."""
    if user.role == Role.LEAD:
        return lead_project_ids(db, user)
    if user.role == Role.ENGINEER:
        if not user.employee_id:
            return set()
        return engineer_approved_project_ids(db, user.employee_id)
    return None


def user_can_access_project(db: Session, user: models.User, project: models.Project) -> bool:
    """Server-side access gate for project-scoped endpoints."""
    if user.role == Role.BU_HEAD:
        return True
    if user.role == Role.LEAD:
        return bool(user.id) and project.id in lead_project_ids(db, user)
    if user.role == Role.ENGINEER:
        return bool(user.employee_id) and project.id in visible_project_ids(db, user)
    return False
