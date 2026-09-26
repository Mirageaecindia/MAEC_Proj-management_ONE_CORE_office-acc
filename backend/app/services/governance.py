"""BU Head governance: executive dashboard, extension decisions, stop/resume execution.

Every governance event is persisted as a GovernanceAction carrying a snapshot
of the project's consumption at that moment (the audit log).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import models
import schemas
from app.core.errors import NO_PROJECT_ACCESS, ConflictError, ForbiddenError, NotFoundError
from app.core.roles import Role
from app.domain.governance import HARD_STOP, LOCK_MANUAL
from app.repositories.governance import GovernanceRepository
from app.repositories.projects import ProjectRepository
from app.services import notifications as notify
from app.services.access import user_can_access_project
from app.services.governance_monitor import GovernanceMonitor
from app.services.metrics import ProjectMetricsService

PROJECT_NOT_FOUND = "Project not found."

EXTENSION_STATUS_LABELS = {
    "pending": "Pending BU Head Approval",
    "approved": "Approved",
    "rejected": "Rejected",
    "cancelled": "Cancelled (project archived)",
}


def extension_request_output(
    db: Session, request: models.ExtensionRequest, project: models.Project | None = None
) -> dict:
    """API shape of an extension request (also used by the Lead endpoint in main.py)."""
    if project is None:
        project = db.get(models.Project, request.project_id)
    return {
        "id": request.id,
        "project_id": request.project_id,
        "project_name": project.project_name if project else "",
        "requested_by": request.requested_by,
        "requested_by_user_id": request.requested_by_user_id,
        "requested_hours": request.requested_hours,
        "justification": request.justification,
        "status": request.status,
        "status_label": EXTENSION_STATUS_LABELS.get(request.status, request.status),
        "decision_comments": request.decision_comments,
        "decided_by": request.decided_by,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
    }


def find_pending_extension_request(db: Session, project_id: int) -> models.ExtensionRequest | None:
    """Used by the Lead extension-request code in main.py."""
    return GovernanceRepository(db).pending_request(project_id)


def governance_action_output(action: models.GovernanceAction) -> dict:
    return {
        "id": action.id,
        "action": action.action,
        "discipline": action.discipline,
        "consumption_pct": action.consumption_pct,
        "threshold_pct": action.threshold_pct,
        "consumption_hours": action.consumption_hours,
        "comments": action.comments,
        "created_by": action.created_by,
        "extension_request_id": action.extension_request_id,
        "requested_hours": action.requested_hours,
        "created_at": action.created_at.isoformat() if action.created_at else None,
    }


class GovernanceService:
    def __init__(
        self,
        db: Session,
        projects: ProjectRepository,
        governance: GovernanceRepository,
        metrics: ProjectMetricsService,
        monitor: GovernanceMonitor,
    ):
        self.db = db
        self.projects = projects
        self.governance = governance
        self.metrics = metrics
        self.monitor = monitor

    def executive_dashboard(self, user: models.User, project_id: int) -> dict:
        project = self._project(project_id)
        # Commercial data: a Lead may only see projects they are assigned to.
        if user.role == Role.LEAD and not user_can_access_project(self.db, user, project):
            raise ForbiddenError(NO_PROJECT_ACCESS)
        data = self.metrics.dashboard_data(project)
        # A Lead only sees the extension requests they raised themselves.
        requested_by = user.id if user.role == Role.LEAD else None
        requests = self.governance.requests_for_project(project_id, requested_by_user_id=requested_by)
        data["extension_requests"] = [extension_request_output(self.db, r, project) for r in requests]
        data["current_extension_request"] = next(
            (r for r in data["extension_requests"] if r["status"] == "pending"), None
        )
        data["governance_actions"] = [
            governance_action_output(action) for action in self.governance.actions_for_project(project_id)
        ]
        return data

    def decide_extension(
        self, user: models.User, project_id: int, request_id: int, decision: str, comments: str | None
    ) -> dict:
        project = self._project(project_id)
        request = self.governance.get_request(project_id, request_id)
        if not request:
            raise NotFoundError("Extension request not found.")
        if request.status != "pending":
            raise ConflictError("This extension request has already been decided.")

        status = "approved" if decision == "approve" else "rejected"
        decided_by = user.full_name or user.username
        request.status = status
        request.decision_comments = comments
        request.decided_by = decided_by
        request.decided_at = datetime.now(UTC)
        project.extension_status = status
        if status == "approved":
            project.extension_approved_hours = (project.extension_approved_hours or 0) + request.requested_hours

        self.governance.add(
            self._audit_action(
                project,
                "approve_extension" if status == "approved" else "reject_extension",
                comments=comments,
                created_by=decided_by,
                extension_request_id=request.id,
                requested_hours=request.requested_hours,
            )
        )
        # The baseline may have risen: re-arm or re-evaluate alerts first.
        reading = self.monitor.evaluate(project, baseline_raised_by_bu_head=status == "approved")
        still_over = reading.level == HARD_STOP
        if status == "approved" and project.timesheets_soft_locked and not still_over:
            # BU Head decision: an approved extension resumes a stopped project,
            # but never while usage is still at/above 100% of the new baseline.
            self._resume(project, decided_by, "Resumed automatically: extension approved.")
        stays_locked = status == "approved" and project.timesheets_soft_locked
        notify.notify_users(
            self.db,
            [request.requested_by_user_id],
            Role.LEAD,
            notify.EXTENSION_DECIDED,
            f"Extension {status}",
            f"Your request for {request.requested_hours:g} extra hours on '{project.project_name}' was {status}."
            + (f" Comment: {comments}" if comments else "")
            + (
                f" Timesheets stay locked: {reading.consumption_pct:g}% of the new baseline is already used."
                if stays_locked
                else ""
            ),
            project.id,
            decided_by,
        )
        self.db.commit()
        self.db.refresh(request)
        return extension_request_output(self.db, request, project)

    def stop_execution(
        self, user: models.User, project_id: int, payload: schemas.GovernanceActionBase
    ) -> models.GovernanceAction:
        project = self._project(project_id)
        if project.timesheets_soft_locked:
            raise ConflictError("Execution is already stopped for this project.")
        actor = user.full_name or user.username
        action = self._audit_action(
            project, "stop_execution", discipline=payload.discipline, comments=payload.comments, created_by=actor
        )
        self.governance.add(action)
        project.timesheets_soft_locked = True
        project.lock_reason = LOCK_MANUAL
        notify.notify_project_leads(
            self.db,
            project,
            notify.EXECUTION_LOCKED,
            "Execution stopped by BU Head",
            f"Timesheets on '{project.project_name}' are locked. Reason: {payload.comments}",
            actor,
        )
        self.db.commit()
        self.db.refresh(action)
        return action

    def resume_execution(self, user: models.User, project_id: int, comments: str | None) -> models.GovernanceAction:
        project = self._project(project_id)
        if not project.timesheets_soft_locked:
            raise ConflictError("Execution is not stopped for this project.")
        action = self._resume(project, user.full_name or user.username, comments)
        self.db.commit()
        self.db.refresh(action)
        return action

    def _resume(self, project: models.Project, actor: str, comments: str | None) -> models.GovernanceAction:
        """Unlock timesheets, audit it and tell the project's Leads. The caller commits."""
        project.timesheets_soft_locked = False
        project.lock_reason = None
        action = self._audit_action(project, "resume_execution", comments=comments, created_by=actor)
        self.governance.add(action)
        notify.notify_project_leads(
            self.db,
            project,
            notify.EXECUTION_RESUMED,
            "Execution resumed",
            f"Timesheets on '{project.project_name}' are open again." + (f" {comments}" if comments else ""),
            actor,
        )
        return action

    def _project(self, project_id: int) -> models.Project:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError(PROJECT_NOT_FOUND)
        return project

    def _audit_action(self, project: models.Project, action: str, *, discipline: str | None = None, **fields):
        """GovernanceAction with a snapshot of the project's current consumption."""
        status = self.metrics.dashboard_data(project)
        return models.GovernanceAction(
            project_id=project.id,
            action=action,
            discipline=discipline or status["governance_status"]["max_discipline"],
            consumption_pct=status["governance_status"]["consumption_pct"],
            threshold_pct=project.governance_threshold_pct,
            consumption_hours=status["summary"]["approved_hours"],
            **fields,
        )
