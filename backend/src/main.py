import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api import get_api_routers
from core.config import Settings, configure_logging, get_settings
from core.error_handling import register_exception_handlers
from core.middlewares import RequestTracingMiddleware
from database.relational_db import (
    dispose_engine,
    get_session_factory,
    wait_for_db,
)

logger = logging.getLogger(__name__)


async def _check_database(settings: Settings) -> str:
    try:
        session_factory = get_session_factory(settings)
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return "error"


async def _check_ml(settings: Settings) -> str:
    """Map ML /health/ready status to ok | degraded | error | not_configured."""
    if not settings.ML_SERVICE_URL:
        return "not_configured"

    try:
        async with httpx.AsyncClient(timeout=settings.ML_HTTP_TIMEOUT_SEC) as client:
            response = await client.get(
                f"{settings.ML_SERVICE_URL.rstrip('/')}/health/ready",
                headers={"X-Service-Token": settings.ML_SERVICE_TOKEN},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("ML readiness check failed: %s", exc)
        return "error"

    ml_status = str(payload.get("status", "")).strip().lower()
    if ml_status == "ready":
        return "ok"
    if ml_status == "degraded":
        return "degraded"
    return "error"


def create_app(
    settings: Settings | None = None,
    check_db_on_startup: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        preload_task: asyncio.Task[None] | None = None
        try:
            if check_db_on_startup:
                await wait_for_db()
                from scripts.seed_demo_user import seed_demo_user

                await seed_demo_user()
                if settings.PRELOAD_DATASETS_ENABLED:
                    from service.ingestion.preloaded import run_preloaded_seed_safely

                    preload_task = asyncio.create_task(
                        run_preloaded_seed_safely(settings),
                        name="preloaded-dataset-seed",
                    )
            yield
        finally:
            if preload_task is not None:
                from service.ingestion.preloaded import cancel_preloaded_seed

                await cancel_preloaded_seed(preload_task)
            await dispose_engine()

    app = FastAPI(
        lifespan=lifespan,
        title="Prompt Radar Backend",
        version=settings.APP_VERSION,
        debug=settings.DEBUG
        if settings.DEBUG is not None
        else settings.APP_STAGE == "dev",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestTracingMiddleware)
    # CORS last so it wraps outermost and sets headers on every response (incl. errors).
    # allow_credentials=True requires explicit origins (no "*") — cookie auth needs it.
    cors_origins = settings.cors_origins_list
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["Content-Disposition"],
        )
    register_exception_handlers(app, settings)

    app.include_router(get_api_routers())

    @app.get("/api/ping")
    async def ping():
        return {"status": "ok"}

    @app.get("/api/health")
    async def health():
        dependencies = {
            "database": await _check_database(settings),
            "ml": await _check_ml(settings),
        }
        healthy_values = {"ok", "not_configured"}
        overall = (
            "ok"
            if all(value in healthy_values for value in dependencies.values())
            else "degraded"
        )
        return {
            "status": overall,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": settings.APP_VERSION,
            "dependencies": dependencies,
        }

    @app.get("/api/ready")
    async def readiness():
        checks = {
            "database": await _check_database(settings),
            "ml": await _check_ml(settings),
        }
        # Database is required; ML degraded/not_configured does not block readiness.
        ready = checks["database"] == "ok" and checks["ml"] != "error"
        if ready:
            return {"status": "ready", "checks": checks}

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "checks": checks},
        )

    return app


app = create_app()
