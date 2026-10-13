"""Typed application settings, read once from the environment and backend/.env.

Environment variables take precedence over the .env file, so tests and
deployments can override any value without touching files.

Nobody signs in to this app: MAEC One Core does, and on every request the gate
(app/api/gate.py) asks Core who the browser is. The four gate settings are
required; the app refuses to start without them (`require_gate_settings`).
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

    # MAEC One Core, which says who each browser is (app/api/gate.py).
    core_url: str = ""  # as this server reaches it: http://maec-core:8000 inside Docker
    core_public_url: str = ""  # as a browser reaches it: where "Sign out" and "Change password" point
    maec_app_key: str = ""  # this app's key in Core: projects
    maec_gate_secret: str = ""  # this app's entry in Core's GATE_SECRETS; never logged, never returned
    # The peers whose X-Forwarded-Proto and X-Forwarded-Host are believed (app/api/proxy.py):
    # comma-separated addresses or CIDR ranges. Unset trusts nobody; "*" is refused.
    trusted_proxies: str = ""

    # Audit log entries older than this are deleted (decided 2026-10-07: 30 days).
    audit_retention_days: int = 30

    azure_client_id: str = ""
    azure_client_secret: str = ""
    azure_tenant_id: str = ""
    sharepoint_site_id: str = ""
    sharepoint_drive_id: str = ""
    sharepoint_site_url: str = "https://mirageace.sharepoint.com/sites/Automation"
    sharepoint_target_path: str = "Project_Mirage_Manage/delivery/Project"

    @field_validator("core_url", "core_public_url", "maec_app_key", "maec_gate_secret", "trusted_proxies")
    @classmethod
    def stripped(cls, value: str) -> str:
        return value.strip()

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


# What .env.example carries for the secret: it must be replaced on the server.
GATE_SECRET_PLACEHOLDER = "generate-on-the-server"
MIN_GATE_SECRET_LENGTH = 32


class GateConfigError(RuntimeError):
    """The gate cannot ask MAEC One who anybody is. Raised at startup, never swallowed."""


def gate_settings_problems(settings: Settings) -> list[str]:
    """What is wrong with the gate settings, in words; empty when they can be used."""
    named = {
        "CORE_URL": settings.core_url,
        "CORE_PUBLIC_URL": settings.core_public_url,
        "MAEC_APP_KEY": settings.maec_app_key,
        "MAEC_GATE_SECRET": settings.maec_gate_secret,
    }
    problems = [f"{name} is not set" for name, value in named.items() if not value]
    secret = settings.maec_gate_secret
    if secret == GATE_SECRET_PLACEHOLDER:
        problems.append("MAEC_GATE_SECRET is still the placeholder: generate one on the server")
    elif secret and len(secret) < MIN_GATE_SECRET_LENGTH:
        problems.append(f"MAEC_GATE_SECRET is shorter than {MIN_GATE_SECRET_LENGTH} characters")
    return problems


def require_gate_settings(settings: Settings | None = None) -> None:
    """Refuse to start without usable gate settings: a gate that cannot ask Core can only refuse
    everybody, and a server that boots into that state does it quietly."""
    problems = gate_settings_problems(settings or get_settings())
    if problems:
        raise GateConfigError(
            "Project Management cannot start: " + "; ".join(problems) + ". See .env.example (MAEC One gate)."
        )
