import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from passlib.context import CryptContext

from core.config import Settings, get_settings

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__type="ID",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=2,
)


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(pwd_context.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(pwd_context.verify, password, password_hash)


async def needs_rehash(password_hash: str) -> bool:
    return await asyncio.to_thread(pwd_context.needs_update, password_hash)


def encode_token(payload: dict[str, Any], *, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGO)


def decode_token(
    token: str,
    *,
    settings: Settings | None = None,
    verify_exp: bool = True,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGO],
            options={"verify_exp": verify_exp},
        )
    except jwt.PyJWTError:
        return None


def create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    *,
    ttl_seconds: int,
    settings: Settings | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    settings = settings or get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "jti": uuid4().hex,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return encode_token(payload, settings=settings)
