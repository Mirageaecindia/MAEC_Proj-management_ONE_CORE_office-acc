from sqlalchemy.orm import Session

import models

PENDING = "pending"


class GovernanceRepository:
    """Extension requests and the governance audit log."""

    def __init__(self, db: Session):
        self.db = db

    def pending_request(self, project_id: int) -> models.ExtensionRequest | None:
        return (
            self.db.query(models.ExtensionRequest)
            .filter_by(project_id=project_id, status=PENDING)
            .order_by(models.ExtensionRequest.requested_at.desc(), models.ExtensionRequest.id.desc())
            .first()
        )

    def get_request(self, project_id: int, request_id: int) -> models.ExtensionRequest | None:
        return self.db.query(models.ExtensionRequest).filter_by(id=request_id, project_id=project_id).first()

    def requests_for_project(
        self, project_id: int, requested_by_user_id: int | None = None
    ) -> list[models.ExtensionRequest]:
        query = self.db.query(models.ExtensionRequest).filter_by(project_id=project_id)
        if requested_by_user_id is not None:
            query = query.filter_by(requested_by_user_id=requested_by_user_id)
        return query.order_by(models.ExtensionRequest.requested_at.desc(), models.ExtensionRequest.id.desc()).all()

    def actions_for_project(self, project_id: int) -> list[models.GovernanceAction]:
        return (
            self.db.query(models.GovernanceAction)
            .filter_by(project_id=project_id)
            .order_by(models.GovernanceAction.created_at.desc(), models.GovernanceAction.id.desc())
            .all()
        )

    def add(self, row: models.ExtensionRequest | models.GovernanceAction) -> None:
        self.db.add(row)
