"""Typed application settings, read once from the environment and backend/.env.

Environment variables take precedence over the .env file, so tests and
deployments can override any value without touching files.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'promanage.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL

    # Sessions expire this many hours after login.
    session_ttl_hours: float = 12
    # This many failed logins for one username within the window lock it out for the window.
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15
    # Audit log entries older than this are deleted (decided 2026-10-07: 30 days).
    audit_retention_days: int = 30

    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    sharepoint_site_id: str = ""
    sharepoint_drive_id: str = ""
    sharepoint_site_url: str = "https://mirageace.sharepoint.com/sites/Automation"
    sharepoint_target_path: str = "Project_Mirage_Manage/delivery/Project"

    @field_validator("database_url")
    @classmethod
    def default_when_blank(cls, value: str) -> str:
        return value.strip() or DEFAULT_DATABASE_URL

    @property
    def sharepoint_configured(self) -> bool:
        return all((self.azure_client_id, self.azure_client_secret, self.azure_tenant_id, self.sharepoint_site_id))


@lru_cache
def get_settings() -> Settings:
    return Settings()
