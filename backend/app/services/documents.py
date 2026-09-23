"""Read-only view of a project's SharePoint folder (the SharePoint Mirror page)."""

import logging

from sqlalchemy.orm import Session

import models
from app.core.errors import NO_PROJECT_ACCESS, ForbiddenError, IntegrationError, NotFoundError, UnexpectedError
from app.core.roles import Role
from app.integrations.sharepoint import DocumentStorage, SharePointError
from app.repositories.projects import ProjectRepository
from app.services.access import user_can_access_project

logger = logging.getLogger(__name__)


class ProjectDocumentService:
    def __init__(self, db: Session, projects: ProjectRepository, storage: DocumentStorage):
        self.db = db
        self.projects = projects
        self.storage = storage

    async def mirror(self, user: models.User, project_id: int) -> dict:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError("Project not found")
        if user.role != Role.BU_HEAD and not user_can_access_project(self.db, user, project):
            raise ForbiddenError(NO_PROJECT_ACCESS)
        try:
            return await self.storage.get_mirror(project)
        except SharePointError as exc:
            logger.error("SharePoint mirror error for project %s: %s", project.project_code, exc)
            raise IntegrationError(f"SharePoint error: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected error fetching SharePoint mirror for project %s", project.project_code)
            raise UnexpectedError(f"Unexpected error: {exc}") from exc
