from sqlalchemy.orm import Session

import models
from app.core.roles import Role


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_leads(self, discipline: str | None = None) -> list[models.User]:
        """Active lead accounts, optionally of one discipline."""
        query = self.db.query(models.User).filter(models.User.role == Role.LEAD, models.User.is_active.is_(True))
        if discipline:
            query = query.filter(models.User.discipline == discipline)
        return query.order_by(models.User.username).all()

    def get_lead(self, user_id: int) -> models.User | None:
        return self.db.query(models.User).filter_by(id=user_id, role=Role.LEAD, is_active=True).first()
