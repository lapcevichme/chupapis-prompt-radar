from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.errors import UnauthorizedError
from core.security import create_token, decode_token, verify_password
from database.relational_db import User


class InvalidCredentials(UnauthorizedError):
    error_code = "AUTH_INVALID_CREDENTIALS"
    default_detail = "Wrong email or password"


class InvalidToken(UnauthorizedError):
    error_code = "AUTH_INVALID_TOKEN"
    default_detail = "Invalid or expired token"


class AuthRequired(UnauthorizedError):
    error_code = "AUTH_REQUIRED"
    default_detail = "Authentication required"


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def _get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def _get_by_id(self, subject: object) -> User | None:
        try:
            user_id = UUID(str(subject))
        except (ValueError, TypeError):
            return None
        return await self.session.scalar(select(User).where(User.id == user_id))

    def _issue_tokens(self, user: User) -> tuple[str, str]:
        subject = str(user.id)
        access = create_token(
            subject,
            "access",
            ttl_seconds=self.settings.ACCESS_TTL,
            settings=self.settings,
        )
        refresh = create_token(
            subject,
            "refresh",
            ttl_seconds=self.settings.REFRESH_TTL,
            settings=self.settings,
        )
        return access, refresh

    async def login(self, email: str, password: str) -> tuple[User, str, str]:
        user = await self._get_by_email(email.strip().lower())
        if user is None:
            raise InvalidCredentials()
        try:
            valid = await verify_password(password, user.password_hash)
        except ValueError:
            raise InvalidCredentials()
        if not valid:
            raise InvalidCredentials()
        access, refresh = self._issue_tokens(user)
        return user, access, refresh

    async def refresh(self, refresh_token: str | None) -> tuple[str, str]:
        if not refresh_token:
            raise InvalidToken()
        payload = decode_token(refresh_token, settings=self.settings)
        if payload is None or payload.get("typ") != "refresh":
            raise InvalidToken()
        user = await self._get_by_id(payload.get("sub"))
        if user is None:
            raise InvalidToken()
        return self._issue_tokens(user)

    async def user_from_access(self, access_token: str | None) -> User:
        if not access_token:
            raise AuthRequired()
        payload = decode_token(access_token, settings=self.settings)
        if payload is None or payload.get("typ") != "access":
            raise AuthRequired()
        user = await self._get_by_id(payload.get("sub"))
        if user is None:
            raise AuthRequired()
        return user
