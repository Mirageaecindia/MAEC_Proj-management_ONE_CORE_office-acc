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
    models.GovernanceAction,
    models.ExtensionRequest,
    models.Notification,
)


class ProjectRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, project_id: int) -> models.Project | None:
        return self.db.get(models.Project, project_id)

    def get_by_code(self, project_code: str) -> models.Project | None:
        return self.db.query(models.Project).filter_by(project_code=project_code).first()

    def list(self, ids: Collection[int] | None = None) -> list[models.Project]:
        """All projects newest first, optionally restricted to `ids`."""
        query = self.db.query(models.Project)
        if ids is not None:
            if not ids:
                return []
            query = query.filter(models.Project.id.in_(ids))
        return query.order_by(models.Project.created_at.desc()).all()

    def add(self, project: models.Project) -> None:
        self.db.add(project)

    def delete_with_children(self, project: models.Project) -> None:
        for model in PROJECT_CHILD_MODELS:
            self.db.query(model).filter_by(project_id=project.id).delete(synchronize_session=False)
        self.db.delete(project)
