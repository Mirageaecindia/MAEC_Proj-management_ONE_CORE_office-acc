import logging
import os
import re
from typing import Any

import httpx
import msal
from dotenv import load_dotenv

from models import Project

load_dotenv()

logger = logging.getLogger(__name__)

DISCIPLINE_FOLDERS = {
    "HVAC Discipline": "01_HVAC Discipline",
    "Electrical Discipline": "02_Electrical Discipline",
    "Plumbing": "03_Plumbing",
    "Firefighting": "04_Firefighting",
    "BIM Models": "05_BIM_Models",
}


class SharePointError(Exception):
    """Custom exception for SharePoint/Graph API errors."""

    pass


class SharePointClient:
    """Microsoft Graph API client for SharePoint operations."""

    def __init__(self):
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.client_secret = os.getenv("AZURE_CLIENT_SECRET")
        self.tenant_id = os.getenv("AZURE_TENANT_ID")
        self.site_id = os.getenv("SHAREPOINT_SITE_ID")
        self.drive_id = os.getenv("SHAREPOINT_DRIVE_ID")
        self.site_url = os.getenv("SHAREPOINT_SITE_URL", "https://mirageace.sharepoint.com/sites/Automation")
        self.target_path = os.getenv("SHAREPOINT_TARGET_PATH", "Project_Mirage_Manage/delivery/Project")

        if not all([self.client_id, self.client_secret, self.tenant_id, self.site_id]):
            raise SharePointError(
                "Missing required Azure AD / SharePoint configuration. "
                "Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID, SHAREPOINT_SITE_ID in environment."
            )

        self._app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        self._token: str | None = None

    def _get_token(self) -> str:
        """Acquire or reuse an access token for Microsoft Graph."""
        if self._token:
            return self._token

        result = self._app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            error_desc = result.get("error_description", "Unknown error")
            raise SharePointError(f"Failed to acquire Graph token: {error_desc}")

        self._token = result["access_token"]
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an authenticated request to Microsoft Graph."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=self._headers(), **kwargs)
            return response

    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize a string to be a valid SharePoint folder name."""
        # SharePoint folder names cannot contain: " * : < > ? / \ | # %
        # Also trim to reasonable length
        sanitized = re.sub(r'[*"<>?/\\|#%]', "_", name)
        sanitized = sanitized.strip(". ")
        return sanitized[:128] if sanitized else "Unnamed_Project"

    async def ensure_folder_path(self, path_parts: list[str]) -> dict:
        """
        Ensure a folder path exists in the SharePoint document library.
        Creates parent folders as needed.
        Returns the final folder metadata.
        """
        if not self.drive_id:
            # Resolve drive ID if not configured
            await self._resolve_drive_id()

        current_path = ""
        parent_item_id = "root"

        for part in path_parts:
            current_path = f"{current_path}/{part}" if current_path else part
            parent_item_id = await self._get_or_create_folder(parent_item_id, part)

        # Return the final folder's web URL
        folder_metadata = await self._get_folder_metadata(parent_item_id)
        return folder_metadata

    async def _resolve_drive_id(self):
        """Resolve the default document library drive ID."""
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives"
        response = await self._request("GET", url)
        if response.status_code != 200:
            raise SharePointError(f"Failed to list drives: {response.text}")

        drives = response.json().get("value", [])
        # Prefer the "Documents" library (usually the default)
        for drive in drives:
            if drive.get("name") in ("Documents", "Shared Documents"):
                self.drive_id = drive["id"]
                logger.info(f"Resolved SharePoint drive ID: {self.drive_id}")
                return

        if drives:
            self.drive_id = drives[0]["id"]
            logger.warning(f"Using first available drive: {self.drive_id}")
            return

        raise SharePointError("No document libraries found in SharePoint site")

    async def _get_or_create_folder(self, parent_id: str, folder_name: str) -> str:
        """Get existing folder or create it. Returns the folder item ID."""
        # Try to get existing folder
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/items/{parent_id}/children/{folder_name}"
        response = await self._request("GET", url)

        if response.status_code == 200:
            return response.json()["id"]

        if response.status_code != 404:
            raise SharePointError(f"Failed to check folder existence: {response.text}")

        # Create folder
        create_url = (
            f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/items/{parent_id}/children"
        )
        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename",
        }
        response = await self._request("POST", create_url, json=payload)

        if response.status_code not in (200, 201):
            raise SharePointError(f"Failed to create folder '{folder_name}': {response.text}")

        logger.info(f"Created SharePoint folder: {folder_name} under parent {parent_id}")
        return response.json()["id"]

    async def _get_folder_metadata(self, item_id: str) -> dict:
        """Get folder metadata including web URL."""
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/items/{item_id}"
        response = await self._request("GET", url)

        if response.status_code != 200:
            raise SharePointError(f"Failed to get folder metadata: {response.text}")

        data = response.json()
        return {
            "id": data["id"],
            "name": data["name"],
            "web_url": data.get("webUrl"),
            "created_date_time": data.get("createdDateTime"),
        }

    async def get_folder_children(self, folder_id: str) -> list[dict[str, Any]]:
        """Get all children (folders and files) of a folder."""
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/items/{folder_id}/children"
        response = await self._request("GET", url)

        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise SharePointError(f"Failed to get folder children: {response.text}")

        return response.json().get("value", [])

    async def get_folder_hierarchy(self, folder_id: str, max_depth: int = 3) -> list[dict[str, Any]]:
        """Recursively fetch folder hierarchy up to max_depth."""
        children = await self.get_folder_children(folder_id)
        folders = []

        for child in children:
            if "folder" in child:
                folder_data = {
                    "id": child["id"],
                    "name": child["name"],
                    "web_url": child.get("webUrl"),
                    "created_date_time": child.get("createdDateTime"),
                    "children": [],
                }
                if max_depth > 1:
                    folder_data["children"] = await self.get_folder_hierarchy(child["id"], max_depth - 1)
                folders.append(folder_data)

        return folders

    async def get_files_in_folder(self, folder_id: str) -> list[dict[str, Any]]:
        """Get all files in a folder with metadata."""
        children = await self.get_folder_children(folder_id)
        files = []

        for child in children:
            if "file" in child:
                file_info = child.get("file", {})
                file_data = {
                    "id": child["id"],
                    "name": child["name"],
                    "web_url": child.get("webUrl"),
                    "size": child.get("size", 0),
                    "last_modified_date_time": child.get("lastModifiedDateTime"),
                    "last_modified_by": child.get("lastModifiedBy", {}).get("user", {}).get("displayName", "Unknown"),
                    "mime_type": file_info.get("mimeType"),
                }
                files.append(file_data)

        return files

    async def get_repository_stats(self, folder_id: str) -> dict[str, Any]:
        """Get total file count and total size for a folder (including subfolders)."""
        total_files = 0
        total_size = 0

        async def count_recursive(fid: str):
            nonlocal total_files, total_size
            children = await self.get_folder_children(fid)
            for child in children:
                if "file" in child:
                    total_files += 1
                    total_size += child.get("size", 0)
                elif "folder" in child:
                    await count_recursive(child["id"])

        await count_recursive(folder_id)
        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_formatted": self._format_size(total_size),
        }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    async def check_connection(self) -> dict[str, Any]:
        """Check if SharePoint/Graph API is reachable and accessible."""
        try:
            if not self.drive_id:
                await self._resolve_drive_id()
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/root"
            response = await self._request("GET", url)
            if response.status_code == 200:
                return {"connected": True, "status": "Connected", "error": None}
            else:
                return {
                    "connected": False,
                    "status": "Error",
                    "error": f"Graph API returned {response.status_code}: {response.text}",
                }
        except SharePointError as e:
            return {"connected": False, "status": "Error", "error": str(e)}
        except Exception as e:
            return {"connected": False, "status": "Error", "error": f"Unexpected error: {str(e)}"}

    async def resolve_project_folder_id(self, project_folder_name: str) -> str | None:
        """Resolve the project folder item ID by name under the target path."""
        if not self.drive_id:
            await self._resolve_drive_id()

        # First, navigate to the target path
        path_parts = [p for p in self.target_path.split("/") if p]
        current_id = "root"

        for part in path_parts:
            url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/items/{current_id}/children/{part}"
            response = await self._request("GET", url)
            if response.status_code != 200:
                return None
            current_id = response.json()["id"]

        # Now find the project folder
        url = f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/{self.drive_id}/items/{current_id}/children/{project_folder_name}"
        response = await self._request("GET", url)
        if response.status_code == 200:
            return response.json()["id"]
        return None


async def provision_sharepoint_directory(project: Project) -> str:
    """
    Provision a real SharePoint folder structure for the project.
    Creates: /Project_Mirage_Manage/delivery/Project/{ProjectName}/[discipline folders]

    Returns the web URL of the created project folder.
    Raises SharePointError on failure (auth, permissions, network, etc.)
    """
    if not project.sharepoint_disciplines:
        raise SharePointError("No SharePoint disciplines selected for this project")

    import json

    disciplines = json.loads(project.sharepoint_disciplines) if project.sharepoint_disciplines else []

    if not disciplines:
        raise SharePointError("No SharePoint disciplines selected for this project")

    client = SharePointClient()

    # Sanitize project name for folder name
    project_folder_name = client._sanitize_folder_name(project.project_name or project.project_code)

    # Build full path: target_path + project_folder + discipline folders
    path_parts = [p for p in client.target_path.split("/") if p]
    path_parts.append(project_folder_name)

    # Ensure the base path + project folder exists
    project_folder = await client.ensure_folder_path(path_parts)

    # Create discipline subfolders inside the project folder
    project_item_id = project_folder["id"]
    for discipline in disciplines:
        folder_name = DISCIPLINE_FOLDERS.get(discipline)
        if folder_name:
            await client._get_or_create_folder(project_item_id, folder_name)

    web_url = project_folder.get("web_url")
    if not web_url:
        # Construct URL manually if not returned
        site_url = client.site_url
        web_url = f"{site_url}/{client.target_path}/{project_folder_name}"

    logger.info(f"Provisioned SharePoint directory for project {project.project_code}: {web_url}")
    return web_url


# Backward-compatible synchronous wrapper for existing call sites
def provision_sharepoint_directory_sync(project: Project) -> str:
    """Synchronous wrapper - only works if event loop is available."""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(provision_sharepoint_directory(project))


async def get_sharepoint_mirror_data(project: Project) -> dict:
    """
    Fetch real SharePoint mirror data for a project.
    Returns folder hierarchy, file listing, connection status, and repository stats.
    """
    if not project.sharepoint_site_url:
        return {
            "provisioned": False,
            "error": (
                "SharePoint directory not provisioned for this project. "
                "Ask BU Head to create the project with SharePoint option enabled."
            ),
            "folder_hierarchy": [],
            "files": [],
            "stats": {"total_files": 0, "total_size_bytes": 0, "total_size_formatted": "0 B"},
            "connection": {"connected": False, "status": "Not Provisioned", "error": "No SharePoint folder URL stored"},
            "target_location": None,
        }

    client = SharePointClient()

    # Extract project folder name from the sharepoint_site_url
    # URL format: https://mirageace.sharepoint.com/sites/Automation/Project_Mirage_Manage/delivery/Project/{ProjectFolderName}
    project_folder_name = project.sharepoint_site_url.rstrip("/").split("/")[-1]

    # Resolve the project folder ID
    project_folder_id = await client.resolve_project_folder_id(project_folder_name)

    if not project_folder_id:
        return {
            "provisioned": False,
            "error": f"SharePoint folder '{project_folder_name}' not found. It may have been deleted or renamed.",
            "folder_hierarchy": [],
            "files": [],
            "stats": {"total_files": 0, "total_size_bytes": 0, "total_size_formatted": "0 B"},
            "connection": {
                "connected": False,
                "status": "Folder Not Found",
                "error": f"Folder '{project_folder_name}' not found in SharePoint",
            },
            "target_location": project.sharepoint_site_url,
        }

    # Fetch all data in parallel
    import asyncio

    connection_task = client.check_connection()
    hierarchy_task = client.get_folder_hierarchy(project_folder_id)
    files_task = client.get_files_in_folder(project_folder_id)
    stats_task = client.get_repository_stats(project_folder_id)

    connection, folder_hierarchy, files, stats = await asyncio.gather(
        connection_task, hierarchy_task, files_task, stats_task, return_exceptions=True
    )

    # Handle any exceptions
    if isinstance(connection, Exception):
        connection = {"connected": False, "status": "Error", "error": str(connection)}
    if isinstance(folder_hierarchy, Exception):
        folder_hierarchy = []
    if isinstance(files, Exception):
        files = []
    if isinstance(stats, Exception):
        stats = {"total_files": 0, "total_size_bytes": 0, "total_size_formatted": "0 B"}

    return {
        "provisioned": True,
        "error": None,
        "folder_hierarchy": folder_hierarchy,
        "files": files,
        "stats": stats,
        "connection": connection,
        "target_location": project.sharepoint_site_url,
    }
