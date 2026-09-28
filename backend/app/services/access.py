"""Who may see which project, and in which role.

Lead and engineer are roles ON A PROJECT, not account types: the same person
can lead one project and work as an engineer on another.
- BU Head: every project.
- Lead of a project: their user id is one of its three project leads, or the
  assigned lead of any of its WBS nodes. Legacy rows without a user id fall
  back to matching the lead's full name.
- Engineer on a project: their employee id has an APPROVED resource booking
  there. BU Head approval is the only event that grants it; a draft/pending
  booking or a WBS task alone grants nothing.
- Leading a project wins over a booking on it.
- Archived projects are closed to everyone but the BU Head (read-only, see
  app/services/archive_guard.py).

Shared with the Lead/Engineer endpoints in main.py, which import these.
"""

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

import models
from app.core.errors import ForbiddenError
from app.core.roles import Role

LEAD, ENGINEER = "lead", "engineer"  # a person's role on a project
NOT_PROJECT_LEAD = "Only a lead of this project can do this."


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


def project_roles(db: Session, user: models.User) -> dict[int, str]:
    """Project id -> LEAD or ENGINEER for every active project this person works on (BU Head: empty)."""
    if user.role == Role.BU_HEAD:
        return {}
    roles = dict.fromkeys(engineer_approved_project_ids(db, user.employee_id), ENGINEER) if user.employee_id else {}
    roles.update(dict.fromkeys(lead_project_ids(db, user), LEAD))
    return roles


def project_role(db: Session, user: models.User, project_id: int) -> str | None:
    """The user's role on one project: bu_head, LEAD, ENGINEER, or None (no access)."""
    if user.role == Role.BU_HEAD:
        return Role.BU_HEAD
    return project_roles(db, user).get(project_id)


def require_project_lead(db: Session, user: models.User, project_id: int) -> None:
    if project_role(db, user, project_id) != LEAD:
        raise ForbiddenError(NOT_PROJECT_LEAD)


def leads_any_project(db: Session, user: models.User) -> bool:
    return user.role != Role.BU_HEAD and bool(lead_project_ids(db, user))


def visible_project_ids(db: Session, user: models.User) -> set[int] | None:
    """Project ids the user may see, or None when they may see every project."""
    if user.role == Role.BU_HEAD:
        return None
    return set(project_roles(db, user))


def user_can_access_project(db: Session, user: models.User, project: models.Project) -> bool:
    """Server-side access gate for project-scoped endpoints."""
    return user.role == Role.BU_HEAD or project.id in project_roles(db, user)
