import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import Settings
from core.errors import DomainError, status_title

logger = logging.getLogger(__name__)


def _error_response(
    *,
    request: Request,
    status_code: int,
    message: str,
    error_code: str,
    details: Any | None = None,
    title: str | None = None,
) -> JSONResponse:
    """Build a uniform error body: error_code, message, details."""
    body: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
        "details": details,
        "title": title or status_title(status_code),
        "status": status_code,
        "instance": str(request.url.path),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id

    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return _error_response(
            request=request,
            status_code=exc.status_code,
            message=exc.detail,
            error_code=exc.error_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request=request,
            status_code=422,
            message="Request validation failed",
            error_code="REQUEST_VALIDATION_ERROR",
            details=exc.errors(),
        )

    async def _http_error_handler(
        request: Request,
        exc: HTTPException | StarletteHTTPException,
    ) -> JSONResponse:
        details: Any | None = None
        message: str

        if isinstance(exc.detail, str):
            message = exc.detail
        elif isinstance(exc.detail, dict):
            message = str(exc.detail.get("detail") or "HTTP error")
            details = exc.detail
        elif isinstance(exc.detail, list):
            message = "HTTP error"
            details = exc.detail
        else:
            message = "HTTP error"

        return _error_response(
            request=request,
            status_code=exc.status_code,
            message=message,
            error_code="HTTP_ERROR",
            details=details,
        )

    app.add_exception_handler(HTTPException, _http_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Unhandled exception path=%s method=%s request_id=%s",
            request.url.path,
            request.method,
            request_id,
        )

        message = "Internal server error"
        if settings.DEBUG:
            message = f"{exc.__class__.__name__}: {exc}"

        return _error_response(
            request=request,
            status_code=500,
            message=message,
            error_code="INTERNAL_SERVER_ERROR",
        )
