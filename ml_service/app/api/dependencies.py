"""FastAPI dependencies — service token auth (ТЗ §7)."""
from __future__ import annotations

from typing import Optional

from fastapi import Header

from app.core.config import settings
from app.core.exceptions import UNAUTHORIZED, MLServiceError


async def require_service_token(
    x_service_token: Optional[str] = Header(default=None, alias="X-Service-Token"),
) -> None:
    """Require X-Service-Token when ML_SERVICE_TOKEN is configured.

    Local/dev without token remains open (auth disabled).
    Health endpoints must NOT use this dependency.
    """
    expected = settings.service_token or ""
    if not expected:
        return
    if not x_service_token or x_service_token != expected:
        raise MLServiceError(
            code=UNAUTHORIZED,
            message="Invalid or missing X-Service-Token",
            retryable=False,
            status_code=401,
        )
