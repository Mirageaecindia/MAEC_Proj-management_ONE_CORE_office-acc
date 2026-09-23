from fastapi import APIRouter, Depends

import models
import schemas
from app.api.deps import get_document_service, get_project_service
from app.core.security import get_current_user, require_any_role, require_bu_head
from app.services.documents import ProjectDocumentService
from app.services.projects import ProjectService

router = APIRouter(tags=["projects"])


@router.get("/project-leads", response_model=list[schemas.ProjectLeadOut])
def list_project_leads(
    discipline: str | None = None,
    _user: models.User = Depends(require_any_role),
    service: ProjectService = Depends(get_project_service),
):
    """Lead accounts for the Create Project dropdowns, optionally filtered by discipline."""
    return service.list_leads(discipline)


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
    user: models.User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    """Projects visible to the caller: all for the BU Head, assigned ones for Leads and Engineers."""
    return service.list_for(user)


@router.get("/projects/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: int,
    user: models.User = Depends(get_current_user),
    service: ProjectService = Depends(get_project_service),
):
    return service.get_for(user, project_id)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    _user: models.User = Depends(require_bu_head),
    service: ProjectService = Depends(get_project_service),
):
    return service.delete(project_id)


@router.get("/projects/{project_id}/sharepoint-mirror")
async def get_sharepoint_mirror(
    project_id: int,
    user: models.User = Depends(require_any_role),
    service: ProjectDocumentService = Depends(get_document_service),
):
    """Live folder tree, files and connection status from SharePoint."""
    return await service.mirror(user, project_id)
