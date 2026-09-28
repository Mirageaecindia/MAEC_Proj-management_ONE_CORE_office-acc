from fastapi import APIRouter, Depends
from pydantic import BaseModel

import models
import schemas
from app.api.deps import get_document_service, get_project_service
from app.core.security import get_current_user, require_any_role, require_bu_head
from app.services.documents import ProjectDocumentService
from app.services.projects import ProjectService

router = APIRouter(tags=["projects"])


class ProjectCommentRequest(BaseModel):
    comments: str | None = None

    @property
    def text(self) -> str | None:
        return (self.comments or "").strip() or None


@router.get("/project-leads", response_model=list[schemas.ProjectLeadOut])
def list_project_leads(
    _user: models.User = Depends(require_any_role),
    service: ProjectService = Depends(get_project_service),
):
    """Everyone the BU Head can choose as a project lead (any active account with an employee record)."""
    return service.list_leads()


@router.post("/projects", response_model=schemas.CreateProjectOut, status_code=201)
async def create_project(
    payload: schemas.ProjectCreatePayload,
    _user: models.User = Depends(require_bu_head),
    service: ProjectService = Depends(get_project_service),
):
    """Create a project and provision its SharePoint folders (reported in `sharepoint_status`)."""
    return await service.create(payload)


@router.get("/projects", response_model=list[schemas.ProjectOut])
def list_projects(
    include_archived: bool = False,
    user: models.User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    """Projects visible to the caller: all for the BU Head, assigned ones for Leads and Engineers.
    Archived projects are listed only for the BU Head, with `include_archived=true`."""
    return service.list_for(user, include_archived)


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: int,
    user: models.User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return service.get_for(user, project_id)


@router.put("/projects/{project_id}", response_model=schemas.ProjectUpdateOut)
def update_project(
    project_id: int,
    payload: schemas.ProjectUpdatePayload,
    user: models.User = Depends(require_bu_head),
    service: ProjectService = Depends(get_project_service),
):
    """Edit a project: audited field by field, lead changes move WBS nodes, the lock is re-checked."""
    return service.update(user, project_id, payload)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    _user: models.User = Depends(require_bu_head),
    service: ProjectService = Depends(get_project_service),
):
    return service.delete(project_id)


@router.post("/projects/{project_id}/archive", response_model=schemas.ProjectOut)
def archive_project(
    project_id: int,
    payload: ProjectCommentRequest | None = None,
    user: models.User = Depends(require_bu_head),
    service: ProjectService = Depends(get_project_service),
):
    """Archive: read-only, hidden from Leads and Engineers, out of the allocation cap and governance."""
    return service.archive(user, project_id, payload.text if payload else None)


@router.post("/projects/{project_id}/unarchive", response_model=schemas.ProjectOut)
def unarchive_project(
    project_id: int,
    payload: ProjectCommentRequest | None = None,
    user: models.User = Depends(require_bu_head),
    service: ProjectService = Depends(get_project_service),
):
    """Reopen an archived project exactly as it was (its timesheet lock included)."""
    return service.unarchive(user, project_id, payload.text if payload else None)


@router.get("/projects/{project_id}/sharepoint-mirror")
async def get_sharepoint_mirror(
    project_id: int,
    user: models.User = Depends(require_any_role),
    service: ProjectDocumentService = Depends(get_document_service),
):
    """Live folder tree, files and connection status from SharePoint."""
    return await service.mirror(user, project_id)
