from fastapi import APIRouter, Request, Response, status

from core.http.cookies import clear_auth_cookies, set_auth_cookies
from domain.auth import LoginRequest, LoginResponse, UserOut

from .deps import AuthServiceDep, CurrentUserDep, SettingsDep

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> LoginResponse:
    user, access, refresh = await service.login(payload.email, payload.password)
    set_auth_cookies(response, access, refresh, settings=settings)
    return LoginResponse(
        user=UserOut(id=user.id, email=user.email, created_at=user.created_at)
    )


@router.post("/auth/refresh")
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> dict[str, str]:
    access, refresh_token = await service.refresh(request.cookies.get("refresh_token"))
    set_auth_cookies(response, access, refresh_token, settings=settings)
    return {"status": "ok"}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: SettingsDep) -> None:
    clear_auth_cookies(response, settings=settings)


@router.get("/users/me", response_model=UserOut)
async def me(user: CurrentUserDep) -> UserOut:
    return UserOut(id=user.id, email=user.email, created_at=user.created_at)
