from fastapi import APIRouter


def get_v1_router() -> APIRouter:
    from . import ingest, logs, sources

    router = APIRouter()
    router.include_router(ingest.router)
    router.include_router(sources.router)
    router.include_router(logs.router)
    return router
