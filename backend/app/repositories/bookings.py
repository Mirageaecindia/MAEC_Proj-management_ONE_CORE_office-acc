from sqlalchemy.orm import Session

import models


class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    def for_project(self, project_id: int) -> list[models.ResourceBooking]:
        return self.db.query(models.ResourceBooking).filter_by(project_id=project_id).all()

    def approval_statuses(self, project_id: int) -> list[str]:
        rows = self.db.query(models.ResourceBooking.approval_status).filter_by(project_id=project_id).all()
        return [status for (status,) in rows]
