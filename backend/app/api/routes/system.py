from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_container
from app.core.container import Container
from app.schemas.system import ComponentStatus, HealthResponse, ReadinessResponse, StatusResponse

router = APIRouter(tags=["system"])


def _ai_status(container: Container) -> ComponentStatus:
    llm = container.llm
    if llm is None:
        return ComponentStatus(name="ai_engine", status="ok", detail="Rule-based engine only (no LLM configured)")
    if not llm.available:
        return ComponentStatus(
            name="ai_engine",
            status="degraded",
            detail=f"Claude {llm.model} paused after: {llm.last_error}; using rule-based fallback",
        )
    return ComponentStatus(
        name="ai_engine",
        status="ok",
        detail=f"Claude {llm.model} (effort {llm.effort}) with rule-based fallback",
    )

ContainerDep = Annotated[Container, Depends(get_container)]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(container: ContainerDep) -> HealthResponse:
    s = container.settings
    return HealthResponse(status="ok", service=s.app_name, version=s.app_version)


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(container: ContainerDep) -> JSONResponse:
    checks = {"sports_provider": await container.sports_provider.health_check()}
    if container.settings.forex_enabled:
        checks["forex_provider"] = await container.forex_provider.health_check()
    ok = all(checks.values())
    body = ReadinessResponse(status="ready" if ok else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)


@router.get("/api/v1/status", response_model=StatusResponse, summary="Service and component status")
async def service_status(container: ContainerDep) -> StatusResponse:
    s = container.settings
    provider = container.sports_provider
    provider_ok = await provider.health_check()
    fx = container.forex_provider
    fx_ok = await fx.health_check()
    now = datetime.now(UTC)
    return StatusResponse(
        service=s.app_name,
        version=s.app_version,
        environment=s.environment,
        started_at=container.started_at,
        uptime_seconds=round((now - container.started_at).total_seconds(), 1),
        components=[
            _ai_status(container),
            ComponentStatus(
                name="sports_provider",
                status="ok" if provider_ok else "down",
                detail=f"{provider.name} ({'SIMULATED data' if provider.is_simulated else 'live data'})",
            ),
            ComponentStatus(name="prediction_engine", status="ok", detail=container.predictions.model_version),
            ComponentStatus(
                name="forex_provider",
                status="disabled" if not s.forex_enabled else "ok" if fx_ok else "down",
                detail=f"{fx.name} ({'SIMULATED data' if fx.is_simulated else 'live data'})",
            ),
            ComponentStatus(
                name="forex_signal_engine",
                status="ok" if s.forex_enabled else "disabled",
                detail=f"{container.forex.model_version}; trade levels "
                f"{'ENABLED' if s.forex_trade_levels_enabled else 'disabled pending licensing review'}",
            ),
            ComponentStatus(
                name="conversation_memory",
                status="ok",
                detail=f"in-memory, {len(container.memory)} active conversations",
            ),
        ],
    )
