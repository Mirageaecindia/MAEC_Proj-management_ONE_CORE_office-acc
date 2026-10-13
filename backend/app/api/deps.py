"""Composition root: builds services from their repositories and adapters.

Routers depend on these factories, so a test (or a future implementation)
can replace any collaborator with `app.dependency_overrides`.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.integrations.sharepoint import DocumentStorage, get_document_storage
from app.repositories.bookings import BookingRepository
from app.repositories.governance import GovernanceRepository
from app.repositories.notifications import NotificationRepository
from app.repositories.projects import ProjectRepository
from app.repositories.tracking import TrackingRepository
from app.repositories.users import UserRepository
from app.repositories.work import WorkRepository
from app.services import archive_guard
from app.services.audit import AuditLog
from app.services.booking_approval import BookingApprovalService
from app.services.documents import ProjectDocumentService
from app.services.governance import GovernanceService
from app.services.governance_monitor import GovernanceMonitor
from app.services.metrics import ProjectMetricsService
from app.services.notifications import NotificationService
from app.services.projects import ProjectService
from app.services.provisioning import Provisioning
from app.services.rejected_hours import RejectedHours
from app.services.team_members import TeamMembers
from app.services.tracking import TrackingService
from app.services.work_summary import WorkSummaryService

archive_guard.install()  # archived projects are read-only for every database session


def get_project_service(
    db: Session = Depends(get_db), storage: DocumentStorage = Depends(get_document_storage)
) -> ProjectService:
    return ProjectService(
        db,
        ProjectRepository(db),
        UserRepository(db),
        BookingRepository(db),
        storage,
        GovernanceMonitor(db, WorkRepository(db)),
    )


def get_document_service(
    db: Session = Depends(get_db), storage: DocumentStorage = Depends(get_document_storage)
) -> ProjectDocumentService:
    return ProjectDocumentService(db, ProjectRepository(db), storage)


def get_governance_service(db: Session = Depends(get_db)) -> GovernanceService:
    work = WorkRepository(db)
    return GovernanceService(
        db, ProjectRepository(db), GovernanceRepository(db), ProjectMetricsService(work), GovernanceMonitor(db, work)
    )


def get_booking_approval_service(db: Session = Depends(get_db)) -> BookingApprovalService:
    return BookingApprovalService(
        db, ProjectRepository(db), BookingRepository(db), NotificationRepository(db), UserRepository(db)
    )


def get_notification_service(db: Session = Depends(get_db)) -> NotificationService:
    return NotificationService(db, NotificationRepository(db))


def get_work_summary_service(db: Session = Depends(get_db)) -> WorkSummaryService:
    return WorkSummaryService(ProjectRepository(db), WorkRepository(db))


def get_tracking_service(db: Session = Depends(get_db)) -> TrackingService:
    return TrackingService(db, TrackingRepository(db))


def get_provisioning(db: Session = Depends(get_db)) -> Provisioning:
    return Provisioning(db)


def get_rejected_hours_service(db: Session = Depends(get_db)) -> RejectedHours:
    return RejectedHours(db)


def get_team_members_service(db: Session = Depends(get_db)) -> TeamMembers:
    return TeamMembers(db)


def get_audit_log(db: Session = Depends(get_db)) -> AuditLog:
    return AuditLog(db)
