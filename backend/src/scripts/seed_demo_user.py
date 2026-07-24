import asyncio
import logging

from sqlalchemy import select

from core.config import get_settings
from core.security import hash_password
from database.relational_db import User, dispose_engine, get_session_factory

logger = logging.getLogger(__name__)


async def seed_demo_user() -> None:
    settings = get_settings()
    email = settings.DEMO_USER_EMAIL.strip().lower()
    factory = get_session_factory(settings)
    async with factory() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            logger.info("Demo user already exists: %s", email)
            return
        user = User(
            email=email,
            password_hash=await hash_password(settings.DEMO_USER_PASSWORD),
        )
        session.add(user)
        await session.commit()
        logger.info("Seeded demo user: %s", email)


async def _run() -> None:
    try:
        await seed_demo_user()
    finally:
        await dispose_engine()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
