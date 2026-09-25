"""BU Head governance: executive dashboard, extension decisions, stop execution.

Every governance event is persisted as a GovernanceAction carrying a snapshot
of the project's consumption at that moment (the audit log).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import models
import schemas
from app.core.errors import ConflictError, NotFoundError
from app.core.roles import Role
from app.repositories.governance import GovernanceRepository
from app.repositories.projects import ProjectRepository
from app.services.metrics import ProjectMetricsService

PROJECT_NOT_FOUND = "Project not found."

EXTENSION_STATUS_LABELS = {
    "pending": "Pending BU Head Approval",
    "approved": "Approved",
    "rejected": "Rejected",
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
    ):
        self.db = db
        self.projects = projects
        self.governance = governance
        self.metrics = metrics

    def executive_dashboard(self, user: models.User, project_id: int) -> dict:
        project = self._project(project_id)
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
        self.db.commit()
        self.db.refresh(request)
        return extension_request_output(self.db, request, project)

    def stop_execution(
        self, user: models.User, project_id: int, payload: schemas.GovernanceActionBase
    ) -> models.GovernanceAction:
        project = self._project(project_id)
        action = self._audit_action(
            project,
            "stop_execution",
            discipline=payload.discipline,
            comments=payload.comments,
            created_by=user.full_name,
        )
        self.governance.add(action)
        project.timesheets_soft_locked = True
        self.db.commit()
        self.db.refresh(action)
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
            consumption_pct=status["governance_status"]["max_discipline_pct"],
            threshold_pct=project.governance_threshold_pct,
            consumption_hours=status["summary"]["logged_hours"],
            **fields,
        )
