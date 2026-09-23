"""Test doubles for external systems."""

import json


class FakeDocumentStorage:
    """In-memory DocumentStorage: records calls and returns (or raises) what the test set."""

    def __init__(self):
        self.provision_url = "https://example.sharepoint.com/sites/Automation/Project/Fake%20Project"
        self.provision_error: Exception | None = None
        self.mirror_data: dict = {}
        self.mirror_error: Exception | None = None
        self.provisioned: list[list[str]] = []
        self.mirrored: list[int] = []

    async def provision_project(self, project) -> str:
        self.provisioned.append(json.loads(project.sharepoint_disciplines))
        if self.provision_error:
            raise self.provision_error
        return self.provision_url

    async def get_mirror(self, project) -> dict:
        self.mirrored.append(project.id)
        if self.mirror_error:
            raise self.mirror_error
        return self.mirror_data
