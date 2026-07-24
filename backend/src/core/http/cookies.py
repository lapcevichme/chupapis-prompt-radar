from typing import Any

from fastapi import Response

from core.config import Settings, get_settings


def _base_cookie_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": settings.COOKIE_PATH,
    }
    if settings.COOKIE_DOMAIN:
        kwargs["domain"] = settings.COOKIE_DOMAIN
    return kwargs


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    base_kwargs = _base_cookie_kwargs(settings)
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.ACCESS_TTL,
        httponly=True,
        **base_kwargs,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.REFRESH_TTL,
        httponly=True,
        **base_kwargs,
    )


def clear_auth_cookies(
    response: Response,
    *,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    base_kwargs = _base_cookie_kwargs(settings)
    response.delete_cookie("access_token", httponly=True, **base_kwargs)
    response.delete_cookie("refresh_token", httponly=True, **base_kwargs)
