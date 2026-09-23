"""The document-storage port used by project services.

Services depend on the small `DocumentStorage` protocol, not on Microsoft
Graph directly (dependency inversion). FastAPI supplies the Graph-backed
implementation through `get_document_storage`; tests override that
dependency with an in-memory fake.
"""

from typing import Any, Protocol

import models
from app.integrations.sharepoint import graph


class DocumentStorage(Protocol):
    async def provision_project(self, project: models.Project) -> str:
        """Create the project's folder structure and return its web URL."""
        ...

    async def get_mirror(self, project: models.Project) -> dict[str, Any]:
        """Return the project's folder tree, files, stats and connection status."""
        ...


class GraphDocumentStorage:
    """DocumentStorage backed by SharePoint through Microsoft Graph."""

    async def provision_project(self, project: models.Project) -> str:
        return await graph.provision_sharepoint_directory(project)

    async def get_mirror(self, project: models.Project) -> dict[str, Any]:
        return await graph.get_sharepoint_mirror_data(project)


def get_document_storage() -> DocumentStorage:
    return GraphDocumentStorage()
