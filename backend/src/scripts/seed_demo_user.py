import asyncio
import logging

logger = logging.getLogger(__name__)


async def seed_demo_user() -> None:
    # TODO: upsert the demo user (get_uow + User + core.security.hash_password).
    logger.info("seed_demo_user placeholder: no-op for now")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_demo_user())


if __name__ == "__main__":
    main()
