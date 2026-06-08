"""
K.U.A. production ASGI entrypoint.

Run (local):

    cd backend && pip install -r requirements.txt
    export PYTHONPATH="..:${PYTHONPATH}"  # repo root for domain modules
    uvicorn app.main:app --host 0.0.0.0 --port 8000

Docker sets ``PYTHONPATH=/app`` with the repository copied to ``/app``.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.endpoints.analyse import router as analyse_router
from app.api.v1.endpoints.deals import router as deals_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.notes import router as notes_router
from app.api.v1.endpoints.property import router as property_router
from app.api.v1.endpoints.scan import router as scan_router
from app.auth.router import router as auth_router
from app.laundry.api import laundry_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.middleware.security import RequestContextMiddleware, SecurityHeadersMiddleware
from app.repositories.user_repository import upsert_operator_template
from app.websocket.manager import WebSocketManager
from app.websocket.routes import router as ws_router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    redis_client: Redis | None = None
    if settings.REDIS_URL:
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    app.state.redis = redis_client

    app.state.ws_manager = WebSocketManager(redis_client)
    await app.state.ws_manager.start_redis_listener()

    if settings.OPERATOR_PASSWORD_HASH:
        try:
            async with AsyncSessionLocal() as db:
                await upsert_operator_template(
                    db,
                    username=settings.OPERATOR_USERNAME,
                    password_hash=settings.OPERATOR_PASSWORD_HASH,
                    display_name=settings.OPERATOR_DISPLAY_NAME,
                    clearance=settings.OPERATOR_CLEARANCE,
                )
                await db.commit()
            log.info("seed.operator_ready", username=settings.OPERATOR_USERNAME)
        except Exception:
            log.exception("seed.operator_failed")

    yield

    await app.state.ws_manager.shutdown()
    if redis_client is not None:
        await redis_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    docs_on = settings.docs_enabled

    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        docs_url="/docs" if docs_on else None,
        redoc_url="/redoc" if docs_on else None,
        openapi_url="/openapi.json" if docs_on else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
        )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_hosts_list,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/")
    async def root() -> dict:
        return {"status": "running", "message": "K.U.A. backend operational"}

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(ws_router)
    app.include_router(analyse_router)
    app.include_router(scan_router)
    app.include_router(deals_router)
    app.include_router(property_router)
    app.include_router(notes_router)
    # Independent laundry acquisition vertical (all routes under /laundry/*)
    app.include_router(laundry_router)

    return app


app = create_app()
