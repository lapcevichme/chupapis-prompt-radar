from fastapi import APIRouter


def get_api_routers() -> APIRouter:
    """Aggregate all REST routers under the /api/v1 prefix."""
    from .v1 import get_v1_router

    router = APIRouter(prefix="/api/v1")
    router.include_router(get_v1_router())
    return router
