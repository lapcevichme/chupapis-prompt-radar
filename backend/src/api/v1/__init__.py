from fastapi import APIRouter


def get_v1_router() -> APIRouter:
    from . import dashboard, ingest, logs, recompute, roi, scenarios, sources

    router = APIRouter()
    router.include_router(ingest.router)
    router.include_router(sources.router)
    router.include_router(recompute.router)
    router.include_router(dashboard.router)
    router.include_router(scenarios.router)
    router.include_router(logs.router)
    router.include_router(roi.router)
    return router
