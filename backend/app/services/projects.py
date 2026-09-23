"""Project lifecycle owned by the BU Head: lead lookup, create (with SharePoint
provisioning), list, read and delete."""

import json
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from app.core.errors import NO_PROJECT_ACCESS, BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.integrations.sharepoint import DocumentStorage, SharePointError
from app.repositories.projects import ProjectRepository
from app.repositories.users import UserRepository
from app.services.access import user_can_access_project, visible_project_ids

logger = logging.getLogger(__name__)

DUPLICATE_CODE = "Project Code already exists"
PROJECT_NOT_FOUND = "Project not found"

# Query-string discipline -> users.discipline value.
LEAD_DISCIPLINES = {"electrical": "Electrical", "mechanical": "Mechanical", "bim": "BIM"}


class ProjectService:
    def __init__(self, db: Session, projects: ProjectRepository, users: UserRepository, storage: DocumentStorage):
        self.db = db
        self.projects = projects
        self.users = users
        self.storage = storage

    def list_leads(self, discipline: str | None) -> list[schemas.ProjectLeadOut]:
        """Real Lead accounts for the Create Project dropdowns (unknown disciplines are ignored)."""
        target = LEAD_DISCIPLINES.get(discipline.strip().lower()) if discipline else None
        return [
            schemas.ProjectLeadOut(id=lead.id, name=lead.full_name or lead.username, title=lead.discipline)
            for lead in self.users.list_leads(target)
        ]

    async def create(self, payload: schemas.ProjectCreatePayload) -> dict:
        if self.projects.get_by_code(payload.project_code):
            raise ConflictError(DUPLICATE_CODE)

        electrical = self._resolve_lead(payload.project_lead_electrical_user_id, payload.project_lead_electrical)
        mechanical = self._resolve_lead(payload.project_lead_mechanical_user_id, payload.project_lead_mechanical)
        bim = self._resolve_lead(payload.project_lead_bim_user_id, payload.project_lead_bim)

        project = models.Project(
            project_name=payload.project_name,
            project_code=payload.project_code,
            client_organization=payload.client_customer,
            # The single legacy project_lead column keeps the primary (electrical) lead.
            project_lead=electrical[0],
            start_date=payload.target_start_date,
            project_lead_electrical=electrical[0],
            project_lead_mechanical=mechanical[0],
            project_lead_bim=bim[0],
            project_lead_electrical_user_id=electrical[1],
            project_lead_mechanical_user_id=mechanical[1],
            project_lead_bim_user_id=bim[1],
            sharepoint_disciplines=json.dumps(payload.sharepoint_disciplines)
            if payload.sharepoint_disciplines
            else None,
            contract_value=payload.total_contract_value,
            contract_currency=payload.contract_currency,
            governance_threshold_pct=payload.alert_override_threshold_pct,
            target_effort_hours=payload.target_effort_hours,
        )
        try:
            self.projects.add(project)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(DUPLICATE_CODE) from exc
        self.db.refresh(project)

        data = schemas.ProjectOut.model_validate(project).model_dump()
        data.update(
            await self._provision(project) if payload.sharepoint_disciplines else _sharepoint_result("not_requested")
        )
        return data

    def list_for(self, user: models.User) -> list[models.Project]:
        return self.projects.list(visible_project_ids(self.db, user))

    def get_for(self, user: models.User, project_id: int) -> models.Project:
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError(PROJECT_NOT_FOUND)
        if not user_can_access_project(self.db, user, project):
            raise ForbiddenError(NO_PROJECT_ACCESS)
        return project

    def delete(self, project_id: int) -> dict:
        """Delete the project and every row it owns. The SharePoint folder is kept."""
        project = self.projects.get(project_id)
        if not project:
            raise NotFoundError(PROJECT_NOT_FOUND)
        self.projects.delete_with_children(project)
        self.db.commit()
        return {"ok": True, "deleted_project_id": project_id}

    def _resolve_lead(self, user_id: int | None, display_name: str) -> tuple[str, int | None]:
        """(display name, lead user id). With an id, the name comes from the real account."""
        if user_id is None:
            return display_name, None
        lead = self.users.get_lead(user_id)
        if not lead:
            raise BadRequestError("Selected Lead is not a valid Lead account.")
        return lead.full_name or lead.username, lead.id

    async def _provision(self, project: models.Project) -> dict:
        """Create the SharePoint folders. Failure never undoes the project; it is reported instead."""
        try:
            url = await self.storage.provision_project(project)
        except SharePointError as exc:
            logger.error("SharePoint provisioning failed for project %s: %s", project.project_code, exc)
            return _sharepoint_result("failed", error=str(exc))
        except Exception as exc:
            logger.exception("Unexpected SharePoint error for project %s", project.project_code)
            return _sharepoint_result("error", error=f"Unexpected error: {exc}")
        project.sharepoint_site_url = url
        self.db.commit()
        return _sharepoint_result("provisioned", url=url)


def _sharepoint_result(status: str, *, url: str | None = None, error: str | None = None) -> dict:
    result = {"sharepoint_status": status, "sharepoint_site_url": url}
    if error is not None:
        result["sharepoint_error"] = error
    return result
