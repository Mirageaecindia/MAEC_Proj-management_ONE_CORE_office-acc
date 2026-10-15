from sqlalchemy.orm import Session

import models


class EstimationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list(self) -> list[models.ProjectEstimation]:
        """Every estimation, the most recently changed first."""
        estimation = models.ProjectEstimation
        return self.db.query(estimation).order_by(estimation.updated_at.desc(), estimation.id.desc()).all()

    def get(self, estimation_id: int) -> models.ProjectEstimation | None:
        return self.db.get(models.ProjectEstimation, estimation_id)

    def add(self, estimation: models.ProjectEstimation) -> None:
        self.db.add(estimation)

    def delete(self, estimation: models.ProjectEstimation) -> None:
        self.db.delete(estimation)
