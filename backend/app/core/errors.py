"""Domain exceptions and their HTTP mapping.

Services raise these instead of HTTPException so business logic stays free of
web-framework concerns; one handler turns them into JSON error responses with
the same `{"detail": ...}` shape FastAPI uses.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str, *, headers: dict[str, str] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.headers = headers


class BadRequestError(DomainError):
    status_code = 400


class ForbiddenError(DomainError):
    status_code = 403


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class UnexpectedError(DomainError):
    status_code = 500


class IntegrationError(DomainError):
    """An external system (e.g. Microsoft Graph) failed."""

    status_code = 502


NO_PROJECT_ACCESS = "You do not have access to this project."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
