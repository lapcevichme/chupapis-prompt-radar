from fastapi import APIRouter


def get_v1_router() -> APIRouter:
    router = APIRouter()
    # TODO: router.include_router(get_auth_router())

    return router
