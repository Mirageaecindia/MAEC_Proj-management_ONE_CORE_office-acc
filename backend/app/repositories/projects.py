from collections.abc import Collection

from sqlalchemy.orm import Session

import models

# Every table owned by a project. There are no database foreign keys, so a
# project delete removes these rows explicitly.
PROJECT_CHILD_MODELS = (
    models.WbsNode,
    models.WbsNodeHistory,
    models.GanttTask,
    models.ResourceBooking,
    models.TimeLogEntry,
    models.TimeSession,
    models.WeeklyHoursSubmission,
    models.GovernanceAction,
    models.ExtensionRequest,
    models.Notification,
)

# Rows that make a project's history worth keeping: such a project is archived, not deleted.
_HISTORY_MODELS = tuple(model for model in PROJECT_CHILD_MODELS if model is not models.Notification)


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, project_id: int) -> models.Project | None:
        return self.db.get(models.Project, project_id)

    def get_by_code(self, project_code: str) -> models.Project | None:
        return self.db.query(models.Project).filter_by(project_code=project_code).first()

    def list(self, ids: Collection[int] | None = None, *, include_archived: bool = False) -> list[models.Project]:
        """Projects newest first, optionally restricted to `ids`; archived ones only on request."""
        query = self.db.query(models.Project)
        if not include_archived:
            query = query.filter(models.Project.archived_at.is_(None))
        if ids is not None:
            if not ids:
                return []
            query = query.filter(models.Project.id.in_(ids))
        return query.order_by(models.Project.created_at.desc()).all()

    def add(self, project: models.Project) -> None:
        self.db.add(project)

    def has_history(self, project_id: int) -> bool:
        return any(
            self.db.query(model.id).filter_by(project_id=project_id).first() is not None for model in _HISTORY_MODELS
        )

    def reassign_lead_nodes(self, project_id: int, old_lead_id: int, new_lead_id: int, new_lead_name: str) -> int:
        """Move a replaced Lead's WBS nodes to their successor; returns how many moved."""
        return (
            self.db.query(models.WbsNode)
            .filter_by(project_id=project_id, assigned_lead_user_id=old_lead_id)
            .update(
                {models.WbsNode.assigned_lead_user_id: new_lead_id, models.WbsNode.assigned_lead: new_lead_name},
                synchronize_session=False,
            )
        )

    def active_sessions(self, project_id: int) -> list[models.TimeSession]:
        return self.db.query(models.TimeSession).filter_by(project_id=project_id, status="active").all()

    def pending_extension_requests(self, project_id: int) -> list[models.ExtensionRequest]:
        return self.db.query(models.ExtensionRequest).filter_by(project_id=project_id, status="pending").all()

    def delete_with_children(self, project: models.Project) -> None:
        for model in PROJECT_CHILD_MODELS:
            self.db.query(model).filter_by(project_id=project.id).delete(synchronize_session=False)
        self.db.delete(project)
