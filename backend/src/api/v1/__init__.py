from fastapi import APIRouter, Depends


def get_v1_router() -> APIRouter:
    from . import (
        auth,
        dashboard,
        ingest,
        live,
        logs,
        recompute,
        roi,
        scenarios,
        sources,
    )
    from .deps import get_current_user, require_ingest_token

    router = APIRouter()
    router.include_router(auth.router)
    router.include_router(live.router, dependencies=[Depends(require_ingest_token)])

    protected = (ingest, sources, recompute, dashboard, scenarios, logs, roi)
    for module in protected:
        router.include_router(module.router, dependencies=[Depends(get_current_user)])
    return router
