"""Sokokali API entry point.

Run from the ``backend`` directory:  uvicorn app.main:app --reload
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import broadcast, chat, forex, sports, system
from app.core.config import Settings, get_settings
from app.core.container import Container, build_container
from app.core.logging import configure_logging
from app.core.security import admin_token_required
from app.integrations.forex.base import ForexDataError
from app.integrations.sports.base import SportsDataError

logger = logging.getLogger("sokokali")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    container = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "sokokali_started",
            extra={
                "version": settings.app_version,
                "environment": settings.environment,
                "sports_provider": container.sports_provider.name,
                "simulated_data": container.sports_provider.is_simulated,
                "forex_enabled": settings.forex_enabled,
                "forex_trade_levels_enabled": settings.forex_trade_levels_enabled,
                "llm": container.llm.model if container.llm else None,
            },
        )
        if settings.admin_token is None:
            if admin_token_required(settings):
                logger.error("admin_token_missing", extra={"effect": "admin endpoints disabled until SOKOKALI_ADMIN_TOKEN is set"})
            else:
                logger.warning("admin_token_not_set", extra={"effect": "admin endpoints open (development only)"})
        yield
        await container.aclose()
        logger.info("sokokali_stopped")

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description="Sokokali, the AI sports and markets presenter. Phase 1 backend: chat, football fixtures "
        "and predictions, forex signals. Data is SIMULATED unless the status endpoint reports otherwise. "
        "Forex output is educational analysis, not financial advice.",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failed", extra={"request_id": request_id, "path": request.url.path})
            response = JSONResponse({"detail": "Internal server error", "request_id": request_id}, status_code=500)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.exception_handler(SportsDataError)
    async def sports_data_error(_: Request, exc: SportsDataError) -> JSONResponse:
        logger.warning("sports_data_unavailable", extra={"error": str(exc)})
        return JSONResponse({"detail": "Sports data is temporarily unavailable"}, status_code=503)

    @app.exception_handler(ForexDataError)
    async def forex_data_error(_: Request, exc: ForexDataError) -> JSONResponse:
        logger.warning("forex_data_unavailable", extra={"error": str(exc)})
        return JSONResponse({"detail": "Forex data is temporarily unavailable"}, status_code=503)

    app.include_router(system.router)
    app.include_router(chat.router)
    app.include_router(sports.router)
    app.include_router(forex.router)
    app.include_router(broadcast.router)
    return app


app = create_app()
